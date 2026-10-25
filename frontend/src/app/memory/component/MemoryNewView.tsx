import { useId, useState, type FormEvent } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";

import { Button, ButtonLink } from "../../component/Button";
import { Icon } from "../../component/Icon";
import { PageHeader } from "../../component/PageHeader";
import { Panel } from "../../component/Panel";
import { useToast } from "../../component/Toast";
import { useSaveMemory } from "../../generated-apis-types/memories/memories";
import { useApiErrorMessage, useI18n } from "../../i18n";

import {
  invalidateMemoryQueries,
  nowLocalInput,
  parseSupersedes,
  savedMemoryMessage,
  type MemorySaveReceipt,
} from "./helpers";

/** Full-page pressing room for a new memory. */
export function MemoryNewView() {
  const { t, formatNumber } = useI18n();
  const apiErrorMessage = useApiErrorMessage();
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

  const parsedSupersedes = parseSupersedes(supersedes, t);
  const supersedesIssue =
    supersedes.trim().length > 0 ? parsedSupersedes.error : null;
  const supersedeCount = parsedSupersedes.ids.length;
  let supersedeMeta = t("memory.newView.metaNewRecord");
  if (supersedeCount === 1) {
    supersedeMeta = t("memory.newView.metaSupersedesOne", {
      count: formatNumber(supersedeCount),
    });
  } else if (supersedeCount > 1) {
    supersedeMeta = t("memory.newView.metaSupersedesOther", {
      count: formatNumber(supersedeCount),
    });
  }
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
      setContentError(t("memory.newView.contentRequired"));
      valid = false;
    } else if (cleaned.length > 8000) {
      setContentError(t("memory.newView.contentTooLong"));
      valid = false;
    } else {
      setContentError(null);
    }

    const occurred = occurredAt.length > 0 ? new Date(occurredAt) : null;
    if (occurred && Number.isNaN(occurred.getTime())) {
      setOccurredError(t("memory.newView.occurredInvalid"));
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
          toast.success(
            savedMemoryMessage(
              t,
              result.memory.memory_id,
              result.deprecated.length,
            ),
          );
          invalidateMemoryQueries(queryClient);
          const receipt: MemorySaveReceipt = {
            deprecated: result.deprecated,
            summary: result.summary,
          };
          navigate(`/memory/${result.memory.memory_id}`, { state: receipt });
        },
        onError: (error) => {
          const message = apiErrorMessage(error, "memory.common.genericError");
          setFailure(message);
          toast.error(t("memory.newView.saveFailed", { detail: message }));
        },
      },
    );
  };

  return (
    <div className="content-container memory-page memory-new-page">
      <nav className="memory-breadcrumb" aria-label={t("memory.common.breadcrumbAria")}>
        <Link to="/memory">{t("memory.vault.title")}</Link>
        <span aria-hidden="true">/</span>
        <span className="memory-breadcrumb__current" aria-current="page">
          {t("memory.newView.breadcrumbCurrent")}
        </span>
      </nav>

      <PageHeader
        eyebrow={t("memory.newView.eyebrow")}
        title={t("memory.newView.title")}
        description={t("memory.newView.description")}
        meta={
          <span className="memory-page-header__meta">
            {supersedeMeta}
          </span>
        }
        actions={
          <ButtonLink to="/memory" variant="ghost" size="sm">
            <Icon name="arrow-right" size={15} className="memory-back-icon" />
            {t("memory.newView.backToVault")}
          </ButtonLink>
        }
      />

      <div className="memory-new">
        <Panel
          eyebrow={t("memory.newView.formEyebrow")}
          title={t("memory.newView.formTitle")}
          className="memory-new__form"
        >
          <form className="memory-form" onSubmit={handleSubmit}>
            <div className="memory-field">
              <label className="memory-field__label" htmlFor={contentId}>
                {t("memory.newView.contentLabel")}{" "}
                <small>{t("memory.newView.contentHint")}</small>
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
                placeholder={t("memory.newView.contentPlaceholder")}
                aria-invalid={contentError !== null}
                aria-describedby={contentDescribedBy}
              />
              <div className="memory-field__footer">
                <span className="field-help" id={`${contentId}-help`}>
                  {t("memory.newView.contentHelp")}
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
                  {t("memory.newView.contentCount", {
                    count: formatNumber(content.length),
                  })}
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
                  {t("memory.newView.occurredLabel")}{" "}
                  <small>{t("memory.newView.occurredHint")}</small>
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
                  {t("memory.newView.supersedesLabel")}{" "}
                  <small>{t("memory.newView.supersedesHint")}</small>
                </label>
                <input
                  id={supersedesId}
                  className="input"
                  type="text"
                  inputMode="numeric"
                  value={supersedes}
                  onChange={(event) => setSupersedes(event.target.value)}
                  placeholder={t("memory.newView.supersedesPlaceholder")}
                  aria-invalid={supersedesIssue !== null}
                  aria-describedby={
                    supersedesIssue
                      ? `${supersedesId}-help ${supersedesId}-error`
                      : `${supersedesId}-help`
                  }
                />
                <span className="field-help" id={`${supersedesId}-help`}>
                  {t("memory.newView.supersedesHelp")}
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
                {saveMemory.isPending
                  ? t("memory.newView.saving")
                  : t("memory.newView.save")}
              </Button>
              <p>
                {t("memory.newView.sourceNoteBefore")}
                <span className="code-inline">manual</span>
                {t("memory.newView.sourceNoteAfter")}
              </p>
            </div>
          </form>
        </Panel>

        <aside className="memory-new__aside">
          <Panel
            eyebrow={t("memory.newView.consequencesEyebrow")}
            title={t("memory.newView.consequencesTitle")}
          >
            <ol className="memory-steps">
              <li>
                <span>01</span>
                <p>
                  {t("memory.newView.step1Before")}
                  <strong>{t("memory.newView.step1Strong")}</strong>
                  {t("memory.newView.step1After")}
                </p>
              </li>
              <li>
                <span>02</span>
                <p>
                  {t("memory.newView.step2Before")}
                  <strong>{t("memory.newView.step2Strong")}</strong>
                  {t("memory.newView.step2After")}
                </p>
              </li>
              <li>
                <span>03</span>
                <p>{t("memory.newView.step3")}</p>
              </li>
              <li>
                <span>04</span>
                <p>{t("memory.newView.step4")}</p>
              </li>
            </ol>
          </Panel>

          <Panel
            eyebrow={t("memory.newView.deprecationsEyebrow")}
            title={t("memory.newView.deprecationsTitle")}
            className="memory-new__deprecations"
          >
            {parsedSupersedes.ids.length > 0 ? (
              <>
                <p className="memory-note">
                  {t("memory.newView.deprecationsNote")}
                </p>
                <ul className="memory-deprecation-list">
                  {parsedSupersedes.ids.map((id) => (
                    <li key={id}>
                      <Link to={`/memory/${id}`}>
                        {t("memory.common.crystal", { id })}
                      </Link>
                    </li>
                  ))}
                </ul>
              </>
            ) : (
              <p className="memory-note">
                {t("memory.newView.deprecationsEmpty")}
              </p>
            )}
          </Panel>
        </aside>
      </div>
    </div>
  );
}
