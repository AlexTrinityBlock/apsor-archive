/** Shared prop model for the dock's panel and expanded surfaces. */
import type { RefObject, UIEventHandler } from "react";

import type {
  AgentApprovalSchema,
  AgentConversationDetailSchema,
  AgentConversationSchema,
  AgentEntrySchema,
} from "../../generated-apis-types/schemas";
import type { ChatStreamView } from "../../chat/hook/useChatStream";
import type { RetryState } from "../../chat/types";
import type { PageContextSnapshot } from "../page-context";
import type { WorkTraceModel } from "../trace";

export type AgentDockMode = "collapsed" | "panel" | "expanded";
export type AgentPane = "thread" | "inspector";

export interface AgentDockSurfaceProps {
  readonly conversations: readonly AgentConversationSchema[];
  readonly listLoading: boolean;
  readonly selectedId: number | null;
  readonly conversation: AgentConversationDetailSchema | null;
  readonly conversationLoading: boolean;
  readonly conversationError: unknown;
  readonly entries: readonly AgentEntrySchema[];
  readonly stream: ChatStreamView | null;
  readonly context: PageContextSnapshot | null;
  readonly lastContextKey: string | null;
  readonly draft: string;
  readonly onDraftChange: (value: string) => void;
  readonly onSubmit: (content: string) => void;
  readonly pending: boolean;
  readonly streaming: boolean;
  readonly disabled: boolean;
  readonly onStop: () => void;
  readonly archived: boolean;
  readonly lastError: string | null;
  readonly onDismissError: () => void;
  readonly onSelectThread: (id: number | null) => void;
  readonly onNewThread: () => void;
  readonly onRetryThread: () => void;
  readonly hasMoreEntries: boolean;
  readonly loadingMore: boolean;
  readonly loadMoreError: string | null;
  readonly onLoadMore: () => void;
  readonly retryState: RetryState;
  readonly retryDisabled: boolean;
  readonly onRetryRun: () => void;
  readonly approvals: readonly AgentApprovalSchema[];
  readonly approvalsDisabled: boolean;
  readonly onResolveApproval: (
    approvalId: number,
    decision: "approve" | "reject",
  ) => Promise<boolean>;
  readonly onContextApplied: (entry: AgentEntrySchema) => void;
  readonly scrollRef: RefObject<HTMLDivElement | null>;
  readonly endRef: RefObject<HTMLDivElement | null>;
  readonly onScroll: UIEventHandler<HTMLDivElement>;
  readonly mode: AgentDockMode;
  readonly onMode: (mode: AgentDockMode) => void;
  readonly trace: WorkTraceModel;
  readonly pinnedId: string | null;
  readonly onPin: (id: string) => void;
  readonly onFollow: () => void;
  readonly pane: AgentPane;
  readonly onPane: (pane: AgentPane) => void;
}
