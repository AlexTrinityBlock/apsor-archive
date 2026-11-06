import { useId, type RefObject } from "react";

import { Button } from "../../component/Button";
import { Icon } from "../../component/Icon";
import { useI18n } from "../../i18n";
import type { VisionPromptMode } from "./vision-prompt-utils";

interface VisionPromptEditorProps {
  readonly mode: VisionPromptMode;
  readonly label: string;
  readonly description: string;
  readonly value: string;
  readonly maxChars: number;
  readonly error: string | null;
  readonly warnings: readonly string[];
  readonly disabled: boolean;
  readonly isDefault: boolean;
  readonly restoreDisabled: boolean;
  readonly textareaRef: RefObject<HTMLTextAreaElement | null>;
  readonly onChange: (value: string) => void;
  readonly onRestoreDefault: () => void;
}

/**
 * One full-prompt editor: label, required context, textarea, character count,
 * field error, safety warnings, and the draft-only restore action. The prompt
 * body itself is data and is never passed through the translation layer.
 */
export function VisionPromptEditor({
  mode,
  label,
  description,
  value,
  maxChars,
  error,
  warnings,
  disabled,
  isDefault,
  restoreDisabled,
  textareaRef,
  onChange,
  onRestoreDefault,
}: VisionPromptEditorProps) {
  const { t, formatNumber } = useI18n();
  const fieldId = useId();
  const descriptionId = `${fieldId}-description`;
  const countId = `${fieldId}-count`;
  const errorId = `${fieldId}-error`;
  const describedBy = [descriptionId, countId, error ? errorId : null]
    .filter(Boolean)
    .join(" ");
  const count = value.trim().length;

  return (
    <div className="vision-prompt-editor" data-mode={mode}>
      <div className="vision-prompt-editor__head">
        <label className="vision-prompt-editor__label" htmlFor={fieldId}>
          {label}
        </label>
        <span
          className={
            isDefault
              ? "vision-prompt-editor__source"
              : "vision-prompt-editor__source is-custom"
          }
        >
          {isDefault
            ? t("settings.visionPrompts.builtIn")
            : t("settings.visionPrompts.custom")}
        </span>
      </div>
      <p className="vision-prompt-editor__description" id={descriptionId}>
        {description}
      </p>
      <textarea
        ref={textareaRef}
        id={fieldId}
        className={
          error
            ? "vision-prompt-editor__textarea is-invalid"
            : "vision-prompt-editor__textarea"
        }
        value={value}
        rows={18}
        dir="auto"
        spellCheck={false}
        autoComplete="off"
        placeholder={t("settings.visionPrompts.placeholder")}
        disabled={disabled}
        aria-invalid={error ? true : undefined}
        aria-describedby={describedBy}
        onChange={(event) => onChange(event.currentTarget.value)}
      />
      <div className="vision-prompt-editor__foot">
        <span
          className={
            error
              ? "vision-prompt-editor__count is-invalid"
              : "vision-prompt-editor__count"
          }
          id={countId}
        >
          {t("settings.visionPrompts.characterCount", {
            count: formatNumber(count),
            max: formatNumber(maxChars),
          })}
        </span>
        <Button
          type="button"
          variant="ghost"
          size="sm"
          onClick={onRestoreDefault}
          disabled={restoreDisabled || disabled}
          title={t("settings.visionPrompts.restoreDefaultHint")}
        >
          <Icon name="history" size={14} />
          {t("settings.visionPrompts.restoreDefault")}
        </Button>
      </div>
      {error ? (
        <p className="vision-prompt-editor__error" id={errorId} role="alert">
          <Icon name="info" size={14} />
          <span>{error}</span>
        </p>
      ) : null}
      {warnings.length > 0 ? (
        <div className="vision-prompt-editor__warnings" role="note">
          <Icon name="info" size={15} />
          <div>
            <strong>{t("settings.visionPrompts.warningTitle")}</strong>
            <ul>
              {warnings.map((warning) => (
                <li key={warning}>{warning}</li>
              ))}
            </ul>
            <p>{t("settings.visionPrompts.warningNonBlocking")}</p>
          </div>
        </div>
      ) : null}
    </div>
  );
}
