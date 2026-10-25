import { useId, type FormEvent } from "react";

import { Button } from "./Button";
import { Icon } from "./Icon";
import { useI18n } from "../i18n";

interface SearchFieldProps {
  readonly value: string;
  readonly onChange: (value: string) => void;
  readonly onSubmit: (value: string) => void;
  readonly label?: string;
  readonly placeholder?: string;
  readonly submitLabel?: string;
  readonly size?: "md" | "lg";
  readonly autoFocus?: boolean;
}

/**
 * The archive's single search affordance, used on the overview and the search
 * route so both keep the same focus behaviour and submit contract.
 */
export function SearchField({
  value,
  onChange,
  onSubmit,
  label,
  placeholder,
  submitLabel,
  size = "md",
  autoFocus = false,
}: SearchFieldProps) {
  const { t } = useI18n();
  const inputId = useId();
  const resolvedLabel = label ?? t("core.searchField.label");
  const resolvedPlaceholder = placeholder ?? t("core.searchField.placeholder");
  const resolvedSubmitLabel = submitLabel ?? t("core.searchField.submit");

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    onSubmit(value.trim());
  };

  return (
    <form
      className={["search-field", `search-field--${size}`].join(" ")}
      role="search"
      onSubmit={handleSubmit}
    >
      <span className="search-field__icon" aria-hidden="true">
        <Icon name="search" size={size === "lg" ? 22 : 19} />
      </span>
      <label className="visually-hidden" htmlFor={inputId}>
        {resolvedLabel}
      </label>
      <input
        id={inputId}
        name="query"
        type="search"
        value={value}
        onChange={(event) => onChange(event.target.value)}
        placeholder={resolvedPlaceholder}
        autoComplete="off"
        spellCheck={false}
        autoFocus={autoFocus}
        className="search-field__input"
      />
      <Button
        type="submit"
        variant="ink"
        size={size === "lg" ? "md" : "sm"}
        className="search-field__submit"
      >
        <span>{resolvedSubmitLabel}</span>
        <Icon name="arrow-right" size={16} />
      </Button>
    </form>
  );
}
