import { useId, useState, type FormEvent } from "react";

import { Button } from "../../component/Button";
import { Icon } from "../../component/Icon";
import { useI18n } from "../../i18n";
import { useAuth } from "../AuthProvider";
import { AuthFrame } from "./AuthFrame";

/** Sign-in form for the single keeper account. */
export function LoginScreen() {
  const { t } = useI18n();
  const { login, isSubmitting, error } = useAuth();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const usernameId = useId();
  const passwordId = useId();

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    void login({ username: username.trim(), password });
  };

  return (
    <AuthFrame
      eyebrow={t("core.auth.login.eyebrow")}
      title={t("core.auth.login.title")}
      description={t("core.auth.login.description")}
      footer={<p>{t("core.auth.login.footer")}</p>}
    >
      <form className="auth-form" onSubmit={handleSubmit}>
        <div className="field">
          <label className="field-label" htmlFor={usernameId}>
            {t("core.auth.login.username")}
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
            required
            disabled={isSubmitting}
          />
        </div>

        <div className="field">
          <label className="field-label" htmlFor={passwordId}>
            {t("core.auth.login.credentialLabel")}
          </label>
          <div className="auth-password">
            <input
              className="input"
              id={passwordId}
              name="password"
              type={showPassword ? "text" : "password"}
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              autoComplete="current-password"
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
        </div>

        {error ? (
          <p className="auth-error" role="alert">
            <Icon name="info" size={16} />
            {error}
          </p>
        ) : null}

        <Button type="submit" variant="primary" size="lg" block disabled={isSubmitting}>
          {isSubmitting
            ? t("core.auth.login.submitting")
            : t("core.auth.login.submit")}
          {!isSubmitting ? <Icon name="arrow-right" size={17} /> : null}
        </Button>
      </form>
    </AuthFrame>
  );
}
