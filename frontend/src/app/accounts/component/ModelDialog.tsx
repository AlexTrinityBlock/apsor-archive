import { useId, useState } from "react";

import { Badge } from "../../component/Badge";
import { Button } from "../../component/Button";
import { Icon } from "../../component/Icon";
import {
  useListChatEndpoints,
  useListChatModels,
  useProbeChatEndpoint,
} from "../../generated-apis-types";
import type {
  AccountSchema,
  ChatEndpointSchema,
  ModelAssignmentSchema,
  ModelAssignmentUpdateSchema,
  ModelCatalogEntrySchema,
} from "../../generated-apis-types/schemas";
import { useApiErrorMessage, useI18n, type TranslationKey } from "../../i18n";
import { AccountDialog } from "./AccountDialog";
import "../accounts.css";

type Slot = "primary" | "auxiliary";

const CONTEXT_WINDOW_MIN = 8_000;
const CONTEXT_WINDOW_MAX = 2_000_000;
const THRESHOLD_MIN = 1_000;
const THRESHOLD_MAX = 1_000_000;

const EFFORT_HINTS: Readonly<Record<string, readonly string[]>> = {
  anthropic: ["low", "medium", "high", "xhigh", "max"],
  deepseek: ["low", "high", "max", "none"],
  "openai-compatible": [
    "none",
    "minimal",
    "low",
    "medium",
    "high",
    "xhigh",
    "max",
  ],
};

const EFFORT_HINT_KEYS: Readonly<Record<string, TranslationKey>> = {
  anthropic: "core.accounts.modelEffortHintsAnthropic",
  deepseek: "core.accounts.modelEffortHintsDeepSeek",
  "openai-compatible": "core.accounts.modelEffortHintsOpenAI",
};

const WARNING_KEYS: Readonly<Record<string, TranslationKey>> = {
  unknown_model: "core.accounts.modelWarningUnknownModel",
  provider_family_mismatch: "core.accounts.modelWarningFamilyMismatch",
  window_above_catalog: "core.accounts.modelWarningWindowAboveCatalog",
  long_prompt_step: "core.accounts.modelWarningLongPromptStep",
  aux_inherited_from_primary: "core.accounts.modelWarningAuxInherited",
};

const DEGRADED_KEYS: Readonly<Record<string, TranslationKey>> = {
  no_active_provider: "core.accounts.modelDegradedNoProvider",
  provider_inactive: "core.accounts.modelDegradedProviderInactive",
  aux_no_active_provider: "core.accounts.modelDegradedAuxNoProvider",
  invalid_threshold: "core.accounts.modelDegradedInvalidThreshold",
};

interface SlotTestState {
  readonly status: "idle" | "testing" | "ok" | "error";
  readonly fingerprint: string | null;
  readonly latencyMs: number | null;
  readonly resolvedModel: string | null;
  readonly detail: string | null;
}

const IDLE_TEST: SlotTestState = {
  status: "idle",
  fingerprint: null,
  latencyMs: null,
  resolvedModel: null,
  detail: null,
};

interface BudgetParse {
  readonly window: number | null;
  readonly threshold: number | null;
  readonly error: "range" | "order" | null;
}

interface InitialForm {
  readonly inheritedAux: boolean;
  readonly primaryEndpointId: string;
  readonly primaryModel: string;
  readonly primaryEffort: string;
  readonly auxEndpointId: string;
  readonly auxModel: string;
  readonly auxEffort: string;
  readonly windowText: string;
  readonly thresholdText: string;
  readonly initialPrimaryFingerprint: string;
  readonly initialAuxFingerprint: string;
}

function parseInteger(
  raw: string,
  min: number,
  max: number,
): number | null | "invalid" {
  const trimmed = raw.trim();
  if (trimmed.length === 0) {
    return null;
  }
  if (!/^\d+$/.test(trimmed)) {
    return "invalid";
  }
  const value = Number(trimmed);
  if (!Number.isSafeInteger(value) || value < min || value > max) {
    return "invalid";
  }
  return value;
}

function parseBudget(windowText: string, thresholdText: string): BudgetParse {
  const window = parseInteger(
    windowText,
    CONTEXT_WINDOW_MIN,
    CONTEXT_WINDOW_MAX,
  );
  const threshold = parseInteger(thresholdText, THRESHOLD_MIN, THRESHOLD_MAX);
  if (window === "invalid" || threshold === "invalid") {
    return { window: null, threshold: null, error: "range" };
  }
  if (window !== null && threshold !== null && threshold >= window) {
    return { window, threshold, error: "order" };
  }
  return { window, threshold, error: null };
}

function fingerprint(
  endpointId: string,
  model: string,
  effort: string,
): string {
  return `${endpointId}|${model.trim()}|${effort.trim()}`;
}

function numericText(value: number | null): string {
  return value === null ? "" : String(value);
}

function createInitialForm(assignment: ModelAssignmentSchema): InitialForm {
  const inheritedAux = assignment.warnings.includes(
    "aux_inherited_from_primary",
  );
  const primaryEndpointId = numericText(assignment.chat_provider_config_id);
  const primaryModel = assignment.effective_chat_model ?? "";
  const primaryEffort = assignment.effective_chat_effort ?? "";
  const auxEndpointId = inheritedAux
    ? primaryEndpointId
    : numericText(assignment.aux_provider_config_id);
  const auxModel = assignment.effective_aux_model ?? "";
  const auxEffort =
    assignment.effective_aux_effort ?? assignment.aux_reasoning_effort ?? "";
  return {
    inheritedAux,
    primaryEndpointId,
    primaryModel,
    primaryEffort,
    auxEndpointId,
    auxModel,
    auxEffort,
    windowText: numericText(assignment.effective_context_window_tokens),
    thresholdText: numericText(
      assignment.effective_compaction_threshold_tokens,
    ),
    initialPrimaryFingerprint: fingerprint(
      primaryEndpointId,
      primaryModel,
      primaryEffort,
    ),
    // An inherited auxiliary pair has no stored connection fingerprint, so the
    // server probes it on the first save that makes it explicit. Match that:
    // the prefilled slot counts as changed until it is tested.
    initialAuxFingerprint: inheritedAux
      ? ""
      : fingerprint(auxEndpointId, auxModel, auxEffort),
  };
}

function endpointLabel(endpoint: ChatEndpointSchema): string {
  return [endpoint.label, endpoint.provider, endpoint.base_url_host]
    .filter((part): part is string => Boolean(part))
    .join(" · ");
}

function effortHintKey(provider: string): TranslationKey {
  return EFFORT_HINT_KEYS[provider] ?? "core.accounts.modelEffortHintsOther";
}

function effortSuggestions(provider: string): readonly string[] {
  return EFFORT_HINTS[provider] ?? EFFORT_HINTS["openai-compatible"];
}

function modelOptionLabel(
  entry: ModelCatalogEntrySchema,
  priceLabel: (input: string, output: string) => string,
): string {
  const parts = [entry.display_name];
  if (entry.tier !== null) {
    parts.push(entry.tier);
  }
  if (entry.pricing !== null) {
    parts.push(
      priceLabel(
        String(entry.pricing.input),
        String(entry.pricing.output),
      ),
    );
  }
  return parts.join(" · ");
}

interface CanSaveInput {
  readonly submitting: boolean;
  readonly probing: boolean;
  readonly endpointsReady: boolean;
  readonly primaryComplete: boolean;
  readonly auxComplete: boolean;
  readonly budgetError: BudgetParse["error"];
  readonly primaryChanged: boolean;
  readonly primaryTested: boolean;
  readonly auxChanged: boolean;
  readonly auxTested: boolean;
}

function canSave(input: CanSaveInput): boolean {
  if (input.submitting || input.probing || !input.endpointsReady) {
    return false;
  }
  if (!input.primaryComplete || !input.auxComplete) {
    return false;
  }
  if (input.budgetError !== null) {
    return false;
  }
  if (input.primaryChanged && !input.primaryTested) {
    return false;
  }
  if (input.auxChanged && !input.auxTested) {
    return false;
  }
  return true;
}

interface SaveBlockInput {
  readonly endpointsReady: boolean;
  readonly primaryComplete: boolean;
  readonly auxComplete: boolean;
  readonly budgetError: BudgetParse["error"];
  readonly primaryNeedsTest: boolean;
  readonly auxNeedsTest: boolean;
  readonly probing: boolean;
}

/** Explain exactly what still blocks the save, in the order the user sees it. */
function resolveSaveBlock(input: SaveBlockInput): SaveBlockReason | null {
  if (!input.endpointsReady) {
    return { key: "core.accounts.modelSaveNeedsEndpoints" };
  }
  if (!input.primaryComplete) {
    return { key: "core.accounts.modelSaveNeedsPrimaryFields" };
  }
  if (!input.auxComplete) {
    return { key: "core.accounts.modelSaveNeedsAuxFields" };
  }
  if (input.budgetError === "order") {
    return { key: "core.accounts.modelSaveNeedsBudgetOrder" };
  }
  if (input.budgetError === "range") {
    return { key: "core.accounts.modelSaveNeedsBudgetRange" };
  }
  if (input.primaryNeedsTest && input.auxNeedsTest) {
    return { key: "core.accounts.modelSaveNeedsBothTests" };
  }
  if (input.primaryNeedsTest) {
    return { key: "core.accounts.modelSaveNeedsPrimaryTest" };
  }
  if (input.auxNeedsTest) {
    return { key: "core.accounts.modelSaveNeedsAuxTest" };
  }
  if (input.probing) {
    return { key: "core.accounts.modelSaveWaitingForTest" };
  }
  return null;
}

interface BuildPayloadInput {
  readonly primaryEndpointId: string;
  readonly primaryModel: string;
  readonly primaryEffort: string;
  readonly auxEndpointId: string;
  readonly auxModel: string;
  readonly auxEffort: string;
  readonly budget: BudgetParse;
}

interface BuildPayloadResult {
  readonly payload: ModelAssignmentUpdateSchema | null;
  readonly errorKey: TranslationKey | null;
}

function buildPayload(input: BuildPayloadInput): BuildPayloadResult {
  if (input.budget.error === "range") {
    return { payload: null, errorKey: "core.accounts.modelBudgetInvalid" };
  }
  if (input.budget.error === "order") {
    return { payload: null, errorKey: "core.accounts.modelThresholdOrder" };
  }
  return {
    payload: {
      chat_provider_config_id: Number(input.primaryEndpointId),
      chat_model: input.primaryModel.trim(),
      chat_reasoning_effort:
        input.primaryEffort.trim().length > 0
          ? input.primaryEffort.trim()
          : null,
      aux_provider_config_id: Number(input.auxEndpointId),
      aux_model: input.auxModel.trim(),
      aux_reasoning_effort:
        input.auxEffort.trim().length > 0 ? input.auxEffort.trim() : null,
      context_window_tokens: input.budget.window,
      compaction_threshold_tokens: input.budget.threshold,
    },
    errorKey: null,
  };
}

interface SlotTestLineProps {
  readonly test: SlotTestState;
}

/** The last probe result for one slot, never a blocking error. */
function SlotTestLine({ test }: SlotTestLineProps) {
  const { t, formatNumber } = useI18n();
  if (test.status === "testing") {
    return (
      <p className="accounts-model__test is-testing" role="status">
        <Icon name="ring" size={13} />
        {t("core.accounts.modelTesting")}
      </p>
    );
  }
  if (test.status === "ok") {
    return (
      <p className="accounts-model__test is-ok" role="status">
        <Icon name="check" size={13} />
        {test.resolvedModel
          ? t("core.accounts.modelTestOk", {
              latency: formatNumber(test.latencyMs ?? 0),
              model: test.resolvedModel,
            })
          : t("core.accounts.modelTestOkNoModel", {
              latency: formatNumber(test.latencyMs ?? 0),
            })}
      </p>
    );
  }
  if (test.status === "error") {
    return (
      <p className="accounts-model__test is-error" role="alert">
        <Icon name="info" size={13} />
        {t("core.accounts.modelTestFailed")}
        {test.detail ? ` — ${test.detail}` : null}
      </p>
    );
  }
  return null;
}

interface SlotFieldsProps {
  readonly idPrefix: string;
  readonly slot: Slot;
  readonly endpoints: readonly ChatEndpointSchema[];
  readonly catalog: readonly ModelCatalogEntrySchema[];
  readonly endpointId: string;
  readonly model: string;
  readonly effort: string;
  readonly endpointLabelOverride: string | null;
  readonly test: SlotTestState;
  readonly disabled: boolean;
  readonly testing: boolean;
  readonly effortRequired: boolean;
  readonly needsTest: boolean;
  readonly onEndpointChange: (value: string) => void;
  readonly onModelChange: (value: string) => void;
  readonly onEffortChange: (value: string) => void;
  readonly onTest: () => void;
}

/**
 * One endpoint/model/effort slot. Both model and effort are free text; the
 * datalists are suggestions only and never a closed list.
 */
function SlotFields({
  idPrefix,
  slot,
  endpoints,
  catalog,
  endpointId,
  model,
  effort,
  endpointLabelOverride,
  test,
  disabled,
  testing,
  effortRequired,
  needsTest,
  onEndpointChange,
  onModelChange,
  onEffortChange,
  onTest,
}: SlotFieldsProps) {
  const { t } = useI18n();
  const endpoint = endpoints.find((item) => String(item.id) === endpointId);
  const provider = endpoint?.provider ?? "";
  const trimmedModel = model.trim();
  const spec = catalog.find((entry) => entry.model === trimmedModel);
  const currentFingerprint = fingerprint(endpointId, model, effort);
  const visibleTest =
    test.fingerprint === currentFingerprint ? test : IDLE_TEST;
  const familyMismatch =
    spec !== undefined &&
    provider.length > 0 &&
    provider !== "none" &&
    provider !== "openai-compatible" &&
    spec.provider !== provider;
  const endpointFieldId = `${idPrefix}-${slot}-endpoint`;
  const modelFieldId = `${idPrefix}-${slot}-model`;
  const effortFieldId = `${idPrefix}-${slot}-effort`;
  const modelListId = `${idPrefix}-${slot}-models`;
  const effortListId = `${idPrefix}-${slot}-efforts`;
  const title =
    slot === "primary"
      ? t("core.accounts.modelSlotPrimaryTitle")
      : t("core.accounts.modelSlotAuxiliaryTitle");
  const description =
    slot === "primary"
      ? t("core.accounts.modelSlotPrimaryDescription")
      : t("core.accounts.modelSlotAuxiliaryDescription");
  const unavailableLabel = endpointLabelOverride ?? endpointId;

  return (
    <fieldset className="accounts-model__slot">
      <legend className="accounts-model__slot-title">{title}</legend>
      <p className="accounts-model__slot-description">{description}</p>

      <label className="field" htmlFor={endpointFieldId}>
        <span className="field-label">{t("core.accounts.modelEndpoint")}</span>
        <select
          id={endpointFieldId}
          className="select"
          value={endpointId}
          onChange={(event) => onEndpointChange(event.target.value)}
          disabled={disabled || endpoints.length === 0}
          data-autofocus={slot === "primary" ? true : undefined}
        >
          <option value="">{t("core.accounts.modelEndpointPlaceholder")}</option>
          {endpoints.map((item) => (
            <option key={item.id} value={String(item.id)}>
              {endpointLabel(item)}
            </option>
          ))}
          {endpointId.length > 0 && endpoint === undefined ? (
            <option value={endpointId}>
              {t("core.accounts.modelEndpointUnavailable", {
                label: unavailableLabel,
              })}
            </option>
          ) : null}
        </select>
      </label>

      <label className="field" htmlFor={modelFieldId}>
        <span className="field-label">{t("core.accounts.modelName")}</span>
        <input
          id={modelFieldId}
          className="input"
          type="text"
          value={model}
          list={modelListId}
          maxLength={128}
          spellCheck={false}
          autoCapitalize="none"
          autoComplete="off"
          disabled={disabled}
          onChange={(event) => onModelChange(event.target.value)}
        />
        <datalist id={modelListId}>
          {catalog.map((entry) => (
            <option
              key={entry.model}
              value={entry.model}
              label={modelOptionLabel(entry, (input, output) =>
                t("core.accounts.modelOptionPrice", { input, output }),
              )}
            />
          ))}
        </datalist>
        <small className="field-help">{t("core.accounts.modelNameHint")}</small>
        {trimmedModel.length > 0 && spec === undefined ? (
          <small className="accounts-model__advisory">
            {t("core.accounts.modelUnknown")}
          </small>
        ) : null}
        {familyMismatch && spec !== undefined ? (
          <small className="accounts-model__advisory">
            {t("core.accounts.modelFamilyMismatch", { family: spec.provider })}
          </small>
        ) : null}
      </label>

      <label className="field" htmlFor={effortFieldId}>
        <span className="field-label">{t("core.accounts.modelEffort")}</span>
        <input
          id={effortFieldId}
          className="input"
          type="text"
          value={effort}
          list={effortListId}
          maxLength={32}
          spellCheck={false}
          autoCapitalize="none"
          autoComplete="off"
          disabled={disabled}
          onChange={(event) => onEffortChange(event.target.value)}
        />
        <datalist id={effortListId}>
          {effortSuggestions(provider).map((suggestion) => (
            <option key={suggestion} value={suggestion} />
          ))}
        </datalist>
        <small className="field-help">{t(effortHintKey(provider))}</small>
        <small className="field-help">
          {slot === "primary"
            ? t("core.accounts.modelPrimaryEffortEmpty")
            : t("core.accounts.modelEffortHint")}
        </small>
      </label>

      <div className="accounts-model__test-row">
        <Button
          type="button"
          variant="secondary"
          size="sm"
          onClick={onTest}
          disabled={
            disabled ||
            testing ||
            endpointId.length === 0 ||
            trimmedModel.length === 0 ||
            (effortRequired && effort.trim().length === 0)
          }
        >
          <Icon name="spark" size={13} />
          {visibleTest.status === "testing"
            ? t("core.accounts.modelTesting")
            : t("core.accounts.modelTest")}
        </Button>
        <span
          className={`accounts-model__test-hint${
            needsTest ? " accounts-model__test-hint--required" : ""
          }`}
        >
          {needsTest
            ? t("core.accounts.modelTestRequired")
            : t("core.accounts.modelTestHint")}
        </span>
      </div>
      <SlotTestLine test={visibleTest} />
    </fieldset>
  );
}

/** Stored warnings and degradation, always advisory and never blocking. */
function AssignmentNotices({
  assignment,
}: {
  readonly assignment: ModelAssignmentSchema;
}) {
  const { t } = useI18n();
  return (
    <>
      {assignment.degraded_reason ? (
        <p className="accounts-model__degraded" role="status">
          <Icon name="info" size={14} />
          {DEGRADED_KEYS[assignment.degraded_reason]
            ? t(DEGRADED_KEYS[assignment.degraded_reason])
            : t("core.accounts.modelDegradedUnknown", {
                reason: assignment.degraded_reason,
              })}
        </p>
      ) : null}
      {assignment.warnings.some(
        (warning) => warning !== "aux_inherited_from_primary",
      ) ? (
        <ul
          className="accounts-model__warnings"
          aria-label={t("core.accounts.modelWarningsTitle")}
        >
          {assignment.warnings
            .filter((warning) => warning !== "aux_inherited_from_primary")
            .map((warning) => (
              <li key={warning}>
                {WARNING_KEYS[warning] ? t(WARNING_KEYS[warning]) : warning}
              </li>
            ))}
        </ul>
      ) : null}
    </>
  );
}

interface BudgetSectionProps {
  readonly idPrefix: string;
  readonly windowText: string;
  readonly thresholdText: string;
  readonly budget: BudgetParse;
  readonly disabled: boolean;
  readonly onWindowChange: (value: string) => void;
  readonly onThresholdChange: (value: string) => void;
}

/** Context-window and compaction-threshold fields for one account. */
function BudgetSection({
  idPrefix,
  windowText,
  thresholdText,
  budget,
  disabled,
  onWindowChange,
  onThresholdChange,
}: BudgetSectionProps) {
  const { t, formatNumber } = useI18n();
  let percent = 0;
  if (
    budget.window !== null &&
    budget.threshold !== null &&
    budget.window > 0
  ) {
    percent = Math.min(
      100,
      Math.round((budget.threshold / budget.window) * 100),
    );
  }
  return (
    <section
      className="accounts-model__budget"
      aria-labelledby={`${idPrefix}-budget-title`}
    >
      <div className="accounts-model__budget-head">
        <h3 id={`${idPrefix}-budget-title`}>
          {t("core.accounts.modelBudgetTitle")}
        </h3>
        <Badge tone={budget.error === null ? "neutral" : "ochre"}>
          {t("core.accounts.modelBudgetPercent", {
            percent: formatNumber(percent),
          })}
        </Badge>
      </div>
      <p className="accounts-model__budget-description">
        {t("core.accounts.modelBudgetDescription")}
      </p>
      <div className="accounts-model__budget-grid">
        <label className="field" htmlFor={`${idPrefix}-window`}>
          <span className="field-label">
            {t("core.accounts.modelContextWindow")}
          </span>
          <input
            id={`${idPrefix}-window`}
            className="input"
            type="number"
            inputMode="numeric"
            min={CONTEXT_WINDOW_MIN}
            max={CONTEXT_WINDOW_MAX}
            step={1000}
            value={windowText}
            disabled={disabled}
            onChange={(event) => onWindowChange(event.target.value)}
          />
          <small className="field-help">
            {t("core.accounts.modelContextWindowHint")}
          </small>
          {budget.error === "range" ? (
            <small className="accounts-model__field-error">
              {t("core.accounts.modelBudgetInvalid")}
            </small>
          ) : null}
        </label>
        <label className="field" htmlFor={`${idPrefix}-threshold`}>
          <span className="field-label">
            {t("core.accounts.modelCompactionThreshold")}
          </span>
          <input
            id={`${idPrefix}-threshold`}
            className={
              budget.error === "order"
                ? "input accounts-model__input--invalid"
                : "input"
            }
            type="number"
            inputMode="numeric"
            min={THRESHOLD_MIN}
            max={THRESHOLD_MAX}
            step={1000}
            value={thresholdText}
            disabled={disabled}
            aria-invalid={budget.error === "order" ? true : undefined}
            onChange={(event) => onThresholdChange(event.target.value)}
          />
          <small className="field-help">
            {t("core.accounts.modelThresholdHint")}
          </small>
          {budget.error === "range" ? (
            <small className="accounts-model__field-error">
              {t("core.accounts.modelBudgetInvalid")}
            </small>
          ) : null}
          {budget.error === "order" ? (
            <small className="accounts-model__field-error">
              {t("core.accounts.modelThresholdOrder")}
            </small>
          ) : null}
        </label>
      </div>
      <p className="accounts-model__budget-hint">
        {t("core.accounts.modelCostHint")}
      </p>
    </section>
  );
}

interface ResetSectionProps {
  readonly name: string;
  readonly submitting: boolean;
  readonly confirming: boolean;
  readonly onRequest: () => void;
  readonly onCancel: () => void;
  readonly onConfirm: () => void;
}

/** Destructive assignment reset with the shared confirm pattern. */
function ResetSection({
  name,
  submitting,
  confirming,
  onRequest,
  onCancel,
  onConfirm,
}: ResetSectionProps) {
  const { t } = useI18n();
  return (
    <section
      className="accounts-model__danger"
      aria-label={t("core.accounts.modelResetTitle")}
    >
      <div className="accounts-model__danger-copy">
        <strong>{t("core.accounts.modelResetTitle")}</strong>
        <small>{t("core.accounts.modelResetDescription")}</small>
      </div>
      {confirming ? (
        <div className="accounts-model__confirm" role="alert">
          <p>
            <Icon name="info" size={15} />
            {t("core.accounts.modelResetConfirm", { name })}
          </p>
          <div className="accounts-model__confirm-actions">
            <Button
              type="button"
              variant="danger"
              size="sm"
              onClick={onConfirm}
              disabled={submitting}
            >
              {submitting
                ? t("core.accounts.modelResetting")
                : t("core.accounts.modelResetConfirmAction")}
            </Button>
            <Button
              type="button"
              variant="ghost"
              size="sm"
              onClick={onCancel}
              disabled={submitting}
            >
              {t("core.accounts.modelResetCancel")}
            </Button>
          </div>
        </div>
      ) : (
        <Button
          type="button"
          variant="danger"
          size="sm"
          onClick={onRequest}
          disabled={submitting}
        >
          {t("core.accounts.modelReset")}
        </Button>
      )}
    </section>
  );
}

interface SaveBlockReason {
  readonly key: TranslationKey;
  readonly params?: Record<string, string>;
}

interface DialogFeedbackProps {
  readonly localError: string | null;
  readonly error: string | null;
  readonly blockReason: SaveBlockReason | null;
}

/** Local validation, server rejection, or the specific save blocker. */
function DialogFeedback({
  localError,
  error,
  blockReason,
}: DialogFeedbackProps) {
  const { t } = useI18n();
  if (localError || error) {
    return (
      <p className="accounts-form__error" role="alert">
        <Icon name="info" size={15} />
        {localError ?? error}
      </p>
    );
  }
  if (blockReason) {
    return (
      <p className="accounts-model__save-note" role="status">
        <Icon name="info" size={14} />
        {t(blockReason.key, blockReason.params)}
      </p>
    );
  }
  return null;
}

interface ModelDialogProps {
  readonly account: AccountSchema;
  readonly assignment: ModelAssignmentSchema;
  readonly onClose: () => void;
  readonly onSave: (payload: ModelAssignmentUpdateSchema) => void;
  readonly onReset: () => void;
  readonly submitting: boolean;
  readonly error: string | null;
  readonly inline?: boolean;
}

/**
 * Root editor for one account's two model endpoints.
 *
 * Save stays disabled until every changed slot has a successful probe for its
 * current endpoint/model/effort fingerprint. Budget-only edits need no probe,
 * because the fingerprint excludes the context window and threshold. The
 * server re-probes changed slots by its own fingerprint, so this check is UX
 * only and never the enforcement.
 */
export function ModelDialog({
  account,
  assignment,
  onClose,
  onSave,
  onReset,
  submitting,
  error,
  inline = false,
}: ModelDialogProps) {
  const { t } = useI18n();
  const apiErrorMessage = useApiErrorMessage();
  const idPrefix = useId();
  const initial = createInitialForm(assignment);

  const [primaryEndpointId, setPrimaryEndpointId] = useState(
    initial.primaryEndpointId,
  );
  const [primaryModel, setPrimaryModel] = useState(initial.primaryModel);
  const [primaryEffort, setPrimaryEffort] = useState(initial.primaryEffort);
  const [auxEndpointId, setAuxEndpointId] = useState(initial.auxEndpointId);
  const [auxModel, setAuxModel] = useState(initial.auxModel);
  const [auxEffort, setAuxEffort] = useState(initial.auxEffort);
  const [windowText, setWindowText] = useState(initial.windowText);
  const [thresholdText, setThresholdText] = useState(initial.thresholdText);
  const [primaryTest, setPrimaryTest] = useState<SlotTestState>(IDLE_TEST);
  const [auxTest, setAuxTest] = useState<SlotTestState>(IDLE_TEST);
  const [localError, setLocalError] = useState<string | null>(null);
  const [confirmingReset, setConfirmingReset] = useState(false);

  const endpointsQuery = useListChatEndpoints({
    query: { retry: false, staleTime: 60_000 },
  });
  const catalogQuery = useListChatModels({
    query: { retry: false, staleTime: 300_000 },
  });
  const probe = useProbeChatEndpoint();

  const endpoints = (endpointsQuery.data?.items ?? []).filter(
    (item) =>
      item.is_active && item.provider !== "none" && item.configured,
  );
  const catalog = catalogQuery.data?.items ?? [];
  const name = account.display_name ?? account.username;
  const budget = parseBudget(windowText, thresholdText);

  // A legacy account with no assignment opens with both slots empty. Derive
  // the deployment's first usable endpoint as a fallback value instead of
  // writing state during render; the first edit or test promotes it into the
  // controlled fields.
  const fallbackEndpoint =
    assignment.chat_provider_config_id === null ? endpoints[0] : undefined;
  const fallbackEndpointId = fallbackEndpoint
    ? String(fallbackEndpoint.id)
    : "";
  const fallbackModel = fallbackEndpoint?.model ?? "";
  const primaryEndpointValue = primaryEndpointId || fallbackEndpointId;
  const primaryModelValue = primaryModel || fallbackModel;
  const auxEndpointValue = auxEndpointId || fallbackEndpointId;
  const auxModelValue = auxModel || fallbackModel;

  const primaryFingerprint = fingerprint(
    primaryEndpointValue,
    primaryModelValue,
    primaryEffort,
  );
  const auxFingerprint = fingerprint(
    auxEndpointValue,
    auxModelValue,
    auxEffort,
  );
  const primaryChanged =
    primaryFingerprint !== initial.initialPrimaryFingerprint;
  const auxChanged = auxFingerprint !== initial.initialAuxFingerprint;
  const primaryTested =
    !primaryChanged ||
    (primaryTest.status === "ok" &&
      primaryTest.fingerprint === primaryFingerprint);
  const auxTested =
    !auxChanged ||
    (auxTest.status === "ok" && auxTest.fingerprint === auxFingerprint);
  const endpointsReady = !endpointsQuery.isPending && !endpointsQuery.isError;
  const primaryComplete =
    primaryEndpointValue.length > 0 && primaryModelValue.trim().length > 0;
  const auxComplete =
    auxEndpointValue.length > 0 &&
    auxModelValue.trim().length > 0;
  const saveAllowed = canSave({
    submitting,
    probing: probe.isPending,
    endpointsReady,
    primaryComplete,
    auxComplete,
    budgetError: budget.error,
    primaryChanged,
    primaryTested,
    auxChanged,
    auxTested,
  });
  const primaryNeedsTest = primaryChanged && !primaryTested;
  const auxNeedsTest = auxChanged && !auxTested;
  const saveBlock = resolveSaveBlock({
    endpointsReady,
    primaryComplete,
    auxComplete,
    budgetError: budget.error,
    primaryNeedsTest,
    auxNeedsTest,
    probing: probe.isPending,
  });
  const saveReasonId = `${idPrefix}-save-reason`;

  const setSlotTest = (slot: Slot, next: SlotTestState) => {
    if (slot === "primary") {
      setPrimaryTest(next);
    } else {
      setAuxTest(next);
    }
  };

  const runTest = async (slot: Slot) => {
    const endpointId =
      slot === "primary" ? primaryEndpointValue : auxEndpointValue;
    const model = slot === "primary" ? primaryModelValue : auxModelValue;
    const effort = slot === "primary" ? primaryEffort : auxEffort;
    const slotFingerprint = fingerprint(endpointId, model, effort);
    setLocalError(null);
    setSlotTest(slot, {
      status: "testing",
      fingerprint: slotFingerprint,
      latencyMs: null,
      resolvedModel: null,
      detail: null,
    });
    try {
      const result = await probe.mutateAsync({
        providerConfigId: Number(endpointId),
        data: {
          model: model.trim(),
          reasoning_effort: effort.trim().length > 0 ? effort.trim() : null,
          purpose: slot,
        },
      });
      setSlotTest(slot, {
        status: result.ok ? "ok" : "error",
        fingerprint: slotFingerprint,
        latencyMs: result.latency_ms,
        resolvedModel: result.resolved_model,
        detail: result.detail,
      });
    } catch (caught) {
      setSlotTest(slot, {
        status: "error",
        fingerprint: slotFingerprint,
        latencyMs: null,
        resolvedModel: null,
        detail: apiErrorMessage(caught, "core.accounts.modelTestError"),
      });
    }
  };

  const submit = () => {
    setLocalError(null);
    const built = buildPayload({
      primaryEndpointId: primaryEndpointValue,
      primaryModel: primaryModelValue,
      primaryEffort,
      auxEndpointId: auxEndpointValue,
      auxModel: auxModelValue,
      auxEffort,
      budget,
    });
    if (built.payload === null || built.errorKey !== null) {
      setLocalError(
        built.errorKey === null ? null : t(built.errorKey),
      );
      return;
    }
    if (!saveAllowed) {
      return;
    }
    onSave(built.payload);
  };

  return (
    <AccountDialog
      eyebrow={t("core.accounts.eyebrow")}
      title={t("core.accounts.modelDialogTitle")}
      description={t("core.accounts.modelDialogDescription", { name })}
      onClose={onClose}
      busy={submitting}
      size="md"
      inline={inline}
      actions={
        <>
          {saveBlock ? (
            <span
              id={saveReasonId}
              className="accounts-model__save-reason"
              role="status"
            >
              <Icon name="info" size={14} />
              {t(saveBlock.key, saveBlock.params)}
            </span>
          ) : null}
          <Button
            type="button"
            variant="ghost"
            onClick={onClose}
            disabled={submitting}
          >
            {t("core.accounts.modelClose")}
          </Button>
          <Button
            type="button"
            variant="ink"
            onClick={submit}
            disabled={!saveAllowed}
            aria-describedby={saveBlock ? saveReasonId : undefined}
            title={saveBlock ? t(saveBlock.key, saveBlock.params) : undefined}
          >
            {submitting
              ? t("core.accounts.modelSaving")
              : t("core.accounts.modelSave")}
          </Button>
        </>
      }
    >
      <p className="accounts-model__hint">
        {t("core.accounts.modelDialogHelp")}
      </p>

      <AssignmentNotices assignment={assignment} />

      {endpointsQuery.isError ? (
        <p className="accounts-form__error" role="alert">
          <Icon name="info" size={15} />
          {t("core.accounts.modelEndpointError")}
        </p>
      ) : null}
      {!endpointsQuery.isPending &&
      !endpointsQuery.isError &&
      endpoints.length === 0 ? (
        <p className="accounts-model__advisory">
          {t("core.accounts.modelEndpointEmpty")}
        </p>
      ) : null}

      <div className="accounts-model__slots">
        <SlotFields
          idPrefix={idPrefix}
          slot="primary"
          endpoints={endpoints}
          catalog={catalog}
          endpointId={primaryEndpointValue}
          model={primaryModelValue}
          effort={primaryEffort}
          endpointLabelOverride={assignment.chat_provider_label}
          test={primaryTest}
          disabled={submitting}
          testing={probe.isPending}
          effortRequired={false}
          needsTest={primaryNeedsTest}
          onEndpointChange={(value) => {
            setPrimaryEndpointId(value);
            setLocalError(null);
          }}
          onModelChange={(value) => {
            setPrimaryModel(value);
            setLocalError(null);
          }}
          onEffortChange={(value) => {
            setPrimaryEffort(value);
            setLocalError(null);
          }}
          onTest={() => void runTest("primary")}
        />

        <SlotFields
          idPrefix={idPrefix}
          slot="auxiliary"
          endpoints={endpoints}
          catalog={catalog}
          endpointId={auxEndpointValue}
          model={auxModelValue}
          effort={auxEffort}
          endpointLabelOverride={
            initial.inheritedAux
              ? assignment.chat_provider_label
              : assignment.aux_provider_label
          }
          test={auxTest}
          disabled={submitting}
          testing={probe.isPending}
          effortRequired={false}
          needsTest={auxNeedsTest}
          onEndpointChange={(value) => {
            setAuxEndpointId(value);
            setLocalError(null);
          }}
          onModelChange={(value) => {
            setAuxModel(value);
            setLocalError(null);
          }}
          onEffortChange={(value) => {
            setAuxEffort(value);
            setLocalError(null);
          }}
          onTest={() => void runTest("auxiliary")}
        />
      </div>

      {initial.inheritedAux ? (
        <p className="accounts-model__advisory">
          {t("core.accounts.modelAuxInherited")}
        </p>
      ) : null}

      <BudgetSection
        idPrefix={idPrefix}
        windowText={windowText}
        thresholdText={thresholdText}
        budget={budget}
        disabled={submitting}
        onWindowChange={(value) => {
          setWindowText(value);
          setLocalError(null);
        }}
        onThresholdChange={(value) => {
          setThresholdText(value);
          setLocalError(null);
        }}
      />

      <ResetSection
        name={name}
        submitting={submitting}
        confirming={confirmingReset}
        onRequest={() => setConfirmingReset(true)}
        onCancel={() => setConfirmingReset(false)}
        onConfirm={() => {
          setConfirmingReset(false);
          onReset();
        }}
      />

      <DialogFeedback
        localError={localError}
        error={error}
        blockReason={saveBlock}
      />
    </AccountDialog>
  );
}
