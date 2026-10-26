import { useId, useState, type FormEvent } from "react";
import { useQueryClient } from "@tanstack/react-query";

import { Badge } from "../component/Badge";
import { Button, ButtonLink } from "../component/Button";
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
import { useApiErrorMessage, useI18n } from "../i18n";
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
  const { t, formatNumber } = useI18n();
  const titleId = useId();
  const contentId = useId();
  const cardLabel = card.title || t("memory.profile.cardFallback");

  return (
    <article className="profile-card">
      <header className="profile-card__head">
        <span className="profile-card__index" aria-hidden="true">
          {String(index + 1).padStart(2, "0")}
        </span>
        <label className="profile-card__title-field" htmlFor={titleId}>
          <span className="visually-hidden">
            {t("memory.profile.cardTitleLabel")}
          </span>
          <input
            id={titleId}
            className="input profile-card__title"
            value={card.title}
            onChange={(event) => onChange(card.key, { title: event.target.value })}
            placeholder={t("memory.profile.cardTitlePlaceholder")}
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
            aria-label={t("memory.profile.moveUpAria", { title: cardLabel })}
            title={t("memory.profile.moveUpTitle")}
          >
            ↑
          </button>
          <button
            type="button"
            className="profile-card__action"
            onClick={() => onMove(card.key, 1)}
            disabled={saving || index === total - 1}
            aria-label={t("memory.profile.moveDownAria", { title: cardLabel })}
            title={t("memory.profile.moveDownTitle")}
          >
            ↓
          </button>
          <button
            type="button"
            className="profile-card__action is-danger"
            onClick={() => onDelete(card.key)}
            disabled={saving}
            aria-label={t("memory.profile.deleteAria", { title: cardLabel })}
            title={t("memory.profile.deleteTitle")}
          >
            <Icon name="trash" size={13} />
          </button>
        </div>
      </header>
      <label className="profile-card__content-field" htmlFor={contentId}>
        <span className="visually-hidden">
          {t("memory.profile.cardContentLabel")}
        </span>
        <textarea
          id={contentId}
          className="textarea profile-card__content"
          value={card.content}
          onChange={(event) => onChange(card.key, { content: event.target.value })}
          placeholder={t("memory.profile.cardContentPlaceholder")}
          maxLength={2000}
          rows={5}
          disabled={saving}
        />
        <span className="field-help">
          {t("memory.profile.cardContentCount", {
            count: formatNumber(card.content.length),
          })}
        </span>
      </label>
    </article>
  );
}

function ProfileEditor({ profile }: { readonly profile: UserProfileSchema }) {
  const { t, formatNumber } = useI18n();
  const apiErrorMessage = useApiErrorMessage();
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
        toast.success(t("memory.profile.savedToast"));
      },
      onError: (caught) => {
        const message = apiErrorMessage(caught, "memory.common.genericError");
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
      setError(t("memory.profile.displayNameRequired"));
      return;
    }
    const cleanCards = cards.map((card) => ({
      title: card.title.trim(),
      content: card.content.trim(),
    }));
    if (cleanCards.some((card) => card.title.length === 0 || card.content.length === 0)) {
      setError(t("memory.profile.cardFieldsRequired"));
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
        eyebrow={t("memory.profile.identityEyebrow")}
        title={t("memory.profile.displayNameTitle")}
        className="profile-identity-panel"
        action={
          <ButtonLink to="/change-password" variant="ghost" size="sm">
            <Icon name="key" size={14} />
            {t("core.nav.changePassword")}
          </ButtonLink>
        }
      >
        <label className="field" htmlFor={`${formId}-name`}>
          <span className="field-label">{t("memory.profile.nameLabel")}</span>
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
          <span className="field-help">{t("memory.profile.nameHelp")}</span>
        </label>
      </Panel>

      <section className="profile-cards" aria-labelledby={`${formId}-cards`}>
        <div className="profile-cards__head">
          <div>
            <p className="eyebrow">{t("memory.profile.cardsEyebrow")}</p>
            <h2 id={`${formId}-cards`}>{t("memory.profile.cardsTitle")}</h2>
            <p className="profile-cards__lede">
              {t("memory.profile.cardsLede")}
            </p>
          </div>
          <Badge tone={cards.length > 0 ? "moss" : "neutral"}>
            {t(
              cards.length === 1
                ? "memory.profile.cardCountOne"
                : "memory.profile.cardCountOther",
              { count: formatNumber(cards.length) },
            )}
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
            <p>{t("memory.profile.empty")}</p>
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
            {t("memory.profile.addCard")}
          </Button>
          <span className="field-help">{t("memory.profile.cardLimit")}</span>
        </div>
      </section>

      {error ? (
        <p className="profile-form__error" role="alert">
          <Icon name="info" size={14} />
          {error}
        </p>
      ) : null}

      <div className="profile-save-bar">
        <span className="field-help">{t("memory.profile.saveBarHelp")}</span>
        <Button type="submit" variant="primary" size="sm" disabled={saving}>
          <Icon name="check" size={14} />
          {saving
            ? t("memory.profile.saving")
            : t("memory.profile.save")}
        </Button>
      </div>
    </form>
  );
}

/** Editable multi-card user profile; frozen into new agent conversations. */
export function ProfilePage() {
  const { t } = useI18n();
  const apiErrorMessage = useApiErrorMessage();
  const query = useGetUserProfile({ query: { retry: false, staleTime: 15_000 } });

  let body = null;
  if (query.isPending) {
    body = (
      <div className="profile-loading" role="status">
        <Loader size={18} label={t("memory.profile.loading")} />
      </div>
    );
  } else if (query.isError) {
    body = (
      <div className="profile-error" role="alert">
        <Icon name="info" size={16} />
        <div>
          <strong>{t("memory.profile.errorTitle")}</strong>
          <p>{apiErrorMessage(query.error, "memory.common.genericError")}</p>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={() => void query.refetch()}
            disabled={query.isFetching}
          >
            <Icon name="ring" size={14} />
            {query.isFetching
              ? t("memory.profile.retrying")
              : t("memory.profile.retry")}
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
        eyebrow={t("memory.profile.eyebrow")}
        title={t("memory.profile.title")}
        description={t("memory.profile.description")}
        actions={
          <Button
            type="submit"
            form="profile-form"
            variant="primary"
            size="sm"
            disabled={!query.data || query.isError}
          >
            <Icon name="check" size={14} />
            {t("memory.profile.save")}
          </Button>
        }
      />
      {body}
    </div>
  );
}
