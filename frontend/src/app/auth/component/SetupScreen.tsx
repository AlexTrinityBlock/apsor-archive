import { useId, useState, type FormEvent } from "react";

import { Button } from "../../component/Button";
import { Icon } from "../../component/Icon";
import { useAuth } from "../AuthProvider";
import { AuthFrame } from "./AuthFrame";

/** First-run form: create the only account and sign in immediately. */
export function SetupScreen() {
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
      setLocalError("Use at least 10 characters for the password.");
      return;
    }
    // This is a local UX confirmation, not a secret comparison; the server
    // verifies the actual password with Argon2.
    // eslint-disable-next-line security/detect-possible-timing-attacks
    if (password !== confirmPassword) {
      setLocalError("The password confirmation does not match.");
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
      eyebrow="First run · create keeper"
      title="Press the first ring."
      description="This archive has no keeper yet. Create the single account that will protect every file and memory on this machine."
      footer={
        <p>
          The password is hashed with Argon2. There is no email recovery, no cloud
          reset, and no second account. Keep it somewhere safe.
        </p>
      }
    >
      <form className="auth-form" onSubmit={handleSubmit}>
        <div className="field">
          <label className="field-label" htmlFor={usernameId}>
            Username
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
            3–64 characters; letters, digits, dot, dash, underscore.
          </small>
        </div>

        <div className="field">
          <label className="field-label" htmlFor={passwordId}>
            Password
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
              aria-label={showPassword ? "Hide password" : "Show password"}
              aria-pressed={showPassword}
              aria-controls={passwordId}
              disabled={isSubmitting}
            >
              {showPassword ? "Hide" : "Show"}
            </button>
          </div>
          <small className="field-help" id={passwordHintId}>
            At least 10 characters. There is no recovery.
          </small>
        </div>

        <div className="field">
          <label className="field-label" htmlFor={confirmId}>
            Confirm password
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
          {isSubmitting ? "Pressing the first ring…" : "Create the archive keeper"}
          {!isSubmitting ? <Icon name="arrow-right" size={17} /> : null}
        </Button>
      </form>
    </AuthFrame>
  );
}
