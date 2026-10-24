import {
  useEffect,
  useRef,
  useState,
  type FormEvent,
} from "react";

import { formatNumber } from "../../../lib/format";
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

interface NumericFieldSpec extends RuntimeNumberSpec {
  readonly key: NumericField;
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

  const panelClassName = ["settings-panel", "runtime-panel", className]
    .filter(Boolean)
    .join(" ");

  return (
    <Panel
      title={
        <span className="settings-panel__title">
          <Icon name="layers" size={16} />
          Ingestion runtime
        </span>
      }
      action={
        <Badge>
          {formatNumber(values.chunk_target_chars)} /{" "}
          {formatNumber(values.chunk_overlap_chars)} chars
        </Badge>
      }
      className={panelClassName}
    >
      <p className="settings-lede">
        The worker reads one snapshot per loop or job. Saving here changes the
        next claim; a job already running keeps the settings it started with.
      </p>

      <RuntimeStatus
        source={source}
        updatedAt={updatedAt}
        summary={`${formatNumber(values.poll_seconds)}s poll · ${formatNumber(values.extract_workers)} threads · ${formatNumber(values.max_inflight_jobs)} in flight`}
        dirty={isDirty}
      />

      <div className="runtime-warning" role="note">
        <Icon name="info" size={15} />
        <span>
          Worker settings apply to the next loop or job. Changing chunk sizes
          only affects files ingested after saving; existing files must be
          re-ingested before their chunk boundaries match.
        </span>
      </div>

      <form
        className="runtime-form"
        onSubmit={handleSubmit}
        aria-busy={saving}
        noValidate
      >
        <div className="runtime-groups">
          <RuntimeGroup
            slot="Group 01"
            title="Worker"
            description="How often the worker polls, how much CPU work it may fan out, and how many jobs and embedding requests it may hold at once."
          >
            {WORKER_FIELDS.map((spec) => (
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
            slot="Group 02"
            title="Chunking"
            description="Chunk boundaries decide retrieval granularity. The overlap must stay below the target size."
          >
            {CHUNK_FIELDS.map((spec) => (
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
