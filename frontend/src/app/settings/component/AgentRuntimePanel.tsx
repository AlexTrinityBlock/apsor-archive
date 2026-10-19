import {
  useEffect,
  useId,
  useRef,
  useState,
  type CSSProperties,
  type FormEvent,
} from "react";

import { formatDateTime, formatNumber } from "../../../lib/format";
import { Badge } from "../../component/Badge";
import { Button } from "../../component/Button";
import { Icon } from "../../component/Icon";
import { Panel } from "../../component/Panel";

/** The runtime bounds the agent applies to a new run. */
export interface AgentRuntimeValues {
  readonly max_total_tokens: number;
  readonly compaction_threshold_tokens: number;
  readonly context_window_tokens: number;
  readonly max_steps: number;
  readonly max_tool_calls_per_turn: number;
  readonly max_parallel_tools: number;
  readonly max_tool_result_chars: number;
  readonly max_page_context_chars: number;
  readonly max_compaction_summary_chars: number;
  readonly max_compaction_last_user_chars: number;
  readonly auto_compaction_enabled: boolean;
  readonly parallel_tools_enabled: boolean;
  readonly save_memory_requires_approval: boolean;
}

/** Props for the presentational runtime panel; persistence stays with the page. */
export interface AgentRuntimePanelProps {
  readonly values: AgentRuntimeValues;
  readonly defaults: AgentRuntimeValues;
  readonly source: "database" | "default";
  readonly updatedAt: string | null;
  readonly saving: boolean;
  readonly error: string | null;
  readonly onSave: (values: AgentRuntimeValues) => void;
  readonly onReset: () => void;
  readonly className?: string;
}

/** Server-side defaults, exported so the settings page can seed the panel. */
export const AGENT_RUNTIME_DEFAULTS: AgentRuntimeValues = {
  max_total_tokens: 100000,
  compaction_threshold_tokens: 75000,
  context_window_tokens: 1000000,
  max_steps: 24,
  max_tool_calls_per_turn: 6,
  max_parallel_tools: 6,
  max_tool_result_chars: 100000,
  max_page_context_chars: 6000,
  max_compaction_summary_chars: 6000,
  max_compaction_last_user_chars: 4000,
  auto_compaction_enabled: true,
  parallel_tools_enabled: true,
  save_memory_requires_approval: true,
};

type BooleanField =
  | "auto_compaction_enabled"
  | "parallel_tools_enabled"
  | "save_memory_requires_approval";

type NumericField = Exclude<keyof AgentRuntimeValues, BooleanField>;

type DraftValues = { readonly [Key in NumericField]: string } & {
  readonly [Key in BooleanField]: boolean;
};

interface NumericFieldSpec {
  readonly key: NumericField;
  readonly label: string;
  readonly unit: string;
  readonly min: number;
  readonly max: number;
  readonly step: number;
  readonly hint: string;
}

const CONTEXT_FIELDS: readonly NumericFieldSpec[] = [
  {
    key: "context_window_tokens",
    label: "Model context window",
    unit: "tokens",
    min: 8000,
    max: 2000000,
    step: 50000,
    hint: "Provider/model input capacity, separate from the turn budget. DeepSeek V4.1 Flash is about 1,000,000 input tokens.",
  },
  {
    key: "max_total_tokens",
    label: "Turn token budget",
    unit: "tokens",
    min: 8000,
    max: 200000,
    step: 5000,
    hint: "Cumulative model-step budget for one agent turn, including tool results. It does not raise the model context window.",
  },
  {
    key: "compaction_threshold_tokens",
    label: "Auto-compaction threshold",
    unit: "tokens",
    min: 1000,
    max: 200000,
    step: 5000,
    hint: "Auto compaction starts before a new turn once the transcript passes this share of the turn budget.",
  },
  {
    key: "max_steps",
    label: "Max steps",
    unit: "steps",
    min: 1,
    max: 32,
    step: 1,
    hint: "Think-and-act rounds allowed in a single turn; 24 is the default, 32 the max."
  },
  {
    key: "max_page_context_chars",
    label: "Page context",
    unit: "chars",
    min: 500,
    max: 50000,
    step: 500,
    hint: "Maximum page text attached to a turn.",
  },
];

const TOOL_FIELDS: readonly NumericFieldSpec[] = [
  {
    key: "max_parallel_tools",
    label: "Max parallel tools",
    unit: "tools",
    min: 1,
    max: 24,
    step: 1,
    hint: "Tools that may execute at the same time.",
  },
  {
    key: "max_tool_calls_per_turn",
    label: "Tool calls per turn",
    unit: "calls",
    min: 1,
    max: 24,
    step: 1,
    hint: "Total tool invocations allowed in one turn.",
  },
  {
    key: "max_tool_result_chars",
    label: "Chars per tool result",
    unit: "chars",
    min: 1000,
    max: 200000,
    step: 5000,
    hint: "Each result is clipped independently; 100k fits about 25 four-kilochar chunks.",
  },
];

const COMPACTION_FIELDS: readonly NumericFieldSpec[] = [
  {
    key: "max_compaction_summary_chars",
    label: "Summary chars",
    unit: "chars",
    min: 1000,
    max: 20000,
    step: 500,
    hint: "Size reserved for the folded-turn summary.",
  },
  {
    key: "max_compaction_last_user_chars",
    label: "Last user input chars",
    unit: "chars",
    min: 500,
    max: 10000,
    step: 500,
    hint: "Most recent user message kept verbatim.",
  },
];

const ALL_FIELD_SPECS: readonly NumericFieldSpec[] = [
  ...CONTEXT_FIELDS,
  ...TOOL_FIELDS,
  ...COMPACTION_FIELDS,
];

const VALUE_KEYS: readonly (keyof AgentRuntimeValues)[] = [
  "max_total_tokens",
  "compaction_threshold_tokens",
  "context_window_tokens",
  "max_steps",
  "max_tool_calls_per_turn",
  "max_parallel_tools",
  "max_tool_result_chars",
  "max_page_context_chars",
  "max_compaction_summary_chars",
  "max_compaction_last_user_chars",
  "auto_compaction_enabled",
  "parallel_tools_enabled",
  "save_memory_requires_approval",
];

function toDraft(values: AgentRuntimeValues): DraftValues {
  return {
    max_total_tokens: String(values.max_total_tokens),
    compaction_threshold_tokens: String(values.compaction_threshold_tokens),
    context_window_tokens: String(values.context_window_tokens),
    max_steps: String(values.max_steps),
    max_tool_calls_per_turn: String(values.max_tool_calls_per_turn),
    max_parallel_tools: String(values.max_parallel_tools),
    max_tool_result_chars: String(values.max_tool_result_chars),
    max_page_context_chars: String(values.max_page_context_chars),
    max_compaction_summary_chars: String(values.max_compaction_summary_chars),
    max_compaction_last_user_chars: String(values.max_compaction_last_user_chars),
    auto_compaction_enabled: values.auto_compaction_enabled,
    parallel_tools_enabled: values.parallel_tools_enabled,
    save_memory_requires_approval: values.save_memory_requires_approval,
  };
}

function fromDraft(draft: DraftValues): AgentRuntimeValues {
  return {
    max_total_tokens: Number(draft.max_total_tokens),
    compaction_threshold_tokens: Number(draft.compaction_threshold_tokens),
    context_window_tokens: Number(draft.context_window_tokens),
    max_steps: Number(draft.max_steps),
    max_tool_calls_per_turn: Number(draft.max_tool_calls_per_turn),
    max_parallel_tools: Number(draft.max_parallel_tools),
    max_tool_result_chars: Number(draft.max_tool_result_chars),
    max_page_context_chars: Number(draft.max_page_context_chars),
    max_compaction_summary_chars: Number(draft.max_compaction_summary_chars),
    max_compaction_last_user_chars: Number(draft.max_compaction_last_user_chars),
    auto_compaction_enabled: draft.auto_compaction_enabled,
    parallel_tools_enabled: draft.parallel_tools_enabled,
    save_memory_requires_approval: draft.save_memory_requires_approval,
  };
}

function valuesKey(values: AgentRuntimeValues): string {
  return VALUE_KEYS.map((key) => `${key}=${String(values[key])}`).join("|");
}

function draftMatchesValues(
  draft: DraftValues,
  values: AgentRuntimeValues,
): boolean {
  const numbersMatch = ALL_FIELD_SPECS.every((spec) => {
    const raw = draft[spec.key].trim();
    return raw.length > 0 && Number(raw) === values[spec.key];
  });
  return (
    numbersMatch &&
    draft.auto_compaction_enabled === values.auto_compaction_enabled &&
    draft.parallel_tools_enabled === values.parallel_tools_enabled &&
    draft.save_memory_requires_approval ===
      values.save_memory_requires_approval
  );
}

interface ValidationResult {
  readonly fieldErrors: Partial<Record<NumericField, string>>;
  readonly parsed: AgentRuntimeValues | null;
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
    if (!Number.isInteger(parsed)) {
      fieldErrors[spec.key] = "Enter a whole number.";
      continue;
    }
    if (parsed < spec.min || parsed > spec.max) {
      fieldErrors[spec.key] = `Enter a value between ${formatNumber(spec.min)} and ${formatNumber(spec.max)}.`;
      continue;
    }
    numbers[spec.key] = parsed;
  }

  const totalTokens = numbers.max_total_tokens;
  const threshold = numbers.compaction_threshold_tokens;
  if (
    totalTokens !== undefined &&
    threshold !== undefined &&
    threshold >= totalTokens &&
    fieldErrors.compaction_threshold_tokens === undefined
  ) {
    fieldErrors.compaction_threshold_tokens = `Must be lower than the max total (${formatNumber(totalTokens)}).`;
  }

  const parallelTools = numbers.max_parallel_tools;
  const toolCalls = numbers.max_tool_calls_per_turn;
  if (
    parallelTools !== undefined &&
    toolCalls !== undefined &&
    parallelTools > toolCalls &&
    fieldErrors.max_parallel_tools === undefined
  ) {
    fieldErrors.max_parallel_tools = `Must not exceed tool calls per turn (${formatNumber(toolCalls)}).`;
  }

  const hasErrors = Object.keys(fieldErrors).length > 0;
  return {
    fieldErrors,
    parsed: hasErrors ? null : fromDraft(draft),
  };
}

function positiveNumber(raw: string): number | null {
  if (raw.trim().length === 0) {
    return null;
  }
  const parsed = Number(raw);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : null;
}

interface RuntimeNumberFieldProps {
  readonly spec: NumericFieldSpec;
  readonly value: string;
  readonly defaultValue: number;
  readonly disabled: boolean;
  readonly error: string | undefined;
  readonly onValueChange: (value: string) => void;
}

function RuntimeNumberField({
  spec,
  value,
  defaultValue,
  disabled,
  error,
  onValueChange,
}: RuntimeNumberFieldProps) {
  const fieldId = useId();
  const hintId = `${fieldId}-hint`;
  const errorId = `${fieldId}-error`;
  const describedBy = error ? `${hintId} ${errorId}` : hintId;

  return (
    <div className="agent-runtime-field">
      <label className="agent-runtime-field__label" htmlFor={fieldId}>
        <span>{spec.label}</span>
        <span className="agent-runtime-field__unit" aria-hidden="true">
          {spec.unit}
        </span>
      </label>
      <input
        id={fieldId}
        className={
          error
            ? "agent-runtime-input agent-runtime-input--invalid"
            : "agent-runtime-input"
        }
        type="number"
        inputMode="numeric"
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
      <span className="agent-runtime-field__hint" id={hintId}>
        {spec.hint} Default {formatNumber(defaultValue)} ·{" "}
        {formatNumber(spec.min)}–{formatNumber(spec.max)} {spec.unit}.
      </span>
      {error ? (
        <span className="agent-runtime-field__error" id={errorId}>
          {error}
        </span>
      ) : null}
    </div>
  );
}

interface RuntimeToggleProps {
  readonly label: string;
  readonly hint: string;
  readonly checked: boolean;
  readonly disabled: boolean;
  readonly onChange: (checked: boolean) => void;
}

function RuntimeToggle({
  label,
  hint,
  checked,
  disabled,
  onChange,
}: RuntimeToggleProps) {
  const fieldId = useId();
  const hintId = `${fieldId}-hint`;

  return (
    <label className="agent-runtime-toggle" htmlFor={fieldId}>
      <span className="agent-runtime-toggle__control">
        <input
          id={fieldId}
          className="agent-runtime-toggle__input"
          type="checkbox"
          role="switch"
          checked={checked}
          disabled={disabled}
          aria-describedby={hintId}
          onChange={(event) => onChange(event.currentTarget.checked)}
        />
        <span className="agent-runtime-toggle__track" aria-hidden="true">
          <span className="agent-runtime-toggle__thumb" />
        </span>
      </span>
      <span className="agent-runtime-toggle__copy">
        <span className="agent-runtime-toggle__title">{label}</span>
        <span className="agent-runtime-toggle__hint" id={hintId}>
          {hint}
        </span>
      </span>
    </label>
  );
}

function GroupHeading({
  slot,
  title,
  scope,
  description,
  advanced = false,
}: {
  readonly slot: string;
  readonly title: string;
  readonly scope: string;
  readonly description: string;
  readonly advanced?: boolean;
}) {
  return (
    <header className="agent-runtime-group__head">
      <p className="agent-runtime-group__slot">{slot}</p>
      <h3 className="agent-runtime-group__title" id={scope}>
        {title}
        {advanced ? (
          <span className="agent-runtime-group__tag">Advanced</span>
        ) : null}
      </h3>
      <p className="agent-runtime-group__intro">{description}</p>
    </header>
  );
}

/**
 * Presentational editor for the agent runtime bounds.
 *
 * The component owns only a draft copy. Saving, resetting, and refetching stay
 * with the parent, which passes the persisted values back through `values`.
 */
export function AgentRuntimePanel({
  values,
  defaults,
  source,
  updatedAt,
  saving,
  error,
  onSave,
  onReset,
  className,
}: AgentRuntimePanelProps) {
  const [draft, setDraft] = useState<DraftValues>(() => toDraft(values));
  const [confirmingReset, setConfirmingReset] = useState(false);
  const contextId = useId();
  const toolId = useId();
  const compactionId = useId();

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

  const draftTotal =
    positiveNumber(draft.max_total_tokens) ?? values.max_total_tokens;
  const draftThreshold =
    positiveNumber(draft.compaction_threshold_tokens) ??
    values.compaction_threshold_tokens;
  const thresholdPercent =
    draftTotal > 0
      ? Math.min(100, Math.max(0, Math.round((draftThreshold / draftTotal) * 100)))
      : 0;
  const headroom = Math.max(0, draftTotal - draftThreshold);
  const budgetStyle = {
    "--agent-runtime-budget-fill": `${thresholdPercent}%`,
  } as CSSProperties;

  const updateNumber = (field: NumericField, next: string) => {
    setDraft((current) => ({ ...current, [field]: next }));
  };

  const updateBoolean = (field: BooleanField, next: boolean) => {
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
    "agent-runtime-panel",
    className,
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <Panel
      eyebrow="Agent · database-backed"
      title="Agent runtime"
      className={panelClassName}
    >
      <p className="agent-runtime-intro">
        These bounds are stored in the database and apply to new runs. An active
        run keeps the snapshot it started with.
      </p>

      <section
        className="agent-runtime-status"
        data-source={source}
        aria-label="Runtime settings status"
      >
        <Badge tone={source === "database" ? "moss" : "neutral"} dot>
          {source === "database" ? "Database" : "Defaults"}
        </Badge>
        <span className="agent-runtime-status__updated">
          {updatedAt ? (
            <>
              Last updated{" "}
              <time dateTime={updatedAt}>{formatDateTime(updatedAt)}</time>
            </>
          ) : (
            "No saved update yet"
          )}
        </span>
        <span className="agent-runtime-status__summary">
          {formatNumber(values.context_window_tokens)} model context ·{" "}
          {formatNumber(values.max_total_tokens)} turn budget ·{" "}
          {formatNumber(values.compaction_threshold_tokens)} compaction
        </span>
        {isDirty ? (
          <span className="agent-runtime-status__draft">Unsaved draft</span>
        ) : null}
      </section>

      <div className="agent-runtime-budget">
        <div className="agent-runtime-budget__head">
          <span className="agent-runtime-budget__label">
            Auto-compaction threshold
          </span>
          <span className="agent-runtime-budget__value">
            {formatNumber(draftThreshold)} / {formatNumber(draftTotal)} tokens
          </span>
        </div>
        <div
          className="agent-runtime-budget__meter"
          role="progressbar"
          aria-label="Compaction threshold as a share of the turn budget"
          aria-valuemin={0}
          aria-valuemax={100}
          aria-valuenow={thresholdPercent}
          style={budgetStyle}
        >
          <span className="agent-runtime-budget__fill" aria-hidden="true" />
          <span className="agent-runtime-budget__threshold" aria-hidden="true" />
        </div>
        <div className="agent-runtime-budget__foot">
          <span>{thresholdPercent}% of the turn budget</span>
          <span>{formatNumber(headroom)} tokens headroom</span>
        </div>
      </div>

      <form
        className="agent-runtime-form"
        onSubmit={handleSubmit}
        aria-busy={saving}
        noValidate
      >
        <div className="agent-runtime-groups">
          <section
            className="agent-runtime-group"
            aria-labelledby={contextId}
          >
            <GroupHeading
              slot="Group 01"
              title="Context budget"
              scope={contextId}
              description="The model's input capacity, the ceiling for a single turn, when older material is folded away, and how much page text the agent may read. The context window is model metadata; it is not the turn budget."
            />
            <div className="agent-runtime-grid">
              <RuntimeNumberField
                spec={CONTEXT_FIELDS[0]}
                value={draft.context_window_tokens}
                defaultValue={defaults.context_window_tokens}
                disabled={saving}
                error={validation.fieldErrors.context_window_tokens}
                onValueChange={(next) =>
                  updateNumber("context_window_tokens", next)
                }
              />
              <RuntimeNumberField
                spec={CONTEXT_FIELDS[1]}
                value={draft.max_total_tokens}
                defaultValue={defaults.max_total_tokens}
                disabled={saving}
                error={validation.fieldErrors.max_total_tokens}
                onValueChange={(next) => updateNumber("max_total_tokens", next)}
              />
              <RuntimeNumberField
                spec={CONTEXT_FIELDS[2]}
                value={draft.compaction_threshold_tokens}
                defaultValue={defaults.compaction_threshold_tokens}
                disabled={saving}
                error={validation.fieldErrors.compaction_threshold_tokens}
                onValueChange={(next) =>
                  updateNumber("compaction_threshold_tokens", next)
                }
              />
              <div className="agent-runtime-field agent-runtime-field--wide">
                <RuntimeToggle
                  label="Auto compaction"
                  hint="Fold older turns into a summary when the threshold is reached."
                  checked={draft.auto_compaction_enabled}
                  disabled={saving}
                  onChange={(next) =>
                    updateBoolean("auto_compaction_enabled", next)
                  }
                />
              </div>
              <RuntimeNumberField
                spec={CONTEXT_FIELDS[3]}
                value={draft.max_steps}
                defaultValue={defaults.max_steps}
                disabled={saving}
                error={validation.fieldErrors.max_steps}
                onValueChange={(next) => updateNumber("max_steps", next)}
              />
              <RuntimeNumberField
                spec={CONTEXT_FIELDS[4]}
                value={draft.max_page_context_chars}
                defaultValue={defaults.max_page_context_chars}
                disabled={saving}
                error={validation.fieldErrors.max_page_context_chars}
                onValueChange={(next) =>
                  updateNumber("max_page_context_chars", next)
                }
              />
            </div>
          </section>

          <section className="agent-runtime-group" aria-labelledby={toolId}>
            <GroupHeading
              slot="Group 02"
              title="Tool execution"
              scope={toolId}
              description="How many tools may run, how often they may be called, and how much their results may carry."
            />
            <div className="agent-runtime-grid">
              <div className="agent-runtime-field agent-runtime-field--wide">
                <RuntimeToggle
                  label="Parallel tools"
                  hint="Let independent tool calls run at the same time."
                  checked={draft.parallel_tools_enabled}
                  disabled={saving}
                  onChange={(next) =>
                    updateBoolean("parallel_tools_enabled", next)
                  }
                />
              </div>
              <div className="agent-runtime-field agent-runtime-field--wide">
                <RuntimeToggle
                  label="Require manual approval for memory writes"
                  hint="When on, the agent's save_memory request waits for your Approve/Reject decision. When off, the agent may save only after its existing prompt-level confirmation. Manual approval is on by default."
                  checked={draft.save_memory_requires_approval}
                  disabled={saving}
                  onChange={(next) =>
                    updateBoolean("save_memory_requires_approval", next)
                  }
                />
              </div>
              <RuntimeNumberField
                spec={TOOL_FIELDS[0]}
                value={draft.max_parallel_tools}
                defaultValue={defaults.max_parallel_tools}
                disabled={saving}
                error={validation.fieldErrors.max_parallel_tools}
                onValueChange={(next) => updateNumber("max_parallel_tools", next)}
              />
              <RuntimeNumberField
                spec={TOOL_FIELDS[1]}
                value={draft.max_tool_calls_per_turn}
                defaultValue={defaults.max_tool_calls_per_turn}
                disabled={saving}
                error={validation.fieldErrors.max_tool_calls_per_turn}
                onValueChange={(next) =>
                  updateNumber("max_tool_calls_per_turn", next)
                }
              />
              <RuntimeNumberField
                spec={TOOL_FIELDS[2]}
                value={draft.max_tool_result_chars}
                defaultValue={defaults.max_tool_result_chars}
                disabled={saving}
                error={validation.fieldErrors.max_tool_result_chars}
                onValueChange={(next) =>
                  updateNumber("max_tool_result_chars", next)
                }
              />
            </div>
          </section>

          <section
            className="agent-runtime-group"
            aria-labelledby={compactionId}
          >
            <GroupHeading
              slot="Group 03"
              title="Compaction detail"
              scope={compactionId}
              description="How much material the summarizer keeps when older turns are folded away."
              advanced
            />
            <div className="agent-runtime-grid">
              <RuntimeNumberField
                spec={COMPACTION_FIELDS[0]}
                value={draft.max_compaction_summary_chars}
                defaultValue={defaults.max_compaction_summary_chars}
                disabled={saving}
                error={validation.fieldErrors.max_compaction_summary_chars}
                onValueChange={(next) =>
                  updateNumber("max_compaction_summary_chars", next)
                }
              />
              <RuntimeNumberField
                spec={COMPACTION_FIELDS[1]}
                value={draft.max_compaction_last_user_chars}
                defaultValue={defaults.max_compaction_last_user_chars}
                disabled={saving}
                error={validation.fieldErrors.max_compaction_last_user_chars}
                onValueChange={(next) =>
                  updateNumber("max_compaction_last_user_chars", next)
                }
              />
            </div>
          </section>
        </div>

        {error ? (
          <p className="agent-runtime-error" role="alert">
            <Icon name="info" size={14} />
            <span>{error}</span>
          </p>
        ) : null}

        <div className="agent-runtime-actions">
          <div className="agent-runtime-actions__reset">
            {confirmingReset ? (
              <>
                <span className="agent-runtime-reset__question" role="status">
                  Reset every runtime value to the default?
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

          <div className="agent-runtime-actions__save">
            {isDirty && !isInvalid && !saving ? (
              <span className="agent-runtime-actions__note">
                Unsaved changes
              </span>
            ) : null}
            <Button
              type="submit"
              variant="primary"
              size="sm"
              disabled={!canSave}
            >
              <Icon name="check" size={14} />
              {saving ? "Saving…" : "Save runtime"}
            </Button>
          </div>
        </div>
      </form>
    </Panel>
  );
}
