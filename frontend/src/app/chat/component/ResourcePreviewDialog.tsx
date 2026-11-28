import {
  useEffect,
  useId,
  useRef,
  type ReactNode,
} from "react";
import { createPortal } from "react-dom";
import { Link } from "react-router-dom";

import { Badge } from "../../component/Badge";
import { Icon } from "../../component/Icon";
import { useGetFile } from "../../generated-apis-types/files/files";
import { useReadMemory } from "../../generated-apis-types/memories/memories";
import { useI18n } from "../../i18n";
import { useScrollLock } from "../../hook/useScrollLock";
import { formatBytes } from "../../../lib/format";
import { libraryFileUrl, libraryMemoryUrl } from "../../../lib/library-url";
import { FileRenderer } from "../../viewer/component/FileViewer";
import {
  ViewerErrorState,
  ViewerLoading,
  ViewerThumbnailLoading,
} from "../../viewer/component/ViewerStates";
import type { ThumbnailInfo } from "../../viewer/component/thumbnail";
import {
  classifyFile,
  kindLabel,
} from "../../viewer/component/viewer-utils";
import { type ResourceMeta } from "../types";

const FOCUSABLE =
  'a[href], button:not([disabled]), input:not([disabled]), textarea:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])';

function ResourceDialogShell({
  eyebrow,
  title,
  meta,
  action,
  children,
  onClose,
}: {
  readonly eyebrow: string;
  readonly title: string;
  readonly meta: string;
  readonly action: ReactNode;
  readonly children: ReactNode;
  readonly onClose: () => void;
}) {
  const { t } = useI18n();
  const titleId = useId();
  const dialogRef = useRef<HTMLDivElement>(null);
  const onCloseRef = useRef(onClose);

  useScrollLock(true);

  useEffect(() => {
    onCloseRef.current = onClose;
  }, [onClose]);

  useEffect(() => {
    const previous =
      document.activeElement instanceof HTMLElement
        ? document.activeElement
        : null;
    dialogRef.current?.focus();
    return () => previous?.focus();
  }, []);

  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        onCloseRef.current();
        return;
      }
      if (event.key !== "Tab") {
        return;
      }
      const dialog = dialogRef.current;
      if (!dialog) {
        return;
      }
      const focusable = Array.from(
        dialog.querySelectorAll<HTMLElement>(FOCUSABLE),
      ).filter((element) => element.offsetParent !== null);
      if (focusable.length === 0) {
        event.preventDefault();
        dialog.focus();
        return;
      }
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, []);

  return createPortal(
    <div
      className="modal chat-resource-modal"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) {
          onClose();
        }
      }}
    >
      <div
        ref={dialogRef}
        className="modal-dialog chat-resource-modal__dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        tabIndex={-1}
      >
        <header className="modal-head chat-resource-modal__head">
          <div className="chat-resource-modal__identity">
            <p className="eyebrow">{eyebrow}</p>
            <h2 id={titleId}>{title}</h2>
            <code>{meta}</code>
          </div>
          <div className="chat-resource-modal__actions">
            {action}
            <button
              type="button"
              className="modal-btn-close"
              onClick={onClose}
              aria-label={t("chat.resource.closePreview")}
              title={t("chat.resource.closePreview")}
            >
              <Icon name="close" size={18} />
            </button>
          </div>
        </header>
        <div className="modal-body chat-resource-modal__body">
          <div className="chat-resource-modal__stage">{children}</div>
        </div>
      </div>
    </div>,
    document.body,
  );
}

function FileResourceBody({
  fileId,
  chunk,
  fallbackTitle,
  thumbnail,
}: {
  readonly fileId: number;
  readonly chunk: number | null;
  readonly fallbackTitle: string | null;
  readonly thumbnail: ThumbnailInfo | null;
}) {
  const { t } = useI18n();
  const query = useGetFile(fileId, { query: { retry: false } });

  if (query.isLoading) {
    // The presented resource already carries the thumbnail, so the dialog
    // shows the page or picture at once instead of an empty spinner.
    const label = t("chat.resource.loadingPreview");
    return thumbnail ? (
      <ViewerThumbnailLoading fileId={fileId} thumbnail={thumbnail} label={label} />
    ) : (
      <ViewerLoading label={label} />
    );
  }
  if (query.error || !query.data) {
    return (
      <ViewerErrorState
        error={query.error}
        title={fallbackTitle ?? t("chat.resource.previewError")}
        onRetry={() => void query.refetch()}
      />
    );
  }

  return <FileRenderer file={query.data} chunk={chunk} />;
}

function MemoryResourceBody({
  memoryId,
  fallbackTitle,
}: {
  readonly memoryId: number;
  readonly fallbackTitle: string | null;
}) {
  const { t, formatDateTime } = useI18n();
  const query = useReadMemory(
    memoryId,
    { memory_range: 1, trace_history: true },
    { query: { retry: false } },
  );

  if (query.isLoading) {
    return <ViewerLoading label={t("chat.resource.loadingPreview")} />;
  }
  if (query.error || !query.data) {
    return (
      <ViewerErrorState
        error={query.error}
        title={fallbackTitle ?? t("chat.resource.previewError")}
        onRetry={() => void query.refetch()}
      />
    );
  }

  const memory = query.data.target;
  return (
    <article className="chat-resource-memory">
      <header className="chat-resource-memory__head">
        <div>
          <p className="eyebrow">{t("chat.inspector.memoryPreview")}</p>
          <h3>{memory.title}</h3>
          <code>memory:{memory.memory_id}</code>
        </div>
        <Badge tone={memory.status === "active" ? "moss" : "ochre"}>
          {memory.status}
        </Badge>
      </header>
      <div className="chat-resource-memory__body">{memory.content}</div>
      <footer className="chat-resource-memory__foot">
        <span>
          {t("chat.resource.updatedAt", {
            time: formatDateTime(memory.update_time),
          })}
        </span>
        <Link className="text-link" to={libraryMemoryUrl(memory.memory_id)}>
          {t("chat.resource.openMemory")}
          <Icon name="arrow-up-right" size={12} />
        </Link>
      </footer>
    </article>
  );
}

interface ResourcePreviewDialogProps {
  readonly resource: ResourceMeta | null;
  readonly onClose: () => void;
}

/** The chat-area preview dialog for a presented file or memory. */
export function ResourcePreviewDialog({
  resource,
  onClose,
}: ResourcePreviewDialogProps) {
  const { t } = useI18n();
  const fileQuery = useGetFile(resource?.resourceId ?? 0, {
    query: {
      enabled: resource?.resourceType === "file" && resource.resourceId !== null,
      retry: false,
    },
  });
  const memoryTitle =
    resource?.resourceType === "memory" ? resource.title : null;

  if (resource === null || resource.resourceId === null) {
    return null;
  }

  if (resource.resourceType === "memory") {
    return (
      <ResourceDialogShell
        eyebrow={t("chat.resource.previewEyebrow")}
        title={
          resource.title ??
          t("chat.resource.memoryFallback", { id: resource.resourceId })
        }
        meta={`memory:${resource.resourceId}`}
        action={null}
        onClose={onClose}
      >
        <MemoryResourceBody
          memoryId={resource.resourceId}
          fallbackTitle={memoryTitle}
        />
      </ResourceDialogShell>
    );
  }

  const file = fileQuery.data;
  const kind = file ? classifyFile(file) : null;
  const meta = [
    kind === null ? null : kindLabel(kind, t),
    file?.mime_type ?? resource.mimeType,
    file ? formatBytes(file.size_bytes) : null,
    resource.chunk === null
      ? null
      : t("chat.common.chunk", { chunk: resource.chunk }),
    file?.raw_file_path,
  ].filter((item): item is string => item !== null && item !== undefined && item.length > 0);

  return (
    <ResourceDialogShell
      eyebrow={t("chat.resource.previewEyebrow")}
      title={
        file?.file_name ??
        resource.title ??
        t("chat.resource.fileFallback", { id: resource.resourceId })
      }
      meta={meta.join(" · ")}
      action={
        <Link
          className="btn btn--ghost btn--sm"
          to={libraryFileUrl(resource.resourceId, "files", {
            chunk: resource.chunk,
          })}
        >
          {t("chat.resource.openInLibrary")}
          <Icon name="arrow-up-right" size={13} />
        </Link>
      }
      onClose={onClose}
    >
      <FileResourceBody
        fileId={resource.resourceId}
        chunk={resource.chunk}
        fallbackTitle={resource.title}
        thumbnail={resource.thumbnail}
      />
    </ResourceDialogShell>
  );
}
