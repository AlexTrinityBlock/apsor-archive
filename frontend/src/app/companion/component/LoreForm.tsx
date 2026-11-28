import { useId, useState, type KeyboardEvent } from "react";

import { Button } from "../../component/Button";
import { Icon } from "../../component/Icon";
import { useI18n, type TranslationKey } from "../../i18n";
import {
  LORE_TEXT_MAX,
  LORE_TIERS,
  addTheme,
  validateLore,
  type LoreInput,
  type LoreTier,
} from "../story";

export const TIER_LABEL_KEYS: Readonly<Record<LoreTier, TranslationKey>> = {
  first: "companion.lore.tierFirst",
  familiar: "companion.lore.tierFamiliar",
  rare: "companion.lore.tierRare",
};

interface LoreFormProps {
  readonly initial: LoreInput;
  readonly busy: boolean;
  readonly onSubmit: (input: LoreInput) => void;
  readonly onCancel: () => void;
}

/** Add or edit one lore fragment: text, theme chips, and tier. */
export function LoreForm({ initial, busy, onSubmit, onCancel }: LoreFormProps) {
  const { t, formatNumber } = useI18n();
  const textId = useId();
  const themeId = useId();
  const tierId = useId();
  const [text, setText] = useState(initial.text);
  const [themes, setThemes] = useState<readonly string[]>(initial.themes);
  const [themeDraft, setThemeDraft] = useState("");
  const [tier, setTier] = useState<LoreTier>(initial.tier);
  const [problem, setProblem] = useState<string | null>(null);

  const commitTheme = () => {
    setThemes((current) => addTheme(current, themeDraft));
    setThemeDraft("");
  };

  const onThemeKey = (event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key === "Enter" || event.key === ",") {
      event.preventDefault();
      commitTheme();
    } else if (event.key === "Backspace" && themeDraft.length === 0 && themes.length > 0) {
      setThemes((current) => current.slice(0, -1));
    }
  };

  const submit = () => {
    const input = { text: text.trim(), themes: addTheme(themes, themeDraft), tier };
    const issue = validateLore(input);
    if (issue === "empty") {
      setProblem(t("companion.lore.errorEmpty"));
      return;
    }
    if (issue === "tooLong") {
      setProblem(t("companion.lore.errorTooLong", { max: formatNumber(LORE_TEXT_MAX) }));
      return;
    }
    setProblem(null);
    onSubmit(input);
  };

  return (
    <div className="companion-lore-form">
      <label className="companion-lore-form__field" htmlFor={textId}>
        <span>{t("companion.lore.formText")}</span>
        <textarea
          id={textId}
          className="input companion-lore-form__text"
          value={text}
          rows={6}
          maxLength={LORE_TEXT_MAX}
          aria-describedby={`${textId}-hint`}
          onChange={(event) => setText(event.currentTarget.value)}
        />
        <span id={`${textId}-hint`} className="companion-lore-form__hint">
          {t("companion.lore.formTextHint")} ·{" "}
          {t("companion.lore.characters", { count: formatNumber(text.length) })}
        </span>
      </label>

      <div className="companion-lore-form__row">
        <div className="companion-lore-form__field companion-lore-form__themes">
          <label htmlFor={themeId}>{t("companion.lore.formThemes")}</label>
          <div className="companion-lore-form__chips">
            {themes.map((theme) => (
              <span key={theme} className="companion-chip">
                {theme}
                <button
                  type="button"
                  onClick={() => setThemes((current) => current.filter((item) => item !== theme))}
                  aria-label={t("companion.lore.removeTheme", { theme })}
                  title={t("companion.lore.removeTheme", { theme })}
                >
                  <Icon name="close" size={10} />
                </button>
              </span>
            ))}
            <input
              id={themeId}
              className="companion-lore-form__theme-input"
              value={themeDraft}
              placeholder={t("companion.lore.formThemePlaceholder")}
              aria-describedby={`${themeId}-hint`}
              onChange={(event) => setThemeDraft(event.currentTarget.value)}
              onKeyDown={onThemeKey}
              onBlur={() => {
                if (themeDraft.trim().length > 0) {
                  commitTheme();
                }
              }}
            />
          </div>
          <span id={`${themeId}-hint`} className="companion-lore-form__hint">
            {t("companion.lore.formThemesHint")}
          </span>
        </div>
        <label className="companion-lore-form__field" htmlFor={tierId}>
          <span>{t("companion.lore.formTier")}</span>
          <select
            id={tierId}
            className="input"
            value={tier}
            onChange={(event) => setTier(event.currentTarget.value as LoreTier)}
          >
            {LORE_TIERS.map((item) => (
              <option key={item} value={item}>
                {t(TIER_LABEL_KEYS[item])}
              </option>
            ))}
          </select>
        </label>
      </div>

      {problem !== null ? (
        <p className="companion-lore-form__problem" role="alert">
          {problem}
        </p>
      ) : null}

      <div className="companion-lore-form__actions">
        <Button variant="ghost" size="sm" onClick={onCancel} disabled={busy}>
          {t("companion.lore.cancel")}
        </Button>
        <Button variant="ink" size="sm" onClick={submit} disabled={busy} aria-busy={busy}>
          {t("companion.lore.save")}
        </Button>
      </div>
    </div>
  );
}
