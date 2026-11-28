/**
 * The companion action vocabulary. Ids are a stable contract shared by preset
 * manifests, custom uploads, the agent's `companion_action` tool, and the chat
 * state machine; never rename one without migrating stored manifests.
 */
import type { TranslationKey } from "../i18n";

export const COMPANION_ACTIONS = [
  "idle",
  "greet",
  "listening",
  "thinking",
  "searching",
  "reading",
  "writing",
  "calculating",
  "browsing",
  "presenting",
  "speaking",
  "waiting",
  "success",
  "confused",
  "sleeping",
  "held",
] as const;

export type CompanionAction = (typeof COMPANION_ACTIONS)[number];

const ACTION_SET: ReadonlySet<string> = new Set(COMPANION_ACTIONS);

export function isCompanionAction(value: unknown): value is CompanionAction {
  return typeof value === "string" && ACTION_SET.has(value);
}

/**
 * Higher wins when two signals compete. `held` always wins because the reader
 * has the figure in hand; the agent's explicit gesture beats automatic tool
 * poses but never a failure or a pending approval.
 */
export const ACTION_PRIORITY: Readonly<Record<CompanionAction, number>> = {
  held: 100,
  confused: 80,
  waiting: 75,
  presenting: 60,
  writing: 58,
  calculating: 56,
  browsing: 54,
  searching: 52,
  reading: 50,
  thinking: 40,
  speaking: 35,
  success: 30,
  greet: 25,
  listening: 20,
  sleeping: 5,
  idle: 0,
};

/** Priority assigned to an action that the agent requested explicitly. */
export const AGENT_OVERRIDE_PRIORITY = 70;

/**
 * When a character has no pose for an action, walk this chain until one
 * exists. Every chain ends at `idle`, which every manifest must provide.
 */
export const ACTION_FALLBACKS: Readonly<
  Record<CompanionAction, readonly CompanionAction[]>
> = {
  idle: [],
  greet: ["success", "idle"],
  listening: ["idle"],
  thinking: ["idle"],
  searching: ["reading", "thinking", "idle"],
  reading: ["searching", "thinking", "idle"],
  writing: ["reading", "thinking", "idle"],
  calculating: ["thinking", "idle"],
  browsing: ["searching", "reading", "thinking", "idle"],
  presenting: ["speaking", "idle"],
  speaking: ["idle"],
  waiting: ["listening", "idle"],
  success: ["greet", "idle"],
  confused: ["thinking", "idle"],
  sleeping: ["idle"],
  held: ["idle"],
};

/** Archive tool name → the pose the companion takes while it runs. */
const TOOL_ACTIONS: Readonly<Record<string, CompanionAction>> = {
  search_knowledge: "searching",
  read_file: "reading",
  read_path: "reading",
  read_memory: "reading",
  read_timeline: "reading",
  history_message: "reading",
  save_memory: "writing",
  calculate: "calculating",
  render_plot: "calculating",
  web_search: "browsing",
  web_fetch: "browsing",
  present_resource: "presenting",
};

/** The agent's own gesture tool; its arguments carry the requested action. */
export const COMPANION_TOOL_NAME = "companion_action";

export function actionForTool(name: string): CompanionAction | null {
  if (Object.hasOwn(TOOL_ACTIONS, name)) {
    return TOOL_ACTIONS[name] ?? null;
  }
  if (name.startsWith("read_")) {
    return "reading";
  }
  if (name.startsWith("web_")) {
    return "browsing";
  }
  return null;
}

export const ACTION_LABEL_KEYS: Readonly<
  Record<CompanionAction, TranslationKey>
> = {
  idle: "companion.actions.idle",
  greet: "companion.actions.greet",
  listening: "companion.actions.listening",
  thinking: "companion.actions.thinking",
  searching: "companion.actions.searching",
  reading: "companion.actions.reading",
  writing: "companion.actions.writing",
  calculating: "companion.actions.calculating",
  browsing: "companion.actions.browsing",
  presenting: "companion.actions.presenting",
  speaking: "companion.actions.speaking",
  waiting: "companion.actions.waiting",
  success: "companion.actions.success",
  confused: "companion.actions.confused",
  sleeping: "companion.actions.sleeping",
  held: "companion.actions.held",
};

/**
 * Only these changes are worth a polite screen-reader announcement. Idle,
 * typing, and token-by-token speech would be noise.
 */
const ANNOUNCED: ReadonlySet<CompanionAction> = new Set([
  "searching",
  "reading",
  "writing",
  "calculating",
  "browsing",
  "presenting",
  "waiting",
  "success",
  "confused",
]);

export function isAnnouncedAction(action: CompanionAction): boolean {
  return ANNOUNCED.has(action);
}
