import { Link } from "react-router-dom";

import { Icon } from "../../../component/Icon";
import { basename, formatBytes, formatNumber } from "../../../../lib/format";
import {
  excerptOf,
  numberField,
  recordId,
  recordList,
  safeResourceUrl,
  textField,
} from "../../trace";
import { LivePanel, PanelEmpty, type PanelProps } from "./common";

function FolderBranch({
  name,
  path,
  depth,
}: {
  readonly name: string;
  readonly path: string;
  readonly depth: number | null;
}) {
  return (
    <li className="pi-branch__folder" style={{ paddingLeft: `${(depth ?? 0) * 12}px` }}>
      <span className="pi-branch__icon" aria-hidden="true">
        <Icon name="folder" size={13} />
      </span>
      <span className="pi-branch__name">{name}</span>
      <code>{path}</code>
    </li>
  );
}

function FileCard({ record }: { readonly record: Record<string, unknown> }) {
  const id = recordId(record, "file_id");
  const path = textField(record, "raw_file_path") ?? textField(record, "path") ?? "";
  const chunks = numberField(record, "total_chunks");
  const size = numberField(record, "size_bytes");
  const href = safeResourceUrl(
    record.viewer_url,
    id === null
      ? null
      : { type: "file", id, chunk: null, title: basename(path) },
  );
  const excerpt = excerptOf(record, ["excerpt"], 180);

  return (
    <li className="pi-branch__file">
      <span className="pi-branch__file-mark" aria-hidden="true">
        <Icon name="file" size={14} />
      </span>
      <div className="pi-branch__file-body">
        <strong>{textField(record, "file_name") ?? (basename(path) || `File ${id ?? "?"}`)}</strong>
        <code>{path || "path unrecorded"}</code>
        {excerpt ? <p>{excerpt}</p> : null}
        <div className="pi-branch__file-meta">
          {chunks !== null ? <span>{formatNumber(chunks)} chunks</span> : null}
          {size !== null ? <span>{formatBytes(size)}</span> : null}
        </div>
      </div>
      {href ? (
        <Link className="pi-branch__file-link" to={href} aria-label={`Open ${basename(path) || "file"}`}>
          <Icon name="arrow-up-right" size={13} />
        </Link>
      ) : null}
    </li>
  );
}

/** `read_path`: a folder branch map with file cards. */
export function ReadPathPanel({ item }: PanelProps) {
  if (item.live || item.status.toLowerCase() === "running") {
    return <LivePanel item={item} detail="Walking the requested folder branch." />;
  }
  if (item.status.toLowerCase() === "error") {
    return (
      <PanelEmpty
        icon="branch"
        title="The folder branch could not be read"
        detail={item.detail ?? "No structured result was recorded."}
      />
    );
  }

  const data = item.data;
  const directories = recordList(data?.directories);
  const files = recordList(data?.files);
  const path = textField(data, "path") ?? textField(item.arguments, "path") ?? "/";

  return (
    <div className="pi-branch">
      <header className="pi-branch__head">
        <div>
          <p className="eyebrow">Folder branch map</p>
          <code>{path}</code>
        </div>
        <span className="pi-branch__counts">
          {directories.length} folders · {files.length} files
        </span>
      </header>

      {textField(data, "fuzzy_search") ? (
        <p className="pi-branch__fuzzy">
          Fuzzy filter: “{textField(data, "fuzzy_search")}”
        </p>
      ) : null}

      <div className="pi-branch__map">
        <div className="pi-branch__trunk" aria-hidden="true" />
        <ul className="pi-branch__folders">
          <li className="pi-branch__root">
            <span aria-hidden="true">
              <Icon name="folder" size={14} />
            </span>
            <code>{path}</code>
          </li>
          {directories.map((directory) => (
            <FolderBranch
              key={textField(directory, "path") ?? textField(directory, "name") ?? "folder"}
              name={textField(directory, "name") ?? "folder"}
              path={textField(directory, "path") ?? ""}
              depth={numberField(directory, "depth")}
            />
          ))}
        </ul>
      </div>

      {files.length === 0 && directories.length === 0 ? (
        <PanelEmpty
          icon="branch"
          title="This branch is empty"
          detail="No folders or files were returned for the requested path."
        />
      ) : (
        <ul className="pi-branch__files">
          {files.map((file, index) => (
            <FileCard
              record={file}
              key={textField(file, "file_id") ?? textField(file, "raw_file_path") ?? index}
            />
          ))}
        </ul>
      )}
    </div>
  );
}
