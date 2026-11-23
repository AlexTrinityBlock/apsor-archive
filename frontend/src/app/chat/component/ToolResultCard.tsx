import type { AgentEntrySchema } from "../../generated-apis-types/schemas";
import {
  readToolResultCallId,
  readToolResultMeta,
  type ResourceMeta,
} from "../types";
import { ToolStepCard } from "./ToolStepCard";

/** A persisted tool result rendered as the visible tool step of a turn. */
export function ToolResultCard({
  entry,
  step = null,
  selectedTraceId = null,
  onSelectTrace,
  onOpenResource,
}: {
  readonly entry: AgentEntrySchema;
  /** The step of the assistant entry this result immediately follows. */
  readonly step?: number | null;
  readonly selectedTraceId?: string | null;
  readonly onSelectTrace?: (traceId: string) => void;
  readonly onOpenResource?: (resource: ResourceMeta) => void;
}) {
  const callId = readToolResultCallId(entry);
  const selected = callId !== null && selectedTraceId === callId;
  return (
    <ToolStepCard
      meta={readToolResultMeta(entry)}
      step={step}
      entryId={entry.id}
      callId={callId}
      selected={selected}
      onSelect={onSelectTrace}
      onOpenResource={onOpenResource}
    />
  );
}
