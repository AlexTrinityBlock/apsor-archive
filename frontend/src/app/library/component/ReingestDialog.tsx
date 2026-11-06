import { useEffect, useRef, type ReactNode } from "react";

import { Badge } from "../../component/Badge";
import { Button } from "../../component/Button";
import { Icon } from "../../component/Icon";
import { useI18n } from "../../i18n";
import type { FileSchema, IngestJobSchema } from "../../generated-apis-types/schemas";
import type { ReingestPhase } from "../hook/useFileReingest";
import { IngestProgress } from "./IngestProgress";
import { LibraryDialog } from "./LibraryDialog";

interface ReingestDialogProps {
  readonly sourceFile: FileSchema;
  readonly phase: ReingestPhase;
  readonly job: IngestJobSchema | null;
  readonly result: FileSchema | null;
  readonly failureMessage: string | null;
  readonly onConfirm: () => void;
  readonly onClose: () => void;
}

function SourceSummary({ file }: { readonly file: FileSchema }) {
  const { t, formatNumber } = useI18n();
  return (
    <div className="library-reingest__source">
      <div className="library-reingest__source-head">
        <Icon name="file" size={15} />
        <span className="library-reingest__source-name">{file.file_name}</span>
        <Badge tone="neutral">
          {t("library.reingest.versionLine", {
            version: formatNumber(file.version),
          })}
        </Badge>
      </div>
      <code className="library-reingest__path">{file.raw_file_path}</code>
    </div>
  );
}

function ConfirmationBody({
  file,
  onConfirm,
  onClose,
}: {
  readonly file: FileSchema;
  readonly onConfirm: () => void;
  readonly onClose: () => void;
}) {
  const { t } = useI18n();
  return (
    <div className="library-reingest">
      <SourceSummary file={file} />
      <div className="library-reingest__note" role="note">
        <Icon name="info" size={15} />
        <span>{t("library.reingest.costNote")}</span>
      </div>
      <p className="library-reingest__history-note">
        <Icon name="history" size={14} />
        <span>{t("library.reingest.newVersionNote")}</span>
      </p>
      <div className="library-reingest__actions">
        <Button type="button" variant="ghost" size="sm" onClick={onClose}>
          {t("library.common.cancel")}
        </Button>
        <Button
          type="button"
          variant="ink"
          size="sm"
          onClick={onConfirm}
          data-autofocus
        >
          {t("library.reingest.confirm")}
        </Button>
      </div>
    </div>
  );
}

function ProgressBody({
  phase,
  job,
  onClose,
}: {
  readonly phase: ReingestPhase;
  readonly job: IngestJobSchema | null;
  readonly onClose: () => void;
}) {
  const { t } = useI18n();
  return (
    <div className="library-reingest">
      <section
        className="library-reingest__progress"
        aria-label={t("library.reingest.progressAria")}
      >
        <IngestProgress
          variant="large"
          stage={job?.status ?? null}
          progressPct={job?.progress_pct ?? null}
          chunksTotal={job?.chunks_total ?? null}
          chunksEmbedded={job?.chunks_embedded ?? null}
          label={
            phase === "enqueueing"
              ? t("library.reingest.starting")
              : t("library.reingest.processing")
          }
        />
        <p className="library-reingest__progress-note">
          {t("library.reingest.closeNote")}
        </p>
      </section>
      <div className="library-reingest__actions">
        <Button
          type="button"
          variant="ghost"
          size="sm"
          onClick={onClose}
          data-autofocus
        >
          {t("library.reingest.stopWaiting")}
        </Button>
      </div>
    </div>
  );
}

function FailureBody({
  message,
  onClose,
}: {
  readonly message: string | null;
  readonly onClose: () => void;
}) {
  const { t } = useI18n();
  return (
    <div className="library-reingest">
      <div className="library-reingest__failure" role="alert">
        <Icon name="info" size={16} />
        <div>
          {message ? <p>{message}</p> : null}
          <p>{t("library.reingest.failureNote")}</p>
        </div>
      </div>
      <div className="library-reingest__actions">
        <Button
          type="button"
          variant="ink"
          size="sm"
          onClick={onClose}
          data-autofocus
        >
          {t("library.reingest.done")}
        </Button>
      </div>
    </div>
  );
}

function SuccessBody({
  result,
  onClose,
}: {
  readonly result: FileSchema;
  readonly onClose: () => void;
}) {
  const { t, formatNumber } = useI18n();
  return (
    <div className="library-reingest">
      <div className="library-reingest__success" role="status">
        <Icon name="check" size={16} />
        <div>
          <p>
            {t("library.reingest.successBody", {
              name: result.file_name,
              version: formatNumber(result.version),
            })}
          </p>
        </div>
      </div>
      <div className="library-reingest__actions">
        <Button
          type="button"
          variant="ink"
          size="sm"
          onClick={onClose}
          data-autofocus
        >
          {t("library.reingest.done")}
        </Button>
      </div>
    </div>
  );
}

function AlreadyProcessingBody({ onClose }: { readonly onClose: () => void }) {
  const { t } = useI18n();
  return (
    <div className="library-reingest">
      <div className="library-reingest__already" role="note">
        <Icon name="clock" size={16} />
        <span>{t("library.reingest.alreadyProcessingBody")}</span>
      </div>
      <div className="library-reingest__actions">
        <Button
          type="button"
          variant="ink"
          size="sm"
          onClick={onClose}
          data-autofocus
        >
          {t("library.reingest.done")}
        </Button>
      </div>
    </div>
  );
}

/**
 * Presentational re-ingest shell: confirmation, durable-job progress, failure,
 * already-processing, and success. The page-level hook owns enqueue/poll state
 * so the job survives closing the preview.
 */
export function ReingestDialog({
  sourceFile,
  phase,
  job,
  result,
  failureMessage,
  onConfirm,
  onClose,
}: ReingestDialogProps) {
  const { t } = useI18n();
  const bodyRef = useRef<HTMLDivElement>(null);

  // The dialog swaps entire bodies between phases, so keep keyboard focus on
  // the new primary action instead of dropping it onto the page beneath.
  useEffect(() => {
    if (phase === "idle") {
      return;
    }
    const target = bodyRef.current?.querySelector<HTMLElement>(
      "[data-autofocus]",
    );
    target?.focus();
  }, [phase]);

  if (phase === "idle") {
    return null;
  }
  const busy = phase === "enqueueing" || phase === "processing";

  let title: string;
  let description: string | undefined;
  if (phase === "confirming") {
    title = t("library.reingest.title", { name: sourceFile.file_name });
    description = t("library.reingest.description");
  } else if (phase === "failure") {
    title = t("library.reingest.failureTitle");
  } else if (phase === "success") {
    title = t("library.reingest.successTitle");
  } else if (phase === "already-processing") {
    title = t("library.reingest.alreadyProcessingTitle");
  } else {
    title = t("library.reingest.progressTitle", {
      name: sourceFile.file_name,
    });
    description = t("library.reingest.progressDescription");
  }

  let body: ReactNode;
  if (phase === "confirming") {
    body = (
      <ConfirmationBody file={sourceFile} onConfirm={onConfirm} onClose={onClose} />
    );
  } else if (busy) {
    body = <ProgressBody phase={phase} job={job} onClose={onClose} />;
  } else if (phase === "failure") {
    body = <FailureBody message={failureMessage} onClose={onClose} />;
  } else if (phase === "success" && result !== null) {
    body = <SuccessBody result={result} onClose={onClose} />;
  } else {
    body = <AlreadyProcessingBody onClose={onClose} />;
  }

  return (
    <LibraryDialog
      eyebrow={t("library.reingest.eyebrow")}
      title={title}
      description={description}
      onClose={onClose}
      dismissible={!busy}
      className="library-reingest-dialog"
    >
      <div ref={bodyRef}>{body}</div>
    </LibraryDialog>
  );
}
