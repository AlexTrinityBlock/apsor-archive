import type {
  DirectorySchema,
  PathFileSchema,
  PathListingSchema,
} from "../../generated-apis-types/schemas";
import { formatBytes } from "../../../lib/format";
import { Badge } from "../../component/Badge";
import { Button } from "../../component/Button";
import { Icon } from "../../component/Icon";
import { useI18n } from "../../i18n";
import {
  contextMenuTriggerFromKeyboard,
  fileKindLabel,
  isContextMenuKey,
  type FileOperationMode,
  type LibraryContextMenuTrigger,
} from "./library-utils";

interface LibraryResultsProps {
  readonly listing: PathListingSchema;
  readonly query: string;
  readonly selecting: boolean;
  readonly selectedFileIds: ReadonlySet<number>;
  readonly onToggleSelected: (fileId: number) => void;
  readonly onOpenFolder: (path: string) => void;
  readonly onOpenFile: (fileId: number) => void;
  readonly onFileContextMenu: (
    event: LibraryContextMenuTrigger,
    file: PathFileSchema,
  ) => void;
  readonly onFolderContextMenu: (
    event: LibraryContextMenuTrigger,
    folder: DirectorySchema,
  ) => void;
  readonly onRequestMove: (file: PathFileSchema, mode: FileOperationMode) => void;
  readonly onRequestDelete: (file: PathFileSchema) => void;
}

/** The dense list presentation of the same folder shelf. */
export function LibraryResults({
  listing,
  query,
  selecting,
  selectedFileIds,
  onToggleSelected,
  onOpenFolder,
  onOpenFile,
  onFileContextMenu,
  onFolderContextMenu,
  onRequestMove,
  onRequestDelete,
}: LibraryResultsProps) {
  const { t, formatDateTime, formatNumber } = useI18n();
  const folders = query ? [] : listing.directories;

  return (
    <div className="library-table-wrap">
      <table className="library-table">
        <thead>
          <tr>
            {selecting ? (
              <th scope="col" className="library-table__select-head">
                <span className="visually-hidden">{t("library.list.select")}</span>
              </th>
            ) : null}
            <th scope="col">{t("library.list.name")}</th>
            <th scope="col" className="library-table__optional">
              {t("library.list.type")}
            </th>
            <th scope="col" className="library-table__optional">
              {t("library.list.chunks")}
            </th>
            <th scope="col">{t("library.list.size")}</th>
            <th scope="col" className="library-table__optional">
              {t("library.list.modified")}
            </th>
            <th scope="col">{t("library.list.actions")}</th>
          </tr>
        </thead>
        <tbody>
          {folders.map((folder) => (
            <tr
              className="library-row library-row--folder"
              key={folder.path}
              onClick={() => onOpenFolder(folder.path)}
              onContextMenu={(event) => onFolderContextMenu(event, folder)}
              tabIndex={-1}
            >
              {selecting ? <td className="library-table__select" aria-hidden="true" /> : null}
              <td data-label={t("library.list.name")}>
                <button
                  type="button"
                  className="library-row__open"
                  onClick={(event) => {
                    event.stopPropagation();
                    onOpenFolder(folder.path);
                  }}
                  onKeyDown={(event) => {
                    if (!isContextMenuKey(event)) {
                      return;
                    }
                    event.preventDefault();
                    event.stopPropagation();
                    onFolderContextMenu(
                      contextMenuTriggerFromKeyboard(event.currentTarget),
                      folder,
                    );
                  }}
                >
                  <span className="library-row__icon library-row__icon--folder" aria-hidden="true">
                    <Icon name="folder" size={18} />
                  </span>
                  <span className="library-row__text">
                    <span className="library-row__label">{folder.name}</span>
                    <span className="library-row__hint">{folder.path}</span>
                  </span>
                  <Icon name="chevron-right" size={14} className="library-row__chevron" />
                </button>
              </td>
              <td data-label={t("library.list.type")} className="library-table__optional">
                <Badge tone="neutral">{t("library.list.folder")}</Badge>
              </td>
              <td data-label={t("library.list.chunks")} className="library-table__optional">
                <span className="library-row__empty">—</span>
              </td>
              <td data-label={t("library.list.size")}>
                <span className="library-row__empty">—</span>
              </td>
              <td data-label={t("library.list.modified")} className="library-table__optional">
                <span className="library-row__empty">—</span>
              </td>
              <td data-label={t("library.list.actions")}>
                <span className="library-row__empty">—</span>
              </td>
            </tr>
          ))}

          {listing.files.map((file) => (
            <tr
              className={
                selectedFileIds.has(file.file_id)
                  ? "library-row library-row--file is-selected"
                  : "library-row library-row--file"
              }
              key={file.file_id}
              onClick={() => onOpenFile(file.file_id)}
              onContextMenu={(event) => onFileContextMenu(event, file)}
              tabIndex={-1}
            >
              {selecting ? (
                <td className="library-table__select" data-label={t("library.list.select")}>
                  <label
                    className="library-checkbox"
                    onClick={(event) => event.stopPropagation()}
                  >
                    <input
                      type="checkbox"
                      checked={selectedFileIds.has(file.file_id)}
                      onChange={() => onToggleSelected(file.file_id)}
                      aria-label={t("library.a11y.selectFile", { name: file.file_name })}
                    />
                    <span className="library-checkbox__box" aria-hidden="true">
                      <Icon name="check" size={12} />
                    </span>
                  </label>
                </td>
              ) : null}
              <td data-label={t("library.list.name")}>
                <button
                  type="button"
                  className="library-row__open"
                  onClick={(event) => {
                    event.stopPropagation();
                    onOpenFile(file.file_id);
                  }}
                  onKeyDown={(event) => {
                    if (!isContextMenuKey(event)) {
                      return;
                    }
                    event.preventDefault();
                    event.stopPropagation();
                    onFileContextMenu(
                      contextMenuTriggerFromKeyboard(event.currentTarget),
                      file,
                    );
                  }}
                >
                  <span className="library-row__icon library-row__icon--file" aria-hidden="true">
                    <Icon name="file" size={17} />
                  </span>
                  <span className="library-row__text">
                    <span className="library-row__label">{file.file_name}</span>
                    <span className="library-row__hint">{file.raw_file_path}</span>
                  </span>
                </button>
              </td>
              <td data-label={t("library.list.type")} className="library-table__optional">
                <span className="file-type-pill">{fileKindLabel(file.raw_file_path)}</span>
              </td>
              <td data-label={t("library.list.chunks")} className="library-table__optional">
                <span className="library-row__mono">{formatNumber(file.total_chunks)}</span>
              </td>
              <td data-label={t("library.list.size")}>
                <span className="library-row__mono">{formatBytes(file.size_bytes)}</span>
              </td>
              <td data-label={t("library.list.modified")} className="library-table__optional">
                <time className="library-row__time" dateTime={file.update_time}>
                  {formatDateTime(file.update_time)}
                </time>
              </td>
              <td data-label={t("library.list.actions")}>
                <div
                  className="library-row__actions"
                  onClick={(event) => event.stopPropagation()}
                >
                  <Button
                    variant="ghost"
                    size="sm"
                    iconOnly
                    aria-label={t("library.a11y.moveFile", { name: file.file_name })}
                    title={t("library.board.moveTo")}
                    onClick={() => onRequestMove(file, "move")}
                  >
                    <Icon name="branch" size={15} />
                  </Button>
                  <Button
                    variant="ghost"
                    size="sm"
                    iconOnly
                    aria-label={t("library.a11y.copyFile", { name: file.file_name })}
                    title={t("library.board.copyTo")}
                    onClick={() => onRequestMove(file, "copy")}
                  >
                    <Icon name="copy" size={15} />
                  </Button>
                  <Button
                    variant="ghost"
                    size="sm"
                    iconOnly
                    className="library-row__delete"
                    aria-label={t("library.a11y.deleteFile", { name: file.file_name })}
                    title={t("library.board.deleteFile")}
                    onClick={() => onRequestDelete(file)}
                  >
                    <Icon name="trash" size={15} />
                  </Button>
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
