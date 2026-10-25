import { useId, useState, type FormEvent } from "react";
import { useQueryClient } from "@tanstack/react-query";

import type { FileSchema } from "../../generated-apis-types/schemas";
import { useRenameFile } from "../../generated-apis-types/files/files";
import { parentPath } from "../../../lib/format";
import { Button } from "../../component/Button";
import { Icon } from "../../component/Icon";
import { useToast } from "../../component/Toast";
import { useI18n } from "../../i18n";
import { LibraryDialog } from "./LibraryDialog";
import {
  describeError,
  invalidateLibraryQueries,
  isSafeUploadName,
  type FileOperationTarget,
} from "./library-utils";

interface RenameFileDialogProps {
  readonly file: FileOperationTarget;
  readonly onClose: () => void;
  readonly onRenamed: (file: FileSchema) => void;
}

interface SplitFileName {
  readonly stem: string;
  readonly extension: string;
}

/** Splits at the last dot; a leading dot belongs to the stem, not an extension. */
function splitFileName(fileName: string): SplitFileName {
  const dotIndex = fileName.lastIndexOf(".");
  if (dotIndex <= 0) {
    return { stem: fileName, extension: "" };
  }
  return {
    stem: fileName.slice(0, dotIndex),
    extension: fileName.slice(dotIndex),
  };
}

/** Control characters (C0, DEL, and C1) cannot appear in a file name. */
function hasControlCharacter(value: string): boolean {
  for (const character of value) {
    const codePoint = character.codePointAt(0) ?? 0;
    if (codePoint < 0x20 || (codePoint >= 0x7f && codePoint <= 0x9f)) {
      return true;
    }
  }
  return false;
}

function isValidStem(stem: string): boolean {
  const trimmed = stem.trim();
  return isSafeUploadName(trimmed) && !hasControlCharacter(trimmed);
}

/**
 * Renames one file inside its current folder. The folder and the original
 * extension are read-only, so the operation can never move the file or change
 * its media type.
 */
export function RenameFileDialog({
  file,
  onClose,
  onRenamed,
}: RenameFileDialogProps) {
  const { t } = useI18n();
  const toast = useToast();
  const queryClient = useQueryClient();
  const nameId = useId();
  const errorId = useId();
  const previewId = useId();
  const [initialSplit] = useState(() => splitFileName(file.file_name));
  const [stem, setStem] = useState(initialSplit.stem);
  const extension = initialSplit.extension;
  const normalizedStem = stem.trim();
  const fullName = `${normalizedStem}${extension}`;
  const folder = parentPath(file.raw_file_path);
  const invalid = !isValidStem(stem);
  const unchanged = fullName === file.file_name;

  const renameMutation = useRenameFile({
    mutation: {
      onSuccess: (renamedFile) => {
        toast.success(
          t("library.rename.renamedToast", {
            old: file.file_name,
            new: renamedFile.file_name,
          }),
        );
        invalidateLibraryQueries(queryClient, {
          paths: true,
          stats: true,
          timeline: true,
          search: true,
          fileIds: [file.file_id, renamedFile.id],
        });
        onRenamed(renamedFile);
      },
    },
  });

  const pending = renameMutation.isPending;
  const serverError = renameMutation.error
    ? describeError(renameMutation.error)
    : null;

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (invalid || unchanged || pending) {
      return;
    }
    renameMutation.mutate({
      fileId: file.file_id,
      data: { file_name: fullName },
    });
  };

  return (
    <LibraryDialog
      eyebrow={t("library.rename.eyebrow")}
      title={t("library.rename.title", { name: file.file_name })}
      description={t("library.rename.description")}
      onClose={onClose}
      dismissible={!pending}
      className="library-rename"
    >
      <div className="library-confirm__path">
        <span className="eyebrow">{t("library.rename.folder")}</span>
        <code>{folder}</code>
      </div>

      <form className="library-form" onSubmit={handleSubmit}>
        <div className="library-field">
          <label className="library-field__label" htmlFor={nameId}>
            {t("library.rename.fileName")}
          </label>
          <span className="library-rename__name">
            <input
              id={nameId}
              className="library-input"
              type="text"
              value={stem}
              onChange={(event) => {
                setStem(event.target.value);
                renameMutation.reset();
              }}
              autoComplete="off"
              spellCheck={false}
              disabled={pending}
              aria-invalid={invalid || undefined}
              aria-describedby={
                invalid ? `${errorId} ${previewId}` : previewId
              }
              data-autofocus
            />
            {extension ? (
              <span className="library-rename__extension">{extension}</span>
            ) : null}
          </span>
          <span id={previewId} className="library-field__hint">
            <code>{fullName || "—"}</code>
          </span>
        </div>

        {invalid ? (
          <p id={errorId} className="library-form__error" role="alert">
            <Icon name="info" size={15} />
            <span>{t("library.rename.errorName")}</span>
          </p>
        ) : null}
        {serverError ? (
          <p className="library-form__error" role="alert">
            <Icon name="info" size={15} />
            <span>{serverError}</span>
          </p>
        ) : null}

        <div className="library-form__actions">
          <Button variant="ghost" size="sm" onClick={onClose} disabled={pending}>
            {t("library.rename.cancel")}
          </Button>
          <Button
            type="submit"
            variant="primary"
            size="sm"
            disabled={pending || invalid || unchanged}
          >
            {pending ? t("library.rename.pending") : t("library.rename.submit")}
            <Icon name="pencil" size={15} />
          </Button>
        </div>
      </form>
    </LibraryDialog>
  );
}
