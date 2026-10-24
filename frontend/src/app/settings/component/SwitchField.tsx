import { useId } from "react";

interface SwitchFieldProps {
  readonly label: string;
  readonly hint: string;
  readonly checked: boolean;
  readonly disabled: boolean;
  readonly onChange: (checked: boolean) => void;
}

/** A labelled switch used by provider and runtime forms. */
export function SwitchField({
  label,
  hint,
  checked,
  disabled,
  onChange,
}: SwitchFieldProps) {
  const fieldId = useId();
  const hintId = `${fieldId}-hint`;

  return (
    <label className="switch-field" htmlFor={fieldId}>
      <span className="switch-field__control">
        <input
          id={fieldId}
          className="switch-field__input"
          type="checkbox"
          role="switch"
          checked={checked}
          disabled={disabled}
          aria-describedby={hintId}
          onChange={(event) => onChange(event.currentTarget.checked)}
        />
        <span className="switch-field__track" aria-hidden="true">
          <span className="switch-field__thumb" />
        </span>
      </span>
      <span className="switch-field__copy">
        <span className="switch-field__title">{label}</span>
        <span className="switch-field__hint" id={hintId}>
          {hint}
        </span>
      </span>
    </label>
  );
}
