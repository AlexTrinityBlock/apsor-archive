import { useId, useState, type FormEvent } from "react";

import { useAuth } from "../auth/AuthProvider";
import { Badge } from "./Badge";
import { Button } from "./Button";
import { Icon } from "./Icon";
import { useToast } from "./Toast";
import { SettingsDialog } from "../settings/component/SettingsDialog";

interface OwnerProfileDialogProps {
  readonly onClose: () => void;
}

function initials(value: string): string {
  const compact = value.trim();
  return compact.length > 0 ? compact.slice(0, 2).toUpperCase() : "A";
}

/**
 * The owner's editable identity. The title is the display name shown in the
 * sidebar and on user turns; the body is a self-introduction frozen into new
 * agent conversations.
 */
export function OwnerProfileDialog({ onClose }: OwnerProfileDialogProps) {
  const { user, updateProfile, isProfileSubmitting, error } = useAuth();
  const toast = useToast();
  const formId = useId();
  const nameId = useId();
  const bioId = useId();
  const [displayName, setDisplayName] = useState(
    user?.display_name ?? user?.username ?? "",
  );
  const [bio, setBio] = useState(user?.bio ?? "");
  const [formError, setFormError] = useState<string | null>(null);

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const trimmedName = displayName.trim();
    if (trimmedName.length === 0) {
      setFormError("A display name is required.");
      return;
    }
    setFormError(null);
    const saved = await updateProfile({
      display_name: trimmedName,
      bio: bio.trim().length > 0 ? bio.trim() : null,
    });
    if (saved) {
      toast.success("Owner profile saved.");
      onClose();
    }
  };

  return (
    <SettingsDialog
      eyebrow="Owner · profile"
      title="How should the archive address you?"
      description="Your name appears in the sidebar and on your chat turns. New conversations include your self-introduction in the frozen agent prompt; existing conversations keep the prompt they started with."
      onClose={onClose}
      actions={
        <>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={onClose}
            disabled={isProfileSubmitting}
          >
            Cancel
          </Button>
          <Button
            type="submit"
            form={formId}
            variant="primary"
            size="sm"
            disabled={isProfileSubmitting}
          >
            <Icon name="check" size={14} />
            {isProfileSubmitting ? "Saving…" : "Save profile"}
          </Button>
        </>
      }
    >
      <form id={formId} className="owner-profile-form" onSubmit={submit}>
        <article className="owner-profile-card">
          <header className="owner-profile-card__head">
            <span className="owner-profile-card__mark" aria-hidden="true">
              {initials(displayName || user?.username || "")}
            </span>
            <div className="owner-profile-card__title">
              <p className="eyebrow">Owner card</p>
              <h4>{displayName.trim() || user?.username || "Owner"}</h4>
            </div>
            <Badge tone="neutral">@{user?.username ?? "owner"}</Badge>
          </header>

          <div className="owner-profile-card__body">
            <label className="field" htmlFor={nameId}>
              <span className="field-label">Name / nickname</span>
              <input
                id={nameId}
                className="input"
                value={displayName}
                onChange={(event) => {
                  setDisplayName(event.target.value);
                  setFormError(null);
                }}
                maxLength={80}
                autoComplete="nickname"
                data-autofocus
                disabled={isProfileSubmitting}
              />
              <span className="field-help">
                Shown in the sidebar and on your messages. Your sign-in username
                stays @{user?.username ?? "owner"}.
              </span>
            </label>

            <label className="field" htmlFor={bioId}>
              <span className="field-label">Self-introduction</span>
              <textarea
                id={bioId}
                className="textarea owner-profile-card__bio"
                value={bio}
                onChange={(event) => {
                  setBio(event.target.value);
                  setFormError(null);
                }}
                maxLength={2000}
                rows={6}
                placeholder="What should the archive know about you? Work, interests, the way you like answers."
                disabled={isProfileSubmitting}
              />
              <span className="field-help">
                {bio.length.toLocaleString()} / 2,000 characters
              </span>
            </label>
          </div>
        </article>

        {formError ?? error ? (
          <p className="owner-profile-form__error" role="alert">
            <Icon name="info" size={14} />
            {formError ?? error}
          </p>
        ) : null}
      </form>
    </SettingsDialog>
  );
}
