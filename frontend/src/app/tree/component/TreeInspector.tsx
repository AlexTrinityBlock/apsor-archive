import { useGetFile } from "../../generated-apis-types/files/files";
import {
  formatBytes,
  formatDateTime,
  formatNumber,
} from "../../../lib/format";
import { Badge } from "../../component/Badge";
import { Button, ButtonLink } from "../../component/Button";
import { Icon } from "../../component/Icon";
import { Loader } from "../../component/Loader";
import { Panel } from "../../component/Panel";
import type { TreeLayoutNode } from "../treeLayout";

interface TreeInspectorProps {
  readonly node: TreeLayoutNode | null;
  readonly onClose: () => void;
}

function numberLabel(value: number | null): string {
  return value === null ? "—" : `#${value}`;
}

function dateLabel(value: string | null): string {
  return value === null || value.length === 0 ? "—" : formatDateTime(value);
}

/**
 * The selected-node dossier. File records are fetched only when the selected
 * node carries a file id, and the Open in library link carries the chunk state.
 */
export function TreeInspector({ node, onClose }: TreeInspectorProps) {
  const fileId = node?.node.file_id ?? null;
  const fileQuery = useGetFile(fileId ?? 0, {
    query: { enabled: fileId !== null },
  });

  if (!node) {
    return (
      <aside className="tree-inspector" aria-label="Node inspector">
        <Panel
          className="tree-inspector__panel"
          eyebrow="Node inspector"
          title="Nothing selected"
        >
          <div className="tree-inspector__empty">
            <p>
              Choose any card on the canvas to read its path, lineage, and linked
              file record.
            </p>
            <ul className="tree-inspector__empty-list">
              <li>
                <Icon name="folder" size={16} />
                Folders keep the archive's path ledger.
              </li>
              <li>
                <Icon name="file" size={16} />
                Files carry version, chunk, and size metadata.
              </li>
              <li>
                <Icon name="history" size={16} />
                Retained branches explain what they were superseded by.
              </li>
            </ul>
          </div>
        </Panel>
      </aside>
    );
  }

  const { node: treeNode, isHistory, isVirtual } = node;
  const stateLabel = isHistory ? "history" : "current";
  const superseded = numberLabel(treeNode.superseded_by_id);
  const file = fileQuery.data;
  const filePending = fileId !== null && fileQuery.isPending;
  const fileError = fileId !== null && fileQuery.isError;

  return (
    <aside className="tree-inspector" aria-label="Node inspector">
      <Panel
        className="tree-inspector__panel"
        eyebrow="Node inspector"
        title={treeNode.name || treeNode.path}
        action={
          <Button
            variant="ghost"
            size="sm"
            iconOnly
            aria-label="Close node inspector"
            onClick={onClose}
          >
            <Icon name="close" size={15} />
          </Button>
        }
      >
        <div className="tree-inspector__badges">
          <Badge tone={treeNode.kind === "folder" ? "moss" : "ochre"}>
            {treeNode.kind}
          </Badge>
          <Badge tone={isHistory ? "ochre" : "moss"} dot>
            {stateLabel}
          </Badge>
          {isVirtual ? <Badge tone="neutral">virtual root</Badge> : null}
        </div>

        <div className="tree-inspector__path">
          <span className="eyebrow">Path</span>
          <code>{treeNode.path}</code>
        </div>

        <dl className="tree-inspector__facts">
          <div>
            <dt>Node id</dt>
            <dd>{isVirtual ? "virtual" : `#${treeNode.id}`}</dd>
          </div>
          <div>
            <dt>Depth</dt>
            <dd>{treeNode.depth}</dd>
          </div>
          <div>
            <dt>State</dt>
            <dd>{stateLabel}</dd>
          </div>
          <div>
            <dt>Superseded by</dt>
            <dd>{superseded}</dd>
          </div>
          <div>
            <dt>Deleted at</dt>
            <dd>{dateLabel(treeNode.deleted_at)}</dd>
          </div>
          <div>
            <dt>Update time</dt>
            <dd>{dateLabel(treeNode.update_time)}</dd>
          </div>
          <div>
            <dt>File id</dt>
            <dd>{numberLabel(treeNode.file_id)}</dd>
          </div>
          <div>
            <dt>Canvas depth</dt>
            <dd>{node.depth}</dd>
          </div>
        </dl>

        {isHistory ? (
          <div className="tree-inspector__note">
            <Icon name="history" size={17} />
            <div>
              <p className="eyebrow">Retained branch</p>
              <p>
                This node is not current. It stays visible only while history is
                included and is excluded from current-only views and search.
                {treeNode.superseded_by_id !== null
                  ? ` The current branch supersedes it as node #${treeNode.superseded_by_id}.`
                  : ""}
                {treeNode.deleted_at !== null
                  ? ` Its leaf was soft-deleted on ${formatDateTime(treeNode.deleted_at)}.`
                  : ""}
              </p>
            </div>
          </div>
        ) : null}

        <section className="tree-inspector__file" aria-label="Linked file">
          <div className="tree-inspector__file-head">
            <p className="eyebrow">Linked file</p>
            {fileQuery.isFetching && !filePending ? (
              <Loader size={18} label="Refreshing file record" />
            ) : null}
          </div>

          {fileId === null ? (
            <p className="tree-inspector__file-note">
              No file record is linked to this node.
            </p>
          ) : null}

          {filePending ? (
            <div className="tree-inspector__file-loading">
              <Loader size={22} label="Reading file record" />
              <span>Reading file record</span>
            </div>
          ) : null}

          {fileError ? (
            <p className="tree-inspector__file-note is-error">
              The linked file record could not be read.
            </p>
          ) : null}

          {file ? (
            <>
              <dl className="tree-inspector__facts tree-inspector__facts--file">
                <div>
                  <dt>Version</dt>
                  <dd>v{file.version}</dd>
                </div>
                <div>
                  <dt>Chunks</dt>
                  <dd>{formatNumber(file.total_chunks)}</dd>
                </div>
                <div>
                  <dt>Size</dt>
                  <dd>{formatBytes(file.size_bytes)}</dd>
                </div>
                <div>
                  <dt>Extension</dt>
                  <dd>{file.extension || "—"}</dd>
                </div>
              </dl>
              <p className="tree-inspector__file-path">{file.raw_file_path}</p>
            </>
          ) : null}

          {fileId !== null ? (
            <ButtonLink
              to={`/library?file=${fileId}&chunk=1`}
              variant="secondary"
              size="sm"
              block
            >
              Open in library
              <Icon name="arrow-right" size={15} />
            </ButtonLink>
          ) : null}
        </section>
      </Panel>
    </aside>
  );
}
