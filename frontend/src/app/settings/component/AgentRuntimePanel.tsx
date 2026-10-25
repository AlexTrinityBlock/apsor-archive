import {
  useEffect,
  useRef,
  useState,
  type CSSProperties,
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
import { SwitchField } from "./SwitchField";

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

type BooleanField =
  | "auto_compaction_enabled"
  | "parallel_tools_enabled"
  | "save_memory_requires_approval";

type NumericField = Exclude<keyof AgentRuntimeValues, BooleanField>;

type DraftValues = { readonly [Key in NumericField]: string } & {
  readonly [Key in BooleanField]: boolean;
};

interface NumericFieldSpec
  extends Omit<RuntimeNumberSpec, "label" | "unit" | "hint"> {
  readonly key: NumericField;
  readonly labelKey: TranslationKey;
  readonly unitKey: TranslationKey;
  readonly hintKey: TranslationKey;
}

const CONTEXT_FIELDS: readonly NumericFieldSpec[] = [
  {
    key: "context_window_tokens",
    labelKey: "settings.agent.fieldContextWindowLabel",
    unitKey: "settings.agent.fieldContextWindowUnit",
    min: 8000,
    max: 2000000,
    step: 50000,
    hintKey: "settings.agent.fieldContextWindowHint",
  },
  {
    key: "max_total_tokens",
    labelKey: "settings.agent.fieldTurnBudgetLabel",
    unitKey: "settings.agent.fieldTurnBudgetUnit",
    min: 8000,
    max: 200000,
    step: 5000,
    hintKey: "settings.agent.fieldTurnBudgetHint",
  },
  {
    key: "compaction_threshold_tokens",
    labelKey: "settings.agent.fieldThresholdLabel",
    unitKey: "settings.agent.fieldThresholdUnit",
    min: 1000,
    max: 200000,
    step: 5000,
    hintKey: "settings.agent.fieldThresholdHint",
  },
  {
    key: "max_steps",
    labelKey: "settings.agent.fieldMaxStepsLabel",
    unitKey: "settings.agent.fieldMaxStepsUnit",
    min: 1,
    max: 32,
    step: 1,
    hintKey: "settings.agent.fieldMaxStepsHint",
  },
  {
    key: "max_page_context_chars",
    labelKey: "settings.agent.fieldPageContextLabel",
    unitKey: "settings.agent.fieldPageContextUnit",
    min: 500,
    max: 50000,
    step: 500,
    hintKey: "settings.agent.fieldPageContextHint",
  },
];

const TOOL_FIELDS: readonly NumericFieldSpec[] = [
  {
    key: "max_parallel_tools",
    labelKey: "settings.agent.fieldParallelToolsLabel",
    unitKey: "settings.agent.fieldParallelToolsUnit",
    min: 1,
    max: 24,
    step: 1,
    hintKey: "settings.agent.fieldParallelToolsHint",
  },
  {
    key: "max_tool_calls_per_turn",
    labelKey: "settings.agent.fieldToolCallsLabel",
    unitKey: "settings.agent.fieldToolCallsUnit",
    min: 1,
    max: 24,
    step: 1,
    hintKey: "settings.agent.fieldToolCallsHint",
  },
  {
    key: "max_tool_result_chars",
    labelKey: "settings.agent.fieldToolResultCharsLabel",
    unitKey: "settings.agent.fieldToolResultCharsUnit",
    min: 1000,
    max: 200000,
    step: 5000,
    hintKey: "settings.agent.fieldToolResultCharsHint",
  },
];

const COMPACTION_FIELDS: readonly NumericFieldSpec[] = [
  {
    key: "max_compaction_summary_chars",
    labelKey: "settings.agent.fieldSummaryCharsLabel",
    unitKey: "settings.agent.fieldSummaryCharsUnit",
    min: 1000,
    max: 20000,
    step: 500,
    hintKey: "settings.agent.fieldSummaryCharsHint",
  },
  {
    key: "max_compaction_last_user_chars",
    labelKey: "settings.agent.fieldLastUserCharsLabel",
    unitKey: "settings.agent.fieldLastUserCharsUnit",
    min: 500,
    max: 10000,
    step: 500,
    hintKey: "settings.agent.fieldLastUserCharsHint",
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
    if (!Number.isInteger(parsed)) {
      fieldErrors[spec.key] = t("settings.runtime.errors.wholeNumber");
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

  const totalTokens = numbers.max_total_tokens;
  const threshold = numbers.compaction_threshold_tokens;
  if (
    totalTokens !== undefined &&
    threshold !== undefined &&
    threshold >= totalTokens &&
    fieldErrors.compaction_threshold_tokens === undefined
  ) {
    fieldErrors.compaction_threshold_tokens = t(
      "settings.runtime.errors.thresholdBelowTotal",
      { total: formatNumber(totalTokens) },
    );
  }

  const parallelTools = numbers.max_parallel_tools;
  const toolCalls = numbers.max_tool_calls_per_turn;
  if (
    parallelTools !== undefined &&
    toolCalls !== undefined &&
    parallelTools > toolCalls &&
    fieldErrors.max_parallel_tools === undefined
  ) {
    fieldErrors.max_parallel_tools = t(
      "settings.runtime.errors.parallelWithinCalls",
      { calls: formatNumber(toolCalls) },
    );
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
    "--runtime-budget-fill": `${thresholdPercent}%`,
  } as CSSProperties;

  const contextFields = CONTEXT_FIELDS.map((spec) => localizeSpec(spec, t));
  const toolFields = TOOL_FIELDS.map((spec) => localizeSpec(spec, t));
  const compactionFields = COMPACTION_FIELDS.map((spec) => localizeSpec(spec, t));

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

  const panelClassName = ["settings-panel", "runtime-panel", className]
    .filter(Boolean)
    .join(" ");

  return (
    <Panel
      title={
        <span className="settings-panel__title">
          <Icon name="spark" size={16} />
          {t("settings.agent.title")}
        </span>
      }
      action={
        <Badge>
          {t("settings.agent.badge", {
            steps: formatNumber(values.max_steps),
            calls: formatNumber(values.max_tool_calls_per_turn),
          })}
        </Badge>
      }
      className={panelClassName}
    >
      <p className="settings-lede">{t("settings.agent.lede")}</p>

      <RuntimeStatus
        source={source}
        updatedAt={updatedAt}
        summary={t("settings.agent.statusSummary", {
          context: formatNumber(values.context_window_tokens),
          budget: formatNumber(values.max_total_tokens),
          compaction: formatNumber(values.compaction_threshold_tokens),
        })}
        dirty={isDirty}
      />

      <div className="runtime-budget">
        <div className="runtime-budget__head">
          <span className="runtime-budget__label">
            {t("settings.agent.budgetLabel")}
          </span>
          <span className="runtime-budget__value">
            {t("settings.agent.budgetValue", {
              threshold: formatNumber(draftThreshold),
              total: formatNumber(draftTotal),
            })}
          </span>
        </div>
        <div
          className="runtime-budget__meter"
          role="progressbar"
          aria-label={t("settings.agent.budgetAria")}
          aria-valuemin={0}
          aria-valuemax={100}
          aria-valuenow={thresholdPercent}
          style={budgetStyle}
        >
          <span className="runtime-budget__fill" aria-hidden="true" />
          <span className="runtime-budget__threshold" aria-hidden="true" />
        </div>
        <div className="runtime-budget__foot">
          <span>
            {t("settings.agent.budgetPercent", {
              percent: formatNumber(thresholdPercent),
            })}
          </span>
          <span>
            {t("settings.agent.budgetHeadroom", {
              tokens: formatNumber(headroom),
            })}
          </span>
        </div>
      </div>

      <form
        className="runtime-form"
        onSubmit={handleSubmit}
        aria-busy={saving}
        noValidate
      >
        <div className="runtime-groups">
          <RuntimeGroup
            slot={t("settings.agent.groupContextSlot")}
            title={t("settings.agent.groupContextTitle")}
            description={t("settings.agent.groupContextDescription")}
          >
            <RuntimeNumberField
              spec={contextFields[0]}
              value={draft.context_window_tokens}
              defaultValue={defaults.context_window_tokens}
              disabled={saving}
              error={validation.fieldErrors.context_window_tokens}
              onValueChange={(next) =>
                updateNumber("context_window_tokens", next)
              }
            />
            <RuntimeNumberField
              spec={contextFields[1]}
              value={draft.max_total_tokens}
              defaultValue={defaults.max_total_tokens}
              disabled={saving}
              error={validation.fieldErrors.max_total_tokens}
              onValueChange={(next) => updateNumber("max_total_tokens", next)}
            />
            <RuntimeNumberField
              spec={contextFields[2]}
              value={draft.compaction_threshold_tokens}
              defaultValue={defaults.compaction_threshold_tokens}
              disabled={saving}
              error={validation.fieldErrors.compaction_threshold_tokens}
              onValueChange={(next) =>
                updateNumber("compaction_threshold_tokens", next)
              }
            />
            <div className="runtime-field runtime-field--wide">
              <SwitchField
                label={t("settings.agent.toggleAutoCompactionLabel")}
                hint={t("settings.agent.toggleAutoCompactionHint")}
                checked={draft.auto_compaction_enabled}
                disabled={saving}
                onChange={(next) =>
                  updateBoolean("auto_compaction_enabled", next)
                }
              />
            </div>
            <RuntimeNumberField
              spec={contextFields[3]}
              value={draft.max_steps}
              defaultValue={defaults.max_steps}
              disabled={saving}
              error={validation.fieldErrors.max_steps}
              onValueChange={(next) => updateNumber("max_steps", next)}
            />
            <RuntimeNumberField
              spec={contextFields[4]}
              value={draft.max_page_context_chars}
              defaultValue={defaults.max_page_context_chars}
              disabled={saving}
              error={validation.fieldErrors.max_page_context_chars}
              onValueChange={(next) =>
                updateNumber("max_page_context_chars", next)
              }
            />
          </RuntimeGroup>

          <RuntimeGroup
            slot={t("settings.agent.groupToolsSlot")}
            title={t("settings.agent.groupToolsTitle")}
            description={t("settings.agent.groupToolsDescription")}
          >
            <div className="runtime-field runtime-field--wide">
              <SwitchField
                label={t("settings.agent.toggleParallelToolsLabel")}
                hint={t("settings.agent.toggleParallelToolsHint")}
                checked={draft.parallel_tools_enabled}
                disabled={saving}
                onChange={(next) =>
                  updateBoolean("parallel_tools_enabled", next)
                }
              />
            </div>
            <div className="runtime-field runtime-field--wide">
              <SwitchField
                label={t("settings.agent.toggleMemoryApprovalLabel")}
                hint={t("settings.agent.toggleMemoryApprovalHint")}
                checked={draft.save_memory_requires_approval}
                disabled={saving}
                onChange={(next) =>
                  updateBoolean("save_memory_requires_approval", next)
                }
              />
            </div>
            <RuntimeNumberField
              spec={toolFields[0]}
              value={draft.max_parallel_tools}
              defaultValue={defaults.max_parallel_tools}
              disabled={saving}
              error={validation.fieldErrors.max_parallel_tools}
              onValueChange={(next) => updateNumber("max_parallel_tools", next)}
            />
            <RuntimeNumberField
              spec={toolFields[1]}
              value={draft.max_tool_calls_per_turn}
              defaultValue={defaults.max_tool_calls_per_turn}
              disabled={saving}
              error={validation.fieldErrors.max_tool_calls_per_turn}
              onValueChange={(next) =>
                updateNumber("max_tool_calls_per_turn", next)
              }
            />
            <RuntimeNumberField
              spec={toolFields[2]}
              value={draft.max_tool_result_chars}
              defaultValue={defaults.max_tool_result_chars}
              disabled={saving}
              error={validation.fieldErrors.max_tool_result_chars}
              onValueChange={(next) =>
                updateNumber("max_tool_result_chars", next)
              }
            />
          </RuntimeGroup>

          <RuntimeGroup
            slot={t("settings.agent.groupCompactionSlot")}
            title={t("settings.agent.groupCompactionTitle")}
            description={t("settings.agent.groupCompactionDescription")}
            advanced
          >
            <RuntimeNumberField
              spec={compactionFields[0]}
              value={draft.max_compaction_summary_chars}
              defaultValue={defaults.max_compaction_summary_chars}
              disabled={saving}
              error={validation.fieldErrors.max_compaction_summary_chars}
              onValueChange={(next) =>
                updateNumber("max_compaction_summary_chars", next)
              }
            />
            <RuntimeNumberField
              spec={compactionFields[1]}
              value={draft.max_compaction_last_user_chars}
              defaultValue={defaults.max_compaction_last_user_chars}
              disabled={saving}
              error={validation.fieldErrors.max_compaction_last_user_chars}
              onValueChange={(next) =>
                updateNumber("max_compaction_last_user_chars", next)
              }
            />
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
