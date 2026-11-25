import {
  useEffect,
  useId,
  useRef,
  useState,
  type CSSProperties,
  type FormEvent,
} from "react";

import { useI18n, type Translate, type TranslationKey } from "../../i18n";
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
  readonly compaction_threshold_tokens: number;
  readonly context_window_tokens: number;
  readonly max_parallel_tools: number;
  readonly max_tool_result_chars: number;
  readonly max_page_context_chars: number;
  readonly max_compaction_summary_chars: number;
  readonly max_compaction_last_user_chars: number;
  readonly auto_compaction_enabled: boolean;
  readonly parallel_tools_enabled: boolean;
  readonly save_memory_requires_approval: boolean;
  readonly chat_attachment_staged_ttl_hours: number;
  readonly chat_attachment_cleanup_interval_seconds: number;
  readonly max_plot_points: number;
  readonly max_plot_bytes: number;
  readonly max_plot_nodes: number;
  readonly compaction_prompt: string;
  readonly compaction_max_output_tokens: number;
  readonly model_escalation_enabled: boolean;
  readonly agent_max_output_tokens: number;
}

/** Props for the presentational runtime panel; persistence stays with the page. */
export interface AgentRuntimePanelProps {
  readonly values: AgentRuntimeValues;
  readonly defaults: AgentRuntimeValues;
  readonly source: "database" | "default";
  readonly updatedAt: string | null;
  readonly saving: boolean;
  readonly error: string | null;
  readonly errorCode: string | null;
  readonly onSave: (values: AgentRuntimeValues) => void;
  readonly onReset: () => void;
  readonly className?: string;
}

type BooleanField =
  | "auto_compaction_enabled"
  | "parallel_tools_enabled"
  | "save_memory_requires_approval"
  | "model_escalation_enabled";

type NumericField = Exclude<
  keyof AgentRuntimeValues,
  BooleanField | "compaction_prompt"
>;

type DraftValues = { readonly [Key in NumericField]: string } & {
  readonly [Key in BooleanField]: boolean;
} & { readonly compaction_prompt: string };

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
    key: "compaction_threshold_tokens",
    labelKey: "settings.agent.fieldThresholdLabel",
    unitKey: "settings.agent.fieldThresholdUnit",
    min: 1000,
    max: 1000000,
    step: 5000,
    hintKey: "settings.agent.fieldThresholdHint",
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
  {
    key: "agent_max_output_tokens",
    labelKey: "settings.agent.fieldAgentMaxOutputLabel",
    unitKey: "settings.agent.fieldAgentMaxOutputUnit",
    min: 256,
    max: 131072,
    step: 256,
    hintKey: "settings.agent.fieldAgentMaxOutputHint",
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
    key: "max_tool_result_chars",
    labelKey: "settings.agent.fieldToolResultCharsLabel",
    unitKey: "settings.agent.fieldToolResultCharsUnit",
    min: 1000,
    max: 200000,
    step: 5000,
    hintKey: "settings.agent.fieldToolResultCharsHint",
  },
  {
    key: "max_plot_points",
    labelKey: "settings.agent.fieldPlotPointsLabel",
    unitKey: "settings.agent.fieldPlotPointsUnit",
    min: 100,
    max: 50000,
    step: 100,
    hintKey: "settings.agent.fieldPlotPointsHint",
  },
  {
    key: "max_plot_bytes",
    labelKey: "settings.agent.fieldPlotBytesLabel",
    unitKey: "settings.agent.fieldPlotBytesUnit",
    min: 10000,
    max: 2000000,
    step: 10000,
    hintKey: "settings.agent.fieldPlotBytesHint",
  },
  {
    key: "max_plot_nodes",
    labelKey: "settings.agent.fieldPlotNodesLabel",
    unitKey: "settings.agent.fieldPlotNodesUnit",
    min: 1000,
    max: 500000,
    step: 1000,
    hintKey: "settings.agent.fieldPlotNodesHint",
  },
];

const ATTACHMENT_FIELDS: readonly NumericFieldSpec[] = [
  {
    key: "chat_attachment_staged_ttl_hours",
    labelKey: "settings.agent.fieldStagedTtlLabel",
    unitKey: "settings.agent.fieldStagedTtlUnit",
    min: 1,
    max: 168,
    step: 1,
    hintKey: "settings.agent.fieldStagedTtlHint",
  },
  {
    key: "chat_attachment_cleanup_interval_seconds",
    labelKey: "settings.agent.fieldCleanupIntervalLabel",
    unitKey: "settings.agent.fieldCleanupIntervalUnit",
    min: 60,
    max: 86400,
    step: 60,
    hintKey: "settings.agent.fieldCleanupIntervalHint",
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
  {
    key: "compaction_max_output_tokens",
    labelKey: "settings.agent.fieldCompactionMaxOutputLabel",
    unitKey: "settings.agent.fieldCompactionMaxOutputUnit",
    min: 256,
    max: 16384,
    step: 256,
    hintKey: "settings.agent.fieldCompactionMaxOutputHint",
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
  ...ATTACHMENT_FIELDS,
  ...COMPACTION_FIELDS,
];

const VALUE_KEYS: readonly (keyof AgentRuntimeValues)[] = [
  "compaction_threshold_tokens",
  "context_window_tokens",
  "max_parallel_tools",
  "max_tool_result_chars",
  "max_page_context_chars",
  "max_compaction_summary_chars",
  "max_compaction_last_user_chars",
  "auto_compaction_enabled",
  "parallel_tools_enabled",
  "save_memory_requires_approval",
  "chat_attachment_staged_ttl_hours",
  "chat_attachment_cleanup_interval_seconds",
  "max_plot_points",
  "max_plot_bytes",
  "max_plot_nodes",
  "compaction_prompt",
  "compaction_max_output_tokens",
  "model_escalation_enabled",
  "agent_max_output_tokens",
];

function toDraft(values: AgentRuntimeValues): DraftValues {
  return {
    compaction_threshold_tokens: String(values.compaction_threshold_tokens),
    context_window_tokens: String(values.context_window_tokens),
    max_parallel_tools: String(values.max_parallel_tools),
    max_tool_result_chars: String(values.max_tool_result_chars),
    max_page_context_chars: String(values.max_page_context_chars),
    max_compaction_summary_chars: String(values.max_compaction_summary_chars),
    max_compaction_last_user_chars: String(values.max_compaction_last_user_chars),
    auto_compaction_enabled: values.auto_compaction_enabled,
    parallel_tools_enabled: values.parallel_tools_enabled,
    save_memory_requires_approval: values.save_memory_requires_approval,
    chat_attachment_staged_ttl_hours: String(
      values.chat_attachment_staged_ttl_hours,
    ),
    chat_attachment_cleanup_interval_seconds: String(
      values.chat_attachment_cleanup_interval_seconds,
    ),
    max_plot_points: String(values.max_plot_points),
    max_plot_bytes: String(values.max_plot_bytes),
    max_plot_nodes: String(values.max_plot_nodes),
    compaction_prompt: values.compaction_prompt,
    compaction_max_output_tokens: String(values.compaction_max_output_tokens),
    model_escalation_enabled: values.model_escalation_enabled,
    agent_max_output_tokens: String(values.agent_max_output_tokens),
  };
}

function fromDraft(draft: DraftValues): AgentRuntimeValues {
  return {
    compaction_threshold_tokens: Number(draft.compaction_threshold_tokens),
    context_window_tokens: Number(draft.context_window_tokens),
    max_parallel_tools: Number(draft.max_parallel_tools),
    max_tool_result_chars: Number(draft.max_tool_result_chars),
    max_page_context_chars: Number(draft.max_page_context_chars),
    max_compaction_summary_chars: Number(draft.max_compaction_summary_chars),
    max_compaction_last_user_chars: Number(draft.max_compaction_last_user_chars),
    auto_compaction_enabled: draft.auto_compaction_enabled,
    parallel_tools_enabled: draft.parallel_tools_enabled,
    save_memory_requires_approval: draft.save_memory_requires_approval,
    chat_attachment_staged_ttl_hours: Number(
      draft.chat_attachment_staged_ttl_hours,
    ),
    chat_attachment_cleanup_interval_seconds: Number(
      draft.chat_attachment_cleanup_interval_seconds,
    ),
    max_plot_points: Number(draft.max_plot_points),
    max_plot_bytes: Number(draft.max_plot_bytes),
    max_plot_nodes: Number(draft.max_plot_nodes),
    compaction_prompt: draft.compaction_prompt,
    compaction_max_output_tokens: Number(draft.compaction_max_output_tokens),
    model_escalation_enabled: draft.model_escalation_enabled,
    agent_max_output_tokens: Number(draft.agent_max_output_tokens),
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
      values.save_memory_requires_approval &&
    draft.model_escalation_enabled === values.model_escalation_enabled &&
    draft.compaction_prompt === values.compaction_prompt
  );
}

interface ValidationResult {
  readonly fieldErrors: Partial<Record<NumericField, string>>;
  readonly promptError: string | null;
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

  const prompt = draft.compaction_prompt;
  let promptError: string | null = null;
  if (prompt.trim().length === 0) {
    promptError = t("settings.agent.compactionPromptRequired");
  } else if (prompt.length > 20000) {
    promptError = t("settings.agent.compactionPromptMax", {
      count: formatNumber(prompt.length),
      max: formatNumber(20000),
    });
  } else if (!prompt.includes("{max_output_tokens}")) {
    promptError = t("settings.agent.compactionPromptPlaceholder", {
      placeholder: "{max_output_tokens}",
    });
  }

  const contextWindow = numbers.context_window_tokens;
  const threshold = numbers.compaction_threshold_tokens;
  if (
    contextWindow !== undefined &&
    threshold !== undefined &&
    threshold >= contextWindow &&
    fieldErrors.compaction_threshold_tokens === undefined
  ) {
    fieldErrors.compaction_threshold_tokens = t(
      "settings.runtime.errors.thresholdBelowContext",
      { context: formatNumber(contextWindow) },
    );
  }

  const plotPoints = numbers.max_plot_points;
  const plotNodes = numbers.max_plot_nodes;
  if (
    plotPoints !== undefined &&
    plotNodes !== undefined &&
    plotNodes < plotPoints &&
    fieldErrors.max_plot_nodes === undefined
  ) {
    fieldErrors.max_plot_nodes = t(
      "settings.runtime.errors.plotNodesAtLeastPoints",
      { points: formatNumber(plotPoints) },
    );
  }

  const hasErrors =
    Object.keys(fieldErrors).length > 0 || promptError !== null;
  return {
    fieldErrors,
    promptError,
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
  errorCode,
  onSave,
  onReset,
  className,
}: AgentRuntimePanelProps) {
  const { t, formatNumber } = useI18n();
  const promptFieldId = useId();
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
  const isInvalid =
    Object.keys(validation.fieldErrors).length > 0 ||
    validation.promptError !== null;
  const promptServerError =
    errorCode === "compaction_prompt_invalid" ? error : null;
  const promptError = validation.promptError ?? promptServerError;
  const canSave = isDirty && !isInvalid && !saving;

  const draftContext =
    positiveNumber(draft.context_window_tokens) ?? values.context_window_tokens;
  const draftThreshold =
    positiveNumber(draft.compaction_threshold_tokens) ??
    values.compaction_threshold_tokens;
  const thresholdPercent =
    draftContext > 0
      ? Math.min(100, Math.max(0, Math.round((draftThreshold / draftContext) * 100)))
      : 0;
  const headroom = Math.max(0, draftContext - draftThreshold);
  const budgetStyle = {
    "--runtime-budget-fill": `${thresholdPercent}%`,
  } as CSSProperties;

  const contextFields = CONTEXT_FIELDS.map((spec) => localizeSpec(spec, t));
  const toolFields = TOOL_FIELDS.map((spec) => localizeSpec(spec, t));
  const attachmentFields = ATTACHMENT_FIELDS.map((spec) =>
    localizeSpec(spec, t),
  );
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
      className={panelClassName}
    >
      <p className="settings-lede">{t("settings.agent.lede")}</p>

      <RuntimeStatus
        source={source}
        updatedAt={updatedAt}
        summary={t("settings.agent.statusSummary", {
          context: formatNumber(values.context_window_tokens),
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
              total: formatNumber(draftContext),
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
              spec={contextFields[2]}
              value={draft.max_page_context_chars}
              defaultValue={defaults.max_page_context_chars}
              disabled={saving}
              error={validation.fieldErrors.max_page_context_chars}
              onValueChange={(next) =>
                updateNumber("max_page_context_chars", next)
              }
            />
            <RuntimeNumberField
              spec={contextFields[3]}
              value={draft.agent_max_output_tokens}
              defaultValue={defaults.agent_max_output_tokens}
              disabled={saving}
              error={validation.fieldErrors.agent_max_output_tokens}
              onValueChange={(next) =>
                updateNumber("agent_max_output_tokens", next)
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
            <div className="runtime-field runtime-field--wide">
              <SwitchField
                label={t("settings.agent.toggleEscalationLabel")}
                hint={t("settings.agent.toggleEscalationHint")}
                checked={draft.model_escalation_enabled}
                disabled={saving}
                onChange={(next) =>
                  updateBoolean("model_escalation_enabled", next)
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
              value={draft.max_tool_result_chars}
              defaultValue={defaults.max_tool_result_chars}
              disabled={saving}
              error={validation.fieldErrors.max_tool_result_chars}
              onValueChange={(next) =>
                updateNumber("max_tool_result_chars", next)
              }
            />
            <RuntimeNumberField
              spec={toolFields[2]}
              value={draft.max_plot_points}
              defaultValue={defaults.max_plot_points}
              disabled={saving}
              error={validation.fieldErrors.max_plot_points}
              onValueChange={(next) => updateNumber("max_plot_points", next)}
            />
            <RuntimeNumberField
              spec={toolFields[3]}
              value={draft.max_plot_bytes}
              defaultValue={defaults.max_plot_bytes}
              disabled={saving}
              error={validation.fieldErrors.max_plot_bytes}
              onValueChange={(next) => updateNumber("max_plot_bytes", next)}
            />
            <RuntimeNumberField
              spec={toolFields[4]}
              value={draft.max_plot_nodes}
              defaultValue={defaults.max_plot_nodes}
              disabled={saving}
              error={validation.fieldErrors.max_plot_nodes}
              onValueChange={(next) => updateNumber("max_plot_nodes", next)}
            />
          </RuntimeGroup>

          <RuntimeGroup
            slot={t("settings.agent.groupAttachmentsSlot")}
            title={t("settings.agent.groupAttachmentsTitle")}
            description={t("settings.agent.groupAttachmentsDescription")}
          >
            <RuntimeNumberField
              spec={attachmentFields[0]}
              value={draft.chat_attachment_staged_ttl_hours}
              defaultValue={defaults.chat_attachment_staged_ttl_hours}
              disabled={saving}
              error={validation.fieldErrors.chat_attachment_staged_ttl_hours}
              onValueChange={(next) =>
                updateNumber("chat_attachment_staged_ttl_hours", next)
              }
            />
            <RuntimeNumberField
              spec={attachmentFields[1]}
              value={draft.chat_attachment_cleanup_interval_seconds}
              defaultValue={defaults.chat_attachment_cleanup_interval_seconds}
              disabled={saving}
              error={
                validation.fieldErrors.chat_attachment_cleanup_interval_seconds
              }
              onValueChange={(next) =>
                updateNumber("chat_attachment_cleanup_interval_seconds", next)
              }
            />
          </RuntimeGroup>

          <RuntimeGroup
            slot={t("settings.agent.groupCompactionSlot")}
            title={t("settings.agent.groupCompactionTitle")}
            description={t("settings.agent.groupCompactionDescription")}
            advanced
          >
            <div className="runtime-field runtime-field--wide">
              <label className="runtime-field__label" htmlFor={promptFieldId}>
                <span>{t("settings.agent.fieldCompactionPromptLabel")}</span>
                <span className="runtime-field__unit" aria-hidden="true">
                  {t("settings.agent.fieldCompactionPromptUnit")}
                </span>
              </label>
              <textarea
                id={promptFieldId}
                className={
                  promptError
                    ? "runtime-input runtime-textarea runtime-input--invalid"
                    : "runtime-input runtime-textarea"
                }
                value={draft.compaction_prompt}
                rows={8}
                spellCheck={false}
                dir="auto"
                disabled={saving}
                aria-invalid={promptError ? true : undefined}
                aria-describedby={`${promptFieldId}-hint${
                  promptError ? ` ${promptFieldId}-error` : ""
                }`}
                onChange={(event) =>
                  setDraft((current) => ({
                    ...current,
                    compaction_prompt: event.target.value,
                  }))
                }
              />
              <span className="runtime-field__hint" id={`${promptFieldId}-hint`}>
                {t("settings.agent.fieldCompactionPromptHint", {
                  placeholder: "{max_output_tokens}",
                })}
              </span>
              <span className="runtime-field__hint">
                {t("settings.agent.compactionPromptCount", {
                  count: formatNumber(draft.compaction_prompt.length),
                  max: formatNumber(20000),
                })}
              </span>
              {promptError ? (
                <span
                  className="runtime-field__error"
                  id={`${promptFieldId}-error`}
                >
                  {promptError}
                </span>
              ) : null}
            </div>
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
            <RuntimeNumberField
              spec={compactionFields[2]}
              value={draft.compaction_max_output_tokens}
              defaultValue={defaults.compaction_max_output_tokens}
              disabled={saving}
              error={validation.fieldErrors.compaction_max_output_tokens}
              onValueChange={(next) =>
                updateNumber("compaction_max_output_tokens", next)
              }
            />
          </RuntimeGroup>
        </div>

        {error && errorCode !== "compaction_prompt_invalid" ? (
          <RuntimeError message={error} />
        ) : null}

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
