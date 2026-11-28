import { useState } from "react";

import { Button } from "../../component/Button";
import type { CompanionConfigKnobSchema } from "../../generated-apis-types/schemas";
import { useI18n, type TranslationKey } from "../../i18n";

type KnobValue = number | boolean | string | string[];

interface ConfigKnobsProps {
  readonly knobs: readonly CompanionConfigKnobSchema[];
  /** Per-account mode: values may be empty (inherit) and show the global value. */
  readonly overrides?: Readonly<Record<string, KnobValue | null | undefined>>;
  readonly busy: boolean;
  readonly saveLabel: string;
  readonly onSave: (values: Record<string, KnobValue | null>) => void;
  readonly onReset: () => void;
  readonly resetLabel: string;
}

const GROUPS = ["recall", "pacing", "life_story", "words"] as const;
/** Retired with the unlock system; hidden even if an older API still sends them. */
const RETIRED_KNOBS = new Set(["familiar_unlock_runs", "rare_unlock_runs"]);

function knobLabelKey(key: string): TranslationKey {
  return `companionAdmin.config.knobs.${key}` as TranslationKey;
}

function display(value: unknown): string {
  return Array.isArray(value) ? value.join(", ") : String(value);
}

function toDraft(value: unknown): string {
  if (value === null || value === undefined) return "";
  // An ISO date-time ("2026-11-28T07:55:00+00:00") fits datetime-local as UTC.
  if (typeof value === "string" && /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}/.test(value)) {
    return value.slice(0, 16);
  }
  return Array.isArray(value) ? value.join("\n") : String(value);
}

/** Convert a text draft back into the knob's type. */
export function parseKnob(
  kind: CompanionConfigKnobSchema["kind"],
  raw: string,
): KnobValue {
  switch (kind) {
    case "bool":
      return raw === "true";
    case "int":
      return Number.parseInt(raw, 10);
    case "float":
      return Number.parseFloat(raw);
    case "list":
      return raw
        .split("\n")
        .map((item) => item.trim())
        .filter(Boolean);
    default:
      return raw;
  }
}

interface KnobInputProps {
  readonly id: string;
  readonly knob: CompanionConfigKnobSchema;
  readonly value: string;
  readonly perAccount: boolean;
  readonly onChange: (value: string) => void;
}

function KnobInput({ id, knob, value, perAccount, onChange }: KnobInputProps) {
  const { t } = useI18n();
  const inherit = perAccount ? (
    <option value="">{t("companionAdmin.overrides.inherit")}</option>
  ) : null;
  if (knob.kind === "bool") {
    return (
      <select
        id={id}
        className="input"
        value={value}
        onChange={(event) => onChange(event.target.value)}
      >
        {inherit}
        <option value="true">{t("companionAdmin.config.on")}</option>
        <option value="false">{t("companionAdmin.config.off")}</option>
      </select>
    );
  }
  if (knob.kind === "weight") {
    return (
      <select
        id={id}
        className="input"
        value={value}
        onChange={(event) => onChange(event.target.value)}
      >
        {inherit}
        {(["everyday", "past", "heart"] as const).map((weight) => (
          <option key={weight} value={weight}>
            {t(`companionAdmin.fragments.weights.${weight}`)}
          </option>
        ))}
      </select>
    );
  }
  if (knob.kind === "datetime") {
    return (
      <input
        id={id}
        className="input"
        type="datetime-local"
        value={value}
        aria-describedby={`${id}-hint`}
        onChange={(event) => onChange(event.target.value)}
      />
    );
  }
  if (knob.kind === "list") {
    return (
      <textarea
        id={id}
        className="input"
        rows={3}
        value={value}
        aria-describedby={`${id}-hint`}
        onChange={(event) => onChange(event.target.value)}
      />
    );
  }
  return (
    <input
      id={id}
      className="input"
      type="number"
      inputMode={knob.kind === "int" ? "numeric" : "decimal"}
      step={knob.kind === "int" ? 1 : 0.01}
      min={knob.minimum ?? undefined}
      max={knob.maximum ?? undefined}
      placeholder={
        perAccount ? t("companionAdmin.overrides.inherit") : undefined
      }
      value={value}
      onChange={(event) => onChange(event.target.value)}
    />
  );
}

/**
 * Every pacing knob with its shipped default. In per-account mode a field may
 * be left empty to inherit the global value, which is shown beside it.
 */
export function ConfigKnobs({
  knobs,
  overrides,
  busy,
  saveLabel,
  onSave,
  onReset,
  resetLabel,
}: ConfigKnobsProps) {
  const { t } = useI18n();
  const perAccount = overrides !== undefined;
  const initial = (knob: CompanionConfigKnobSchema): string =>
    toDraft(perAccount ? overrides?.[knob.key] : knob.value);
  const [draft, setDraft] = useState<Record<string, string>>(() =>
    Object.fromEntries(knobs.map((knob) => [knob.key, initial(knob)])),
  );

  const submit = () => {
    const values: Record<string, KnobValue | null> = {};
    for (const knob of knobs) {
      if (RETIRED_KNOBS.has(knob.key)) continue;
      const raw = draft[knob.key] ?? "";
      if (raw === initial(knob)) continue;
      if (raw !== "") values[knob.key] = parseKnob(knob.kind, raw);
      else if (perAccount) values[knob.key] = null;
    }
    if (Object.keys(values).length > 0) onSave(values);
  };

  const hintFor = (knob: CompanionConfigKnobSchema): string => {
    const base = perAccount
      ? t("companionAdmin.overrides.inherited", { value: display(knob.value) })
      : t("companionAdmin.config.default", { value: display(knob.default) });
    return knob.kind === "list"
      ? `${base} · ${t("companionAdmin.config.listHint")}`
      : base;
  };

  return (
    <div className="ca-knobs">
      {GROUPS.map((group) => {
        const items = knobs.filter(
          (knob) => knob.group === group && !RETIRED_KNOBS.has(knob.key),
        );
        if (items.length === 0) return null;
        return (
          <fieldset key={group} className="ca-knob-group">
            <legend>{t(`companionAdmin.config.groups.${group}`)}</legend>
            {items.map((knob) => {
              const id = `knob-${knob.key}`;
              return (
                <div key={knob.key} className="ca-knob">
                  <label htmlFor={id}>{t(knobLabelKey(knob.key))}</label>
                  <KnobInput
                    id={id}
                    knob={knob}
                    value={draft[knob.key] ?? ""}
                    perAccount={perAccount}
                    onChange={(value) =>
                      setDraft({ ...draft, [knob.key]: value })
                    }
                  />
                  <small id={`${id}-hint`}>{hintFor(knob)}</small>
                </div>
              );
            })}
          </fieldset>
        );
      })}
      <div className="ca-actions">
        <Button
          type="button"
          variant="primary"
          size="sm"
          disabled={busy}
          onClick={submit}
        >
          {saveLabel}
        </Button>
        <Button
          type="button"
          variant="ghost"
          size="sm"
          disabled={busy}
          onClick={onReset}
        >
          {resetLabel}
        </Button>
      </div>
    </div>
  );
}
