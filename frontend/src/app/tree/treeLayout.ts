import type { TreeNodeSchema } from "../generated-apis-types/schemas";

/** Visual dimensions shared by the layout engine and the SVG renderer. */
export const TREE_NODE_WIDTH = 224;
export const TREE_NODE_HEIGHT = 52;
export const TREE_COLUMN_GAP = 92;
export const TREE_ROW_GAP = 18;
export const TREE_LAYOUT_PADDING = 56;

const VIRTUAL_ROOT_ID = -1;
const VIRTUAL_ROOT_KEY = "virtual:root";

/** One placed node, including its visual coordinates in layout space. */
export interface TreeLayoutNode {
  readonly node: TreeNodeSchema;
  readonly key: string;
  readonly depth: number;
  readonly x: number;
  readonly y: number;
  readonly isVirtual: boolean;
  readonly isHistory: boolean;
}

/** A parent-to-child connector. Coordinates are edge midpoints in layout space. */
export interface TreeLayoutLink {
  readonly key: string;
  readonly parentKey: string;
  readonly childKey: string;
  readonly x1: number;
  readonly y1: number;
  readonly x2: number;
  readonly y2: number;
  readonly isHistory: boolean;
}

/** The complete render model for one tree query. */
export interface TreeLayout {
  readonly root: TreeLayoutNode;
  readonly nodes: readonly TreeLayoutNode[];
  readonly links: readonly TreeLayoutLink[];
  readonly width: number;
  readonly height: number;
  readonly rootPath: string;
  readonly dropped: number;
}

/**
 * Normalizes a user-supplied tree root into an absolute path without a
 * trailing slash. The empty string and "/" both become "/".
 */
export function normalizeTreeRoot(value: string | null | undefined): string {
  const trimmed = (value ?? "").trim();
  if (trimmed.length === 0) {
    return "/";
  }
  const withLeadingSlash = trimmed.startsWith("/") ? trimmed : `/${trimmed}`;
  const collapsed = withLeadingSlash.replace(/\/+/g, "/");
  if (collapsed === "/") {
    return "/";
  }
  let end = collapsed.length;
  while (end > 1 && collapsed[end - 1] === "/") {
    end -= 1;
  }
  return collapsed.slice(0, end);
}

/** True when path is the root itself or lives below it. */
export function isPathWithinRoot(path: string, root: string): boolean {
  const normalizedPath = normalizeTreeRoot(path);
  const normalizedRoot = normalizeTreeRoot(root);
  if (normalizedRoot === "/") {
    return true;
  }
  return (
    normalizedPath === normalizedRoot || normalizedPath.startsWith(`${normalizedRoot}/`)
  );
}

function isHistory(node: TreeNodeSchema): boolean {
  return !node.is_current || node.deleted_at !== null;
}

function basename(path: string): string {
  const segments = path.split("/").filter(Boolean);
  return segments.at(-1) ?? path;
}

function compareNodes(a: TreeNodeSchema, b: TreeNodeSchema): number {
  if (a.is_current !== b.is_current) {
    return a.is_current ? -1 : 1;
  }
  if (a.kind !== b.kind) {
    return a.kind === "folder" ? -1 : 1;
  }
  const nameA = a.name.toLowerCase();
  const nameB = b.name.toLowerCase();
  if (nameA !== nameB) {
    return nameA < nameB ? -1 : 1;
  }
  return a.id - b.id;
}

function makeVirtualRoot(path: string): TreeNodeSchema {
  return {
    id: VIRTUAL_ROOT_ID,
    parent_id: null,
    path,
    name: path === "/" ? "archive" : basename(path),
    kind: "folder",
    file_id: null,
    depth: 0,
    is_current: true,
    superseded_by_id: null,
    deleted_at: null,
    update_time: "",
  };
}

function findVisualRoot(
  nodes: readonly TreeNodeSchema[],
  rootPath: string,
): TreeNodeSchema | null {
  const matches = nodes.filter((node) => normalizeTreeRoot(node.path) === rootPath);
  const current = matches.find((node) => node.is_current && node.deleted_at === null);
  return current ?? matches[0] ?? null;
}

function groupChildren(nodes: readonly TreeNodeSchema[]): Map<number, TreeNodeSchema[]> {
  const children = new Map<number, TreeNodeSchema[]>();
  for (const node of nodes) {
    if (node.parent_id === null) {
      continue;
    }
    const bucket = children.get(node.parent_id);
    if (bucket) {
      bucket.push(node);
    } else {
      children.set(node.parent_id, [node]);
    }
  }
  return children;
}

/**
 * Builds a tidy horizontal tree from the flat API response.
 *
 * Leaves receive sequential rows in post-order; every parent is vertically
 * centered between its first and last child. Unreachable nodes caused by
 * missing parents, self-references, or cycles are attached defensively where
 * they can be placed and otherwise counted in `dropped`. No DOM APIs are used.
 */
export function buildTreeLayout(
  nodes: readonly TreeNodeSchema[],
  root: string,
): TreeLayout {
  const rootPath = normalizeTreeRoot(root);
  const byId = new Map<number, TreeNodeSchema>();
  for (const node of nodes) {
    if (!byId.has(node.id)) {
      byId.set(node.id, node);
    }
  }

  const uniqueNodes = [...byId.values()];
  const visualRoot = findVisualRoot(uniqueNodes, rootPath);
  const childrenByParent = groupChildren(uniqueNodes);
  const placedIds = new Set<number>();
  const placedNodes: TreeLayoutNode[] = [];
  const links: TreeLayoutLink[] = [];
  let nextRow = 0;

  const placeNode = (
    node: TreeNodeSchema,
    depth: number,
    childLayouts: readonly TreeLayoutNode[],
    virtual: boolean,
  ): TreeLayoutNode => {
    const rowStep = TREE_NODE_HEIGHT + TREE_ROW_GAP;
    const y =
      childLayouts.length === 0
        ? nextRow * rowStep
        : (childLayouts[0].y + childLayouts[childLayouts.length - 1].y) / 2;
    if (childLayouts.length === 0) {
      nextRow += 1;
    }

    const layoutNode: TreeLayoutNode = {
      node,
      key: virtual ? VIRTUAL_ROOT_KEY : `node:${node.id}`,
      depth,
      x: depth * (TREE_NODE_WIDTH + TREE_COLUMN_GAP),
      y,
      isVirtual: virtual,
      isHistory: virtual ? false : isHistory(node),
    };
    placedIds.add(node.id);
    placedNodes.push(layoutNode);

    for (const child of childLayouts) {
      links.push({
        key: `${layoutNode.key}->${child.key}`,
        parentKey: layoutNode.key,
        childKey: child.key,
        x1: layoutNode.x + TREE_NODE_WIDTH,
        y1: layoutNode.y + TREE_NODE_HEIGHT / 2,
        x2: child.x,
        y2: child.y + TREE_NODE_HEIGHT / 2,
        isHistory: layoutNode.isHistory || child.isHistory,
      });
    }

    return layoutNode;
  };

  const visit = (
    node: TreeNodeSchema,
    depth: number,
    virtual: boolean,
  ): TreeLayoutNode => {
    placedIds.add(node.id);
    const children = (childrenByParent.get(node.id) ?? [])
      .filter((child) => !placedIds.has(child.id))
      .sort(compareNodes);
    const childLayouts: TreeLayoutNode[] = [];
    for (const child of children) {
      if (placedIds.has(child.id)) {
        continue;
      }
      childLayouts.push(visit(child, depth + 1, false));
    }
    return placeNode(node, depth, childLayouts, virtual);
  };

  const missingParentNodes = uniqueNodes.filter(
    (node) =>
      node.id !== visualRoot?.id &&
      (node.parent_id === null || !byId.has(node.parent_id)),
  );
  const scopedMissingParentNodes = missingParentNodes.filter((node) => {
    if (rootPath === "/") {
      return true;
    }
    return isPathWithinRoot(node.path, rootPath);
  });

  if (visualRoot) {
    visit(visualRoot, 0, false);
    for (const orphan of scopedMissingParentNodes) {
      if (placedIds.has(orphan.id) || orphan.id === visualRoot.id) {
        continue;
      }
      visit(orphan, 1, false);
    }
  } else {
    const candidates = scopedMissingParentNodes.sort(compareNodes);
    const rootChildren = candidates.map((candidate) => visit(candidate, 1, false));
    const virtualNode = makeVirtualRoot(rootPath);
    placeNode(virtualNode, 0, rootChildren, true);
  }

  links.sort((a, b) => a.x1 - b.x1 || a.y1 - b.y1);

  const rootLayout =
    placedNodes.find((node) => node.key === VIRTUAL_ROOT_KEY) ??
    placedNodes.find((node) => node.node.id === visualRoot?.id) ??
    placedNodes[0];

  // The root is guaranteed to exist because the virtual root is always placed.
  const safeRoot: TreeLayoutNode = rootLayout ?? {
    node: makeVirtualRoot(rootPath),
    key: VIRTUAL_ROOT_KEY,
    depth: 0,
    x: 0,
    y: 0,
    isVirtual: true,
    isHistory: false,
  };

  let width = TREE_NODE_WIDTH;
  let height = TREE_NODE_HEIGHT;
  for (const node of placedNodes) {
    width = Math.max(width, node.x + TREE_NODE_WIDTH);
    height = Math.max(height, node.y + TREE_NODE_HEIGHT);
  }

  let inScopeCount = 0;
  for (const node of uniqueNodes) {
    if (rootPath === "/" || isPathWithinRoot(node.path, rootPath)) {
      inScopeCount += 1;
    }
  }

  return {
    root: safeRoot,
    nodes: placedNodes,
    links,
    width,
    height,
    rootPath,
    dropped: Math.max(0, inScopeCount - placedIds.size),
  };
}
