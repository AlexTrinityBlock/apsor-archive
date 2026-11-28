import {
  useEffect,
  useId,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
  type CSSProperties,
  type KeyboardEvent as ReactKeyboardEvent,
} from "react";

import { Icon } from "../../component/Icon";
import { useI18n } from "../../i18n";
import { ACTION_LABEL_KEYS, isAnnouncedAction } from "../actions";
import type { CompanionStreamInput } from "../director";
import type { DragRelease, ResizeSource } from "../gesture";
import { useBusySignal } from "../hook/useBusySignal";
import { BOOKMARK_HEIGHT, CompanionBookmark } from "./CompanionBookmark";
import { useChatLayout } from "../hook/useChatLayout";
import { useCompanionDirector } from "../hook/useCompanionDirector";
import { useCompanionGestures } from "../hook/useCompanionGestures";
import {
  DOCK_SIDES,
  FIGURE_HEADROOM,
  anchorFeet,
  avoidance,
  breakpointFor,
  defaultPosition,
  dockX,
  intersectionArea,
  isLeftSide,
  bookmarkTop,
  landingPosition,
  peekGeometry,
  resolveBox,
  shiftPosition,
  type Breakpoint,
  type SavedPosition,
} from "../layout";
import type { CompanionCharacter } from "../manifest";
import type { CompanionMotion, CompanionOpacityMode } from "../preference";
import {
  boxForFigure,
  detentsFor,
  displayLevel,
  figureForDisplayLevel,
  figureForLevel,
  gripLevel,
  heightForLevel,
  pinchLevel,
  readoutFor,
  settleLevel,
  sizeRange,
  stepLevel,
  toggleFull,
  wheelLevel,
  type Detent,
  type Readout,
} from "../size";
import { DOCK_SPRING, isSettled, stepSpring, type SpringState } from "../spring";
import {
  readLastNonFull,
  readMinimized,
  readPosition,
  readResizeHintSeen,
  writeLastNonFull,
  writeMinimized,
  writePosition,
  writeResizeHintSeen,
} from "../storage";
import { CompanionResizeHint } from "./CompanionResizeHint";
import { CompanionSizeReadout } from "./CompanionSizeReadout";
import { CompanionStage } from "./CompanionStage";

interface CompanionOverlayProps {
  readonly character: CompanionCharacter;
  readonly motion: CompanionMotion;
  /** Committed size level, 0 (compact) to 1 (full). */
  readonly level: number;
  /** Save a new size level; `deferred` coalesces rapid keyboard steps. */
  readonly onLevel: (level: number, deferred: boolean) => void;
  readonly opacityMode: CompanionOpacityMode;
  readonly stream: CompanionStreamInput | null;
  readonly draft: string;
  readonly conversationKey: string;
}

type Positions = Readonly<Record<Breakpoint, SavedPosition | null>>;

interface Landing {
  readonly id: number;
  readonly dx: number;
  readonly dy: number;
  /** Starting scale of the new box (old height / new height). */
  readonly k: number;
}

interface LiveResize {
  readonly startHeight: number;
  display: number;
  snapped: Detent | null;
  dx: number;
  dy: number;
}

interface ReadoutState extends Readout {
  readonly level: number;
  readonly coversText: boolean;
}

const EXPAND_MS = 6000;
const KEY_STEP = 0.04;
const READOUT_LINGER_MS = 900;
const ANNOUNCE_DELAY_MS = 500;
const HINT_HOVER_MS = 700;
const QUIET_ACTIONS: ReadonlySet<string> = new Set(["idle", "greet", "listening", "sleeping"]);

function readPositions(): Positions {
  return {
    phone: readPosition("phone"),
    tablet: readPosition("tablet"),
    desktop: readPosition("desktop"),
  };
}

function setTransform(root: HTMLElement | null, dx: number, dy: number, k: number) {
  root?.style.setProperty("--companion-dx", `${dx.toFixed(1)}px`);
  root?.style.setProperty("--companion-dy", `${dy.toFixed(1)}px`);
  root?.style.setProperty("--companion-k", k.toFixed(4));
}

/**
 * The free-standing companion beside the chat box: placement, drag/throw/snap,
 * direct resizing (corner grip, pinch, Ctrl/⌘+wheel, double-click, keys),
 * minimize, reader-avoidance, and the live caption.
 */
export function CompanionOverlay({
  character,
  motion,
  level,
  onLevel,
  stream,
  draft,
  conversationKey,
  opacityMode,
}: CompanionOverlayProps) {
  const { t } = useI18n();
  const hintId = useId();
  const gripHintId = useId();
  const rootRef = useRef<HTMLDivElement>(null);
  const tabRef = useRef<HTMLButtonElement>(null);
  const focusTabRef = useRef(false);
  const landingCounter = useRef(0);
  const liveRef = useRef<LiveResize | null>(null);
  const moveRef = useRef({ dx: 0, dy: 0 });
  const lastNonFull = useRef<number | null>(readLastNonFull());
  const hintTimer = useRef<number | null>(null);

  const { context, dialogOpen } = useChatLayout(true);
  const breakpoint = breakpointFor(context.viewport.width);
  const [positions, setPositions] = useState<Positions>(readPositions);
  const [minimized, setMinimized] = useState(readMinimized);
  const [held, setHeld] = useState(false);
  const [resizing, setResizing] = useState(false);
  const [expanded, setExpanded] = useState(false);
  const [landing, setLanding] = useState<Landing | null>(null);
  const [readout, setReadout] = useState<ReadoutState | null>(null);
  const [readoutVisible, setReadoutVisible] = useState(false);
  const [announcement, setAnnouncement] = useState<{ text: string; at: number } | null>(null);
  const [spoken, setSpoken] = useState("");
  const [hintSeen, setHintSeen] = useState(readResizeHintSeen);
  const [hintOpen, setHintOpen] = useState(false);

  const director = useCompanionDirector({ stream, draft, conversationKey, held });
  const { action } = director;
  // The coach hint only appears while the companion is not working; timers
  // read the latest pose through this ref.
  const quietRef = useRef(true);
  useLayoutEffect(() => {
    quietRef.current = QUIET_ACTIONS.has(action);
  }, [action]);

  const range = useMemo(() => sizeRange(breakpoint, context), [breakpoint, context]);
  const detents = useMemo(() => detentsFor(range), [range]);
  const figure = figureForLevel(level, range);
  const size = boxForFigure(figure);
  const busy = useBusySignal(opacityMode === "auto");
  const position = positions[breakpoint] ?? defaultPosition(breakpoint, context, size);
  const box = useMemo(() => resolveBox(position, context, size), [position, context, size]);
  const presence = avoidance(box, context, dialogOpen, breakpoint, position.side);
  const settled = !expanded && !held && !resizing;
  const peeking = presence === "peek" && settled;
  // Tucked away at the window edge as a bookmark until tapped or hovered.
  const retracted = presence === "retract" && settled;
  const peek = peekGeometry(size, context);
  const left = isLeftSide(position.side);
  const rubber = motion === "full";

  const coversText = (rect: { left: number; top: number; width: number; height: number }) => {
    const column = context.column;
    if (column === null) {
      return false;
    }
    return intersectionArea(rect, column) / Math.max(1, rect.width * rect.height) > 0.12;
  };

  const sizeLabel = (value: Readout): string =>
    value.labelKey === null
      ? t("companion.size.percent", { percent: value.percent })
      : t(value.labelKey);

  const commitPosition = (next: SavedPosition, from: { left: number; top: number }) => {
    const nextBox = resolveBox(next, context, size);
    writePosition(breakpoint, next);
    setPositions((current) => ({ ...current, [breakpoint]: next }));
    landingCounter.current += 1;
    setLanding({
      id: landingCounter.current,
      dx: from.left - nextBox.left,
      dy: from.top - nextBox.top,
      k: 1,
    });
  };

  const dismissHint = () => {
    setHintOpen(false);
    if (!hintSeen) {
      writeResizeHintSeen();
      setHintSeen(true);
    }
  };

  /**
   * Store a new size: keep the feet still, spring from the old box (or from
   * the live preview, which already matches) and announce it.
   */
  const commitLevel = (next: number, options: { animate: boolean; deferred?: boolean }) => {
    const settled = settleLevel(next);
    const nextFigure = figureForLevel(settled, range);
    const nextBox = boxForFigure(nextFigure);
    const nextPosition = anchorFeet(position, context, box, nextBox);
    const nextRect = resolveBox(nextPosition, context, nextBox);
    writePosition(breakpoint, nextPosition);
    setPositions((current) => ({ ...current, [breakpoint]: nextPosition }));
    landingCounter.current += 1;
    setLanding(
      options.animate
        ? {
            id: landingCounter.current,
            dx: box.left - nextRect.left,
            dy: box.top - nextRect.top,
            k: size.height / nextBox.height,
          }
        : { id: landingCounter.current, dx: 0, dy: 0, k: 1 },
    );
    if (settled < 0.999) {
      lastNonFull.current = settled;
      writeLastNonFull(settled);
    }
    const snapped = detents.find((detent) => Math.abs(detent.level - settled) < 0.001) ?? null;
    const value = readoutFor(settled, snapped, range);
    setReadout({ ...value, level: settled, coversText: coversText(nextRect) });
    setReadoutVisible(true);
    setExpanded(true);
    setAnnouncement({
      text: t("companion.overlay.resize.announce", {
        name: character.name,
        label: sizeLabel(value),
      }),
      at: Date.now(),
    });
    dismissHint();
    onLevel(settled, options.deferred === true);
  };

  const applyLive = (raw: number) => {
    const live = liveRef.current;
    if (live === null) {
      return;
    }
    const shown = displayLevel(raw, detents, live.snapped, rubber);
    live.display = shown.level;
    live.snapped = shown.snapped;
    const liveBox = boxForFigure(figureForDisplayLevel(shown.level, range));
    const target = resolveBox(anchorFeet(position, context, box, liveBox), context, liveBox);
    live.dx = target.left - box.left;
    live.dy = target.top - box.top;
    setTransform(rootRef.current, live.dx, live.dy, liveBox.height / size.height);
    const value = readoutFor(settleLevel(shown.level), shown.snapped, range);
    const covers = coversText(target);
    setReadout((current) =>
      current !== null &&
      current.labelKey === value.labelKey &&
      current.percent === value.percent &&
      current.coversText === covers
        ? current
        : { ...value, level: settleLevel(shown.level), coversText: covers },
    );
  };

  // Spring the figure from where it was released, moved, or resized from.
  useLayoutEffect(() => {
    const root = rootRef.current;
    if (root === null) {
      return undefined;
    }
    const still = landing === null || (landing.dx === 0 && landing.dy === 0 && landing.k === 1);
    if (still || motion !== "full") {
      setTransform(root, 0, 0, 1);
      return undefined;
    }
    let x: SpringState = { value: landing.dx, velocity: 0 };
    let y: SpringState = { value: landing.dy, velocity: 0 };
    let k: SpringState = { value: landing.k, velocity: 0 };
    setTransform(root, x.value, y.value, k.value);
    let last = performance.now();
    let frame = requestAnimationFrame(function tick(now) {
      const seconds = Math.min(0.05, (now - last) / 1000);
      last = now;
      x = stepSpring(x, 0, seconds, DOCK_SPRING);
      y = stepSpring(y, 0, seconds, DOCK_SPRING);
      k = stepSpring(k, 1, seconds, DOCK_SPRING);
      setTransform(root, x.value, y.value, k.value);
      if (isSettled(x, 0, 0.3) && isSettled(y, 0, 0.3) && isSettled(k, 1, 0.002)) {
        setTransform(root, 0, 0, 1);
        return;
      }
      frame = requestAnimationFrame(tick);
    });
    return () => cancelAnimationFrame(frame);
  }, [landing, motion]);

  useEffect(() => {
    if (!expanded) {
      return undefined;
    }
    const timer = window.setTimeout(() => setExpanded(false), EXPAND_MS);
    return () => window.clearTimeout(timer);
  }, [expanded]);

  useEffect(() => {
    if (!readoutVisible || resizing) {
      return undefined;
    }
    const timer = window.setTimeout(() => setReadoutVisible(false), READOUT_LINGER_MS);
    return () => window.clearTimeout(timer);
  }, [readoutVisible, resizing, readout]);

  useEffect(() => {
    if (announcement === null) {
      return undefined;
    }
    const timer = window.setTimeout(() => setSpoken(announcement.text), ANNOUNCE_DELAY_MS);
    return () => window.clearTimeout(timer);
  }, [announcement]);

  useEffect(() => {
    if (!hintOpen) {
      return undefined;
    }
    const timer = window.setTimeout(dismissHint, 8000);
    return () => window.clearTimeout(timer);
    // dismissHint only writes the seen flag; re-arming on its identity is not wanted.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [hintOpen]);

  useEffect(
    () => () => {
      if (hintTimer.current !== null) {
        window.clearTimeout(hintTimer.current);
      }
    },
    [],
  );

  useEffect(() => {
    if (minimized && focusTabRef.current) {
      focusTabRef.current = false;
      tabRef.current?.focus();
    } else if (!minimized && focusTabRef.current) {
      focusTabRef.current = false;
      rootRef.current?.focus();
    }
  }, [minimized]);

  const startResize = (source: ResizeSource) => {
    const startLevel = level;
    liveRef.current = {
      startHeight: heightForLevel(startLevel, range),
      display: startLevel,
      snapped: detents.find((detent) => Math.abs(detent.level - startLevel) < 0.001) ?? null,
      dx: 0,
      dy: 0,
    };
    setResizing(true);
    setExpanded(false);
    setReadoutVisible(true);
    disarmHint();
    setHintOpen(false);
    if (source === "wheel") {
      setReadout({
        ...readoutFor(startLevel, liveRef.current.snapped, range),
        level: startLevel,
        coversText: false,
      });
    }
  };

  const endResize = (commit: boolean) => {
    const live = liveRef.current;
    liveRef.current = null;
    setResizing(false);
    if (live === null) {
      return;
    }
    if (!commit) {
      setTransform(rootRef.current, 0, 0, 1);
      return;
    }
    commitLevel(live.display, { animate: false });
  };

  const gestures = useCompanionGestures(rootRef, {
    onMoveStart: () => {
      setHeld(true);
      setExpanded(false);
      disarmHint();
      setHintOpen(false);
    },
    onMove: (dx, dy) => {
      moveRef.current = { dx, dy };
      setTransform(rootRef.current, dx, dy, 1);
    },
    onMoveEnd: (release: DragRelease) => {
      setHeld(false);
      const from = { left: box.left + release.dx, top: box.top + release.dy };
      commitPosition(
        landingPosition(from.left, from.top, { x: release.vx, y: release.vy }, context, size),
        from,
      );
    },
    onMoveAbort: () => {
      setHeld(false);
      const { dx, dy } = moveRef.current;
      commitPosition(position, { left: box.left + dx, top: box.top + dy });
    },
    onResizeStart: startResize,
    onResizeGrip: (dx, dy) => {
      const live = liveRef.current;
      if (live !== null) {
        applyLive(gripLevel(live.startHeight, range, dx, dy, left));
      }
    },
    onResizePinch: (ratio) => {
      const live = liveRef.current;
      if (live !== null) {
        applyLive(pinchLevel(live.startHeight, range, ratio));
      }
    },
    onResizeWheel: (deltaY, deltaMode) => {
      const live = liveRef.current;
      if (live !== null) {
        applyLive(
          wheelLevel(settleLevel(live.display), range, deltaY, deltaMode, context.viewport.height),
        );
      }
    },
    onResizeEnd: () => endResize(true),
    onResizeCancel: () => endResize(false),
    onTap: () => {
      director.poke();
      setExpanded((value) => !value || breakpoint !== "phone");
      if (!hintSeen && range.resizable && quietRef.current) {
        setHintOpen(true);
      }
    },
    onDoubleTap: () => {
      if (!range.resizable) {
        return;
      }
      const toggled = toggleFull(level, lastNonFull.current);
      commitLevel(toggled.level, { animate: true });
    },
  });

  const setMinimizedPersisted = (value: boolean, moveFocus: boolean) => {
    focusTabRef.current = moveFocus;
    writeMinimized(value);
    setMinimized(value);
  };

  const resizeByKey = (next: number) => {
    if (range.resizable && Math.abs(next - level) > 0.0005) {
      commitLevel(next, { animate: true, deferred: true });
    }
  };

  const onRootKeyDown = (event: ReactKeyboardEvent<HTMLDivElement>) => {
    if (event.key === "Escape" && gestures.cancel()) {
      event.preventDefault();
      return;
    }
    if (event.target !== event.currentTarget) {
      return;
    }
    const from = { left: box.left, top: box.top };
    if (event.key === "Escape") {
      event.preventDefault();
      setMinimizedPersisted(true, true);
      return;
    }
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      director.poke();
      setExpanded((value) => !value);
      return;
    }
    if (!event.ctrlKey && !event.metaKey && !event.altKey) {
      if (event.key === "+" || event.key === "=") {
        event.preventDefault();
        resizeByKey(stepLevel(level, 1, false, detents));
        return;
      }
      if (event.key === "-" || event.key === "_") {
        event.preventDefault();
        resizeByKey(stepLevel(level, -1, false, detents));
        return;
      }
      if (event.key === "0") {
        event.preventDefault();
        resizeByKey(1);
        return;
      }
    }
    if (event.key === "ArrowUp" || event.key === "ArrowDown") {
      event.preventDefault();
      const step = (event.shiftKey ? 3 : 1) * KEY_STEP * (event.key === "ArrowUp" ? -1 : 1);
      commitPosition(shiftPosition(position, step), from);
      return;
    }
    if (event.key === "ArrowLeft" || event.key === "ArrowRight") {
      event.preventDefault();
      const ordered = DOCK_SIDES.filter((side) => context.panel !== null || !side.startsWith("panel"))
        .map((side) => ({ side, x: dockX(side, context, size.width) }))
        .sort((a, b) => a.x - b.x);
      const index = ordered.findIndex((item) => item.side === position.side);
      const nextIndex =
        event.key === "ArrowLeft" ? Math.max(0, index - 1) : Math.min(ordered.length - 1, index + 1);
      const next = ordered[nextIndex];
      if (next !== undefined && next.side !== position.side) {
        commitPosition({ ...position, side: next.side }, from);
      }
    }
  };

  const onGripKeyDown = (event: ReactKeyboardEvent<HTMLDivElement>) => {
    let next: number | null = null;
    switch (event.key) {
      case "ArrowUp":
      case "ArrowRight":
        next = stepLevel(level, 1, false, detents);
        break;
      case "ArrowDown":
      case "ArrowLeft":
        next = stepLevel(level, -1, false, detents);
        break;
      case "PageUp":
        next = stepLevel(level, 1, true, detents);
        break;
      case "PageDown":
        next = stepLevel(level, -1, true, detents);
        break;
      case "Home":
        next = 0;
        break;
      case "End":
        next = 1;
        break;
      default:
        return;
    }
    event.preventDefault();
    event.stopPropagation();
    resizeByKey(next);
  };

  const armHint = () => {
    if (hintSeen || !range.resizable || hintTimer.current !== null) {
      return;
    }
    hintTimer.current = window.setTimeout(() => {
      hintTimer.current = null;
      // Re-read the flag: a resize during the wait may have just set it.
      if (quietRef.current && !readResizeHintSeen()) {
        setHintOpen(true);
      }
    }, HINT_HOVER_MS);
  };

  const disarmHint = () => {
    if (hintTimer.current !== null) {
      window.clearTimeout(hintTimer.current);
      hintTimer.current = null;
    }
  };

  const peekStyle: "none" | "shrink" = peeking ? "shrink" : "none";
  const label = t(ACTION_LABEL_KEYS[action]);
  const actionAnnouncement = isAnnouncedAction(action)
    ? t("companion.overlay.announce", { name: character.name, action: label })
    : "";
  const current: Readout = readoutFor(
    level,
    detents.find((detent) => Math.abs(detent.level - level) < 0.001) ?? null,
    range,
  );

  if (minimized || retracted) {
    return (
      <div className="companion-layer" data-companion-root="">
        <CompanionBookmark
          ref={tabRef}
          character={character}
          left={left}
          placement={bookmarkTop(box.top + FIGURE_HEADROOM, BOOKMARK_HEIGHT, context)}
          label={t("companion.overlay.restore", { name: character.name })}
          hidden={presence === "hidden"}
          onActivate={() => (minimized ? setMinimizedPersisted(false, true) : setExpanded(true))}
        />
      </div>
    );
  }

  const style = {
    left: box.left,
    top: box.top,
    width: size.width,
    height: size.height,
    "--companion-peek-scale": peek.scale,
    "--companion-peek-slide": `${Math.round(peek.slide * 100)}%`,
    "--companion-peek-slide-neg": `${-Math.round(peek.slide * 100)}%`,
  } as CSSProperties;

  return (
    <div className="companion-layer" data-companion-root="">
      <div
        ref={rootRef}
        className={[
          "companion",
          `is-${breakpoint}`,
          `opacity-${opacityMode}`,
          busy ? "is-busy" : null,
          left ? "is-left" : "is-right",
          peekStyle !== "none" ? `is-peek is-peek-${peekStyle}` : null,
          presence === "hidden" ? "is-hidden" : null,
          held ? "is-held" : null,
          resizing ? "is-resizing" : null,
          expanded ? "is-awake" : null,
        ]
          .filter(Boolean)
          .join(" ")}
        style={style}
        role="group"
        tabIndex={presence === "hidden" ? -1 : 0}
        aria-label={t("companion.overlay.label", { name: character.name })}
        aria-describedby={hintId}
        aria-hidden={presence === "hidden" ? true : undefined}
        onKeyDown={onRootKeyDown}
        onPointerDown={gestures.onPointerDown}
        onPointerMove={gestures.onPointerMove}
        onPointerUp={gestures.onPointerUp}
        onPointerCancel={gestures.onPointerCancel}
        onLostPointerCapture={gestures.onLostPointerCapture}
        onPointerEnter={armHint}
        onPointerLeave={disarmHint}
        onFocus={armHint}
        onBlur={disarmHint}
        title={label}
      >
        <CompanionStage
          character={character}
          action={action}
          motion={motion}
          width={figure.width}
          figureHeight={figure.height}
          span={FIGURE_HEADROOM}
          dragMotion={gestures.dragMotion}
          active={presence !== "hidden"}
        />
        {range.resizable ? (
          <div
            className="companion__grip"
            data-companion-grip=""
            role="slider"
            tabIndex={0}
            aria-label={t("companion.overlay.resize.handle", { name: character.name })}
            aria-orientation="vertical"
            aria-valuemin={0}
            aria-valuemax={100}
            aria-valuenow={Math.round(level * 100)}
            aria-valuetext={t("companion.overlay.resize.valueText", {
              label: sizeLabel(current),
              percent: current.percent,
            })}
            aria-describedby={gripHintId}
            onKeyDown={onGripKeyDown}
          />
        ) : null}
        <button
          type="button"
          className="companion__minimize"
          onClick={() => setMinimizedPersisted(true, true)}
          aria-label={t("companion.overlay.minimize")}
          title={t("companion.overlay.minimize")}
        >
          <Icon name="minimize" size={12} />
        </button>
        {readout !== null ? (
          <CompanionSizeReadout
            label={sizeLabel(readout)}
            percent={readout.percent}
            level={readout.level}
            coversText={readout.coversText}
            visible={readoutVisible}
            showPercent={readout.labelKey !== null}
          />
        ) : null}
        {hintOpen ? (
          <CompanionResizeHint onDismiss={dismissHint} />
        ) : null}
        <span className="visually-hidden" id={hintId}>
          {t("companion.overlay.hint")}
        </span>
        <span className="visually-hidden" id={gripHintId}>
          {t("companion.overlay.resize.handleHint")}
        </span>
      </div>
      <span className="visually-hidden" aria-live="polite" aria-atomic="true">
        {actionAnnouncement}
      </span>
      <span
        className="visually-hidden"
        aria-live="polite"
        aria-atomic="true"
        data-companion-size-live=""
      >
        {spoken}
      </span>
    </div>
  );
}
