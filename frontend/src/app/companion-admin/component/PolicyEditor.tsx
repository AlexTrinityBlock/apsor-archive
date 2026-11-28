import { useState } from "react";

import { Button } from "../../component/Button";
import { useToast } from "../../component/Toast";
import { useUpdateCompanionAccountPolicyAdmin } from "../../generated-apis-types";
import type { CompanionPolicyAdminSchema } from "../../generated-apis-types/schemas";
import { useApiErrorMessage, useI18n } from "../../i18n";
import { refLabel, useAdminRefresh } from "../hook/useAdminRefresh";

interface PolicyEditorProps {
  readonly userId: number;
  readonly policy: CompanionPolicyAdminSchema;
  readonly names: ReadonlyMap<string, string>;
}

/**
 * Root's layer of the companion choice: a default, an optional allowed set,
 * and an optional pin. The account's own pick is shown but never edited here.
 */
export function PolicyEditor({ userId, policy, names }: PolicyEditorProps) {
  const { t } = useI18n();
  const toast = useToast();
  const apiErrorMessage = useApiErrorMessage();
  const refresh = useAdminRefresh();
  const mutation = useUpdateCompanionAccountPolicyAdmin();
  const [defaultRef, setDefaultRef] = useState(policy.default_ref ?? "");
  const [restrict, setRestrict] = useState(policy.allowed_refs != null);
  const [allowed, setAllowed] = useState<readonly string[]>(
    policy.allowed_refs ?? policy.options,
  );
  const [allowCustom, setAllowCustom] = useState(policy.allow_custom ?? true);
  const [pinnedRef, setPinnedRef] = useState(
    policy.pin_enabled ? (policy.pinned_ref ?? "") : "",
  );

  const save = async () => {
    try {
      await mutation.mutateAsync({
        userId,
        data: {
          default_ref: defaultRef || null,
          allowed_refs: restrict ? [...allowed] : null,
          allow_custom: allowCustom,
          pinned_ref: pinnedRef || null,
          pin_enabled: Boolean(pinnedRef),
        },
      });
      refresh();
      toast.success(t("companionAdmin.world.saved"));
    } catch (caught) {
      toast.error(apiErrorMessage(caught, "companionAdmin.world.error"));
    }
  };

  return (
    <div className="ca-policy">
      <p className="ca-hint">{t("companionAdmin.policy.hint")}</p>
      <p className="ca-policy__user">
        {policy.user_selected
          ? t("companionAdmin.policy.userSelected", {
              name: refLabel(policy.user_selected, names),
            })
          : t("companionAdmin.policy.userSelectedNone")}
      </p>
      <div className="ca-row">
        <label className="ca-field">
          <span>{t("companionAdmin.policy.defaultLabel")}</span>
          <select
            className="input"
            value={defaultRef}
            onChange={(event) => setDefaultRef(event.target.value)}
          >
            <option value="">{t("companionAdmin.policy.defaultNone")}</option>
            {policy.options.map((ref) => (
              <option key={ref} value={ref}>
                {refLabel(ref, names)}
              </option>
            ))}
          </select>
        </label>
        <label className="ca-field">
          <span>{t("companionAdmin.policy.pinLabel")}</span>
          <select
            className="input"
            value={pinnedRef}
            onChange={(event) => setPinnedRef(event.target.value)}
          >
            <option value="">{t("companionAdmin.policy.pinNone")}</option>
            {policy.options.map((ref) => (
              <option key={ref} value={ref}>
                {refLabel(ref, names)}
              </option>
            ))}
          </select>
          <small>{t("companionAdmin.policy.pinHint")}</small>
        </label>
      </div>
      <fieldset className="ca-allowed">
        <legend>{t("companionAdmin.policy.allowedLabel")}</legend>
        <label className="ca-check">
          <input
            type="checkbox"
            checked={!restrict}
            onChange={(event) => setRestrict(!event.target.checked)}
          />
          {t("companionAdmin.policy.allowAll")}
        </label>
        {restrict ? (
          <div className="ca-chips">
            {policy.options
              .filter((ref) => ref.startsWith("preset:"))
              .map((ref) => {
                const on = allowed.includes(ref);
                return (
                  <button
                    key={ref}
                    type="button"
                    className={`ca-chip${on ? " is-on" : ""}`}
                    aria-pressed={on}
                    onClick={() =>
                      setAllowed(
                        on
                          ? allowed.filter((item) => item !== ref)
                          : [...allowed, ref],
                      )
                    }
                  >
                    {refLabel(ref, names)}
                  </button>
                );
              })}
          </div>
        ) : null}
        <label className="ca-check">
          <input
            type="checkbox"
            checked={allowCustom}
            onChange={(event) => setAllowCustom(event.target.checked)}
          />
          {t("companionAdmin.policy.allowCustom")}
        </label>
        <small className="ca-hint">
          {t("companionAdmin.policy.allowCustomHint")}
        </small>
      </fieldset>
      <div className="ca-actions">
        <Button
          type="button"
          variant="primary"
          size="sm"
          disabled={mutation.isPending}
          onClick={() => void save()}
        >
          {t("companionAdmin.policy.save")}
        </Button>
      </div>
    </div>
  );
}
