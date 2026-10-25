import { Button } from "../../component/Button";
import { Icon } from "../../component/Icon";
import { useI18n, type Translate } from "../../i18n";
import { IngestProgress } from "./IngestProgress";
import {
  INGEST_STAGE_KEYS,
  type LibraryUploadTask,
} from "./library-utils";

interface LibraryUploadTrayProps {
  readonly tasks: readonly LibraryUploadTask[];
  readonly onRetry: (task: LibraryUploadTask) => void;
  readonly onDismiss: () => void;
}

function stageLabel(task: LibraryUploadTask, t: Translate, fallback: string): string {
  return task.stage ? t(INGEST_STAGE_KEYS[task.stage]) : fallback;
}

function uploadStatusLabel(
  task: LibraryUploadTask,
  t: Translate,
  formatNumber: (value: number) => string,
): string {
  if (task.status === "queued") {
    return t("library.ingest.stage.queued");
  }
  if (task.status === "uploading") {
    return t("library.tray.uploading");
  }
  if (task.status === "done") {
    return t("library.ingest.stage.ready");
  }
  if (task.status === "error") {
    return task.rejected ? t("library.tray.rejected") : t("library.tray.failed");
  }
  if (
    task.stage === "embedding" &&
    typeof task.chunksTotal === "number" &&
    typeof task.chunksEmbedded === "number"
  ) {
    return t("library.tray.embedding", {
      done: formatNumber(task.chunksEmbedded),
      total: formatNumber(task.chunksTotal),
    });
  }
  return stageLabel(task, t, t("library.tray.processing"));
}

function uploadLiveSummary(task: LibraryUploadTask, t: Translate): string {
  if (task.status === "done") {
    return t("library.tray.liveReady", { name: task.name });
  }
  if (task.status === "error") {
    return task.rejected
      ? t("library.tray.liveRejected", { name: task.name })
      : t("library.tray.liveFailed", { name: task.name });
  }
  if (task.status === "uploading") {
    return t("library.tray.liveUploading", { name: task.name });
  }
  if (task.status === "queued") {
    return t("library.tray.liveQueued", { name: task.name });
  }
  return task.stage
    ? `${task.name} ${t(INGEST_STAGE_KEYS[task.stage])}`
    : t("library.tray.liveProcessing", { name: task.name });
}

function TaskMark({ task }: { readonly task: LibraryUploadTask }) {
  if (task.status === "done") {
    return (
      <span className="library-upload-task__mark" aria-hidden="true">
        <Icon name="check" size={13} />
      </span>
    );
  }
  if (task.status === "error") {
    return (
      <span className="library-upload-task__mark" aria-hidden="true">
        <Icon name="info" size={13} />
      </span>
    );
  }
  return (
    <span className="library-upload-task__mark" aria-hidden="true">
      <span className="library-upload-task__spinner" />
    </span>
  );
}

/** The shared intake queue for drag/drop, clipboard, and Media tab uploads. */
export function LibraryUploadTray({ tasks, onRetry, onDismiss }: LibraryUploadTrayProps) {
  const { t, formatNumber } = useI18n();
  if (tasks.length === 0) {
    return null;
  }

  const active = tasks.some(
    (task) =>
      task.status === "queued" ||
      task.status === "uploading" ||
      task.status === "processing",
  );
  const activeCount = tasks.filter(
    (task) =>
      task.status === "queued" ||
      task.status === "uploading" ||
      task.status === "processing",
  ).length;
  const finished = tasks.filter((task) => task.status === "done").length;
  const liveSummary = tasks
    .map((task) => uploadLiveSummary(task, t))
    .join(t("library.tray.liveSeparator"));

  return (
    <section
      className="library-upload-tray"
      aria-busy={active}
      aria-label={t("library.tray.aria")}
    >
      <p className="visually-hidden" aria-live="polite">
        {liveSummary}
      </p>
      <header className="library-upload-tray__head">
        <div>
          <p className="eyebrow">{t("library.tray.eyebrow")}</p>
          <span className="library-upload-tray__count">
            {t("library.tray.readyCount", {
              done: formatNumber(finished),
              total: formatNumber(tasks.length),
            })}
          </span>
        </div>
        {active ? (
          <span className="library-upload-tray__busy">
            {t(
              activeCount === 1
                ? "library.tray.processingOne"
                : "library.tray.processingOther",
              { count: formatNumber(activeCount) },
            )}
          </span>
        ) : (
          <Button variant="ghost" size="sm" onClick={onDismiss}>
            {t("library.tray.clear")}
          </Button>
        )}
      </header>
      <ul className="library-upload-tray__list">
        {tasks.map((task) => (
          <li className={`library-upload-task is-${task.status}`} key={task.id}>
            <TaskMark task={task} />
            <span className="library-upload-task__body">
              <span className="library-upload-task__name">{task.name}</span>
              <code className="library-upload-task__path">{task.targetPath}</code>
              {task.status === "queued" ||
              task.status === "uploading" ||
              task.status === "processing" ? (
                <IngestProgress
                  className="library-upload-task__progress"
                  variant="compact"
                  stage={task.stage ?? null}
                  progressPct={task.progressPct ?? null}
                  chunksTotal={task.chunksTotal ?? null}
                  chunksEmbedded={task.chunksEmbedded ?? null}
                  label={
                    task.status === "uploading"
                      ? t("library.tray.uploadingLabel")
                      : undefined
                  }
                />
              ) : null}
              {task.message ? (
                <span className="library-upload-task__message">{task.message}</span>
              ) : null}
            </span>
            <span className="library-upload-task__side">
              <span className="library-upload-task__status">
                {uploadStatusLabel(task, t, formatNumber)}
              </span>
              {task.status === "error" && !task.rejected ? (
                <Button variant="ghost" size="sm" onClick={() => onRetry(task)}>
                  <Icon name="history" size={13} />
                  {t("library.common.retry")}
                </Button>
              ) : null}
            </span>
          </li>
        ))}
      </ul>
    </section>
  );
}
