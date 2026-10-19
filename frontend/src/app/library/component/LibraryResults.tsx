import type { PathListingSchema } from "../../generated-apis-types/schemas";
import { formatBytes, formatDateTime } from "../../../lib/format";
import { Badge } from "../../component/Badge";
import { Button } from "../../component/Button";
import { EmptyState } from "../../component/EmptyState";
import { Icon } from "../../component/Icon";
import { Panel } from "../../component/Panel";
import { fileKindLabel } from "./library-utils";

interface LibraryResultsProps {
  readonly listing: PathListingSchema;
  readonly query: string;
  readonly seeding: boolean;
  readonly selecting: boolean;
  readonly selectedFileIds: ReadonlySet<number>;
  readonly onToggleSelected: (fileId: number) => void;
  readonly onOpenFolder: (path: string) => void;
  readonly onOpenFile: (fileId: number, rawPath: string) => void;
  readonly onUpload: () => void;
  readonly onClearSearch: () => void;
  readonly onSeed: () => void;
}

interface LibraryTableProps {
  readonly listing: PathListingSchema;
  readonly query: string;
  readonly selecting: boolean;
  readonly selectedFileIds: ReadonlySet<number>;
  readonly onToggleSelected: (fileId: number) => void;
  readonly onOpenFolder: (path: string) => void;
  readonly onOpenFile: (fileId: number, rawPath: string) => void;
}

function LibraryTable({
  listing,
  query,
  selecting,
  selectedFileIds,
  onToggleSelected,
  onOpenFolder,
  onOpenFile,
}: LibraryTableProps) {
  const folderCount = query ? 0 : listing.directories.length;
  const entryCount = folderCount + listing.files.length;

  return (
    <Panel
      tone="paper"
      padded={false}
      className="library-shelf reveal reveal-3"
      eyebrow={query ? "Fuzzy path matches" : "Current shelf"}
      title={query ? "Matching leaves" : "Directory contents"}
      action={
        <Badge tone={query ? "ochre" : "moss"}>
          {entryCount} {entryCount === 1 ? "entry" : "entries"}
        </Badge>
      }
    >
      <div className="library-table-wrap">
        <table className="library-table">
          <thead>
            <tr>
              {selecting ? (
                <th scope="col" className="library-row__select-head">
                  <span className="visually-hidden">Select</span>
                </th>
              ) : null}
              <th scope="col">Name</th>
              <th scope="col">Kind</th>
              <th scope="col">Chunks</th>
              <th scope="col">Size</th>
              <th scope="col">Updated</th>
              <th scope="col">State</th>
            </tr>
          </thead>
          <tbody>
            {listing.directories.map((folder) => (
              <tr className="library-row library-row--folder" key={folder.path}>
                {selecting ? <td className="library-row__select" aria-hidden="true" /> : null}
                <td className="library-row__name" data-label="Name">
                  <button
                    type="button"
                    className="library-row__open"
                    onClick={() => onOpenFolder(folder.path)}
                  >
                    <span className="visually-hidden">Open folder </span>
                    <span className="library-row__icon library-row__icon--folder" aria-hidden="true">
                      <Icon name="folder" size={18} />
                    </span>
                    <span className="library-row__text">
                      <span className="library-row__label">{folder.name}</span>
                      <span className="library-row__hint">
                        Depth {folder.depth} · browse children
                      </span>
                    </span>
                    <Icon name="chevron-right" size={14} className="library-row__chevron" />
                  </button>
                </td>
                <td data-label="Kind">
                  <span className="library-row__mono">folder</span>
                </td>
                <td data-label="Chunks">
                  <span className="library-row__empty">—</span>
                </td>
                <td data-label="Size">
                  <span className="library-row__empty">—</span>
                </td>
                <td data-label="Updated">
                  <span className="library-row__empty">—</span>
                </td>
                <td data-label="State">
                  <Badge tone="neutral">Branch</Badge>
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
              >
                {selecting ? (
                  <td className="library-row__select" data-label="Select">
                    <label className="library-checkbox">
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
                <td className="library-row__name" data-label="Name">
                  <button
                    type="button"
                    className="library-row__open"
                    onClick={() => onOpenFile(file.file_id, file.raw_file_path)}
                  >
                    <span className="visually-hidden">Read file </span>
                    <span className="library-row__icon library-row__icon--file" aria-hidden="true">
                      <Icon name="file" size={17} />
                    </span>
                    <span className="library-row__text">
                      <span className="library-row__label">{file.file_name}</span>
                      <span className="library-row__hint">{file.raw_file_path}</span>
                    </span>
                  </button>
                </td>
                <td data-label="Kind">
                  <span className="library-row__mono">{fileKindLabel(file.raw_file_path)}</span>
                </td>
                <td data-label="Chunks">
                  <span className="library-row__mono">{file.total_chunks}</span>
                </td>
                <td data-label="Size">
                  <span className="library-row__mono">{formatBytes(file.size_bytes)}</span>
                </td>
                <td data-label="Updated">
                  <time className="library-row__time" dateTime={file.update_time}>
                    {formatDateTime(file.update_time)}
                  </time>
                </td>
                <td data-label="State">
                  <Badge tone="moss" dot>
                    Current
                  </Badge>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Panel>
  );
}

function EmptyLibrary({ seeding, onUpload, onSeed }: Pick<LibraryResultsProps, "seeding" | "onUpload" | "onSeed">) {
  return (
    <EmptyState
      icon="library"
      eyebrow="First run · empty archive"
      title="The shelf is ready for its first leaf."
      description="Upload a file or write a text note. DendroMatrix creates the path, splits the text into chunks, and keeps later versions on their own branch."
      endpoint="/api/v1/paths?path=/&path_depth=1"
      method="GET"
      className="reveal reveal-3"
      action={
        <div className="empty-state__actions">
          <Button variant="ink" size="sm" onClick={onSeed} disabled={seeding} aria-busy={seeding}>
            {seeding ? "Seeding demo archive…" : "Seed demo archive"}
            {seeding ? null : <Icon name="spark" size={15} />}
          </Button>
          <Button variant="secondary" size="sm" onClick={onUpload}>
            <Icon name="plus" size={15} />
            Upload a file
          </Button>
        </div>
      }
    />
  );
}

function EmptyFolder({
  path,
  onUpload,
  onOpenFolder,
}: Pick<LibraryResultsProps, "onUpload" | "onOpenFolder"> & { readonly path: string }) {
  return (
    <EmptyState
      icon="folder"
      eyebrow="Empty directory"
      title="No leaves in this folder yet."
      description="Upload a file into this path, or write a text note. Parent folders are created automatically and versions branch beside the current leaf."
      endpoint="/api/v1/files"
      method="POST"
      className="reveal reveal-3"
      aside={<code className="library-empty__path">{path}</code>}
      action={
        <div className="empty-state__actions">
          <Button variant="ink" size="sm" onClick={onUpload}>
            <Icon name="plus" size={15} />
            Upload a file
          </Button>
          <Button variant="ghost" size="sm" onClick={() => onOpenFolder("/")}>
            Back to archive root
          </Button>
        </div>
      }
    />
  );
}

function NoMatches({
  listing,
  query,
  onClearSearch,
}: Pick<LibraryResultsProps, "listing" | "query" | "onClearSearch">) {
  return (
    <EmptyState
      icon="search"
      eyebrow="Fuzzy path search"
      title={`No paths match “${query}”.`}
      description="Try fewer characters or another fragment of the path. Search is scoped to the folder shown in the breadcrumb."
      endpoint={`/api/v1/paths?path=${encodeURIComponent(listing.path)}&fuzzy_search=${encodeURIComponent(query)}`}
      method="GET"
      className="reveal reveal-3"
      action={
        <Button variant="secondary" size="sm" onClick={onClearSearch}>
          Clear search
        </Button>
      }
    />
  );
}

/** Chooses the right shelf state: listing, first-run, empty folder, or no match. */
export function LibraryResults({
  listing,
  query,
  seeding,
  selecting,
  selectedFileIds,
  onToggleSelected,
  onOpenFolder,
  onOpenFile,
  onUpload,
  onClearSearch,
  onSeed,
}: LibraryResultsProps) {
  if (query) {
    if (listing.files.length === 0) {
      return <NoMatches listing={listing} query={query} onClearSearch={onClearSearch} />;
    }
    return (
      <LibraryTable
        listing={listing}
        query={query}
        selecting={selecting}
        selectedFileIds={selectedFileIds}
        onToggleSelected={onToggleSelected}
        onOpenFolder={onOpenFolder}
        onOpenFile={onOpenFile}
      />
    );
  }

  if (listing.directories.length === 0 && listing.files.length === 0) {
    if (listing.path === "/") {
      return <EmptyLibrary seeding={seeding} onUpload={onUpload} onSeed={onSeed} />;
    }
    return <EmptyFolder path={listing.path} onUpload={onUpload} onOpenFolder={onOpenFolder} />;
  }

  return (
    <LibraryTable
      listing={listing}
      query={query}
      selecting={selecting}
      selectedFileIds={selectedFileIds}
      onToggleSelected={onToggleSelected}
      onOpenFolder={onOpenFolder}
      onOpenFile={onOpenFile}
    />
  );
}
