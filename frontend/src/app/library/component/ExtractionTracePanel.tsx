import { useId, type ReactNode } from "react";

import { Button } from "../../component/Button";
import { CopyButton } from "../../component/CopyButton";
import { Icon } from "../../component/Icon";
import { useI18n, type TranslationKey } from "../../i18n";
import type { FileSchema } from "../../generated-apis-types/schemas";
import {
  reingestBlockReason,
  reingestVisionMode,
  shortFingerprint,
  type ReingestBlockReason,
} from "./library-utils";

const BLOCK_REASON_KEYS: Record<ReingestBlockReason, TranslationKey> = {
  deleted: "library.extraction.reasons.deleted",
  historical: "library.extraction.reasons.historical",
  noOriginal: "library.extraction.reasons.noOriginal",
  unsupported: "library.extraction.reasons.unsupported",
  active: "library.extraction.reasons.active",
};

interface ExtractionTracePanelProps {
  readonly file: FileSchema;
  readonly reingestActive: boolean;
  readonly onReingest: (file: FileSchema) => void;
}

/**
 * The Metadata tab's extraction trace. It shows what produced the indexed text,
 * which prompt fingerprint was recorded, and whether a re-ingest can create a
 * new version from the stored original. Legacy rows stay readable without a
 * synthetic fingerprint.
 */
export function ExtractionTracePanel({
  file,
  reingestActive,
  onReingest,
}: ExtractionTracePanelProps) {
  const { t } = useI18n();
  const titleId = useId();
  const visionMode = reingestVisionMode(file);
  const fingerprint = file.vision_prompt_sha256;
  const blockReason = reingestBlockReason(file, reingestActive);

  let provenance: ReactNode;
  if (fingerprint) {
    provenance = (
      <details className="library-extraction__technical">
        <summary>{t("library.extraction.technical")}</summary>
        <div className="library-extraction__hash">
          <code>{fingerprint}</code>
          <CopyButton
            value={fingerprint}
            label={t("library.extraction.copyFingerprint")}
            title={t("library.extraction.fullFingerprint")}
            iconOnly
          />
        </div>
      </details>
    );
  } else if (visionMode !== null) {
    provenance = (
      <div className="library-extraction__legacy" role="note">
        <Icon name="history" size={15} />
        <div>
          <strong>{t("library.extraction.legacy")}</strong>
          <p>{t("library.extraction.legacyHint")}</p>
        </div>
      </div>
    );
  } else {
    provenance = (
      <p className="library-extraction__not-applicable" role="note">
        <Icon name="info" size={15} />
        <span>{t("library.extraction.notApplicable")}</span>
      </p>
    );
  }

  return (
    <section className="library-extraction" aria-labelledby={titleId}>
      <header className="library-extraction__head">
        <div>
          <p className="eyebrow">{t("library.extraction.eyebrow")}</p>
          <h3 id={titleId}>{t("library.extraction.title")}</h3>
        </div>
        <ExtractionModeBadge mode={file.vision_prompt_mode} />
      </header>
      <p className="library-extraction__lede">
        {t("library.extraction.description")}
      </p>

      <dl className="library-extraction__facts">
        <div className="library-extraction__fact">
          <dt>{t("library.extraction.method")}</dt>
          <dd>
            <code>{file.extraction_method || t("library.extraction.noValue")}</code>
          </dd>
        </div>
        <div className="library-extraction__fact">
          <dt>{t("library.extraction.promptMode")}</dt>
          <dd>
            {file.vision_prompt_mode ? (
              <code>{file.vision_prompt_mode}</code>
            ) : (
              t("library.extraction.noValue")
            )}
          </dd>
        </div>
        <div className="library-extraction__fact">
          <dt>{t("library.extraction.descriptionLanguage")}</dt>
          <dd>{file.vision_description_language || t("library.extraction.noValue")}</dd>
        </div>
        <div className="library-extraction__fact">
          <dt>{t("library.extraction.promptFingerprint")}</dt>
          <dd>
            {fingerprint ? (
              <code title={fingerprint}>{shortFingerprint(fingerprint)}</code>
            ) : (
              t("library.extraction.noValue")
            )}
          </dd>
        </div>
      </dl>

      {provenance}

      <div className="library-extraction__action">
        <Button
          type="button"
          variant="secondary"
          size="sm"
          disabled={blockReason !== null}
          aria-label={t("library.extraction.reingestAria", {
            name: file.file_name,
          })}
          onClick={() => onReingest(file)}
        >
          <Icon name="history" size={14} />
          {t("library.extraction.reingest")}
        </Button>
        {blockReason ? (
          <p className="library-extraction__reason" role="note">
            {t(BLOCK_REASON_KEYS[blockReason])}
          </p>
        ) : null}
      </div>
    </section>
  );
}

function ExtractionModeBadge({
  mode,
}: {
  readonly mode: string | null;
}) {
  const { t } = useI18n();
  if (!mode) {
    return null;
  }
  return (
    <span
      className="library-extraction__mode"
      aria-label={t("library.extraction.modeAria", { mode })}
    >
      <Icon name="spark" size={13} />
      <code>{mode}</code>
    </span>
  );
}
