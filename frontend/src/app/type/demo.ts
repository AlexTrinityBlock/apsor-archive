/**
 * Typed placeholder content for the foundation.
 *
 * DEMO ONLY: the tool catalogue and example citation chips below are static
 * editorial data. Page-level statistics, memories, trees, and timelines now
 * come from the generated React Query hooks. Replace any remaining demo reads
 * with Orval hooks when those surfaces gain live endpoints.
 */
export type StatAccent = "moss" | "ochre" | "vermilion" | "ink";

export interface ArchiveStat {
  readonly label: string;
  readonly value: string;
  readonly note: string;
  readonly accent: StatAccent;
}

export const demoStats: readonly ArchiveStat[] = [
  { label: "Files archived", value: "1,284", note: "across 37 branching paths", accent: "moss" },
  { label: "Memories pressed", value: "3,842", note: "181 superseded, still traceable", accent: "ochre" },
  { label: "AI summaries", value: "96", note: "generator recorded on every one", accent: "vermilion" },
  { label: "Indexed chunks", value: "12,408", note: "1-based, current leaves only", accent: "ink" },
];

export interface MemoryPreview {
  readonly id: number;
  readonly displayDate: string;
  readonly time: string;
  readonly occurredAt: string;
  readonly kind: "memory" | "summary" | "file";
  readonly status: "active" | "summary" | "updated";
  readonly title: string;
  readonly excerpt: string;
  readonly themes: readonly string[];
  readonly path?: string;
}

export const demoMemories: readonly MemoryPreview[] = [
  {
    id: 1015,
    displayDate: "18 Oct 2026",
    time: "09:42",
    occurredAt: "2026-10-18T09:42:00Z",
    kind: "memory",
    status: "active",
    title: "Superseded memories stay readable, not searchable.",
    excerpt:
      "A deprecated memory leaves the default search surface but keeps its supersede chain. History is a route, never a gap.",
    themes: ["retrieval", "history"],
  },
  {
    id: 1009,
    displayDate: "17 Oct 2026",
    time: "21:18",
    occurredAt: "2026-10-17T21:18:00Z",
    kind: "summary",
    status: "summary",
    title: "Week 42: the archive is the index.",
    excerpt:
      "The tree is not a folder picker bolted onto search. Path, time, and citation share one retrievable grain.",
    themes: ["weekly", "structure"],
  },
  {
    id: 997,
    displayDate: "16 Oct 2026",
    time: "14:05",
    occurredAt: "2026-10-16T14:05:00Z",
    kind: "memory",
    status: "updated",
    title: "A path is an argument about where knowledge belongs.",
    excerpt:
      "Re-uploading the same path grows a new branch. The previous version becomes history instead of being overwritten.",
    themes: ["files", "lineage"],
  },
  {
    id: 982,
    displayDate: "14 Oct 2026",
    time: "08:30",
    occurredAt: "2026-10-14T08:30:00Z",
    kind: "file",
    status: "updated",
    title: "Automobile history, third edition.",
    excerpt:
      "189 chunks re-indexed. The Ford chapter now carries a 1970s market timeline alongside the production notes.",
    themes: ["automobiles", "version 3"],
    path: "/history/industry/automobiles/2026_automobile_history.md",
  },
];

export interface LineageFile {
  readonly name: string;
  readonly version: number;
  readonly state: "current" | "superseded";
  readonly chunks: number;
  readonly kind: "markdown" | "pdf" | "csv";
  readonly updated: string;
}

export interface FileLineagePreview {
  readonly root: string;
  readonly branch: string;
  readonly files: readonly LineageFile[];
}

export const demoFileLineage: FileLineagePreview = {
  root: "/history/industry",
  branch: "/automobiles",
  files: [
    {
      name: "2026_automobile_history.md",
      version: 3,
      state: "current",
      chunks: 189,
      kind: "markdown",
      updated: "18 Oct 2026",
    },
    {
      name: "2024_ev_industry.pdf",
      version: 1,
      state: "current",
      chunks: 92,
      kind: "pdf",
      updated: "02 Sep 2026",
    },
    {
      name: "2022_automobile_annual.md",
      version: 2,
      state: "superseded",
      chunks: 41,
      kind: "markdown",
      updated: "11 Mar 2025",
    },
    {
      name: "1970s_market_notes.csv",
      version: 1,
      state: "current",
      chunks: 24,
      kind: "csv",
      updated: "28 Jul 2026",
    },
  ],
};

export type ToolName =
  | "search_knowledge"
  | "read_file"
  | "read_timeline"
  | "read_path"
  | "save_memory"
  | "read_memory";

export interface ToolDemo {
  readonly name: ToolName;
  readonly index: string;
  readonly title: string;
  readonly description: string;
  readonly endpoint: string;
  readonly method: "GET" | "POST";
  readonly href: string;
  readonly accent: StatAccent;
}

export const demoTools: readonly ToolDemo[] = [
  {
    name: "search_knowledge",
    index: "01",
    title: "Search the archive",
    description: "Text and vector candidates, fused once and deduplicated across files, memories, and summaries.",
    endpoint: "GET /api/v1/search",
    method: "GET",
    href: "/search",
    accent: "moss",
  },
  {
    name: "read_file",
    index: "02",
    title: "Read a file window",
    description: "Open a cited chunk with its neighbours, so a snippet arrives with the paragraph around it.",
    endpoint: "GET /api/v1/files/{id}/chunks/{chunk}",
    method: "GET",
    href: "/library",
    accent: "ochre",
  },
  {
    name: "read_timeline",
    index: "03",
    title: "Sample a season",
    description: "Five anchors across a date range, plus the density and skips needed to see the gaps honestly.",
    endpoint: "GET /api/v1/timeline",
    method: "GET",
    href: "/timeline",
    accent: "vermilion",
  },
  {
    name: "read_path",
    index: "04",
    title: "Walk a branch",
    description: "Browse a directory or fuzzy-match a path without loading the whole library first.",
    endpoint: "GET /api/v1/paths",
    method: "GET",
    href: "/tree",
    accent: "ink",
  },
  {
    name: "save_memory",
    index: "05",
    title: "Press a new leaf",
    description: "Record a moment and optionally point it at the memories it supersedes. Nothing is overwritten.",
    endpoint: "POST /api/v1/memories",
    method: "POST",
    href: "/memory/new",
    accent: "moss",
  },
  {
    name: "read_memory",
    index: "06",
    title: "Trace a memory",
    description: "Read the target, its neighbours, and the full supersede chain, including deprecated entries.",
    endpoint: "GET /api/v1/memories/{id}",
    method: "GET",
    href: "/timeline",
    accent: "ochre",
  },
];

export interface AskCitation {
  readonly label: string;
  readonly tone: "file" | "memory";
}

export const demoAskCitations: readonly AskCitation[] = [
  { label: "file:12#15", tone: "file" },
  { label: "memory:1015", tone: "memory" },
  { label: "summary:96", tone: "memory" },
];

/** Placeholder for the eventual GET /api/v1/ai/status response. */
export const demoAiStatus = {
  configured: false,
  provider: "DeepSeek",
  model: "deepseek-flash",
  state: "Awaiting backend",
} as const;

/** Placeholder for GET /api/v1/health and /api/v1/stats. */
export const demoSystemStatus = {
  label: "Local preview",
  detail: "API not connected",
  version: "0.1.0",
  apiBase: "http://127.0.0.1:8000",
  frontend: "Vite + React 19",
} as const;
