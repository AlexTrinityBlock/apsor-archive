import { useRef, useState, type FormEvent } from "react";

import { Button } from "../../component/Button";
import { Icon } from "../../component/Icon";
import type { AccountCreateSchema } from "../../generated-apis-types/schemas";
import { useI18n } from "../../i18n";
import { AccountDialog } from "./AccountDialog";
import "../accounts.css";

interface CreateAccountDialogProps {
  readonly onClose: () => void;
  readonly onSubmit: (payload: AccountCreateSchema) => void;
  readonly submitting: boolean;
  readonly error: string | null;
}

/** Collects the two identity fields; the server owns role and password state. */
export function CreateAccountDialog({
  onClose,
  onSubmit,
  submitting,
  error,
}: CreateAccountDialogProps) {
  const { t } = useI18n();
  const [username, setUsername] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [fieldErrors, setFieldErrors] = useState<{
    readonly username?: string;
    readonly displayName?: string;
  }>({});
  const usernameRef = useRef<HTMLInputElement>(null);
  const displayNameRef = useRef<HTMLInputElement>(null);
  const formId = "create-account-form";
  const usernameErrorId = "create-account-username-error";
  const displayNameErrorId = "create-account-display-name-error";

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const cleanUsername = username.trim();
    const cleanDisplayName = displayName.trim();
    const errors: { username?: string; displayName?: string } = {};
    if (cleanUsername.length < 3) {
      errors.username = t("core.accounts.usernameRequired");
    }
    if (cleanDisplayName.length === 0) {
      errors.displayName = t("core.accounts.displayNameRequired");
    }
    if (errors.username || errors.displayName) {
      setFieldErrors(errors);
      if (errors.username) {
        usernameRef.current?.focus();
      } else {
        displayNameRef.current?.focus();
      }
      return;
    }
    setFieldErrors({});
    onSubmit({
      username: cleanUsername,
      display_name: cleanDisplayName,
    });
  };

  return (
    <AccountDialog
      eyebrow={t("core.accounts.eyebrow")}
      title={t("core.accounts.createTitle")}
      description={t("core.accounts.createDescription")}
      onClose={onClose}
      busy={submitting}
      actions={
        <>
          <Button
            type="button"
            variant="ghost"
            onClick={onClose}
            disabled={submitting}
          >
            {t("core.accounts.cancel")}
          </Button>
          <Button
            type="submit"
            form={formId}
            variant="primary"
            disabled={submitting}
          >
            {submitting
              ? t("core.accounts.creating")
              : t("core.accounts.createSubmit")}
          </Button>
        </>
      }
    >
      <form className="accounts-form" id={formId} onSubmit={handleSubmit} noValidate>
        {error ? (
          <p className="accounts-form__error" role="alert">
            <Icon name="info" size={15} />
            {error}
          </p>
        ) : null}

        <div className="field">
          <label className="field-label" htmlFor="create-account-username">
            {t("core.accounts.username")}
          </label>
          <input
            ref={usernameRef}
            className="input"
            id="create-account-username"
            name="username"
            value={username}
            onChange={(event) => {
              setUsername(event.target.value);
              setFieldErrors((current) => ({ ...current, username: undefined }));
            }}
            autoComplete="off"
            autoCapitalize="none"
            spellCheck={false}
            minLength={3}
            maxLength={64}
            required
            disabled={submitting}
            data-autofocus
            aria-invalid={fieldErrors.username ? true : undefined}
            aria-describedby={
              fieldErrors.username
                ? `create-account-username-hint ${usernameErrorId}`
                : "create-account-username-hint"
            }
          />
          <small className="field-help" id="create-account-username-hint">
            {t("core.accounts.usernameHint")}
          </small>
          {fieldErrors.username ? (
            <p className="field-error" id={usernameErrorId} role="alert">
              {fieldErrors.username}
            </p>
          ) : null}
        </div>

        <div className="field">
          <label className="field-label" htmlFor="create-account-display-name">
            {t("core.accounts.displayName")}
          </label>
          <input
            ref={displayNameRef}
            className="input"
            id="create-account-display-name"
            name="display-name"
            value={displayName}
            onChange={(event) => {
              setDisplayName(event.target.value);
              setFieldErrors((current) => ({
                ...current,
                displayName: undefined,
              }));
            }}
            autoComplete="off"
            maxLength={80}
            required
            disabled={submitting}
            aria-invalid={fieldErrors.displayName ? true : undefined}
            aria-describedby={
              fieldErrors.displayName
                ? `create-account-display-name-hint ${displayNameErrorId}`
                : "create-account-display-name-hint"
            }
          />
          <small className="field-help" id="create-account-display-name-hint">
            {t("core.accounts.displayNameHint")}
          </small>
          {fieldErrors.displayName ? (
            <p className="field-error" id={displayNameErrorId} role="alert">
              {fieldErrors.displayName}
            </p>
          ) : null}
        </div>
      </form>
    </AccountDialog>
  );
}
