import { useId, useState } from "react";

import { Button } from "../../component/Button";
import { Icon } from "../../component/Icon";
import { useToast } from "../../component/Toast";
import { useI18n } from "../../i18n";
import { companionRef, useCompanionStory, type CompanionStory as Story } from "../api";
import type { CompanionCharacter } from "../manifest";
import {
  PERSONA_MAX,
  groupLoreByTier,
  loreSnippet,
  type LoreFragment,
  type LoreInput,
} from "../story";
import { LoreForm, TIER_LABEL_KEYS } from "./LoreForm";

const EMPTY_LORE: LoreInput = { text: "", themes: [], tier: "familiar" };

let localSequence = 0;

function PersonaEditor({
  story,
  isPreset,
  initial,
}: {
  readonly story: Story;
  readonly isPreset: boolean;
  readonly initial: string;
}) {
  const { t, formatNumber } = useI18n();
  const toast = useToast();
  const fieldId = useId();
  const [draft, setDraft] = useState(initial);
  const [busy, setBusy] = useState(false);

  const run = async (action: () => Promise<void>, done: string) => {
    setBusy(true);
    try {
      await action();
      toast.success(done);
    } catch {
      toast.error(t("companion.story.error"));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="companion-story__persona">
      <label className="companion-story__label" htmlFor={fieldId}>
        {t("companion.story.personaLabel")}
      </label>
      <textarea
        id={fieldId}
        className="input companion-story__persona-text"
        value={draft}
        rows={7}
        maxLength={PERSONA_MAX}
        aria-describedby={`${fieldId}-hint ${fieldId}-count`}
        onChange={(event) => setDraft(event.currentTarget.value)}
      />
      <div className="companion-story__persona-meta">
        <span id={`${fieldId}-hint`}>{t("companion.story.personaHint")}</span>
        <span id={`${fieldId}-count`} className="companion-story__count">
          {t("companion.story.personaCount", {
            count: formatNumber(draft.length),
            max: formatNumber(PERSONA_MAX),
          })}
        </span>
      </div>
      <div className="companion-story__actions">
        {isPreset ? (
          <Button
            variant="ghost"
            size="sm"
            disabled={!story.supported || busy}
            onClick={() => void run(story.resetPersona, t("companion.story.personaResetDone"))}
          >
            {t("companion.story.personaReset")}
          </Button>
        ) : null}
        <Button
          variant="ink"
          size="sm"
          disabled={!story.supported || busy || draft === initial}
          aria-busy={busy}
          onClick={() => void run(() => story.savePersona(draft), t("companion.story.personaSaved"))}
        >
          {t("companion.story.personaSave")}
        </Button>
      </div>
    </div>
  );
}

function FragmentCard({
  fragment,
  busy,
  onSave,
  onDelete,
}: {
  readonly fragment: LoreFragment;
  readonly busy: boolean;
  readonly onSave: (input: LoreInput) => void;
  readonly onDelete: () => void;
}) {
  const { t } = useI18n();
  const [editing, setEditing] = useState(false);
  const [confirming, setConfirming] = useState(false);
  let provenance = t("companion.lore.yours");
  if (fragment.isDefault) {
    provenance = fragment.edited ? t("companion.lore.edited") : t("companion.lore.authored");
  }

  if (editing) {
    return (
      <article className="companion-page">
        <LoreForm
          initial={{ text: fragment.text, themes: fragment.themes, tier: fragment.tier }}
          busy={busy}
          onSubmit={(input) => {
            onSave(input);
            setEditing(false);
          }}
          onCancel={() => setEditing(false)}
        />
      </article>
    );
  }

  return (
    <article className="companion-page">
      <details className="companion-page__details">
        <summary className="companion-page__summary">
          <span className="companion-page__snippet">{loreSnippet(fragment.text)}</span>
          <span className="companion-page__read">{t("companion.lore.read")}</span>
        </summary>
        <p className="companion-page__text">{fragment.text}</p>
      </details>
      <footer className="companion-page__meta">
        <span className="companion-page__badge">{provenance}</span>
        {fragment.themes.map((theme) => (
          <span key={theme} className="companion-chip is-static">
            {theme}
          </span>
        ))}
        <span className="companion-page__tools">
          {confirming ? (
            <>
              <span className="companion-page__confirm">{t("companion.lore.confirmDelete")}</span>
              <Button variant="danger" size="sm" disabled={busy} onClick={onDelete}>
                {t("companion.lore.confirm")}
              </Button>
              <Button variant="ghost" size="sm" onClick={() => setConfirming(false)}>
                {t("companion.lore.cancel")}
              </Button>
            </>
          ) : (
            <>
              <Button variant="ghost" size="sm" disabled={busy} onClick={() => setEditing(true)}>
                <Icon name="pencil" size={12} />
                {t("companion.lore.edit")}
              </Button>
              <Button variant="ghost" size="sm" disabled={busy} onClick={() => setConfirming(true)}>
                <Icon name="trash" size={12} />
                {t("companion.lore.delete")}
              </Button>
            </>
          )}
        </span>
      </footer>
    </article>
  );
}

/**
 * A companion's story: the persona the assistant follows when speaking as the
 * librarian, and the lore fragments it may weave into an answer in its own
 * words. Until the story endpoints exist, edits are a local draft in this tab
 * and saving is disabled.
 */
export function CompanionStory({ character }: { readonly character: CompanionCharacter }) {
  const { t } = useI18n();
  const toast = useToast();
  const headingId = useId();
  const ref = companionRef(character);
  const story = useCompanionStory(ref);
  const isPreset = ref.startsWith("preset:");
  const [localLore, setLocalLore] = useState<readonly LoreFragment[]>([]);
  const [adding, setAdding] = useState(false);
  const [confirmReset, setConfirmReset] = useState(false);
  const [busy, setBusy] = useState(false);
  const fragments = story.supported ? story.lore : localLore;
  const groups = groupLoreByTier(fragments);

  const mutate = async (remote: () => Promise<void>, local: () => void, done: string) => {
    if (!story.supported) {
      local();
      return;
    }
    setBusy(true);
    try {
      await remote();
      toast.success(done);
    } catch {
      toast.error(t("companion.story.error"));
    } finally {
      setBusy(false);
    }
  };

  const addFragment = (input: LoreInput) => {
    setAdding(false);
    void mutate(
      () => story.createLore(input),
      () => {
        localSequence += 1;
        const id = `local-${localSequence}`;
        setLocalLore((current) => [...current, { id, ...input, isDefault: false, edited: false }]);
      },
      t("companion.lore.saved"),
    );
  };

  const saveFragment = (id: string, input: LoreInput) =>
    void mutate(
      () => story.updateLore(id, input),
      () =>
        setLocalLore((current) =>
          current.map((item) => (item.id === id ? { ...item, ...input, edited: true } : item)),
        ),
      t("companion.lore.saved"),
    );

  const deleteFragment = (id: string) =>
    void mutate(
      () => story.deleteLore(id),
      () => setLocalLore((current) => current.filter((item) => item.id !== id)),
      t("companion.lore.deleted"),
    );

  const resetAll = () => {
    setConfirmReset(false);
    void mutate(story.resetLore, () => setLocalLore([]), t("companion.lore.resetDone"));
  };

  return (
    <section className="companion-story" aria-labelledby={headingId}>
      <header className="companion-story__head">
        <h3 id={headingId} className="companion-story__title">
          {t("companion.story.title", { name: character.name })}
        </h3>
        <p className="companion-story__description">
          {t("companion.story.description", { name: character.name })}
        </p>
        {!story.supported ? (
          <p className="companion-editor__notice" role="note">
            <Icon name="info" size={14} />
            <span>{t("companion.story.unavailable")}</span>
          </p>
        ) : null}
      </header>

      <PersonaEditor
        key={`${ref}:${story.persona?.text ?? ""}`}
        story={story}
        isPreset={isPreset}
        initial={story.persona?.text ?? ""}
      />

      <div className="companion-lore">
        <div className="companion-lore__head">
          <span className="companion-lore__spool" aria-hidden="true" />
          <div>
            <h4 className="companion-lore__title">{t("companion.lore.title")}</h4>
            <p className="companion-lore__description">
              {t("companion.lore.description", { name: character.name })}
            </p>
          </div>
        </div>

        {fragments.length === 0 && !adding ? (
          <p className="companion-lore__empty">
            {t("companion.lore.empty", { name: character.name })}
          </p>
        ) : null}

        {groups.map((group) => (
          <section key={group.tier} className={`companion-lore__tier is-${group.tier}`}>
            <h5 className="companion-lore__tier-title">{t(TIER_LABEL_KEYS[group.tier])}</h5>
            <div className="companion-lore__pages">
              {group.fragments.map((fragment) => (
                <FragmentCard
                  key={fragment.id}
                  fragment={fragment}
                  busy={busy}
                  onSave={(input) => saveFragment(fragment.id, input)}
                  onDelete={() => deleteFragment(fragment.id)}
                />
              ))}
            </div>
          </section>
        ))}

        {adding ? (
          <div className="companion-page is-new">
            <LoreForm
              initial={EMPTY_LORE}
              busy={busy}
              onSubmit={addFragment}
              onCancel={() => setAdding(false)}
            />
          </div>
        ) : null}

        <div className="companion-lore__actions">
          {confirmReset ? (
            <>
              <span className="companion-lore__confirm">{t("companion.lore.confirmReset")}</span>
              <Button variant="danger" size="sm" disabled={busy} onClick={resetAll}>
                {t("companion.lore.confirm")}
              </Button>
              <Button variant="ghost" size="sm" onClick={() => setConfirmReset(false)}>
                {t("companion.lore.cancel")}
              </Button>
            </>
          ) : (
            <>
              <Button
                variant="ghost"
                size="sm"
                disabled={busy || fragments.length === 0}
                onClick={() => setConfirmReset(true)}
              >
                {t("companion.lore.resetAll")}
              </Button>
              <Button
                variant="secondary"
                size="sm"
                disabled={busy || adding}
                onClick={() => setAdding(true)}
              >
                <Icon name="plus" size={12} />
                {t("companion.lore.add")}
              </Button>
            </>
          )}
        </div>
      </div>
    </section>
  );
}
