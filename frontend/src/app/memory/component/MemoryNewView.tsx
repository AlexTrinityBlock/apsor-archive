import { useId, useState, type FormEvent } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";

import { Button, ButtonLink } from "../../component/Button";
import { Icon } from "../../component/Icon";
import { PageHeader } from "../../component/PageHeader";
import { Panel } from "../../component/Panel";
import { useToast } from "../../component/Toast";
import { useSaveMemory } from "../../generated-apis-types/memories/memories";
import { formatNumber } from "../../../lib/format";

import {
  errorText,
  invalidateMemoryQueries,
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
  const [supersedes, setSupersedes] = useState(() => {
    const repeated = searchParams.getAll("supersedes");
    return repeated.length > 0
      ? repeated.join(", ")
      : (searchParams.get("supersedes") ?? "");
  });
  const [contentError, setContentError] = useState<string | null>(null);
  const [occurredError, setOccurredError] = useState<string | null>(null);
  const [failure, setFailure] = useState<string | null>(null);

  const parsedSupersedes = parseSupersedes(supersedes);
  const supersedesIssue =
    supersedes.trim().length > 0 ? parsedSupersedes.error : null;
  const supersedeCount = parsedSupersedes.ids.length;
  const supersedeNoun = supersedeCount === 1 ? "record" : "records";
  const supersedeMeta =
    supersedeCount > 0 ? `supersedes ${supersedeCount} ${supersedeNoun}` : "new record";
  const nearContentLimit = content.length >= 7600;
  const contentDescribedBy = [
    `${contentId}-help`,
    `${contentId}-count`,
    contentError ? `${contentId}-error` : null,
  ]
    .filter(Boolean)
    .join(" ");

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const cleaned = content.trim();
    let valid = true;

    if (cleaned.length === 0) {
      setContentError("Write the memory before pressing it into the archive.");
      valid = false;
    } else if (cleaned.length > 8000) {
      setContentError("A memory is limited to 8,000 characters.");
      valid = false;
    } else {
      setContentError(null);
    }

    const occurred = occurredAt.length > 0 ? new Date(occurredAt) : null;
    if (occurred && Number.isNaN(occurred.getTime())) {
      setOccurredError("The occurred-at time is not a valid date.");
      valid = false;
    } else {
      setOccurredError(null);
    }

    if (!valid) {
      return;
    }
    if (parsedSupersedes.error) {
      return;
    }

    setFailure(null);
    saveMemory.mutate(
      {
        data: {
          content: cleaned,
          supersedes: parsedSupersedes.ids,
          occurred_at: occurred ? occurred.toISOString() : null,
          source: "manual",
        },
      },
      {
        onSuccess: (result) => {
          toast.success(savedMemoryMessage(result.memory.memory_id, result.deprecated.length));
          invalidateMemoryQueries(queryClient);
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
    <div className="content-container memory-page memory-new-page">
      <nav className="memory-breadcrumb" aria-label="Breadcrumb">
        <Link to="/memory">Memory Vault</Link>
        <span aria-hidden="true">/</span>
        <span className="memory-breadcrumb__current" aria-current="page">
          Pressing room
        </span>
      </nav>

      <PageHeader
        eyebrow="Memory · pressing room"
        title="Press a new memory."
        description="A new memory records an occurrence and may supersede earlier beliefs. The older entries become deprecated, not deleted: they leave default search and the timeline, yet the lineage remains readable."
        meta={
          <span className="memory-page-header__meta">
            {supersedeMeta}
          </span>
        }
        actions={
          <ButtonLink to="/memory" variant="ghost" size="sm">
            <Icon name="arrow-right" size={15} className="memory-back-icon" />
            Back to vault
          </ButtonLink>
        }
      />

      <div className="memory-new">
        <Panel
          eyebrow="New record"
          title="What should be remembered?"
          className="memory-new__form"
        >
          <form className="memory-form" onSubmit={handleSubmit}>
            <div className="memory-field">
              <label className="memory-field__label" htmlFor={contentId}>
                Content <small>required · 8,000 characters max</small>
              </label>
              <textarea
                id={contentId}
                className="textarea"
                value={content}
                onChange={(event) => {
                  const next = event.target.value;
                  setContent(next);
                  if (contentError && next.trim().length > 0) {
                    setContentError(null);
                  }
                }}
                rows={12}
                maxLength={8000}
                aria-required="true"
                autoFocus
                placeholder="A decision, a change of mind, an observation, a moment that should survive."
                aria-invalid={contentError !== null}
                aria-describedby={contentDescribedBy}
              />
              <div className="memory-field__footer">
                <span className="field-help" id={`${contentId}-help`}>
                  Plain text; stored and indexed exactly as written.
                </span>
                <span
                  className={[
                    "memory-field__count",
                    nearContentLimit ? "is-near-limit" : null,
                  ]
                    .filter(Boolean)
                    .join(" ")}
                  id={`${contentId}-count`}
                >
                  {formatNumber(content.length)} / 8,000
                </span>
              </div>
              {contentError ? (
                <p className="field-error" id={`${contentId}-error`} role="alert">
                  {contentError}
                </p>
              ) : null}
            </div>

            <div className="memory-form__grid">
              <div className="memory-field">
                <label className="memory-field__label" htmlFor={occurredId}>
                  Occurred at <small>optional · defaults to now</small>
                </label>
                <input
                  id={occurredId}
                  className="input"
                  type="datetime-local"
                  value={occurredAt}
                  onChange={(event) => {
                    setOccurredAt(event.target.value);
                    if (occurredError) {
                      setOccurredError(null);
                    }
                  }}
                  aria-invalid={occurredError !== null}
                  aria-describedby={occurredError ? `${occurredId}-error` : undefined}
                />
                {occurredError ? (
                  <p className="field-error" id={`${occurredId}-error`} role="alert">
                    {occurredError}
                  </p>
                ) : null}
              </div>

              <div className="memory-field">
                <label className="memory-field__label" htmlFor={supersedesId}>
                  Supersedes <small>optional · comma-separated ids</small>
                </label>
                <input
                  id={supersedesId}
                  className="input"
                  type="text"
                  inputMode="numeric"
                  value={supersedes}
                  onChange={(event) => setSupersedes(event.target.value)}
                  placeholder="12, 14"
                  aria-invalid={supersedesIssue !== null}
                  aria-describedby={
                    supersedesIssue
                      ? `${supersedesId}-help ${supersedesId}-error`
                      : `${supersedesId}-help`
                  }
                />
                <span className="field-help" id={`${supersedesId}-help`}>
                  Numeric memory ids only. Up to 50 records can be replaced.
                </span>
                {supersedesIssue ? (
                  <p className="field-error" id={`${supersedesId}-error`} role="alert">
                    {supersedesIssue}
                  </p>
                ) : null}
              </div>
            </div>

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
                disabled={saveMemory.isPending}
              >
                <Icon name="leaf" size={17} />
                {saveMemory.isPending ? "Pressing the memory…" : "Save memory"}
              </Button>
              <p>
                The record is saved with source <span className="code-inline">manual</span>. If the
                API returns an auto-created summary, it appears in the receipt on the saved
                record.
              </p>
            </div>
          </form>
        </Panel>

        <aside className="memory-new__aside">
          <Panel
            eyebrow="Consequences"
            title="What saving does"
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
                  Deprecated memories leave default search and the default timeline. Their chunks
                  stop being retrieved; their text remains readable with the full chain.
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
            className="memory-new__deprecations"
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
                      <Link to={`/memory/${id}`}>CRYSTAL #{id}</Link>
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
        </aside>
      </div>
    </div>
  );
}
