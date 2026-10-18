import { useId, useState, type FormEvent } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";

import { Button, ButtonLink } from "../../component/Button";
import { Badge } from "../../component/Badge";
import { Icon } from "../../component/Icon";
import { PageHeader } from "../../component/PageHeader";
import { Panel } from "../../component/Panel";
import { useToast } from "../../component/Toast";
import { useSaveMemory } from "../../generated-apis-types/memories/memories";
import { formatNumber } from "../../../lib/format";

import {
  errorText,
  nowLocalInput,
  parseSupersedes,
  savedMemoryMessage,
  type MemorySaveReceipt,
} from "./helpers";

/** Full-page pressing room for a new memory. */
export function MemoryNewView() {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const toast = useToast();
  const queryClient = useQueryClient();
  const saveMemory = useSaveMemory();
  const contentId = useId();
  const occurredId = useId();
  const supersedesId = useId();

  const [content, setContent] = useState("");
  const [occurredAt, setOccurredAt] = useState(nowLocalInput);
  const [supersedes, setSupersedes] = useState(() => searchParams.get("supersedes") ?? "");
  const [failure, setFailure] = useState<string | null>(null);

  const parsedSupersedes = parseSupersedes(supersedes);
  const supersedesIssue =
    supersedes.trim().length > 0 ? parsedSupersedes.error : null;

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const cleaned = content.trim();
    if (cleaned.length === 0) {
      setFailure("Write the memory before pressing it into the archive.");
      return;
    }
    if (cleaned.length > 8000) {
      setFailure("A memory is limited to 8,000 characters.");
      return;
    }
    if (parsedSupersedes.error) {
      setFailure(parsedSupersedes.error);
      return;
    }
    const occurred = occurredAt.length > 0 ? new Date(occurredAt) : null;
    if (occurred && Number.isNaN(occurred.getTime())) {
      setFailure("The occurred-at time is not a valid date.");
      return;
    }

    setFailure(null);
    saveMemory.mutate(
      {
        data: {
          content: cleaned,
          supersedes: parsedSupersedes.ids,
          occurred_at: occurred ? occurred.toISOString() : null,
        },
      },
      {
        onSuccess: (result) => {
          toast.success(savedMemoryMessage(result.memory.memory_id, result.deprecated.length));
          void queryClient.invalidateQueries();
          const receipt: MemorySaveReceipt = {
            deprecated: result.deprecated,
            summary: result.summary,
          };
          navigate(`/memory/${result.memory.memory_id}`, { state: receipt });
        },
        onError: (error) => {
          const message = errorText(error);
          setFailure(message);
          toast.error(`Could not save the memory. ${message}`);
        },
      },
    );
  };

  return (
    <div className="page memory-page memory-new-page">
      <PageHeader
        eyebrow="Memory · pressing room"
        title="Press a new memory."
        description="A new memory records a moment and may supersede earlier beliefs. The older entries become deprecated, not deleted: they leave search and the default timeline, yet the lineage remains readable."
        meta={<span>supersede in both directions</span>}
        actions={
          <ButtonLink to="/timeline" variant="ghost" size="sm">
            <Icon name="arrow-right" size={15} className="memory-back-icon" />
            Back to timeline
          </ButtonLink>
        }
      />

      <div className="memory-new">
        <Panel
          eyebrow="New record"
          title="What should be remembered?"
          className="memory-new__form reveal reveal-2"
        >
          <form className="memory-form" onSubmit={handleSubmit}>
            <label className="memory-field" htmlFor={contentId}>
              <span className="memory-field__label">
                Content <small>required · 8,000 characters max</small>
              </span>
              <textarea
                id={contentId}
                value={content}
                onChange={(event) => setContent(event.target.value)}
                rows={10}
                maxLength={8000}
                required
                autoFocus
                placeholder="A decision, a change of mind, an observation, a moment that should survive."
              />
              <span className="memory-field__count">{formatNumber(content.length)} / 8,000</span>
            </label>

            <div className="memory-form__grid">
              <label className="memory-field" htmlFor={occurredId}>
                <span className="memory-field__label">
                  Occurred at <small>optional · defaults to now</small>
                </span>
                <input
                  id={occurredId}
                  type="datetime-local"
                  value={occurredAt}
                  onChange={(event) => setOccurredAt(event.target.value)}
                />
              </label>
              <label className="memory-field" htmlFor={supersedesId}>
                <span className="memory-field__label">
                  Supersedes <small>optional · comma-separated ids</small>
                </span>
                <input
                  id={supersedesId}
                  type="text"
                  inputMode="numeric"
                  value={supersedes}
                  onChange={(event) => setSupersedes(event.target.value)}
                  placeholder="12, 14"
                  aria-invalid={supersedesIssue !== null}
                  aria-describedby={supersedesIssue ? `${supersedesId}-error` : undefined}
                />
              </label>
            </div>

            {supersedesIssue ? (
              <p className="memory-form__issue" id={`${supersedesId}-error`} role="alert">
                {supersedesIssue}
              </p>
            ) : null}

            {failure ? (
              <p className="memory-form__failure" role="alert">
                {failure}
              </p>
            ) : null}

            <div className="memory-form__submit">
              <Button
                type="submit"
                variant="primary"
                size="lg"
                disabled={saveMemory.isPending || content.trim().length === 0}
              >
                <Icon name="leaf" size={17} />
                {saveMemory.isPending ? "Pressing the memory" : "Save memory"}
              </Button>
              <p>
                The endpoint may also return an auto-created summary. It will be shown on the saved
                record together with the deprecated list.
              </p>
            </div>
          </form>
        </Panel>

        <aside className="memory-new__side">
          <Panel
            eyebrow="Consequences"
            title="What saving does"
            className="reveal reveal-3"
            action={<Badge tone="neutral">source: manual</Badge>}
          >
            <ol className="memory-steps">
              <li>
                <span>01</span>
                <p>
                  The new memory becomes <strong>active</strong> with a fresh id and its occurred-at
                  time.
                </p>
              </li>
              <li>
                <span>02</span>
                <p>
                  Every listed memory becomes <strong>deprecated</strong> and points to the new
                  record as its successor.
                </p>
              </li>
              <li>
                <span>03</span>
                <p>
                  Deprecated memories leave search and the default timeline. Their chunks stop
                  being retrieved; their text remains readable.
                </p>
              </li>
              <li>
                <span>04</span>
                <p>
                  If enough unsummarized memories have accumulated, the response may include an
                  auto-created summary.
                </p>
              </li>
            </ol>
          </Panel>

          <Panel
            eyebrow="Will be deprecated"
            title="Listed earlier memories"
            className="memory-new__deprecations reveal reveal-4"
          >
            {parsedSupersedes.ids.length > 0 ? (
              <>
                <p className="memory-note">
                  These ids will be deprecated if they exist and are still active. The backend
                  rejects an id that is already deprecated.
                </p>
                <ul className="memory-deprecation-list">
                  {parsedSupersedes.ids.map((id) => (
                    <li key={id}>
                      <Link to={`/memory/${id}`}>memory:{id}</Link>
                    </li>
                  ))}
                </ul>
              </>
            ) : (
              <p className="memory-note">
                No earlier memories are listed. This save will not deprecate anything.
              </p>
            )}
          </Panel>

          <Panel
            tone="plain"
            eyebrow="Endpoint"
            title="save_memory"
            className="memory-new__endpoint reveal reveal-4"
          >
            <div className="endpoint-label">
              <span>POST</span>
              <code>/api/v1/memories</code>
            </div>
            <p className="memory-note">
              Uses the generated <code>useSaveMemory</code> hook. All timeline, memory, and
              summary queries are invalidated after a successful save.
            </p>
          </Panel>
        </aside>
      </div>
    </div>
  );
}
