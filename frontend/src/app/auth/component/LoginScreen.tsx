import { useId, useState, type FormEvent } from "react";

import { Button } from "../../component/Button";
import { Icon } from "../../component/Icon";
import { useAuth } from "../AuthProvider";
import { AuthFrame } from "./AuthFrame";

/** Sign-in form for the single owner account. */
export function LoginScreen() {
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
      eyebrow="Keeper sign-in"
      title="Return to the rings."
      description="The archive is private. Enter the account created on this machine to read its files, memories, and media."
      footer={
        <p>
          No account yet? The setup screen appears automatically when the archive
          has no keeper. There is no cloud recovery.
        </p>
      }
    >
      <form className="auth-form" onSubmit={handleSubmit}>
        <label className="auth-field" htmlFor={usernameId}>
          <span>Username</span>
          <input
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
        </label>

        <label className="auth-field" htmlFor={passwordId}>
          <span>Password</span>
          <span className="auth-password">
            <input
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
              aria-label={showPassword ? "Hide password" : "Show password"}
              disabled={isSubmitting}
            >
              {showPassword ? "Hide" : "Show"}
            </button>
          </span>
        </label>

        {error ? (
          <p className="auth-error" role="alert">
            <Icon name="info" size={16} />
            {error}
          </p>
        ) : null}

        <Button type="submit" variant="ink" size="lg" block disabled={isSubmitting}>
          {isSubmitting ? "Opening the archive…" : "Enter the archive"}
          {!isSubmitting ? <Icon name="arrow-right" size={17} /> : null}
        </Button>
      </form>
    </AuthFrame>
  );
}
