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
import { useChatLayout } from "../hook/useChatLayout";
import { useCompanionDirector } from "../hook/useCompanionDirector";
import { useCompanionDrag, type DragRelease } from "../hook/useCompanionDrag";
import {
  DOCK_SIDES,
  FIGURE_HEADROOM,
  avoidance,
  boxSize,
  breakpointFor,
  defaultPosition,
  dockX,
  figureSize,
  isLeftSide,
  isViewportSide,
  landingPosition,
  resolveBox,
  type Breakpoint,
  type SavedPosition,
} from "../layout";
import type { CompanionCharacter } from "../manifest";
import type { CompanionMotion } from "../preference";
import { DOCK_SPRING, isSettled, stepSpring, type SpringState } from "../spring";
import { readMinimized, readPosition, writeMinimized, writePosition } from "../storage";
import { CompanionStage } from "./CompanionStage";

interface CompanionOverlayProps {
  readonly character: CompanionCharacter;
  readonly motion: CompanionMotion;
  readonly stream: CompanionStreamInput | null;
  readonly draft: string;
  readonly conversationKey: string;
}

type Positions = Readonly<Record<Breakpoint, SavedPosition | null>>;

interface Landing {
  readonly id: number;
  readonly dx: number;
  readonly dy: number;
}

const EXPAND_MS = 6000;
const KEY_STEP = 0.04;

function readPositions(): Positions {
  return {
    phone: readPosition("phone"),
    tablet: readPosition("tablet"),
    desktop: readPosition("desktop"),
  };
}

/**
 * The free-standing companion beside the chat box: placement, drag/throw/snap,
 * keyboard moves, minimize, reader-avoidance, and the live caption.
 */
export function CompanionOverlay({
  character,
  motion,
  stream,
  draft,
  conversationKey,
}: CompanionOverlayProps) {
  const { t } = useI18n();
  const hintId = useId();
  const rootRef = useRef<HTMLDivElement>(null);
  const tabRef = useRef<HTMLButtonElement>(null);
  const focusTabRef = useRef(false);
  const landingCounter = useRef(0);

  const { context, dialogOpen } = useChatLayout(true);
  const breakpoint = breakpointFor(context.viewport.width);
  const [positions, setPositions] = useState<Positions>(readPositions);
  const [minimized, setMinimized] = useState(readMinimized);
  const [held, setHeld] = useState(false);
  const [expanded, setExpanded] = useState(false);
  const [landing, setLanding] = useState<Landing | null>(null);

  const director = useCompanionDirector({ stream, draft, conversationKey, held });
  const { action } = director;

  const size = boxSize(breakpoint);
  const figure = figureSize(breakpoint);
  const position = positions[breakpoint] ?? defaultPosition(breakpoint, context);
  const box = useMemo(() => resolveBox(position, context, size), [position, context, size]);
  const presence = avoidance(box, context, dialogOpen, breakpoint);
  const peeking = presence === "peek" && !expanded && !held;

  const commitPosition = (next: SavedPosition, from: { left: number; top: number }) => {
    const nextBox = resolveBox(next, context, size);
    writePosition(breakpoint, next);
    setPositions((current) => ({ ...current, [breakpoint]: next }));
    landingCounter.current += 1;
    setLanding({
      id: landingCounter.current,
      dx: from.left - nextBox.left,
      dy: from.top - nextBox.top,
    });
  };

  // Spring the figure from where it was released (or moved from) to its dock.
  useLayoutEffect(() => {
    const root = rootRef.current;
    if (root === null) {
      return undefined;
    }
    if (landing === null || motion !== "full") {
      root.style.setProperty("--companion-dx", "0px");
      root.style.setProperty("--companion-dy", "0px");
      return undefined;
    }
    let x: SpringState = { value: landing.dx, velocity: 0 };
    let y: SpringState = { value: landing.dy, velocity: 0 };
    root.style.setProperty("--companion-dx", `${x.value}px`);
    root.style.setProperty("--companion-dy", `${y.value}px`);
    let last = performance.now();
    let frame = requestAnimationFrame(function tick(now) {
      const seconds = Math.min(0.05, (now - last) / 1000);
      last = now;
      x = stepSpring(x, 0, seconds, DOCK_SPRING);
      y = stepSpring(y, 0, seconds, DOCK_SPRING);
      root.style.setProperty("--companion-dx", `${x.value.toFixed(1)}px`);
      root.style.setProperty("--companion-dy", `${y.value.toFixed(1)}px`);
      if (isSettled(x, 0, 0.3) && isSettled(y, 0, 0.3)) {
        root.style.setProperty("--companion-dx", "0px");
        root.style.setProperty("--companion-dy", "0px");
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
    if (minimized && focusTabRef.current) {
      focusTabRef.current = false;
      tabRef.current?.focus();
    } else if (!minimized && focusTabRef.current) {
      focusTabRef.current = false;
      rootRef.current?.focus();
    }
  }, [minimized]);

  const drag = useCompanionDrag(
    {
      onStart: () => {
        setHeld(true);
        setExpanded(false);
      },
      onMove: (dx, dy) => {
        rootRef.current?.style.setProperty("--companion-dx", `${dx}px`);
        rootRef.current?.style.setProperty("--companion-dy", `${dy}px`);
      },
      onEnd: (release: DragRelease) => {
        setHeld(false);
        const from = { left: box.left + release.dx, top: box.top + release.dy };
        commitPosition(
          landingPosition(from.left, from.top, { x: release.vx, y: release.vy }, context, size),
          from,
        );
      },
      onTap: () => {
        director.poke();
        setExpanded((value) => !value || breakpoint !== "phone");
      },
    },
  );

  const setMinimizedPersisted = (value: boolean, moveFocus: boolean) => {
    focusTabRef.current = moveFocus;
    writeMinimized(value);
    setMinimized(value);
  };

  const moveByKeyboard = (event: ReactKeyboardEvent<HTMLDivElement>) => {
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
    if (event.key === "ArrowUp" || event.key === "ArrowDown") {
      event.preventDefault();
      const step = (event.shiftKey ? 3 : 1) * KEY_STEP * (event.key === "ArrowUp" ? -1 : 1);
      commitPosition({ side: position.side, y: Math.min(1, Math.max(0, position.y + step)) }, from);
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
        commitPosition({ side: next.side, y: position.y }, from);
      }
    }
  };

  const left = isLeftSide(position.side);
  let peekStyle: "none" | "slide" | "shrink" = "none";
  if (peeking) {
    peekStyle = isViewportSide(position.side) ? "slide" : "shrink";
  }
  const label = t(ACTION_LABEL_KEYS[action]);
  const announcement = isAnnouncedAction(action)
    ? t("companion.overlay.announce", { name: character.name, action: label })
    : "";

  if (minimized) {
    return (
      <div className="companion-layer" data-companion-root="">
        <button
          ref={tabRef}
          type="button"
          className={`companion-tab${left ? " is-left" : ""}`}
          style={{ top: box.top + FIGURE_HEADROOM }}
          onClick={() => setMinimizedPersisted(false, true)}
          aria-label={t("companion.overlay.restore", { name: character.name })}
          title={t("companion.overlay.restore", { name: character.name })}
          hidden={presence === "hidden"}
        >
          {character.portrait !== null ? (
            <img src={character.portrait} alt="" width={28} height={28} draggable={false} />
          ) : (
            <Icon name="user" size={16} />
          )}
          <span className="companion-tab__ribbon" aria-hidden="true" />
        </button>
      </div>
    );
  }

  const style = {
    left: box.left,
    top: box.top,
    width: size.width,
    height: size.height,
  } as CSSProperties;

  return (
    <div className="companion-layer" data-companion-root="">
      <div
        ref={rootRef}
        className={[
          "companion",
          `is-${breakpoint}`,
          left ? "is-left" : "is-right",
          peekStyle !== "none" ? `is-peek is-peek-${peekStyle}` : null,
          presence === "hidden" ? "is-hidden" : null,
          held ? "is-held" : null,
        ]
          .filter(Boolean)
          .join(" ")}
        style={style}
        role="group"
        tabIndex={presence === "hidden" ? -1 : 0}
        aria-label={t("companion.overlay.label", { name: character.name })}
        aria-describedby={hintId}
        aria-hidden={presence === "hidden" ? true : undefined}
        onKeyDown={moveByKeyboard}
        onPointerDown={drag.onPointerDown}
        onPointerMove={drag.onPointerMove}
        onPointerUp={drag.onPointerUp}
        onPointerCancel={drag.onPointerCancel}
        title={label}
      >
        <CompanionStage
          character={character}
          action={action}
          motion={motion}
          width={figure.width}
          figureHeight={figure.height}
          span={FIGURE_HEADROOM}
          dragMotion={drag.dragMotion}
          active={presence !== "hidden"}
        />
        <button
          type="button"
          className="companion__minimize"
          onClick={() => setMinimizedPersisted(true, true)}
          aria-label={t("companion.overlay.minimize")}
          title={t("companion.overlay.minimize")}
        >
          <Icon name="minimize" size={12} />
        </button>
        <span className="visually-hidden" id={hintId}>
          {t("companion.overlay.hint")}
        </span>
      </div>
      <span className="visually-hidden" aria-live="polite" aria-atomic="true">
        {announcement}
      </span>
    </div>
  );
}
