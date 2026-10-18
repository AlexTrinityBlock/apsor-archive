import type { ReactNode } from "react";
import { Link } from "react-router-dom";

import { Icon } from "../../component/Icon";
import { useListAgentTools } from "../../generated-apis-types/agent/agent";
import type { AgentConversationDetailSchema } from "../../generated-apis-types/schemas";
import type { SystemVersions } from "../types";

interface MethodDisclosureProps {
  readonly conversation: AgentConversationDetailSchema;
  readonly hiddenCount: number;
  readonly entryCount: number;
  readonly versions: SystemVersions;
}

/**
 * The prompt and frozen tool set stay behind a disclosure. Their text is never
 * injected into the reading view.
 */
export function MethodDisclosure({
  conversation,
  hiddenCount,
  entryCount,
  versions,
}: MethodDisclosureProps) {
  const toolsQuery = useListAgentTools({
    query: { staleTime: 300_000 },
  });
  const tools = toolsQuery.data?.tools ?? [];

  let toolBody: ReactNode = null;
  if (tools.length > 0) {
    toolBody = (
      <div className="chat-method__tools">
        <p className="chat-method__tools-label">
          Current tool catalog
          {toolsQuery.data?.tools_version
            ? ` · ${toolsQuery.data.tools_version}`
            : ""}
        </p>
        <ul>
          {tools.map((tool) => (
            <li key={tool.name}>
              <code>{tool.name}</code>
              <span>{tool.description}</span>
            </li>
          ))}
        </ul>
      </div>
    );
  } else if (toolsQuery.isError) {
    toolBody = (
      <p className="chat-method__note">The tool catalog is unavailable.</p>
    );
  }

  return (
    <details className="chat-method">
      <summary>
        <span className="chat-method__seal" aria-hidden="true">
          <Icon name="method" size={14} />
        </span>
        <span className="chat-method__label">Method</span>
        <span className="chat-method__hint">
          {conversation.provider} · {conversation.model} · {hiddenCount} hidden{" "}
          {hiddenCount === 1 ? "entry" : "entries"}
        </span>
        <Icon name="chevron-down" size={14} className="chat-method__chevron" />
      </summary>
      <div className="chat-method__body">
        <dl>
          <div>
            <dt>Provider</dt>
            <dd>{conversation.provider}</dd>
          </div>
          <div>
            <dt>Model</dt>
            <dd>{conversation.model}</dd>
          </div>
          <div>
            <dt>Prompt</dt>
            <dd>{versions.promptVersion ?? "—"}</dd>
          </div>
          <div>
            <dt>Tools</dt>
            <dd>{versions.toolsVersion ?? "—"}</dd>
          </div>
          <div>
            <dt>Transcript</dt>
            <dd>
              {entryCount} {entryCount === 1 ? "entry" : "entries"}
            </dd>
          </div>
        </dl>
        <p className="chat-method__note">
          System, reset, and compaction entries are hidden from this reading
          view. The frozen prompt and tool snapshot remain in the transcript.
        </p>
        {toolBody}
        <Link className="chat-method__link" to="/method">
          Read the method
          <Icon name="arrow-right" size={14} />
        </Link>
      </div>
    </details>
  );
}
