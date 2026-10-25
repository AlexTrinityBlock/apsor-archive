import { useId, useState, type FormEvent } from "react";
import { useQueryClient } from "@tanstack/react-query";

import { Badge } from "../component/Badge";
import { Button } from "../component/Button";
import { Icon } from "../component/Icon";
import { Loader } from "../component/Loader";
import { PageHeader } from "../component/PageHeader";
import { Panel } from "../component/Panel";
import { useToast } from "../component/Toast";
import {
  getGetAuthStatusQueryKey,
  getGetUserProfileQueryKey,
  useGetUserProfile,
  useUpdateUserProfile,
} from "../generated-apis-types";
import type {
  AuthStatusSchema,
  UserProfileSchema,
} from "../generated-apis-types/schemas";
import { apiErrorMessage } from "../settings/component/settings-utils";
import "./profile.css";

interface DraftCard {
  readonly key: string;
  readonly title: string;
  readonly content: string;
}

function draftCards(profile: UserProfileSchema): DraftCard[] {
  return profile.cards.map((card) => ({
    key: `card-${card.card_id}`,
    title: card.title,
    content: card.content,
  }));
}

let draftSequence = 0;

function newDraftCard(): DraftCard {
  draftSequence += 1;
  return {
    key: `new-${Date.now()}-${draftSequence}`,
    title: "",
    content: "",
  };
}

function ProfileCard({
  card,
  index,
  total,
  saving,
  onChange,
  onMove,
  onDelete,
}: {
  readonly card: DraftCard;
  readonly index: number;
  readonly total: number;
  readonly saving: boolean;
  readonly onChange: (key: string, patch: Partial<DraftCard>) => void;
  readonly onMove: (key: string, direction: -1 | 1) => void;
  readonly onDelete: (key: string) => void;
}) {
  const titleId = useId();
  const contentId = useId();
  return (
    <article className="profile-card">
      <header className="profile-card__head">
        <span className="profile-card__index" aria-hidden="true">
          {String(index + 1).padStart(2, "0")}
        </span>
        <label className="profile-card__title-field" htmlFor={titleId}>
          <span className="visually-hidden">Card title</span>
          <input
            id={titleId}
            className="input profile-card__title"
            value={card.title}
            onChange={(event) => onChange(card.key, { title: event.target.value })}
            placeholder="Card title, for example Work or Answer preferences"
            maxLength={120}
            disabled={saving}
          />
        </label>
        <div className="profile-card__actions">
          <button
            type="button"
            className="profile-card__action"
            onClick={() => onMove(card.key, -1)}
            disabled={saving || index === 0}
            aria-label={`Move ${card.title || "card"} up`}
            title="Move up"
          >
            ↑
          </button>
          <button
            type="button"
            className="profile-card__action"
            onClick={() => onMove(card.key, 1)}
            disabled={saving || index === total - 1}
            aria-label={`Move ${card.title || "card"} down`}
            title="Move down"
          >
            ↓
          </button>
          <button
            type="button"
            className="profile-card__action is-danger"
            onClick={() => onDelete(card.key)}
            disabled={saving}
            aria-label={`Delete ${card.title || "card"}`}
            title="Delete card"
          >
            <Icon name="trash" size={13} />
          </button>
        </div>
      </header>
      <label className="profile-card__content-field" htmlFor={contentId}>
        <span className="visually-hidden">Card content</span>
        <textarea
          id={contentId}
          className="textarea profile-card__content"
          value={card.content}
          onChange={(event) => onChange(card.key, { content: event.target.value })}
          placeholder="Write what the archive should know. This becomes one line in the frozen user profile."
          maxLength={2000}
          rows={5}
          disabled={saving}
        />
        <span className="field-help">
          {card.content.length.toLocaleString()} / 2,000 characters
        </span>
      </label>
    </article>
  );
}

function ProfileEditor({ profile }: { readonly profile: UserProfileSchema }) {
  const queryClient = useQueryClient();
  const toast = useToast();
  const formId = "profile-form";
  const [displayName, setDisplayName] = useState(profile.display_name);
  const [cards, setCards] = useState<DraftCard[]>(() => draftCards(profile));
  const [error, setError] = useState<string | null>(null);

  const mutation = useUpdateUserProfile({
    mutation: {
      onSuccess: (data) => {
        queryClient.setQueryData<UserProfileSchema>(
          getGetUserProfileQueryKey(),
          data,
        );
        const status = queryClient.getQueryData<AuthStatusSchema>(
          getGetAuthStatusQueryKey(),
        );
        if (status?.user) {
          queryClient.setQueryData<AuthStatusSchema>(getGetAuthStatusQueryKey(), {
            ...status,
            user: { ...status.user, display_name: data.display_name },
          });
        }
        setError(null);
        toast.success("User profile saved.");
      },
      onError: (caught) => {
        const message = apiErrorMessage(caught);
        setError(message);
        toast.error(message);
      },
    },
  });

  const updateCard = (key: string, patch: Partial<DraftCard>) => {
    setCards((current) =>
      current.map((card) => (card.key === key ? { ...card, ...patch } : card)),
    );
    setError(null);
  };

  const moveCard = (key: string, direction: -1 | 1) => {
    setCards((current) => {
      const index = current.findIndex((card) => card.key === key);
      const target = index + direction;
      if (index < 0 || target < 0 || target >= current.length) {
        return current;
      }
      const next = [...current];
      [next[index], next[target]] = [next[target], next[index]];
      return next;
    });
  };

  const deleteCard = (key: string) => {
    setCards((current) => current.filter((card) => card.key !== key));
    setError(null);
  };

  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const cleanName = displayName.trim();
    if (cleanName.length === 0) {
      setError("A display name is required.");
      return;
    }
    const cleanCards = cards.map((card) => ({
      title: card.title.trim(),
      content: card.content.trim(),
    }));
    if (cleanCards.some((card) => card.title.length === 0 || card.content.length === 0)) {
      setError("Every profile card needs both a title and content.");
      return;
    }
    setError(null);
    mutation.mutate({
      data: {
        display_name: cleanName,
        cards: cleanCards,
      },
    });
  };

  const saving = mutation.isPending;

  return (
    <form id={formId} className="profile-form" onSubmit={submit}>
      <Panel
        tone="plain"
        eyebrow="Identity"
        title="Display name"
        className="profile-identity-panel"
      >
        <label className="field" htmlFor={`${formId}-name`}>
          <span className="field-label">Name / nickname</span>
          <input
            id={`${formId}-name`}
            className="input"
            value={displayName}
            onChange={(event) => {
              setDisplayName(event.target.value);
              setError(null);
            }}
            maxLength={80}
            autoComplete="nickname"
            disabled={saving}
          />
          <span className="field-help">
            Shown in the sidebar and on your chat turns. Your sign-in username is
            managed separately.
          </span>
        </label>
      </Panel>

      <section className="profile-cards" aria-labelledby={`${formId}-cards`}>
        <div className="profile-cards__head">
          <div>
            <p className="eyebrow">Profile cards</p>
            <h2 id={`${formId}-cards`}>How the archive should know you</h2>
            <p className="profile-cards__lede">
              Each card becomes one titled line in the frozen user profile of new
              conversations. Cards are ordered top to bottom; existing
              conversations keep the profile they started with.
            </p>
          </div>
          <Badge tone={cards.length > 0 ? "moss" : "neutral"}>
            {cards.length} {cards.length === 1 ? "card" : "cards"}
          </Badge>
        </div>

        <div className="profile-cards__list">
          {cards.map((card, index) => (
            <ProfileCard
              key={card.key}
              card={card}
              index={index}
              total={cards.length}
              saving={saving}
              onChange={updateCard}
              onMove={moveCard}
              onDelete={deleteCard}
            />
          ))}
        </div>

        {cards.length === 0 ? (
          <div className="profile-cards__empty">
            <p>No profile cards yet. Add one to describe your work, interests, or answer preferences.</p>
          </div>
        ) : null}

        <div className="profile-cards__foot">
          <Button
            type="button"
            variant="secondary"
            size="sm"
            onClick={() => {
              setCards((current) => [...current, newDraftCard()]);
              setError(null);
            }}
            disabled={saving || cards.length >= 20}
          >
            <Icon name="plus" size={13} />
            Add card
          </Button>
          <span className="field-help">Up to 20 cards.</span>
        </div>
      </section>

      {error ? (
        <p className="profile-form__error" role="alert">
          <Icon name="info" size={14} />
          {error}
        </p>
      ) : null}

      <div className="profile-save-bar">
        <span className="field-help">
          Saving replaces every card in one transaction and updates the sidebar name.
        </span>
        <Button type="submit" variant="primary" size="sm" disabled={saving}>
          <Icon name="check" size={14} />
          {saving ? "Saving…" : "Save profile"}
        </Button>
      </div>
    </form>
  );
}

/** Editable multi-card user profile; frozen into new agent conversations. */
export function ProfilePage() {
  const query = useGetUserProfile({ query: { retry: false, staleTime: 15_000 } });

  let body = null;
  if (query.isPending) {
    body = (
      <div className="profile-loading" role="status">
        <Loader size={18} label="Reading the user profile" />
      </div>
    );
  } else if (query.isError) {
    body = (
      <div className="profile-error" role="alert">
        <Icon name="info" size={16} />
        <div>
          <strong>The user profile did not answer.</strong>
          <p>{apiErrorMessage(query.error)}</p>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={() => void query.refetch()}
            disabled={query.isFetching}
          >
            <Icon name="ring" size={14} />
            {query.isFetching ? "Retrying…" : "Retry"}
          </Button>
        </div>
      </div>
    );
  } else if (query.data) {
    const key = [
      query.data.display_name,
      ...query.data.cards.map((card) => card.card_id),
    ].join("|");
    body = <ProfileEditor key={key} profile={query.data} />;
  }

  return (
    <div className="content-container profile-page">
      <PageHeader
        eyebrow="User · profile"
        title="User Profile"
        description="A display name plus ordered cards that describe you. New conversations freeze the current profile into their system prompt; existing conversations keep the profile they started with."
        actions={
          <Button
            type="submit"
            form="profile-form"
            variant="primary"
            size="sm"
            disabled={!query.data || query.isError}
          >
            <Icon name="check" size={14} />
            Save profile
          </Button>
        }
      />
      {body}
    </div>
  );
}
