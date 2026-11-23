import { Badge } from "../../component/Badge";
import { Button } from "../../component/Button";
import { Icon } from "../../component/Icon";
import { Panel } from "../../component/Panel";
import { useGetMyModelAssignment } from "../../generated-apis-types";
import type {
  ModelAssignmentSchema,
  ModelPricingSchema,
} from "../../generated-apis-types/schemas";
import {
  useApiErrorMessage,
  useI18n,
  type TranslationKey,
} from "../../i18n";

const WARNING_KEYS: Readonly<Record<string, TranslationKey>> = {
  unknown_model: "core.settings.model.warningUnknownModel",
  provider_family_mismatch: "core.settings.model.warningFamilyMismatch",
  window_above_catalog: "core.settings.model.warningWindowAboveCatalog",
  long_prompt_step: "core.settings.model.warningLongPromptStep",
  aux_inherited_from_primary: "core.settings.model.warningAuxInherited",
};

const DEGRADED_KEYS: Readonly<Record<string, TranslationKey>> = {
  no_active_provider: "core.settings.model.degradedNoProvider",
  provider_inactive: "core.settings.model.degradedProviderInactive",
  aux_no_active_provider: "core.settings.model.degradedAuxNoProvider",
  invalid_threshold: "core.settings.model.degradedInvalidThreshold",
};

function pricingLabel(
  pricing: ModelPricingSchema | null,
  t: (key: TranslationKey, vars?: Record<string, string>) => string,
): string {
  if (pricing === null) {
    return t("core.settings.model.pricingUnpriced");
  }
  return t("core.settings.model.pricing", {
    input: String(pricing.input),
    output: String(pricing.output),
  });
}

interface AssignmentSlotProps {
  readonly slot: "primary" | "auxiliary";
  readonly assignment: ModelAssignmentSchema;
}

/** One read-only endpoint slot: label, model, effort, tier, and price. */
function AssignmentSlot({ slot, assignment }: AssignmentSlotProps) {
  const { t } = useI18n();
  const primary = slot === "primary";
  const inherited = assignment.warnings.includes(
    "aux_inherited_from_primary",
  );
  let label = assignment.chat_provider_label;
  if (!primary) {
    label = assignment.aux_provider_label;
    if (label === null && inherited) {
      label = assignment.chat_provider_label;
    }
  }
  const provider = primary
    ? assignment.effective_chat_provider
    : assignment.effective_aux_provider;
  const model = primary
    ? assignment.effective_chat_model
    : assignment.effective_aux_model;
  const effort = primary
    ? assignment.effective_chat_effort
    : assignment.effective_aux_effort;
  const tier = primary ? assignment.chat_tier : assignment.aux_tier;
  const pricing = primary ? assignment.chat_pricing : assignment.aux_pricing;

  return (
    <section className="model-settings__slot">
      <header className="model-settings__slot-head">
        <h3>
          {primary
            ? t("core.settings.model.primary")
            : t("core.settings.model.auxiliary")}
        </h3>
        <Badge tone={tier === null ? "ochre" : "moss"}>
          {tier ?? t("core.settings.model.tierUnpriced")}
        </Badge>
        {!primary && inherited ? (
          <Badge tone="neutral">{t("core.settings.model.inherited")}</Badge>
        ) : null}
      </header>
      <dl className="meta-grid">
        <div className="meta-item">
          <dt className="meta-key">{t("core.settings.model.endpoint")}</dt>
          <dd className="meta-value">
            {label ?? t("core.settings.model.noEndpoint")}
          </dd>
        </div>
        <div className="meta-item">
          <dt className="meta-key">{t("core.settings.model.provider")}</dt>
          <dd className="meta-value">
            <code>{provider}</code>
          </dd>
        </div>
        <div className="meta-item">
          <dt className="meta-key">{t("core.settings.model.model")}</dt>
          <dd className="meta-value">
            <code>{model ?? "—"}</code>
          </dd>
        </div>
        <div className="meta-item">
          <dt className="meta-key">{t("core.settings.model.effort")}</dt>
          <dd className="meta-value">
            {effort ?? t("core.settings.model.effortEmpty")}
          </dd>
        </div>
        <div className="meta-item">
          <dt className="meta-key">{t("core.settings.model.price")}</dt>
          <dd className="meta-value">{pricingLabel(pricing, t)}</dd>
        </div>
      </dl>
    </section>
  );
}

/**
 * Read-only view of the signed-in account's model assignment.
 *
 * Every role sees the same facts: the two endpoints, their effective model and
 * effort, the advisory tier, and the effective context budget. There are no
 * controls; assignment stays with root on the Accounts page.
 */
export function ModelSettingsPanel() {
  const { t, formatDateTime, formatNumber } = useI18n();
  const apiErrorMessage = useApiErrorMessage();
  const query = useGetMyModelAssignment({ query: { staleTime: 60_000 } });

  if (query.isPending) {
    return (
      <Panel
        title={
          <span className="settings-panel__title">
            <Icon name="spark" size={16} />
            {t("core.settings.model.title")}
          </span>
        }
        className="settings-panel model-settings-panel"
      >
        <div
          className="runtime-loading"
          role="status"
          aria-busy="true"
          aria-label={t("core.settings.model.loadReadingAria")}
        >
          <span className="settings-skeleton settings-skeleton--line" />
          <span className="settings-skeleton settings-skeleton--line is-short" />
          <span className="settings-skeleton settings-skeleton--field" />
          <span className="settings-skeleton settings-skeleton--field" />
        </div>
      </Panel>
    );
  }

  if (query.isError || !query.data) {
    return (
      <Panel
        title={
          <span className="settings-panel__title">
            <Icon name="spark" size={16} />
            {t("core.settings.model.title")}
          </span>
        }
        className="settings-panel model-settings-panel"
      >
        <div className="settings-inline-error" role="alert">
          <Icon name="info" size={16} />
          <div>
            <strong>{t("core.settings.model.loadErrorTitle")}</strong>
            <p>{apiErrorMessage(query.error)}</p>
            <Button
              type="button"
              variant="ghost"
              size="sm"
              onClick={() => void query.refetch()}
              disabled={query.isFetching}
            >
              <Icon name="ring" size={14} />
              {query.isFetching
                ? t("core.common.retrying")
                : t("core.common.retry")}
            </Button>
          </div>
        </div>
      </Panel>
    );
  }

  const assignment = query.data;
  const unassigned = assignment.source === "unassigned";

  return (
    <Panel
      title={
        <span className="settings-panel__title">
          <Icon name="spark" size={16} />
          {t("core.settings.model.title")}
        </span>
      }
      action={
        <Badge tone={unassigned ? "ochre" : "moss"} dot>
          {unassigned
            ? t("core.settings.model.unassignedBadge")
            : t("core.settings.model.adminNote")}
        </Badge>
      }
      className="settings-panel model-settings-panel"
    >
      <p className="settings-lede">{t("core.settings.model.lede")}</p>

      {assignment.degraded_reason ? (
        <p className="model-settings__degraded" role="status">
          <Icon name="info" size={14} />
          {DEGRADED_KEYS[assignment.degraded_reason]
            ? t(DEGRADED_KEYS[assignment.degraded_reason])
            : t("core.settings.model.degradedUnknown", {
                reason: assignment.degraded_reason,
              })}
        </p>
      ) : null}

      {unassigned ? (
        <div className="model-settings__unassigned">
          <strong>{t("core.settings.model.unassigned")}</strong>
          <p>{t("core.settings.model.unassignedHint")}</p>
        </div>
      ) : (
        <div className="model-settings__slots">
          <AssignmentSlot slot="primary" assignment={assignment} />
          <AssignmentSlot slot="auxiliary" assignment={assignment} />
        </div>
      )}

      <section
        className="model-settings__budget"
        aria-label={t("core.settings.model.budgetTitle")}
      >
        <h3>{t("core.settings.model.budgetTitle")}</h3>
        <dl className="meta-grid">
          <div className="meta-item">
            <dt className="meta-key">
              {t("core.settings.model.budgetContext")}
            </dt>
            <dd className="meta-value">
              {assignment.effective_context_window_tokens === null
                ? t("core.settings.model.deploymentDefault")
                : formatNumber(assignment.effective_context_window_tokens)}
            </dd>
          </div>
          <div className="meta-item">
            <dt className="meta-key">
              {t("core.settings.model.budgetThreshold")}
            </dt>
            <dd className="meta-value">
              {assignment.effective_compaction_threshold_tokens === null
                ? t("core.settings.model.deploymentDefault")
                : formatNumber(
                    assignment.effective_compaction_threshold_tokens,
                  )}
            </dd>
          </div>
        </dl>
        {assignment.effective_context_window_tokens === null ||
        assignment.effective_compaction_threshold_tokens === null ? (
          <p className="settings-hint">
            {t("core.settings.model.budgetDefaultHint")}
          </p>
        ) : null}
      </section>

      {assignment.warnings.length > 0 ? (
        <section
          className="model-settings__warnings"
          aria-label={t("core.settings.model.warningsTitle")}
        >
          <h3>{t("core.settings.model.warningsTitle")}</h3>
          <ul>
            {assignment.warnings.map((warning) => (
              <li key={warning}>
                {WARNING_KEYS[warning]
                  ? t(WARNING_KEYS[warning])
                  : warning}
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      {unassigned ? null : (
        <p className="settings-hint">
          {t("core.settings.model.adminNote")}{" "}
          {t("core.settings.model.updated")}{" "}
          <time dateTime={assignment.updated_at}>
            {formatDateTime(assignment.updated_at)}
          </time>
        </p>
      )}
    </Panel>
  );
}
