import { Badge } from "../../component/Badge";
import { ButtonLink } from "../../component/Button";
import { Icon } from "../../component/Icon";
import { PageHeader } from "../../component/PageHeader";
import { Panel } from "../../component/Panel";

interface MemoryMissingProps {
  readonly memoryId?: string;
  readonly invalid?: boolean;
}

/** Calm 404 and malformed-id state for the memory route. */
export function MemoryMissing({ memoryId, invalid = false }: MemoryMissingProps) {
  return (
    <div className="page memory-page">
      <PageHeader
        eyebrow="Memory · trace"
        title="Memory not found."
        description={
          invalid
            ? "The route did not contain a numeric memory id. Memories are addressed by their stable integer id, not by a title."
            : `Memory ${memoryId ?? "on this route"} is not in the archive. It may have been removed, or the id may never have existed.`
        }
        meta={<Badge tone="vermilion">404</Badge>}
        actions={
          <ButtonLink to="/timeline" variant="secondary" size="sm">
            <Icon name="arrow-right" size={15} className="memory-back-icon" />
            Back to timeline
          </ButtonLink>
        }
      />

      <Panel tone="plain" className="memory-missing reveal reveal-2">
        <div className="memory-missing__mark" aria-hidden="true">
          <Icon name="memory" size={28} />
        </div>
        <p className="eyebrow">No leaf at this address</p>
        <h2>This memory is not in the archive.</h2>
        <p className="memory-missing__copy">
          Deprecated memories remain readable, so a missing record means it is genuinely absent
          rather than merely replaced. The timeline and the neighbor links are the reliable way
          back to the surviving lineage.
        </p>
        <div className="memory-missing__actions">
          <ButtonLink to="/timeline" variant="ink" size="sm">
            Browse the timeline
            <Icon name="arrow-right" size={15} />
          </ButtonLink>
          <ButtonLink to="/memory/new" variant="ghost" size="sm">
            Press a new memory
          </ButtonLink>
        </div>
      </Panel>
    </div>
  );
}
