import { useCallback, useMemo, useState, type ReactNode } from "react";
import { useSearchParams } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";

import { useSearchKnowledge } from "../generated-apis-types/search/search";
import { useSeedDemo } from "../generated-apis-types/system/system";
import { getGetTreeUrl, useGetTree } from "../generated-apis-types/tree/tree";
import { useDebouncedValue } from "../hook/useDebouncedValue";
import { Badge } from "../component/Badge";
import { Button } from "../component/Button";
import { EmptyState } from "../component/EmptyState";
import { Icon } from "../component/Icon";
import { Loader } from "../component/Loader";
import { PageHeader } from "../component/PageHeader";
import { Panel } from "../component/Panel";
import { useToast } from "../component/Toast";
import { TreeCanvas } from "./component/TreeCanvas";
import { TreeControls } from "./component/TreeControls";
import { TreeInspector } from "./component/TreeInspector";
import {
  buildTreeLayout,
  normalizeTreeRoot,
  type TreeLayoutNode,
} from "./treeLayout";
import "./tree.css";

const MAX_DEPTH = 20;
const DEFAULT_DEPTH = 20;

interface Breadcrumb {
  readonly label: string;
  readonly path: string;
}

function parseDepth(value: string | null): number {
  if (value === null || value.trim().length === 0) {
    return DEFAULT_DEPTH;
  }
  const parsed = Number(value);
  if (!Number.isInteger(parsed)) {
    return DEFAULT_DEPTH;
  }
  return Math.min(MAX_DEPTH, Math.max(3, parsed));
}

function buildBreadcrumbs(root: string): readonly Breadcrumb[] {
  const segments = root.split("/").filter(Boolean);
  const crumbs: Breadcrumb[] = [{ label: "archive", path: "/" }];
  let current = "";
  for (const segment of segments) {
    current = `${current}/${segment}`;
    crumbs.push({ label: segment, path: current });
  }
  return crumbs;
}

function describeError(error: unknown): string {
  if (error instanceof Error && error.message.length > 0) {
    return error.message;
  }
  return "The tree endpoint did not answer.";
}

/**
 * The live knowledge tree. URL parameters hold the root, depth, and history
 * view; search is a local highlight layer that never blocks the canvas.
 */
export function TreePage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const rootPath = normalizeTreeRoot(searchParams.get("root"));
  const depth = parseDepth(searchParams.get("depth"));
  const includeHistory = searchParams.get("history") === "1";

  const [searchDraft, setSearchDraft] = useState("");
  const [searchSubmitTick, setSearchSubmitTick] = useState(0);
  const [selectedKey, setSelectedKey] = useState<string | null>(null);

  const debouncedSearch = useDebouncedValue(searchDraft, 260);
  const searchTerm = debouncedSearch.trim();
  const searchActive = searchTerm.length >= 2;

  const treeParams = useMemo(
    () => ({
      root: rootPath,
      depth,
      include_history: includeHistory,
    }),
    [depth, includeHistory, rootPath],
  );

  const treeQuery = useGetTree(treeParams);
  const searchQuery = useSearchKnowledge(
    { query: searchTerm, result_number: 5 },
    { query: { enabled: searchActive } },
  );

  const matchFileIds = useMemo(() => {
    const ids = new Set<number>();
    if (!searchActive || searchQuery.isError) {
      return ids;
    }
    for (const result of searchQuery.data?.file_results ?? []) {
      ids.add(result.file_id);
    }
    return ids;
  }, [searchActive, searchQuery.data, searchQuery.isError]);

  const layout = useMemo(
    () => buildTreeLayout(treeQuery.data?.nodes ?? [], rootPath),
    [rootPath, treeQuery.data],
  );

  const selectedNode = useMemo(
    () => layout.nodes.find((node) => node.key === selectedKey) ?? null,
    [layout.nodes, selectedKey],
  );

  const breadcrumbs = useMemo(() => buildBreadcrumbs(rootPath), [rootPath]);

  const searchFocusSignal = searchActive
    ? `${searchTerm}|${searchQuery.dataUpdatedAt}|${searchSubmitTick}`
    : "";
  const searchBusy = searchActive && searchQuery.isPending;
  const searchFailed = searchActive && searchQuery.isError;
  const searchMatchCount = matchFileIds.size;
  const searchFocusFileId = useMemo(() => {
    if (!searchActive || searchQuery.isError || !searchQuery.data) {
      return null;
    }
    const visibleFileIds = new Set(
      layout.nodes
        .filter((node) => node.node.kind === "file")
        .map((node) => node.node.file_id)
        .filter((fileId): fileId is number => fileId !== null),
    );
    for (const result of searchQuery.data.file_results) {
      if (visibleFileIds.has(result.file_id)) {
        return result.file_id;
      }
    }
    return null;
  }, [layout.nodes, searchActive, searchQuery.data, searchQuery.isError]);

  const queryClient = useQueryClient();
  const toast = useToast();
  const seedDemo = useSeedDemo({
    mutation: {
      onSuccess: (result) => {
        toast.success(
          `Seeded ${result.files_created} files and ${result.memories_created} memories.`,
        );
        void queryClient.invalidateQueries();
      },
      onError: () => {
        toast.error("The demo archive could not be seeded.");
      },
    },
  });

  const updateQuery = useCallback(
    (updates: Readonly<Record<string, string | null>>) => {
      setSearchParams((current) => {
        const next = new URLSearchParams(current);
        for (const [key, value] of Object.entries(updates)) {
          if (value === null) {
            next.delete(key);
          } else {
            next.set(key, value);
          }
        }
        return next;
      });
    },
    [setSearchParams],
  );

  const selectRoot = useCallback(
    (nextRoot: string) => {
      const normalized = normalizeTreeRoot(nextRoot);
      if (normalized === rootPath) {
        return;
      }
      setSelectedKey(null);
      updateQuery({ root: normalized });
    },
    [rootPath, updateQuery],
  );

  const handleReadRoot = useCallback(
    (nextRoot: string) => {
      if (nextRoot !== rootPath) {
        selectRoot(nextRoot);
      }
    },
    [rootPath, selectRoot],
  );

  const handleDepthChange = (value: string) => {
    setSelectedKey(null);
    updateQuery({ depth: value });
  };

  const toggleHistory = () => {
    setSelectedKey(null);
    updateQuery({ history: includeHistory ? null : "1" });
  };

  const handleSelect = useCallback((node: TreeLayoutNode) => {
    setSelectedKey(node.key);
  }, []);

  const handleSearchSubmit = (value: string) => {
    setSearchDraft(value);
    setSearchSubmitTick((current) => current + 1);
  };

  const treeTotal = treeQuery.data?.total ?? 0;
  const endpoint = getGetTreeUrl(treeParams);
  const isEmpty =
    treeQuery.data !== undefined && treeQuery.data.nodes.length === 0;

  let board: ReactNode;
  if (treeQuery.isPending) {
    board = (
      <Panel tone="plain" className="tree-stage__state">
        <Loader size={44} label="Reading the knowledge tree" />
        <div>
          <p className="eyebrow">Reading the tree</p>
          <h2>Following the branch ledger.</h2>
          <p>
            Mapping nodes below <code>{rootPath}</code> to depth {depth}.
          </p>
        </div>
      </Panel>
    );
  } else if (treeQuery.isError) {
    board = (
      <Panel tone="plain" className="tree-stage__state tree-stage__state--error">
        <div>
          <p className="eyebrow">Read interrupted</p>
          <h2>The tree did not answer.</h2>
          <p>{describeError(treeQuery.error)}</p>
        </div>
        <Button
          variant="secondary"
          size="sm"
          onClick={() => {
            void treeQuery.refetch();
          }}
        >
          Try again
          <Icon name="arrow-right" size={15} />
        </Button>
      </Panel>
    );
  } else if (isEmpty) {
    board = (
      <EmptyState
        icon="tree"
        eyebrow="No branches recorded"
        title={
          rootPath === "/"
            ? "The archive is still bare."
            : "No branches under this root."
        }
        description={`The tree endpoint returned no nodes for ${rootPath}. Seed a small demonstration archive, or read from the archive root to inspect the whole ledger.`}
        endpoint={endpoint}
        method="GET"
        action={
          <div className="empty-state__actions">
            <Button
              variant="primary"
              size="sm"
              onClick={() => seedDemo.mutate()}
              disabled={seedDemo.isPending}
            >
              <Icon name={seedDemo.isPending ? "clock" : "plus"} size={15} />
              {seedDemo.isPending ? "Seeding archive..." : "Seed demo archive"}
            </Button>
            {rootPath !== "/" ? (
              <Button variant="ghost" size="sm" onClick={() => selectRoot("/")}>
                Read from archive root
              </Button>
            ) : null}
          </div>
        }
      />
    );
  } else {
    board = (
      <TreeCanvas
        layout={layout}
        selectedKey={selectedKey}
        onSelect={handleSelect}
        matchFileIds={matchFileIds}
        focusFileId={searchFocusFileId}
        searchFocusSignal={searchFocusSignal}
        renderKey={treeQuery.dataUpdatedAt}
        truncated={treeQuery.data?.truncated ?? false}
      />
    );
  }

  return (
    <div className="page tree-page">
      <PageHeader
        eyebrow="Knowledge tree · path index"
        title="One tree, whole archive."
        description="Folders, current files, and their retained branches share one tidy SVG. Carry the root in the URL, search to ring matching files, drag to pan, and open any card to read its lineage."
        meta={
          <span>
            root {rootPath} · {treeTotal > 0 ? `${treeTotal} nodes` : "awaiting nodes"}{" "}
            · depth {depth}
          </span>
        }
        actions={
          <div className="tree-page__badges">
            <Badge tone="moss" dot>
              {includeHistory ? "current + history" : "current only"}
            </Badge>
            <Badge tone={includeHistory ? "ochre" : "neutral"} dot={includeHistory}>
              {includeHistory ? "history on" : "history off"}
            </Badge>
          </div>
        }
      />

      <TreeControls
        rootPath={rootPath}
        depth={depth}
        includeHistory={includeHistory}
        breadcrumbs={breadcrumbs}
        searchDraft={searchDraft}
        searchActive={searchActive}
        searchBusy={searchBusy}
        searchFailed={searchFailed}
        searchMatchCount={searchMatchCount}
        onReadRoot={handleReadRoot}
        onDepthChange={handleDepthChange}
        onToggleHistory={toggleHistory}
        onBreadcrumb={selectRoot}
        onSearchChange={setSearchDraft}
        onSearchSubmit={handleSearchSubmit}
      />

      <div className="tree-stage reveal reveal-3">
        <div className="tree-stage__board" aria-busy={treeQuery.isFetching}>
          {board}
        </div>
        <TreeInspector node={selectedNode} onClose={() => setSelectedKey(null)} />
      </div>
    </div>
  );
}
