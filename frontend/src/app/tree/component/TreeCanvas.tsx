import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
  type KeyboardEvent,
  type PointerEvent as ReactPointerEvent,
} from "react";

import { basename, truncate } from "../../../lib/format";
import { Badge } from "../../component/Badge";
import { Button } from "../../component/Button";
import { Panel } from "../../component/Panel";
import {
  TREE_LAYOUT_PADDING,
  TREE_NODE_HEIGHT,
  TREE_NODE_WIDTH,
  type TreeLayout,
  type TreeLayoutLink,
  type TreeLayoutNode,
} from "../treeLayout";

const MIN_ZOOM = 0.4;
const MAX_ZOOM = 2.5;
const ZOOM_STEP = 1.25;

interface TreeCanvasProps {
  readonly layout: TreeLayout;
  readonly selectedKey: string | null;
  readonly onSelect: (node: TreeLayoutNode) => void;
  readonly matchFileIds: ReadonlySet<number>;
  readonly focusFileId: number | null;
  readonly searchFocusSignal: string;
  readonly renderKey: number;
  readonly truncated: boolean;
}

interface DragState {
  readonly pointerId: number;
  readonly startX: number;
  readonly startY: number;
  readonly scrollLeft: number;
  readonly scrollTop: number;
}

interface ZoomFocus {
  readonly clientX: number;
  readonly clientY: number;
  readonly unitX: number;
  readonly unitY: number;
}

function clamp(value: number, minimum: number, maximum: number): number {
  return Math.min(maximum, Math.max(minimum, value));
}

function prefersReducedMotion(): boolean {
  return (
    typeof window !== "undefined" &&
    window.matchMedia("(prefers-reduced-motion: reduce)").matches
  );
}

function linkPath(link: TreeLayoutLink): string {
  const controlX = (link.x1 + link.x2) / 2;
  return `M ${link.x1} ${link.y1} C ${controlX} ${link.y1}, ${controlX} ${link.y2}, ${link.x2} ${link.y2}`;
}

function treeNameLabel(name: string): string {
  const wide = [...name].some((character) => {
    const codePoint = character.codePointAt(0);
    return codePoint !== undefined && codePoint > 0xff;
  });
  return truncate(name, wide ? 15 : 26);
}

function TreeIcon({ folder }: { readonly folder: boolean }) {
  if (folder) {
    return <path d="M3.5 6.5h6l2 2H20.5v11H3.5z" />;
  }
  return (
    <>
      <path d="M6 3.5h8l4 4V20.5H6z" />
      <path d="M14 3.5v4h4" />
    </>
  );
}

interface TreeNodeCardProps {
  readonly layoutNode: TreeLayoutNode;
  readonly selected: boolean;
  readonly matched: boolean;
  readonly onSelect: (node: TreeLayoutNode) => void;
}

function TreeNodeCard({ layoutNode, selected, matched, onSelect }: TreeNodeCardProps) {
  const { node } = layoutNode;
  const displayName = treeNameLabel(node.name || basename(node.path));
  let meta: string = node.kind;
  if (layoutNode.isVirtual) {
    meta = "virtual root";
  } else if (layoutNode.isHistory) {
    meta = "retained history";
  } else if (layoutNode.depth === 0) {
    meta = `${node.kind} · root`;
  }
  const classNames = [
    "tree-node",
    node.kind === "folder" ? "is-folder" : "is-file",
    layoutNode.isHistory ? "is-history" : "is-current",
    layoutNode.isVirtual ? "is-virtual" : null,
    selected ? "is-selected" : null,
    matched ? "is-search-match" : null,
  ]
    .filter(Boolean)
    .join(" ");

  const handleKeyDown = (event: KeyboardEvent<SVGGElement>) => {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      onSelect(layoutNode);
    }
  };

  return (
    <g
      className={classNames}
      transform={`translate(${layoutNode.x} ${layoutNode.y})`}
      role="treeitem"
      aria-level={layoutNode.depth + 1}
      aria-selected={selected}
      tabIndex={0}
      onClick={(event) => {
        event.stopPropagation();
        onSelect(layoutNode);
      }}
      onKeyDown={handleKeyDown}
      onPointerDown={(event) => event.stopPropagation()}
    >
      <title>{node.path}</title>
      {matched ? (
        <rect
          className="tree-node__match"
          x={-6}
          y={-6}
          width={TREE_NODE_WIDTH + 12}
          height={TREE_NODE_HEIGHT + 12}
          rx={7}
        />
      ) : null}
      <rect
        className="tree-node__card"
        width={TREE_NODE_WIDTH}
        height={TREE_NODE_HEIGHT}
        rx={4}
      />
      <rect
        className="tree-node__kind-bar"
        x={0}
        y={9}
        width={2.5}
        height={TREE_NODE_HEIGHT - 18}
        rx={1.25}
      />
      <g className="tree-node__icon" transform="translate(13 15)">
        <TreeIcon folder={node.kind === "folder"} />
      </g>
      <text className="tree-node__name" x={46} y={23}>
        {displayName}
      </text>
      <text className="tree-node__meta" x={46} y={39}>
        {meta}
      </text>
    </g>
  );
}

/**
 * The interactive tidy-tree board: zoom buttons, wheel zoom, drag pan, native
 * scrollbars for wide trees, search rings, and the node renderer.
 */
export function TreeCanvas({
  layout,
  selectedKey,
  onSelect,
  matchFileIds,
  focusFileId,
  searchFocusSignal,
  renderKey,
  truncated,
}: TreeCanvasProps) {
  const scrollRef = useRef<HTMLDivElement>(null);
  const svgRef = useRef<SVGSVGElement>(null);
  const dragRef = useRef<DragState | null>(null);
  const zoomFocusRef = useRef<ZoomFocus | null>(null);
  const zoomRef = useRef(1);
  const lastViewSignatureRef = useRef("");
  const handledResetRef = useRef(0);

  const [zoom, setZoom] = useState(1);
  const [dragging, setDragging] = useState(false);
  const [resetTick, setResetTick] = useState(0);

  const contentWidth = layout.width + TREE_LAYOUT_PADDING * 2;
  const contentHeight = layout.height + TREE_LAYOUT_PADDING * 2;
  const scaledWidth = Math.max(1, contentWidth * zoom);
  const scaledHeight = Math.max(1, contentHeight * zoom);

  useEffect(() => {
    zoomRef.current = zoom;
  }, [zoom]);

  const centerNode = useCallback(
    (node: TreeLayoutNode, behavior: ScrollBehavior = "smooth") => {
      const container = scrollRef.current;
      if (!container) {
        return;
      }
      const centerX =
        (TREE_LAYOUT_PADDING + node.x + TREE_NODE_WIDTH / 2) * zoomRef.current;
      const centerY =
        (TREE_LAYOUT_PADDING + node.y + TREE_NODE_HEIGHT / 2) * zoomRef.current;
      container.scrollTo({
        left: Math.max(0, centerX - container.clientWidth / 2),
        top: Math.max(0, centerY - container.clientHeight / 2),
        behavior,
      });
    },
    [],
  );

  const zoomAt = useCallback(
    (factor: number, clientX: number, clientY: number) => {
      const svg = svgRef.current;
      if (!svg) {
        return;
      }
      const current = zoomRef.current;
      const next = clamp(current * factor, MIN_ZOOM, MAX_ZOOM);
      if (Math.abs(next - current) < 0.0005) {
        return;
      }
      const rect = svg.getBoundingClientRect();
      zoomFocusRef.current = {
        clientX,
        clientY,
        unitX: (clientX - rect.left) / current,
        unitY: (clientY - rect.top) / current,
      };
      zoomRef.current = next;
      setZoom(next);
    },
    [],
  );

  const zoomBy = useCallback(
    (factor: number) => {
      const container = scrollRef.current;
      if (!container) {
        return;
      }
      const rect = container.getBoundingClientRect();
      zoomAt(factor, rect.left + rect.width / 2, rect.top + rect.height / 2);
    },
    [zoomAt],
  );

  const resetView = useCallback(() => {
    zoomFocusRef.current = null;
    zoomRef.current = 1;
    setZoom(1);
    setResetTick((current) => current + 1);
  }, []);

  useLayoutEffect(() => {
    const focus = zoomFocusRef.current;
    if (!focus) {
      return;
    }
    zoomFocusRef.current = null;
    const container = scrollRef.current;
    const svg = svgRef.current;
    if (!container || !svg) {
      return;
    }
    const rect = svg.getBoundingClientRect();
    const nextClientX = rect.left + focus.unitX * zoom;
    const nextClientY = rect.top + focus.unitY * zoom;
    container.scrollLeft += nextClientX - focus.clientX;
    container.scrollTop += nextClientY - focus.clientY;
  }, [zoom]);

  const viewSignature = `${layout.rootPath}|${layout.root.key}|${layout.nodes.length}|${layout.width}|${layout.height}|${renderKey}`;

  useEffect(() => {
    if (lastViewSignatureRef.current === viewSignature) {
      return;
    }
    lastViewSignatureRef.current = viewSignature;
    centerNode(layout.root, prefersReducedMotion() ? "auto" : "smooth");
  }, [centerNode, layout.root, viewSignature]);

  useEffect(() => {
    if (resetTick === 0 || handledResetRef.current === resetTick) {
      return;
    }
    handledResetRef.current = resetTick;
    centerNode(layout.root, prefersReducedMotion() ? "auto" : "smooth");
  }, [centerNode, layout.root, resetTick]);

  useEffect(() => {
    if (searchFocusSignal.length === 0 || focusFileId === null) {
      return;
    }
    const firstMatch = layout.nodes.find(
      (node) => node.node.kind === "file" && node.node.file_id === focusFileId,
    );
    if (!firstMatch) {
      return;
    }
    centerNode(firstMatch, prefersReducedMotion() ? "auto" : "smooth");
  }, [centerNode, focusFileId, layout.nodes, searchFocusSignal]);

  useEffect(() => {
    const container = scrollRef.current;
    if (!container) {
      return;
    }
    const handleWheel = (event: WheelEvent) => {
      event.preventDefault();
      let deltaMode = 1;
      if (event.deltaMode === 1) {
        deltaMode = 16;
      } else if (event.deltaMode === 2) {
        deltaMode = 100;
      }
      const deltaX = event.deltaX * deltaMode;
      const deltaY = event.deltaY * deltaMode;

      if (
        Math.abs(deltaX) > Math.abs(deltaY) * 1.2 ||
        (event.shiftKey && !event.ctrlKey && !event.metaKey)
      ) {
        container.scrollLeft += event.shiftKey ? deltaY : deltaX;
        return;
      }
      if (deltaY === 0) {
        return;
      }
      zoomAt(Math.exp(-deltaY * 0.0015), event.clientX, event.clientY);
    };
    container.addEventListener("wheel", handleWheel, { passive: false });
    return () => container.removeEventListener("wheel", handleWheel);
  }, [zoomAt]);

  const handlePointerDown = (event: ReactPointerEvent<HTMLDivElement>) => {
    if (event.pointerType === "mouse" && event.button !== 0) {
      return;
    }
    const container = scrollRef.current;
    if (!container) {
      return;
    }
    dragRef.current = {
      pointerId: event.pointerId,
      startX: event.clientX,
      startY: event.clientY,
      scrollLeft: container.scrollLeft,
      scrollTop: container.scrollTop,
    };
    container.setPointerCapture(event.pointerId);
    setDragging(true);
  };

  const handlePointerMove = (event: ReactPointerEvent<HTMLDivElement>) => {
    const drag = dragRef.current;
    const container = scrollRef.current;
    if (!drag || !container || drag.pointerId !== event.pointerId) {
      return;
    }
    container.scrollLeft = drag.scrollLeft - (event.clientX - drag.startX);
    container.scrollTop = drag.scrollTop - (event.clientY - drag.startY);
  };

  const endDrag = (event: ReactPointerEvent<HTMLDivElement>) => {
    const drag = dragRef.current;
    const container = scrollRef.current;
    if (container && drag && container.hasPointerCapture(drag.pointerId)) {
      container.releasePointerCapture(drag.pointerId);
    }
    dragRef.current = null;
    if (drag?.pointerId === event.pointerId) {
      setDragging(false);
    }
  };

  const zoomPercent = Math.round(zoom * 100);
  const scrollClass = dragging
    ? "tree-canvas__scroll is-dragging"
    : "tree-canvas__scroll";

  return (
    <Panel
      className="tree-board"
      padded={false}
      eyebrow="Tidy tree · SVG"
      title="Branch map"
      action={
        <div className="tree-zoom" role="group" aria-label="Tree zoom controls">
          <Button
            variant="secondary"
            size="sm"
            iconOnly
            aria-label="Zoom out"
            onClick={() => zoomBy(1 / ZOOM_STEP)}
          >
            <span aria-hidden="true">−</span>
          </Button>
          <span className="tree-zoom__value" aria-live="polite">
            {zoomPercent}%
          </span>
          <Button
            variant="secondary"
            size="sm"
            iconOnly
            aria-label="Zoom in"
            onClick={() => zoomBy(ZOOM_STEP)}
          >
            <span aria-hidden="true">+</span>
          </Button>
          <Button variant="ghost" size="sm" className="tree-zoom__reset" onClick={resetView}>
            Reset
          </Button>
        </div>
      }
      footer={
        <div className="tree-board__footer">
          <div className="tree-legend" aria-label="Tree legend">
            <span className="tree-legend__item">
              <span className="tree-legend__swatch is-folder" aria-hidden="true" />
              folder
            </span>
            <span className="tree-legend__item">
              <span className="tree-legend__swatch is-file" aria-hidden="true" />
              file
            </span>
            <span className="tree-legend__item">
              <span className="tree-legend__swatch is-history" aria-hidden="true" />
              history
            </span>
            <span className="tree-legend__item">
              <span className="tree-legend__line" aria-hidden="true" />
              current link
            </span>
            <span className="tree-legend__item">
              <span className="tree-legend__line is-history" aria-hidden="true" />
              retained link
            </span>
          </div>
          <div className="tree-board__notes">
            {truncated ? <Badge tone="ochre">depth limit truncated</Badge> : null}
            {layout.dropped > 0 ? (
              <Badge tone="vermilion">{layout.dropped} unplaced</Badge>
            ) : null}
            <span className="tree-canvas__hint">
              Wheel to zoom · drag to pan · scrollbars for wide trees
            </span>
          </div>
        </div>
      }
    >
      <div className="tree-canvas">
        <div
          ref={scrollRef}
          className={scrollClass}
          tabIndex={0}
          aria-label={`Interactive knowledge tree rooted at ${layout.rootPath}`}
          onPointerDown={handlePointerDown}
          onPointerMove={handlePointerMove}
          onPointerUp={endDrag}
          onPointerCancel={endDrag}
          onLostPointerCapture={() => {
            dragRef.current = null;
            setDragging(false);
          }}
        >
          <svg
            ref={svgRef}
            className="tree-canvas__svg"
            width={scaledWidth}
            height={scaledHeight}
            viewBox={`0 0 ${contentWidth} ${contentHeight}`}
            role="tree"
            aria-label={`Knowledge tree rooted at ${layout.rootPath}`}
          >
            <g
              className="tree-links"
              key={renderKey}
              transform={`translate(${TREE_LAYOUT_PADDING} ${TREE_LAYOUT_PADDING})`}
              aria-hidden="true"
            >
              {layout.links.map((link, index) => (
                <path
                  key={link.key}
                  className={
                    link.isHistory ? "tree-link is-history" : "tree-link"
                  }
                  d={linkPath(link)}
                  pathLength={1}
                  style={{ animationDelay: `${Math.min(index * 18, 640)}ms` }}
                />
              ))}
            </g>
            <g
              className="tree-nodes"
              transform={`translate(${TREE_LAYOUT_PADDING} ${TREE_LAYOUT_PADDING})`}
            >
              {layout.nodes.map((node) => (
                <TreeNodeCard
                  key={node.key}
                  layoutNode={node}
                  selected={node.key === selectedKey}
                  matched={
                    node.node.kind === "file" &&
                    node.node.file_id !== null &&
                    matchFileIds.has(node.node.file_id)
                  }
                  onSelect={onSelect}
                />
              ))}
            </g>
          </svg>
        </div>
      </div>
    </Panel>
  );
}
