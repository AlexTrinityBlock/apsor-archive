import type { PathFileSchema, PathListingSchema } from "../../generated-apis-types/schemas";
import { formatBytes, formatDateTime } from "../../../lib/format";
import { Badge } from "../../component/Badge";
import { Button } from "../../component/Button";
import { Icon } from "../../component/Icon";
import { fileKindLabel, type FileOperationMode } from "./library-utils";

interface LibraryResultsProps {
  readonly listing: PathListingSchema;
  readonly query: string;
  readonly selecting: boolean;
  readonly selectedFileIds: ReadonlySet<number>;
  readonly onToggleSelected: (fileId: number) => void;
  readonly onOpenFolder: (path: string) => void;
  readonly onOpenFile: (fileId: number) => void;
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
  onRequestMove,
  onRequestDelete,
}: LibraryResultsProps) {
  const folders = query ? [] : listing.directories;

  return (
    <div className="library-table-wrap">
      <table className="library-table">
        <thead>
          <tr>
            {selecting ? (
              <th scope="col" className="library-table__select-head">
                <span className="visually-hidden">Select</span>
              </th>
            ) : null}
            <th scope="col">Name</th>
            <th scope="col" className="library-table__optional">Type</th>
            <th scope="col" className="library-table__optional">Chunks</th>
            <th scope="col">Size</th>
            <th scope="col" className="library-table__optional">Modified</th>
            <th scope="col">Actions</th>
          </tr>
        </thead>
        <tbody>
          {folders.map((folder) => (
            <tr
              className="library-row library-row--folder"
              key={folder.path}
              onClick={() => onOpenFolder(folder.path)}
            >
              {selecting ? <td className="library-table__select" aria-hidden="true" /> : null}
              <td data-label="Name">
                <button
                  type="button"
                  className="library-row__open"
                  onClick={(event) => {
                    event.stopPropagation();
                    onOpenFolder(folder.path);
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
              <td data-label="Type" className="library-table__optional">
                <Badge tone="neutral">Folder</Badge>
              </td>
              <td data-label="Chunks" className="library-table__optional">
                <span className="library-row__empty">—</span>
              </td>
              <td data-label="Size">
                <span className="library-row__empty">—</span>
              </td>
              <td data-label="Modified" className="library-table__optional">
                <span className="library-row__empty">—</span>
              </td>
              <td data-label="Actions">
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
            >
              {selecting ? (
                <td className="library-table__select" data-label="Select">
                  <label
                    className="library-checkbox"
                    onClick={(event) => event.stopPropagation()}
                  >
                    <input
                      type="checkbox"
                      checked={selectedFileIds.has(file.file_id)}
                      onChange={() => onToggleSelected(file.file_id)}
                      aria-label={`Select ${file.file_name}`}
                    />
                    <span className="library-checkbox__box" aria-hidden="true">
                      <Icon name="check" size={12} />
                    </span>
                  </label>
                </td>
              ) : null}
              <td data-label="Name">
                <button
                  type="button"
                  className="library-row__open"
                  onClick={(event) => {
                    event.stopPropagation();
                    onOpenFile(file.file_id);
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
              <td data-label="Type" className="library-table__optional">
                <span className="file-type-pill">{fileKindLabel(file.raw_file_path)}</span>
              </td>
              <td data-label="Chunks" className="library-table__optional">
                <span className="library-row__mono">{file.total_chunks}</span>
              </td>
              <td data-label="Size">
                <span className="library-row__mono">{formatBytes(file.size_bytes)}</span>
              </td>
              <td data-label="Modified" className="library-table__optional">
                <time className="library-row__time" dateTime={file.update_time}>
                  {formatDateTime(file.update_time)}
                </time>
              </td>
              <td data-label="Actions">
                <div
                  className="library-row__actions"
                  onClick={(event) => event.stopPropagation()}
                >
                  <Button
                    variant="ghost"
                    size="sm"
                    iconOnly
                    aria-label={`Move ${file.file_name}`}
                    title="Move to…"
                    onClick={() => onRequestMove(file, "move")}
                  >
                    <Icon name="branch" size={15} />
                  </Button>
                  <Button
                    variant="ghost"
                    size="sm"
                    iconOnly
                    aria-label={`Copy ${file.file_name}`}
                    title="Copy to…"
                    onClick={() => onRequestMove(file, "copy")}
                  >
                    <Icon name="copy" size={15} />
                  </Button>
                  <Button
                    variant="ghost"
                    size="sm"
                    iconOnly
                    className="library-row__delete"
                    aria-label={`Delete ${file.file_name}`}
                    title="Delete file"
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
