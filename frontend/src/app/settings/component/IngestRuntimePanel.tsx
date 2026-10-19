import {
  useEffect,
  useId,
  useRef,
  useState,
  type FormEvent,
} from "react";

import { formatDateTime, formatNumber } from "../../../lib/format";
import { Badge } from "../../component/Badge";
import { Button } from "../../component/Button";
import { Icon } from "../../component/Icon";
import { Panel } from "../../component/Panel";

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

/** Server-side defaults, kept in sync with the backend domain constants. */
export const INGEST_RUNTIME_DEFAULTS: IngestRuntimeValues = {
  poll_seconds: 1,
  extract_workers: 2,
  max_inflight_jobs: 2,
  embedding_concurrency: 6,
  chunk_target_chars: 4000,
  chunk_overlap_chars: 500,
};

type NumericField = keyof IngestRuntimeValues;
type DraftValues = { readonly [Key in NumericField]: string };

interface NumericFieldSpec {
  readonly key: NumericField;
  readonly label: string;
  readonly unit: string;
  readonly min: number;
  readonly max: number;
  readonly step: number;
  readonly integer: boolean;
  readonly hint: string;
}

const WORKER_FIELDS: readonly NumericFieldSpec[] = [
  {
    key: "poll_seconds",
    label: "Poll seconds",
    unit: "seconds",
    min: 0.25,
    max: 30,
    step: 0.25,
    integer: false,
    hint: "Idle wait between database claims.",
  },
  {
    key: "extract_workers",
    label: "Extract threads",
    unit: "threads",
    min: 1,
    max: 8,
    step: 1,
    integer: true,
    hint: "Bounded CPU threads for parsing and chunking.",
  },
  {
    key: "max_inflight_jobs",
    label: "Max in-flight jobs",
    unit: "jobs",
    min: 1,
    max: 4,
    step: 1,
    integer: true,
    hint: "Jobs one worker process may hold at a time.",
  },
  {
    key: "embedding_concurrency",
    label: "Embedding concurrency",
    unit: "requests",
    min: 1,
    max: 32,
    step: 1,
    integer: true,
    hint: "Global async embedding limit shared across jobs.",
  },
];

const CHUNK_FIELDS: readonly NumericFieldSpec[] = [
  {
    key: "chunk_target_chars",
    label: "Target chars",
    unit: "chars",
    min: 1000,
    max: 20000,
    step: 500,
    integer: true,
    hint: "Preferred size of one indexed chunk.",
  },
  {
    key: "chunk_overlap_chars",
    label: "Overlap chars",
    unit: "chars",
    min: 0,
    max: 5000,
    step: 100,
    integer: true,
    hint: "Text repeated at the start of the next chunk.",
  },
];

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

function validateDraft(draft: DraftValues): ValidationResult {
  const fieldErrors: Partial<Record<NumericField, string>> = {};
  const numbers: Partial<Record<NumericField, number>> = {};

  for (const spec of ALL_FIELD_SPECS) {
    const raw = draft[spec.key].trim();
    if (raw.length === 0) {
      fieldErrors[spec.key] = "A value is required.";
      continue;
    }
    const parsed = Number(raw);
    if (spec.integer && !Number.isInteger(parsed)) {
      fieldErrors[spec.key] = "Enter a whole number.";
      continue;
    }
    if (!Number.isFinite(parsed)) {
      fieldErrors[spec.key] = "Enter a number.";
      continue;
    }
    if (parsed < spec.min || parsed > spec.max) {
      fieldErrors[spec.key] = `Enter a value between ${formatNumber(spec.min)} and ${formatNumber(spec.max)}.`;
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
    fieldErrors.chunk_overlap_chars = `Must be lower than target chars (${formatNumber(target)}).`;
  }

  const hasErrors = Object.keys(fieldErrors).length > 0;
  return {
    fieldErrors,
    parsed: hasErrors ? null : fromDraft(draft),
  };
}

interface IngestNumberFieldProps {
  readonly spec: NumericFieldSpec;
  readonly value: string;
  readonly defaultValue: number;
  readonly disabled: boolean;
  readonly error: string | undefined;
  readonly onValueChange: (value: string) => void;
}

function IngestNumberField({
  spec,
  value,
  defaultValue,
  disabled,
  error,
  onValueChange,
}: IngestNumberFieldProps) {
  const fieldId = useId();
  const hintId = `${fieldId}-hint`;
  const errorId = `${fieldId}-error`;
  const describedBy = error ? `${hintId} ${errorId}` : hintId;

  return (
    <div className="ingest-runtime-field">
      <label className="ingest-runtime-field__label" htmlFor={fieldId}>
        <span>{spec.label}</span>
        <span className="ingest-runtime-field__unit" aria-hidden="true">
          {spec.unit}
        </span>
      </label>
      <input
        id={fieldId}
        className={
          error
            ? "ingest-runtime-input ingest-runtime-input--invalid"
            : "ingest-runtime-input"
        }
        type="number"
        inputMode={spec.integer ? "numeric" : "decimal"}
        value={value}
        min={spec.min}
        max={spec.max}
        step={spec.step}
        placeholder={formatNumber(defaultValue)}
        disabled={disabled}
        aria-invalid={error ? true : undefined}
        aria-describedby={describedBy}
        onChange={(event) => onValueChange(event.currentTarget.value)}
      />
      <span className="ingest-runtime-field__hint" id={hintId}>
        {spec.hint} Default {formatNumber(defaultValue)} ·{" "}
        {formatNumber(spec.min)}–{formatNumber(spec.max)} {spec.unit}.
      </span>
      {error ? (
        <span className="ingest-runtime-field__error" id={errorId}>
          {error}
        </span>
      ) : null}
    </div>
  );
}

function GroupHeading({
  slot,
  title,
  scope,
  description,
}: {
  readonly slot: string;
  readonly title: string;
  readonly scope: string;
  readonly description: string;
}) {
  return (
    <header className="ingest-runtime-group__head">
      <p className="ingest-runtime-group__slot">{slot}</p>
      <h3 className="ingest-runtime-group__title" id={scope}>
        {title}
      </h3>
      <p className="ingest-runtime-group__intro">{description}</p>
    </header>
  );
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
  const [draft, setDraft] = useState<DraftValues>(() => toDraft(values));
  const [confirmingReset, setConfirmingReset] = useState(false);
  const workerGroupId = useId();
  const chunkGroupId = useId();

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

  const validation = validateDraft(draft);
  const isDirty = !draftMatchesValues(draft, values);
  const isInvalid = Object.keys(validation.fieldErrors).length > 0;
  const canSave = isDirty && !isInvalid && !saving;

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

  const panelClassName = [
    "settings-panel",
    "ingest-runtime-panel",
    className,
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <Panel
      eyebrow="Ingestion · database-backed"
      title="Ingestion runtime"
      className={panelClassName}
    >
      <p className="ingest-runtime-intro">
        The worker reads one snapshot per loop or job. Saving here changes the
        next claim; a job already running keeps the settings it started with.
      </p>

      <section
        className="ingest-runtime-status"
        data-source={source}
        aria-label="Ingestion runtime settings status"
      >
        <Badge tone={source === "database" ? "moss" : "neutral"} dot>
          {source === "database" ? "Database" : "Defaults"}
        </Badge>
        <span className="ingest-runtime-status__updated">
          {updatedAt ? (
            <>
              Last updated{" "}
              <time dateTime={updatedAt}>{formatDateTime(updatedAt)}</time>
            </>
          ) : (
            "No saved update yet"
          )}
        </span>
        <span className="ingest-runtime-status__summary">
          {formatNumber(values.poll_seconds)}s poll ·{" "}
          {formatNumber(values.extract_workers)} threads ·{" "}
          {formatNumber(values.max_inflight_jobs)} in flight
        </span>
        {isDirty ? (
          <span className="ingest-runtime-status__draft">Unsaved draft</span>
        ) : null}
      </section>

      <div className="ingest-runtime-warning" role="note">
        <Icon name="info" size={15} />
        <span>
          Worker settings apply to the next loop or job. Changing chunk sizes
          only affects files ingested after saving; existing files must be
          re-ingested before their chunk boundaries match.
        </span>
      </div>

      <form
        className="ingest-runtime-form"
        onSubmit={handleSubmit}
        aria-busy={saving}
        noValidate
      >
        <div className="ingest-runtime-groups">
          <section
            className="ingest-runtime-group"
            aria-labelledby={workerGroupId}
          >
            <GroupHeading
              slot="Group 01"
              title="Worker"
              scope={workerGroupId}
              description="How often the worker polls, how much CPU work it may fan out, and how many jobs and embedding requests it may hold at once."
            />
            <div className="ingest-runtime-grid">
              {WORKER_FIELDS.map((spec) => (
                <IngestNumberField
                  key={spec.key}
                  spec={spec}
                  value={draft[spec.key]}
                  defaultValue={defaults[spec.key]}
                  disabled={saving}
                  error={validation.fieldErrors[spec.key]}
                  onValueChange={(next) => updateNumber(spec.key, next)}
                />
              ))}
            </div>
          </section>

          <section
            className="ingest-runtime-group"
            aria-labelledby={chunkGroupId}
          >
            <GroupHeading
              slot="Group 02"
              title="Chunking"
              scope={chunkGroupId}
              description="Chunk boundaries decide retrieval granularity. The overlap must stay below the target size."
            />
            <div className="ingest-runtime-grid">
              {CHUNK_FIELDS.map((spec) => (
                <IngestNumberField
                  key={spec.key}
                  spec={spec}
                  value={draft[spec.key]}
                  defaultValue={defaults[spec.key]}
                  disabled={saving}
                  error={validation.fieldErrors[spec.key]}
                  onValueChange={(next) => updateNumber(spec.key, next)}
                />
              ))}
            </div>
          </section>
        </div>

        {error ? (
          <p className="ingest-runtime-error" role="alert">
            <Icon name="info" size={14} />
            <span>{error}</span>
          </p>
        ) : null}

        <div className="ingest-runtime-actions">
          <div className="ingest-runtime-actions__reset">
            {confirmingReset ? (
              <>
                <span className="ingest-runtime-reset__question" role="status">
                  Reset every ingestion runtime value to the default?
                </span>
                <Button
                  type="button"
                  variant="secondary"
                  size="sm"
                  onClick={confirmReset}
                  disabled={saving}
                >
                  Reset values
                </Button>
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  onClick={() => setConfirmingReset(false)}
                  disabled={saving}
                >
                  Keep current
                </Button>
              </>
            ) : (
              <Button
                type="button"
                variant="ghost"
                size="sm"
                onClick={() => setConfirmingReset(true)}
                disabled={saving}
              >
                <Icon name="history" size={14} />
                Reset defaults
              </Button>
            )}
          </div>

          <div className="ingest-runtime-actions__save">
            {isDirty && !isInvalid && !saving ? (
              <span className="ingest-runtime-actions__note">
                Unsaved changes
              </span>
            ) : null}
            <Button type="submit" variant="primary" size="sm" disabled={!canSave}>
              <Icon name="check" size={14} />
              {saving ? "Saving…" : "Save runtime"}
            </Button>
          </div>
        </div>
      </form>
    </Panel>
  );
}
