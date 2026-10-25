import type { ReactNode } from "react";
import { Link } from "react-router-dom";

import { Icon } from "../../component/Icon";
import { useListAgentTools } from "../../generated-apis-types/agent/agent";
import type { AgentConversationDetailSchema } from "../../generated-apis-types/schemas";
import { useI18n } from "../../i18n";
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
  const { t, formatNumber } = useI18n();
  const toolsQuery = useListAgentTools({
    query: { staleTime: 300_000 },
  });
  const tools = toolsQuery.data?.tools ?? [];

  let toolBody: ReactNode = null;
  if (tools.length > 0) {
    toolBody = (
      <div className="chat-method__tools">
        <p className="chat-method__tools-label">
          {t("chat.method.currentToolCatalog")}
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
      <p className="chat-method__note">
        {t("chat.method.toolCatalogUnavailable")}
      </p>
    );
  }

  return (
    <details className="chat-method">
      <summary>
        <span className="chat-method__seal" aria-hidden="true">
          <Icon name="method" size={14} />
        </span>
        <span className="chat-method__label">{t("chat.method.label")}</span>
        <span className="chat-method__hint">
          {conversation.provider} · {conversation.model} ·{" "}
          {t(
            hiddenCount === 1
              ? "chat.method.hiddenOne"
              : "chat.method.hiddenOther",
            { count: formatNumber(hiddenCount) },
          )}
        </span>
        <Icon name="chevron-down" size={14} className="chat-method__chevron" />
      </summary>
      <div className="chat-method__body">
        <dl>
          <div>
            <dt>{t("chat.method.provider")}</dt>
            <dd>{conversation.provider}</dd>
          </div>
          <div>
            <dt>{t("chat.method.model")}</dt>
            <dd>{conversation.model}</dd>
          </div>
          <div>
            <dt>{t("chat.method.prompt")}</dt>
            <dd>{versions.promptVersion ?? "—"}</dd>
          </div>
          <div>
            <dt>{t("chat.method.tools")}</dt>
            <dd>{versions.toolsVersion ?? "—"}</dd>
          </div>
          <div>
            <dt>{t("chat.method.transcript")}</dt>
            <dd>
              {t(
                entryCount === 1
                  ? "chat.common.entryOne"
                  : "chat.common.entryOther",
                { count: formatNumber(entryCount) },
              )}
            </dd>
          </div>
        </dl>
        <p className="chat-method__note">{t("chat.method.note")}</p>
        {toolBody}
        <Link className="chat-method__link" to="/method">
          {t("chat.method.readMethod")}
          <Icon name="arrow-right" size={14} />
        </Link>
      </div>
    </details>
  );
}
