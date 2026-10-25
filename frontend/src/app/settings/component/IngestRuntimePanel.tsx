import {
  useEffect,
  useRef,
  useState,
  type FormEvent,
} from "react";

import { useI18n, type Translate, type TranslationKey } from "../../i18n";
import { Badge } from "../../component/Badge";
import { Icon } from "../../component/Icon";
import { Panel } from "../../component/Panel";
import {
  RuntimeActions,
  RuntimeError,
  RuntimeGroup,
  RuntimeNumberField,
  RuntimeStatus,
  type RuntimeNumberSpec,
} from "./RuntimeControls";

/** The ingestion worker bounds applied to the next loop or job. */
export interface IngestRuntimeValues {
  readonly poll_seconds: number;
  readonly extract_workers: number;
  readonly max_inflight_jobs: number;
  readonly embedding_concurrency: number;
  readonly chunk_target_chars: number;
  readonly chunk_overlap_chars: number;
}

/** Props for the presentational panel; persistence stays with the page. */
export interface IngestRuntimePanelProps {
  readonly values: IngestRuntimeValues;
  readonly defaults: IngestRuntimeValues;
  readonly source: "database" | "default";
  readonly updatedAt: string | null;
  readonly saving: boolean;
  readonly error: string | null;
  readonly onSave: (values: IngestRuntimeValues) => void;
  readonly onReset: () => void;
  readonly className?: string;
}

type NumericField = keyof IngestRuntimeValues;
type DraftValues = { readonly [Key in NumericField]: string };

interface NumericFieldSpec
  extends Omit<RuntimeNumberSpec, "label" | "unit" | "hint"> {
  readonly key: NumericField;
  readonly labelKey: TranslationKey;
  readonly unitKey: TranslationKey;
  readonly hintKey: TranslationKey;
}

const WORKER_FIELDS: readonly NumericFieldSpec[] = [
  {
    key: "poll_seconds",
    labelKey: "settings.ingest.fieldPollSecondsLabel",
    unitKey: "settings.ingest.fieldPollSecondsUnit",
    min: 0.25,
    max: 30,
    step: 0.25,
    integer: false,
    hintKey: "settings.ingest.fieldPollSecondsHint",
  },
  {
    key: "extract_workers",
    labelKey: "settings.ingest.fieldExtractThreadsLabel",
    unitKey: "settings.ingest.fieldExtractThreadsUnit",
    min: 1,
    max: 8,
    step: 1,
    integer: true,
    hintKey: "settings.ingest.fieldExtractThreadsHint",
  },
  {
    key: "max_inflight_jobs",
    labelKey: "settings.ingest.fieldMaxInflightLabel",
    unitKey: "settings.ingest.fieldMaxInflightUnit",
    min: 1,
    max: 4,
    step: 1,
    integer: true,
    hintKey: "settings.ingest.fieldMaxInflightHint",
  },
  {
    key: "embedding_concurrency",
    labelKey: "settings.ingest.fieldEmbeddingConcurrencyLabel",
    unitKey: "settings.ingest.fieldEmbeddingConcurrencyUnit",
    min: 1,
    max: 32,
    step: 1,
    integer: true,
    hintKey: "settings.ingest.fieldEmbeddingConcurrencyHint",
  },
];

const CHUNK_FIELDS: readonly NumericFieldSpec[] = [
  {
    key: "chunk_target_chars",
    labelKey: "settings.ingest.fieldChunkTargetLabel",
    unitKey: "settings.ingest.fieldChunkTargetUnit",
    min: 1000,
    max: 20000,
    step: 500,
    integer: true,
    hintKey: "settings.ingest.fieldChunkTargetHint",
  },
  {
    key: "chunk_overlap_chars",
    labelKey: "settings.ingest.fieldChunkOverlapLabel",
    unitKey: "settings.ingest.fieldChunkOverlapUnit",
    min: 0,
    max: 5000,
    step: 100,
    integer: true,
    hintKey: "settings.ingest.fieldChunkOverlapHint",
  },
];

function localizeSpec(
  spec: NumericFieldSpec,
  t: Translate,
): NumericFieldSpec & RuntimeNumberSpec {
  return {
    ...spec,
    label: t(spec.labelKey),
    unit: t(spec.unitKey),
    hint: t(spec.hintKey),
  };
}

const ALL_FIELD_SPECS: readonly NumericFieldSpec[] = [
  ...WORKER_FIELDS,
  ...CHUNK_FIELDS,
];

const VALUE_KEYS: readonly NumericField[] = [
  "poll_seconds",
  "extract_workers",
  "max_inflight_jobs",
  "embedding_concurrency",
  "chunk_target_chars",
  "chunk_overlap_chars",
];

function toDraft(values: IngestRuntimeValues): DraftValues {
  return {
    poll_seconds: String(values.poll_seconds),
    extract_workers: String(values.extract_workers),
    max_inflight_jobs: String(values.max_inflight_jobs),
    embedding_concurrency: String(values.embedding_concurrency),
    chunk_target_chars: String(values.chunk_target_chars),
    chunk_overlap_chars: String(values.chunk_overlap_chars),
  };
}

function fromDraft(draft: DraftValues): IngestRuntimeValues {
  return {
    poll_seconds: Number(draft.poll_seconds),
    extract_workers: Number(draft.extract_workers),
    max_inflight_jobs: Number(draft.max_inflight_jobs),
    embedding_concurrency: Number(draft.embedding_concurrency),
    chunk_target_chars: Number(draft.chunk_target_chars),
    chunk_overlap_chars: Number(draft.chunk_overlap_chars),
  };
}

function valuesKey(values: IngestRuntimeValues): string {
  return VALUE_KEYS.map((key) => `${key}=${String(values[key])}`).join("|");
}

function draftMatchesValues(
  draft: DraftValues,
  values: IngestRuntimeValues,
): boolean {
  return ALL_FIELD_SPECS.every((spec) => {
    const raw = draft[spec.key].trim();
    return raw.length > 0 && Number(raw) === values[spec.key];
  });
}

interface ValidationResult {
  readonly fieldErrors: Partial<Record<NumericField, string>>;
  readonly parsed: IngestRuntimeValues | null;
}

function validateDraft(
  draft: DraftValues,
  t: Translate,
  formatNumber: (value: number) => string,
): ValidationResult {
  const fieldErrors: Partial<Record<NumericField, string>> = {};
  const numbers: Partial<Record<NumericField, number>> = {};

  for (const spec of ALL_FIELD_SPECS) {
    const raw = draft[spec.key].trim();
    if (raw.length === 0) {
      fieldErrors[spec.key] = t("settings.runtime.errors.required");
      continue;
    }
    const parsed = Number(raw);
    if (spec.integer && !Number.isInteger(parsed)) {
      fieldErrors[spec.key] = t("settings.runtime.errors.wholeNumber");
      continue;
    }
    if (!Number.isFinite(parsed)) {
      fieldErrors[spec.key] = t("settings.runtime.errors.number");
      continue;
    }
    if (parsed < spec.min || parsed > spec.max) {
      fieldErrors[spec.key] = t("settings.runtime.errors.range", {
        min: formatNumber(spec.min),
        max: formatNumber(spec.max),
      });
      continue;
    }
    numbers[spec.key] = parsed;
  }

  const overlap = numbers.chunk_overlap_chars;
  const target = numbers.chunk_target_chars;
  if (
    overlap !== undefined &&
    target !== undefined &&
    overlap >= target &&
    fieldErrors.chunk_overlap_chars === undefined
  ) {
    fieldErrors.chunk_overlap_chars = t(
      "settings.runtime.errors.overlapBelowTarget",
      { target: formatNumber(target) },
    );
  }

  const hasErrors = Object.keys(fieldErrors).length > 0;
  return {
    fieldErrors,
    parsed: hasErrors ? null : fromDraft(draft),
  };
}

/**
 * Presentational editor for the ingestion worker settings.
 *
 * The component owns only a draft copy. Saving, resetting, and refetching stay
 * with the parent, which passes the persisted values back through `values`.
 */
export function IngestRuntimePanel({
  values,
  defaults,
  source,
  updatedAt,
  saving,
  error,
  onSave,
  onReset,
  className,
}: IngestRuntimePanelProps) {
  const { t, formatNumber } = useI18n();
  const [draft, setDraft] = useState<DraftValues>(() => toDraft(values));
  const [confirmingReset, setConfirmingReset] = useState(false);

  const currentValuesKey = valuesKey(values);
  const syncedValuesKey = useRef(currentValuesKey);

  useEffect(() => {
    if (syncedValuesKey.current === currentValuesKey) {
      return;
    }
    syncedValuesKey.current = currentValuesKey;
    setDraft(toDraft(values));
    setConfirmingReset(false);
  }, [currentValuesKey, values]);

  const validation = validateDraft(draft, t, formatNumber);
  const isDirty = !draftMatchesValues(draft, values);
  const isInvalid = Object.keys(validation.fieldErrors).length > 0;
  const canSave = isDirty && !isInvalid && !saving;

  const workerFields = WORKER_FIELDS.map((spec) => localizeSpec(spec, t));
  const chunkFields = CHUNK_FIELDS.map((spec) => localizeSpec(spec, t));

  const updateNumber = (field: NumericField, next: string) => {
    setDraft((current) => ({ ...current, [field]: next }));
  };

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!canSave || validation.parsed === null) {
      return;
    }
    onSave(validation.parsed);
  };

  const confirmReset = () => {
    setConfirmingReset(false);
    onReset();
  };

  const panelClassName = ["settings-panel", "runtime-panel", className]
    .filter(Boolean)
    .join(" ");

  return (
    <Panel
      title={
        <span className="settings-panel__title">
          <Icon name="layers" size={16} />
          {t("settings.ingest.title")}
        </span>
      }
      action={
        <Badge>
          {t("settings.ingest.badge", {
            target: formatNumber(values.chunk_target_chars),
            overlap: formatNumber(values.chunk_overlap_chars),
          })}
        </Badge>
      }
      className={panelClassName}
    >
      <p className="settings-lede">{t("settings.ingest.lede")}</p>

      <RuntimeStatus
        source={source}
        updatedAt={updatedAt}
        summary={t("settings.ingest.statusSummary", {
          poll: formatNumber(values.poll_seconds),
          threads: formatNumber(values.extract_workers),
          inflight: formatNumber(values.max_inflight_jobs),
        })}
        dirty={isDirty}
      />

      <div className="runtime-warning" role="note">
        <Icon name="info" size={15} />
        <span>{t("settings.ingest.warning")}</span>
      </div>

      <form
        className="runtime-form"
        onSubmit={handleSubmit}
        aria-busy={saving}
        noValidate
      >
        <div className="runtime-groups">
          <RuntimeGroup
            slot={t("settings.ingest.groupWorkerSlot")}
            title={t("settings.ingest.groupWorkerTitle")}
            description={t("settings.ingest.groupWorkerDescription")}
          >
            {workerFields.map((spec) => (
              <RuntimeNumberField
                key={spec.key}
                spec={spec}
                value={draft[spec.key]}
                defaultValue={defaults[spec.key]}
                disabled={saving}
                error={validation.fieldErrors[spec.key]}
                onValueChange={(next) => updateNumber(spec.key, next)}
              />
            ))}
          </RuntimeGroup>

          <RuntimeGroup
            slot={t("settings.ingest.groupChunkingSlot")}
            title={t("settings.ingest.groupChunkingTitle")}
            description={t("settings.ingest.groupChunkingDescription")}
          >
            {chunkFields.map((spec) => (
              <RuntimeNumberField
                key={spec.key}
                spec={spec}
                value={draft[spec.key]}
                defaultValue={defaults[spec.key]}
                disabled={saving}
                error={validation.fieldErrors[spec.key]}
                onValueChange={(next) => updateNumber(spec.key, next)}
              />
            ))}
          </RuntimeGroup>
        </div>

        {error ? <RuntimeError message={error} /> : null}

        <RuntimeActions
          saving={saving}
          canSave={canSave}
          dirty={isDirty}
          invalid={isInvalid}
          confirmingReset={confirmingReset}
          onRequestReset={() => setConfirmingReset(true)}
          onCancelReset={() => setConfirmingReset(false)}
          onConfirmReset={confirmReset}
        />
      </form>
    </Panel>
  );
}
