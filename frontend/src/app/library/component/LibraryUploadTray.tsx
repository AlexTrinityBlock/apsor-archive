import { Button } from "../../component/Button";
import { Icon } from "../../component/Icon";
import { IngestProgress } from "./IngestProgress";
import {
  ingestStageLabel,
  type LibraryUploadTask,
} from "./library-utils";

interface LibraryUploadTrayProps {
  readonly tasks: readonly LibraryUploadTask[];
  readonly onRetry: (task: LibraryUploadTask) => void;
  readonly onDismiss: () => void;
}

function uploadStatusLabel(task: LibraryUploadTask): string {
  if (task.status === "queued") {
    return "Queued";
  }
  if (task.status === "uploading") {
    return "Uploading…";
  }
  if (task.status === "done") {
    return "Ready";
  }
  if (task.status === "error") {
    return task.rejected ? "Rejected" : "Failed";
  }
  if (
    task.stage === "embedding" &&
    typeof task.chunksTotal === "number" &&
    typeof task.chunksEmbedded === "number"
  ) {
    return `Embedding ${task.chunksEmbedded}/${task.chunksTotal}`;
  }
  return ingestStageLabel(task.stage, "Processing");
}

function uploadLiveSummary(task: LibraryUploadTask): string {
  if (task.status === "done") {
    return `${task.name} ready`;
  }
  if (task.status === "error") {
    return `${task.name} ${task.rejected ? "rejected" : "failed"}`;
  }
  if (task.status === "uploading") {
    return `${task.name} uploading`;
  }
  if (task.status === "queued") {
    return `${task.name} queued`;
  }
  return `${task.name} ${ingestStageLabel(task.stage, "processing")}`;
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
  const liveSummary = tasks.map(uploadLiveSummary).join(". ");

  return (
    <section className="library-upload-tray" aria-busy={active} aria-label="Upload queue">
      <p className="visually-hidden" aria-live="polite">
        {liveSummary}
      </p>
      <header className="library-upload-tray__head">
        <div>
          <p className="eyebrow">Intake queue</p>
          <span className="library-upload-tray__count">
            {finished}/{tasks.length} ready
          </span>
        </div>
        {active ? (
          <span className="library-upload-tray__busy">
            {activeCount} {activeCount === 1 ? "file" : "files"} processing…
          </span>
        ) : (
          <Button variant="ghost" size="sm" onClick={onDismiss}>
            Clear tray
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
                  label={task.status === "uploading" ? "Uploading" : undefined}
                />
              ) : null}
              {task.message ? (
                <span className="library-upload-task__message">{task.message}</span>
              ) : null}
            </span>
            <span className="library-upload-task__side">
              <span className="library-upload-task__status">{uploadStatusLabel(task)}</span>
              {task.status === "error" && !task.rejected ? (
                <Button variant="ghost" size="sm" onClick={() => onRetry(task)}>
                  <Icon name="history" size={13} />
                  Retry
                </Button>
              ) : null}
            </span>
          </li>
        ))}
      </ul>
    </section>
  );
}
