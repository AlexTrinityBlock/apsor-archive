import { useRef, useState, type FormEvent } from "react";
import { useQueryClient } from "@tanstack/react-query";

import { ApiError } from "../../../apis/fetch-client";
import { Button } from "../../component/Button";
import { Icon } from "../../component/Icon";
import { useToast } from "../../component/Toast";
import {
  getGetAuthStatusQueryKey,
  useChangePassword,
} from "../../generated-apis-types";
import type { AuthStatusSchema } from "../../generated-apis-types/schemas";
import { useI18n } from "../../i18n";
import { translateApiError } from "../../i18n/errors";
import "../auth.css";

interface PasswordFieldErrors {
  current?: string;
  newPassword?: string;
  confirm?: string;
}

function hasFieldErrors(errors: PasswordFieldErrors): boolean {
  return Boolean(errors.current || errors.newPassword || errors.confirm);
}

interface ChangePasswordFormProps {
  readonly onSuccess?: () => void;
}

/**
 * Self-service password form shared by the forced gate, the voluntary route,
 * and the footer dialog. A wrong current password is a field error, never a
 * session expiry.
 */
export function ChangePasswordForm({ onSuccess }: ChangePasswordFormProps = {}) {
  const { t } = useI18n();
  const queryClient = useQueryClient();
  const toast = useToast();
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [fieldErrors, setFieldErrors] = useState<PasswordFieldErrors>({});
  const [formError, setFormError] = useState<string | null>(null);
  const currentRef = useRef<HTMLInputElement>(null);
  const newRef = useRef<HTMLInputElement>(null);
  const confirmRef = useRef<HTMLInputElement>(null);
  const currentErrorId = "change-password-current-error";
  const newHintId = "change-password-new-hint";
  const newErrorId = "change-password-new-error";
  const confirmErrorId = "change-password-confirm-error";

  const mutation = useChangePassword({
    mutation: {
      onSuccess: () => {
        const status = queryClient.getQueryData<AuthStatusSchema>(
          getGetAuthStatusQueryKey(),
        );
        if (status?.user) {
          queryClient.setQueryData<AuthStatusSchema>(
            getGetAuthStatusQueryKey(),
            {
              ...status,
              user: { ...status.user, must_change_password: false },
            },
          );
        }
        void queryClient.invalidateQueries({
          queryKey: getGetAuthStatusQueryKey(),
        });
        setCurrentPassword("");
        setNewPassword("");
        setConfirmPassword("");
        setFieldErrors({});
        setFormError(null);
        toast.success(t("core.auth.changePassword.success"));
        onSuccess?.();
      },
      onError: (caught) => {
        if (caught instanceof ApiError) {
          if (caught.code === "current_password_invalid") {
            setFieldErrors({
              current: t("core.auth.changePassword.currentInvalid"),
            });
            currentRef.current?.focus();
            return;
          }
          if (caught.code === "weak_password") {
            setFieldErrors({
              newPassword: t("core.auth.changePassword.weak"),
            });
            newRef.current?.focus();
            return;
          }
          if (caught.code === "password_mismatch") {
            setFieldErrors({
              confirm: t("core.auth.changePassword.mismatch"),
            });
            confirmRef.current?.focus();
            return;
          }
        }
        setFormError(translateApiError(caught, t, "core.errors.generic"));
      },
    },
  });

  const focusFirstError = (errors: PasswordFieldErrors) => {
    if (errors.current) {
      currentRef.current?.focus();
      return;
    }
    if (errors.newPassword) {
      newRef.current?.focus();
      return;
    }
    confirmRef.current?.focus();
  };

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setFormError(null);
    const errors: PasswordFieldErrors = {};
    if (currentPassword.length === 0) {
      errors.current = t("core.auth.changePassword.currentRequired");
    }
    if (newPassword.length < 10) {
      errors.newPassword = t("core.auth.changePassword.weak");
    }
    // This is a local UX confirmation, not a secret comparison; the server
    // verifies and hashes the password with Argon2.
    if (newPassword !== confirmPassword) {
      errors.confirm = t("core.auth.changePassword.mismatch");
    }
    if (hasFieldErrors(errors)) {
      setFieldErrors(errors);
      focusFirstError(errors);
      return;
    }
    setFieldErrors({});
    mutation.mutate({
      data: {
        current_password: currentPassword,
        new_password: newPassword,
        confirm_password: confirmPassword,
      },
    });
  };

  const submitting = mutation.isPending;

  return (
    <form
      className="auth-form change-password-form"
      onSubmit={handleSubmit}
      noValidate
    >
      <div className="field">
        <label className="field-label" htmlFor="change-password-current">
          {t("core.auth.changePassword.currentPassword")}
        </label>
        <input
          ref={currentRef}
          className="input"
          id="change-password-current"
          name="current-password"
          type="password"
          value={currentPassword}
          onChange={(event) => {
            setCurrentPassword(event.target.value);
            setFieldErrors((current) => ({ ...current, current: undefined }));
            setFormError(null);
          }}
          autoComplete="current-password"
          maxLength={256}
          required
          disabled={submitting}
          autoFocus
          aria-invalid={fieldErrors.current ? true : undefined}
          aria-describedby={fieldErrors.current ? currentErrorId : undefined}
        />
        {fieldErrors.current ? (
          <p className="field-error" id={currentErrorId} role="alert">
            {fieldErrors.current}
          </p>
        ) : null}
      </div>

      <div className="field">
        <label className="field-label" htmlFor="change-password-new">
          {t("core.auth.changePassword.newPassword")}
        </label>
        <input
          ref={newRef}
          className="input"
          id="change-password-new"
          name="new-password"
          type="password"
          value={newPassword}
          onChange={(event) => {
            setNewPassword(event.target.value);
            setFieldErrors((current) => ({ ...current, newPassword: undefined }));
            setFormError(null);
          }}
          autoComplete="new-password"
          minLength={10}
          maxLength={256}
          required
          disabled={submitting}
          aria-invalid={fieldErrors.newPassword ? true : undefined}
          aria-describedby={
            fieldErrors.newPassword
              ? `${newHintId} ${newErrorId}`
              : newHintId
          }
        />
        <small className="field-help" id={newHintId}>
          {t("core.auth.changePassword.passwordHint")}
        </small>
        {fieldErrors.newPassword ? (
          <p className="field-error" id={newErrorId} role="alert">
            {fieldErrors.newPassword}
          </p>
        ) : null}
      </div>

      <div className="field">
        <label className="field-label" htmlFor="change-password-confirm">
          {t("core.auth.changePassword.confirmPassword")}
        </label>
        <input
          ref={confirmRef}
          className="input"
          id="change-password-confirm"
          name="confirm-password"
          type="password"
          value={confirmPassword}
          onChange={(event) => {
            setConfirmPassword(event.target.value);
            setFieldErrors((current) => ({ ...current, confirm: undefined }));
            setFormError(null);
          }}
          autoComplete="new-password"
          minLength={10}
          maxLength={256}
          required
          disabled={submitting}
          aria-invalid={fieldErrors.confirm ? true : undefined}
          aria-describedby={fieldErrors.confirm ? confirmErrorId : undefined}
        />
        {fieldErrors.confirm ? (
          <p className="field-error" id={confirmErrorId} role="alert">
            {fieldErrors.confirm}
          </p>
        ) : null}
      </div>

      {formError ? (
        <p className="auth-error" role="alert">
          <Icon name="info" size={16} />
          {formError}
        </p>
      ) : null}

      <Button type="submit" variant="primary" size="lg" block disabled={submitting}>
        {submitting
          ? t("core.auth.changePassword.submitting")
          : t("core.auth.changePassword.submit")}
        {!submitting ? <Icon name="check" size={16} /> : null}
      </Button>
    </form>
  );
}
