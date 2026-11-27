import { Link } from "react-router-dom";

import { Badge } from "../../../component/Badge";
import { ButtonLink } from "../../../component/Button";
import { Icon } from "../../../component/Icon";
import { PageHeader } from "../../../component/PageHeader";
import { useI18n } from "../../../i18n";

import { MemoryEmptyState } from "./MemoryStates";
import {
  libraryMemoriesUrl,
  libraryNewMemoryUrl,
} from "../../../../lib/library-url";

interface MemoryMissingProps {
  readonly memoryId?: string;
  readonly invalid?: boolean;
}

/** Calm 404 and malformed-id state for the memory routes. */
export function MemoryMissing({ memoryId, invalid = false }: MemoryMissingProps) {
  const { t } = useI18n();
  let description = t("memory.missing.missingDescriptionFallback");
  if (invalid) {
    description = t("memory.missing.invalidDescription");
  } else if (memoryId) {
    description = t("memory.missing.missingDescription", { id: memoryId });
  }

  return (
    <div className="content-container memory-page memory-missing-page">
      <nav className="memory-breadcrumb" aria-label={t("memory.common.breadcrumbAria")}>
        <Link to={libraryMemoriesUrl()}>{t("memory.vault.title")}</Link>
        <span aria-hidden="true">/</span>
        <span className="memory-breadcrumb__current" aria-current="page">
          {t("memory.missing.breadcrumbCurrent")}
        </span>
      </nav>

      <PageHeader
        headingLevel={2}
        eyebrow={t("memory.missing.eyebrow")}
        title={t("memory.missing.title")}
        description={description}
        meta={<Badge tone="vermilion">404</Badge>}
        actions={
          <ButtonLink to={libraryMemoriesUrl()} variant="secondary" size="sm">
            <Icon name="arrow-right" size={15} className="memory-back-icon" />
            {t("memory.missing.backToVault")}
          </ButtonLink>
        }
      />

      <MemoryEmptyState
        icon="memory"
        eyebrow={t("memory.missing.emptyEyebrow")}
        title={t("memory.missing.emptyTitle")}
        description={t("memory.missing.emptyDescription")}
        action={
          <>
            <ButtonLink to={libraryMemoriesUrl()} variant="ink" size="sm">
              {t("memory.missing.browseVault")}
              <Icon name="arrow-right" size={15} />
            </ButtonLink>
            <ButtonLink to={libraryNewMemoryUrl()} variant="ghost" size="sm">
              {t("memory.missing.pressNew")}
            </ButtonLink>
          </>
        }
      />
    </div>
  );
}
