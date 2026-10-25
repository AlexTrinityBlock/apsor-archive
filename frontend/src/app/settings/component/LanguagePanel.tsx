import { Icon } from "../../component/Icon";
import { Panel } from "../../component/Panel";
import { LOCALE_OPTIONS, useI18n } from "../../i18n";
import "./LanguagePanel.css";

/**
 * Immediate interface-language switcher. Native language names are deliberately
 * not translated so every reader can recognize their own language.
 */
export function LanguagePanel() {
  const { t, locale, setLocale } = useI18n();

  return (
    <Panel eyebrow={t("core.languagePanel.eyebrow")} title={t("core.languagePanel.title")}>
      <div className="language-panel">
        <p className="language-panel__intro">
          {t("core.languagePanel.description")}
        </p>

        <fieldset className="language-panel__options">
          <legend className="visually-hidden">
            {t("core.languagePanel.aria")}
          </legend>
          {LOCALE_OPTIONS.map((option) => {
            const selected = option.id === locale;
            return (
              <label
                key={option.id}
                className={
                  selected
                    ? "language-panel__option is-selected"
                    : "language-panel__option"
                }
                title={option.nativeLabel}
              >
                <span className="language-panel__option-main">
                  <span className="language-panel__option-label">
                    {option.nativeLabel}
                  </span>
                  <span className="language-panel__option-code">
                    {option.code}
                  </span>
                </span>
                <span className="language-panel__option-mark" aria-hidden="true">
                  {selected ? <Icon name="check" size={14} /> : null}
                </span>
                <input
                  className="visually-hidden"
                  type="radio"
                  name="interface-language"
                  value={option.id}
                  checked={selected}
                  onChange={() => setLocale(option.id)}
                />
              </label>
            );
          })}
        </fieldset>

        <p className="language-panel__note">
          {t("core.languagePanel.note")}
        </p>
      </div>
    </Panel>
  );
}
