import { useId, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";

import { Badge } from "../../component/Badge";
import { Button } from "../../component/Button";
import { Icon } from "../../component/Icon";
import { Panel } from "../../component/Panel";
import { useToast } from "../../component/Toast";
import {
  getGetSystemPromptQueryKey,
  useGetSystemPrompt,
  useResetSystemPrompt,
  useUpdateSystemPrompt,
} from "../../generated-apis-types";
import type { SystemPromptReadSchema } from "../../generated-apis-types/schemas";
import { apiErrorMessage } from "./settings-utils";
import { SettingsDialog } from "./SettingsDialog";

const COLLAPSE_KEY = "dendromatrix.settings.systemPromptOpen";

function initiallyOpen(): boolean {
  try {
    return window.localStorage.getItem(COLLAPSE_KEY) !== "false";
  } catch {
    return true;
  }
}

const SECTION_ORDER = [
  "System prompt",
  "Identity",
  "Instructions",
  "Examples",
  "Context protocol",
  "Tool catalog",
  "Conversation messages",
];

interface EditorProps {
  readonly data: SystemPromptReadSchema;
  readonly saving: boolean;
  readonly error: string | null;
  readonly onSave: (title: string, body: string) => void;
  readonly onRequestReset: () => void;
}

/** Controlled fields remount only when the persisted prompt changes. */
function SystemPromptEditor({
  data,
  saving,
  error,
  onSave,
  onRequestReset,
}: EditorProps) {
  const [title, setTitle] = useState(data.title);
  const [body, setBody] = useState(data.body);
  const titleId = useId();
  const bodyId = useId();

  const dirty = title !== data.title || body !== data.body;
  const valid = title.trim().length > 0 && body.trim().length > 0;

  return (
    <div className="system-prompt">
      <p className="settings-lede">
        The first section of every new conversation. It is written once as the
        stable prefix before identity, tool rules, and messages, then frozen so
        editing it never rewrites an existing KV-cache prefix.
      </p>

      <div className="system-prompt__order-block">
        <p className="mono-label">Provider request order</p>
        <ol className="system-prompt__order" aria-label="System prompt load order">
          {SECTION_ORDER.map((label, index) => (
            <li key={label} className={index === 0 ? "is-first" : undefined}>
              <span className="system-prompt__order-index">
                {String(index + 1).padStart(2, "0")}
              </span>
              <span>{label}</span>
            </li>
          ))}
        </ol>
        <p className="settings-hint">
          Stable order: system message → tools → append-only messages. The
          current time is appended to each user message when it is sent, so
          history is never rewritten.
        </p>
      </div>

      <div className="system-prompt__grid">
        <div className="field system-prompt__title">
          <label className="field-label" htmlFor={titleId}>
            Title
          </label>
          <input
            id={titleId}
            className="input"
            value={title}
            onChange={(event) => setTitle(event.target.value)}
            maxLength={200}
            placeholder="Archive voice"
            disabled={saving}
          />
          <span className="field-help">
            Rendered as the Markdown heading of the first section.
          </span>
        </div>

        <div className="field system-prompt__body">
          <label className="field-label" htmlFor={bodyId}>
            Body
          </label>
          <textarea
            id={bodyId}
            className="textarea system-prompt__textarea"
            value={body}
            onChange={(event) => setBody(event.target.value)}
            maxLength={32_000}
            rows={10}
            placeholder="Add persistent instructions for the archive agent. The built-in identity and tool rules still follow this section."
            disabled={saving}
          />
          <span className="field-help system-prompt__count">
            {body.length.toLocaleString()} / 32,000 characters
          </span>
        </div>
      </div>

      {error ? (
        <p className="vault-feedback vault-feedback--error" role="alert">
          <Icon name="info" size={14} />
          {error}
        </p>
      ) : null}

      <div className="system-prompt__actions">
        <Button
          type="button"
          variant="primary"
          size="sm"
          onClick={() => onSave(title.trim(), body.trim())}
          disabled={!valid || !dirty || saving}
        >
          <Icon name="check" size={14} />
          {saving ? "Saving…" : "Save system prompt"}
        </Button>
        <Button
          type="button"
          variant="secondary"
          size="sm"
          onClick={onRequestReset}
          disabled={!data.is_custom || saving}
        >
          <Icon name="history" size={14} />
          Reset to built-in
        </Button>
        <span className="system-prompt__meta">
          {data.updated_at
            ? `Updated ${new Date(data.updated_at).toLocaleString()}`
            : "No custom prompt saved"}
        </span>
      </div>
    </div>
  );
}

/** Owner-authored first system section, frozen into each new conversation. */
export function SystemPromptPanel() {
  const queryClient = useQueryClient();
  const toast = useToast();
  const query = useGetSystemPrompt({ query: { retry: false, staleTime: 15_000 } });
  const [open, setOpen] = useState(initiallyOpen);
  const [resetOpen, setResetOpen] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const updateMutation = useUpdateSystemPrompt({
    mutation: {
      onMutate: () => setError(null),
      onSuccess: (data) => {
        queryClient.setQueryData(getGetSystemPromptQueryKey(), data);
        toast.success("System prompt saved. It applies to new conversations.");
      },
      onError: (caught) => {
        const message = apiErrorMessage(caught);
        setError(message);
        toast.error(message);
      },
    },
  });

  const resetMutation = useResetSystemPrompt({
    mutation: {
      onMutate: () => setError(null),
      onSuccess: (data) => {
        queryClient.setQueryData(getGetSystemPromptQueryKey(), data);
        setResetOpen(false);
        toast.success("Custom prompt removed. Built-in sections only.");
      },
      onError: (caught) => {
        const message = apiErrorMessage(caught);
        setError(message);
        toast.error(message);
      },
    },
  });

  const saving = updateMutation.isPending || resetMutation.isPending;
  const custom = query.data?.is_custom ?? false;

  let statusBadge = <Badge tone="neutral">Built-in</Badge>;
  if (query.isPending) {
    statusBadge = <Badge tone="neutral">Loading</Badge>;
  } else if (query.isError) {
    statusBadge = <Badge tone="vermilion">Unavailable</Badge>;
  } else if (custom) {
    statusBadge = <Badge tone="moss">Custom + built-in</Badge>;
  }

  const data = query.data;
  const editorKey = data?.updated_at ?? (data ? "built-in" : "empty");

  return (
    <>
      <Panel
        id="settings-system-prompt"
        className="settings-panel system-prompt-panel"
        title={
          <span className="settings-panel__title">
            <Icon name="layers" size={16} />
            System prompt
          </span>
        }
        action={
          <div className="settings-panel__badges">
            {statusBadge}
            <button
              type="button"
              className="system-prompt__collapse"
              aria-expanded={open}
              aria-controls="system-prompt-body"
              onClick={() => setOpen((current) => !current)}
              title={open ? "Collapse system prompt" : "Expand system prompt"}
            >
              <Icon name={open ? "chevron-down" : "chevron-right"} size={14} />
              <span>{open ? "Collapse" : "Expand"}</span>
            </button>
          </div>
        }
      >
        {open ? (
          <div id="system-prompt-body">
            {query.isError ? (
              <div className="settings-inline-error" role="alert">
                <Icon name="info" size={16} />
                <div>
                  <p>{apiErrorMessage(query.error)}</p>
                  <Button
                    type="button"
                    variant="secondary"
                    size="sm"
                    onClick={() => void query.refetch()}
                  >
                    Try again
                  </Button>
                </div>
              </div>
            ) : null}

            {query.isPending ? (
              <div className="system-prompt" aria-busy="true">
                <span className="settings-skeleton settings-skeleton--line" />
                <span className="settings-skeleton settings-skeleton--field" />
                <span className="settings-skeleton settings-skeleton--field" />
              </div>
            ) : null}

            {data ? (
              <SystemPromptEditor
                key={editorKey}
                data={data}
                saving={saving}
                error={error}
                onSave={(title, body) =>
                  updateMutation.mutate({ data: { title, body } })
                }
                onRequestReset={() => setResetOpen(true)}
              />
            ) : null}
          </div>
        ) : null}
      </Panel>

      {resetOpen ? (
        <SettingsDialog
          eyebrow="Settings · system prompt"
          title="Remove the custom prompt?"
          description="New conversations will use the built-in identity, instructions, examples, and context protocol only. Existing conversations keep their frozen prompt."
          onClose={() => {
            if (!resetMutation.isPending) {
              setResetOpen(false);
            }
          }}
          actions={
            <>
              <Button
                type="button"
                variant="ghost"
                size="sm"
                onClick={() => setResetOpen(false)}
                disabled={resetMutation.isPending}
                data-autofocus
              >
                Cancel
              </Button>
              <Button
                type="button"
                variant="danger"
                size="sm"
                onClick={() => resetMutation.mutate()}
                disabled={resetMutation.isPending}
              >
                {resetMutation.isPending ? "Removing…" : "Remove prompt"}
              </Button>
            </>
          }
        >
          <p className="settings-lede">
            The built-in identity, instruction, example, and context-protocol
            sections remain in place. Only the custom first section is removed.
          </p>
        </SettingsDialog>
      ) : null}
    </>
  );
}
