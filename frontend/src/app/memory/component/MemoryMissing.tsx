import { Link } from "react-router-dom";

import { Badge } from "../../component/Badge";
import { ButtonLink } from "../../component/Button";
import { Icon } from "../../component/Icon";
import { PageHeader } from "../../component/PageHeader";

import { MemoryEmptyState } from "./MemoryStates";

interface MemoryMissingProps {
  readonly memoryId?: string;
  readonly invalid?: boolean;
}

/** Calm 404 and malformed-id state for the memory routes. */
export function MemoryMissing({ memoryId, invalid = false }: MemoryMissingProps) {
  return (
    <div className="content-container memory-page memory-missing-page">
      <nav className="memory-breadcrumb" aria-label="Breadcrumb">
        <Link to="/memory">Memory Vault</Link>
        <span aria-hidden="true">/</span>
        <span className="memory-breadcrumb__current" aria-current="page">
          Record not found
        </span>
      </nav>

      <PageHeader
        eyebrow="Memory · record not found"
        title="Memory not found."
        description={
          invalid
            ? "The route did not contain a numeric memory id. Memories are addressed by their stable integer id, not by a title."
            : `Memory ${memoryId ?? "on this route"} is not in the archive. It may have been removed, or the id may never have existed.`
        }
        meta={<Badge tone="vermilion">404</Badge>}
        actions={
          <ButtonLink to="/memory" variant="secondary" size="sm">
            <Icon name="arrow-right" size={15} className="memory-back-icon" />
            Back to vault
          </ButtonLink>
        }
      />

      <MemoryEmptyState
        icon="memory"
        eyebrow="No crystal at this address"
        title="This memory is not in the archive."
        description="Deprecated memories remain readable, so a missing record means it is genuinely absent rather than merely retired. Return to the vault to browse the surviving lineage."
        action={
          <>
            <ButtonLink to="/memory" variant="ink" size="sm">
              Browse the vault
              <Icon name="arrow-right" size={15} />
            </ButtonLink>
            <ButtonLink to="/memory/new" variant="ghost" size="sm">
              Press a new memory
            </ButtonLink>
          </>
        }
      />
    </div>
  );
}
