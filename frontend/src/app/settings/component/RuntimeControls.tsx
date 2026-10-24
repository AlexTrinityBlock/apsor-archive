import { useId, type ReactNode } from "react";

import { formatDateTime, formatNumber } from "../../../lib/format";
import { Badge } from "../../component/Badge";
import { Button } from "../../component/Button";
import { Icon } from "../../component/Icon";

export interface RuntimeNumberSpec {
  readonly label: string;
  readonly unit: string;
  readonly min: number;
  readonly max: number;
  readonly step: number;
  readonly integer?: boolean;
  readonly hint: string;
}

interface RuntimeNumberFieldProps {
  readonly spec: RuntimeNumberSpec;
  readonly value: string;
  readonly defaultValue: number;
  readonly disabled: boolean;
  readonly error: string | undefined;
  readonly onValueChange: (value: string) => void;
}

/** One validated numeric runtime bound with defaults and range in its hint. */
export function RuntimeNumberField({
  spec,
  value,
  defaultValue,
  disabled,
  error,
  onValueChange,
}: RuntimeNumberFieldProps) {
  const fieldId = useId();
  const hintId = `${fieldId}-hint`;
  const errorId = `${fieldId}-error`;
  const describedBy = error ? `${hintId} ${errorId}` : hintId;

  return (
    <div className="runtime-field">
      <label className="runtime-field__label" htmlFor={fieldId}>
        <span>{spec.label}</span>
        <span className="runtime-field__unit" aria-hidden="true">
          {spec.unit}
        </span>
      </label>
      <input
        id={fieldId}
        className={
          error ? "runtime-input runtime-input--invalid" : "runtime-input"
        }
        type="number"
        inputMode={spec.integer === false ? "decimal" : "numeric"}
        value={value}
        min={spec.min}
        max={spec.max}
        step={spec.step}
        placeholder={formatNumber(defaultValue)}
        disabled={disabled}
        aria-invalid={error ? true : undefined}
        aria-describedby={describedBy}
        onChange={(event) => onValueChange(event.currentTarget.value)}
      />
      <span className="runtime-field__hint" id={hintId}>
        {spec.hint} Default {formatNumber(defaultValue)} ·{" "}
        {formatNumber(spec.min)}–{formatNumber(spec.max)} {spec.unit}.
      </span>
      {error ? (
        <span className="runtime-field__error" id={errorId}>
          {error}
        </span>
      ) : null}
    </div>
  );
}

interface RuntimeGroupProps {
  readonly slot: string;
  readonly title: string;
  readonly description: string;
  readonly advanced?: boolean;
  readonly children: ReactNode;
}

/** A titled cluster of runtime controls. */
export function RuntimeGroup({
  slot,
  title,
  description,
  advanced = false,
  children,
}: RuntimeGroupProps) {
  const headingId = useId();

  return (
    <section className="runtime-group" aria-labelledby={headingId}>
      <header className="runtime-group__head">
        <p className="runtime-group__slot">{slot}</p>
        <h3 className="runtime-group__title" id={headingId}>
          {title}
          {advanced ? (
            <span className="runtime-group__tag">Advanced</span>
          ) : null}
        </h3>
        <p className="runtime-group__intro">{description}</p>
      </header>
      <div className="runtime-grid">{children}</div>
    </section>
  );
}

interface RuntimeStatusProps {
  readonly source: "database" | "default";
  readonly updatedAt: string | null;
  readonly summary: string;
  readonly dirty: boolean;
}

/** The persisted source, timestamp, and active draft marker for a panel. */
export function RuntimeStatus({
  source,
  updatedAt,
  summary,
  dirty,
}: RuntimeStatusProps) {
  return (
    <div className="runtime-status" aria-label="Runtime settings status">
      <Badge tone={source === "database" ? "moss" : "neutral"} dot>
        {source === "database" ? "Database" : "Defaults"}
      </Badge>
      <span className="runtime-status__updated">
        {updatedAt ? (
          <>
            Last updated{" "}
            <time dateTime={updatedAt}>{formatDateTime(updatedAt)}</time>
          </>
        ) : (
          "No saved update yet"
        )}
      </span>
      <span className="runtime-status__summary">{summary}</span>
      {dirty ? (
        <span className="runtime-status__draft">Unsaved draft</span>
      ) : null}
    </div>
  );
}

interface RuntimeActionsProps {
  readonly saving: boolean;
  readonly canSave: boolean;
  readonly dirty: boolean;
  readonly invalid: boolean;
  readonly confirmingReset: boolean;
  readonly onRequestReset: () => void;
  readonly onCancelReset: () => void;
  readonly onConfirmReset: () => void;
}

/** Shared reset/save footer for both runtime forms. */
export function RuntimeActions({
  saving,
  canSave,
  dirty,
  invalid,
  confirmingReset,
  onRequestReset,
  onCancelReset,
  onConfirmReset,
}: RuntimeActionsProps) {
  return (
    <div className="runtime-actions">
      <div className="runtime-actions__reset">
        {confirmingReset ? (
          <>
            <span className="runtime-reset__question" role="status">
              Reset every runtime value to the default?
            </span>
            <Button
              type="button"
              variant="secondary"
              size="sm"
              onClick={onConfirmReset}
              disabled={saving}
            >
              Reset values
            </Button>
            <Button
              type="button"
              variant="ghost"
              size="sm"
              onClick={onCancelReset}
              disabled={saving}
            >
              Keep current
            </Button>
          </>
        ) : (
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={onRequestReset}
            disabled={saving}
          >
            <Icon name="history" size={14} />
            Reset defaults
          </Button>
        )}
      </div>

      <div className="runtime-actions__save">
        {dirty && !invalid && !saving ? (
          <span className="runtime-actions__note">Unsaved changes</span>
        ) : null}
        <Button type="submit" variant="ink" size="sm" disabled={!canSave}>
          <Icon name="check" size={14} />
          {saving ? "Saving…" : "Save runtime"}
        </Button>
      </div>
    </div>
  );
}

/** Shared inline mutation error for a runtime panel. */
export function RuntimeError({ message }: { readonly message: string }) {
  return (
    <p className="runtime-error" role="alert">
      <Icon name="info" size={14} />
      <span>{message}</span>
    </p>
  );
}
