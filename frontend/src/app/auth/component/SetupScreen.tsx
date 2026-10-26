import { useId, useState, type FormEvent } from "react";

import { Button } from "../../component/Button";
import { Icon } from "../../component/Icon";
import { useI18n } from "../../i18n";
import { useAuth } from "../AuthProvider";
import { AuthFrame } from "./AuthFrame";

/** First-run form: create the root account and sign in immediately. */
export function SetupScreen() {
  const { t } = useI18n();
  const { setup, isSubmitting, error } = useAuth();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [localError, setLocalError] = useState<string | null>(null);
  const usernameId = useId();
  const usernameHintId = useId();
  const passwordId = useId();
  const passwordHintId = useId();
  const confirmId = useId();

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setLocalError(null);
    if (password.length < 10) {
      setLocalError(t("core.auth.setup.credentialTooShort"));
      return;
    }
    // This is a local UX confirmation, not a secret comparison; the server
    // verifies the actual password with Argon2.
    // eslint-disable-next-line security/detect-possible-timing-attacks
    if (password !== confirmPassword) {
      setLocalError(t("core.auth.setup.credentialMismatch"));
      return;
    }
    void setup({
      username: username.trim(),
      password,
      confirm_password: confirmPassword,
    });
  };

  return (
    <AuthFrame
      eyebrow={t("core.auth.setup.eyebrow")}
      title={t("core.auth.setup.title")}
      description={t("core.auth.setup.description")}
      footer={<p>{t("core.auth.setup.footer")}</p>}
    >
      <form className="auth-form" onSubmit={handleSubmit}>
        <div className="field">
          <label className="field-label" htmlFor={usernameId}>
            {t("core.auth.setup.username")}
          </label>
          <input
            className="input"
            id={usernameId}
            name="username"
            value={username}
            onChange={(event) => setUsername(event.target.value)}
            autoComplete="username"
            autoCapitalize="none"
            spellCheck={false}
            minLength={3}
            maxLength={64}
            aria-describedby={usernameHintId}
            required
            disabled={isSubmitting}
          />
          <small className="field-help" id={usernameHintId}>
            {t("core.auth.setup.usernameHint")}
          </small>
        </div>

        <div className="field">
          <label className="field-label" htmlFor={passwordId}>
            {t("core.auth.setup.credentialLabel")}
          </label>
          <div className="auth-password">
            <input
              className="input"
              id={passwordId}
              name="password"
              type={showPassword ? "text" : "password"}
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              autoComplete="new-password"
              minLength={10}
              maxLength={256}
              aria-describedby={passwordHintId}
              required
              disabled={isSubmitting}
            />
            <button
              type="button"
              className="auth-password__toggle"
              onClick={() => setShowPassword((current) => !current)}
              aria-label={
                showPassword
                  ? t("core.auth.login.hidePassword")
                  : t("core.auth.login.showPassword")
              }
              aria-pressed={showPassword}
              aria-controls={passwordId}
              disabled={isSubmitting}
            >
              {showPassword
                ? t("core.auth.login.hide")
                : t("core.auth.login.show")}
            </button>
          </div>
          <small className="field-help" id={passwordHintId}>
            {t("core.auth.setup.credentialHint")}
          </small>
        </div>

        <div className="field">
          <label className="field-label" htmlFor={confirmId}>
            {t("core.auth.setup.confirmCredential")}
          </label>
          <input
            className="input"
            id={confirmId}
            name="confirm-password"
            type={showPassword ? "text" : "password"}
            value={confirmPassword}
            onChange={(event) => setConfirmPassword(event.target.value)}
            autoComplete="new-password"
            minLength={10}
            maxLength={256}
            required
            disabled={isSubmitting}
          />
        </div>

        {localError || error ? (
          <p className="auth-error" role="alert">
            <Icon name="info" size={16} />
            {localError ?? error}
          </p>
        ) : null}

        <Button type="submit" variant="primary" size="lg" block disabled={isSubmitting}>
          {isSubmitting
            ? t("core.auth.setup.submitting")
            : t("core.auth.setup.submit")}
          {!isSubmitting ? <Icon name="arrow-right" size={17} /> : null}
        </Button>
      </form>
    </AuthFrame>
  );
}
