import {
  useEffect,
  useId,
  useRef,
  useState,
  type FormEvent,
  type KeyboardEvent,
  type ReactNode,
  type RefObject,
} from "react";
import { useQueryClient } from "@tanstack/react-query";

import { Badge } from "../../component/Badge";
import { Button } from "../../component/Button";
import { CopyButton } from "../../component/CopyButton";
import { Icon } from "../../component/Icon";
import { Panel } from "../../component/Panel";
import { useToast } from "../../component/Toast";
import { useI18n } from "../../i18n";
import type { VisionPromptSettingsReadSchema } from "../../generated-apis-types/schemas";
import {
  getGetIngestVisionPromptsQueryKey,
  useGetIngestVisionPrompts,
  useUpdateIngestVisionPrompts,
} from "../../generated-apis-types/settings/settings";
import { RuntimeError } from "./RuntimeControls";
import { apiErrorMessage } from "./settings-utils";
import { VisionPromptEditor } from "./VisionPromptEditor";
import {
  VISION_PROMPT_MODES,
  fromVisionPromptDrafts,
  shortSha256,
  toVisionPromptDrafts,
  validateVisionPrompt,
  visionPromptDraftsMatch,
  visionPromptWarnings,
  type VisionPromptDrafts,
  type VisionPromptMode,
  type VisionPromptValues,
} from "./vision-prompt-utils";

interface VisionPromptPanelFrameProps {
  readonly children: ReactNode;
  readonly action?: ReactNode;
}

function promptValuesKey(values: VisionPromptValues): string {
  return JSON.stringify([values.image_prompt, values.document_prompt]);
}

function promptFor(
  values: VisionPromptValues,
  mode: VisionPromptMode,
): string {
  return mode === "image" ? values.image_prompt : values.document_prompt;
}

function VisionPromptPanelFrame({
  children,
  action,
}: VisionPromptPanelFrameProps) {
  const { t } = useI18n();
  return (
    <Panel
      title={
        <span className="settings-panel__title">
          <Icon name="pencil" size={16} />
          {t("settings.visionPrompts.title")}
        </span>
      }
      action={action}
      className="settings-panel vision-prompt-panel"
    >
      {children}
    </Panel>
  );
}

interface VisionPromptSettingsFormProps {
  readonly settings: VisionPromptSettingsReadSchema;
  readonly saving: boolean;
  readonly error: string | null;
  readonly onSave: (values: VisionPromptValues) => void;
  readonly onDiscard: () => void;
}

function VisionPromptSettingsForm({
  settings,
  saving,
  error,
  onSave,
  onDiscard,
}: VisionPromptSettingsFormProps) {
  const { t, formatDateTime, formatNumber } = useI18n();
  const [drafts, setDrafts] = useState<VisionPromptDrafts>(() =>
    toVisionPromptDrafts(settings.config),
  );
  const [activeMode, setActiveMode] = useState<VisionPromptMode>("image");
  const imageTextareaRef = useRef<HTMLTextAreaElement>(null);
  const documentTextareaRef = useRef<HTMLTextAreaElement>(null);
  const imageTabRef = useRef<HTMLButtonElement>(null);
  const documentTabRef = useRef<HTMLButtonElement>(null);
  const contractId = useId();
  const tabBaseId = useId();

  const textareaRefs: Record<
    VisionPromptMode,
    RefObject<HTMLTextAreaElement | null>
  > = {
    image: imageTextareaRef,
    document: documentTextareaRef,
  };
  const tabRefs: Record<
    VisionPromptMode,
    RefObject<HTMLButtonElement | null>
  > = {
    image: imageTabRef,
    document: documentTabRef,
  };

  const savedKey = promptValuesKey(settings.config);
  const syncedKey = useRef(savedKey);

  useEffect(() => {
    if (syncedKey.current === savedKey) {
      return;
    }
    syncedKey.current = savedKey;
    setDrafts(toVisionPromptDrafts(settings.config));
  }, [savedKey, settings.config]);

  const fieldErrors: Record<VisionPromptMode, string | null> = {
    image: validateVisionPrompt(
      drafts.image,
      settings.max_chars,
      settings.required_keys,
      t,
      formatNumber,
    ),
    document: validateVisionPrompt(
      drafts.document,
      settings.max_chars,
      settings.required_keys,
      t,
      formatNumber,
    ),
  };
  const invalidModes = VISION_PROMPT_MODES.filter(
    (mode) => fieldErrors[mode] !== null,
  );
  const hasErrors = invalidModes.length > 0;
  const dirty = !visionPromptDraftsMatch(drafts, settings.config);
  const customPrompts =
    settings.config.image_prompt !== settings.defaults.image_prompt ||
    settings.config.document_prompt !== settings.defaults.document_prompt;

  const isDefaultForMode = (mode: VisionPromptMode): boolean =>
    promptFor(settings.config, mode) === promptFor(settings.defaults, mode);

  const updateDraft = (mode: VisionPromptMode, value: string) => {
    setDrafts((current) => ({ ...current, [mode]: value }));
  };

  const restoreDefault = (mode: VisionPromptMode) => {
    setDrafts((current) => ({
      ...current,
      [mode]: promptFor(settings.defaults, mode),
    }));
  };

  const selectMode = (mode: VisionPromptMode) => {
    setActiveMode(mode);
  };

  const handleTabKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    const currentIndex = VISION_PROMPT_MODES.indexOf(activeMode);
    let next: VisionPromptMode | null = null;
    if (event.key === "ArrowRight") {
      next = VISION_PROMPT_MODES[(currentIndex + 1) % VISION_PROMPT_MODES.length];
    } else if (event.key === "ArrowLeft") {
      next =
        VISION_PROMPT_MODES[
          (currentIndex - 1 + VISION_PROMPT_MODES.length) %
            VISION_PROMPT_MODES.length
        ];
    } else if (event.key === "Home") {
      next = VISION_PROMPT_MODES[0];
    } else if (event.key === "End") {
      next = VISION_PROMPT_MODES[VISION_PROMPT_MODES.length - 1];
    }
    if (next === null) {
      return;
    }
    event.preventDefault();
    selectMode(next);
    tabRefs[next].current?.focus();
  };

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!dirty || saving) {
      return;
    }
    const firstInvalid = invalidModes[0];
    if (firstInvalid !== undefined) {
      selectMode(firstInvalid);
      window.requestAnimationFrame(() => {
        textareaRefs[firstInvalid].current?.focus();
      });
      return;
    }
    onSave(fromVisionPromptDrafts(drafts));
  };

  const handleDiscard = () => {
    setDrafts(toVisionPromptDrafts(settings.config));
    onDiscard();
  };

  return (
    <VisionPromptPanelFrame
      action={
        <Badge tone={customPrompts ? "moss" : "neutral"} dot>
          {customPrompts
            ? t("settings.visionPrompts.custom")
            : t("settings.visionPrompts.builtIn")}
        </Badge>
      }
    >
      <p className="settings-lede">{t("settings.visionPrompts.lede")}</p>

      <div
        className="vision-prompt__status"
        aria-label={t("settings.visionPrompts.statusAria")}
      >
        <Badge
          tone={settings.source === "database" ? "moss" : "neutral"}
          dot
        >
          {settings.source === "database"
            ? t("settings.visionPrompts.sourceDatabase")
            : t("settings.visionPrompts.sourceDefault")}
        </Badge>
        <span className="vision-prompt__updated">
          {settings.updated_at ? (
            <>
              {t("settings.visionPrompts.lastUpdated")}{" "}
              <time dateTime={settings.updated_at}>
                {formatDateTime(settings.updated_at)}
              </time>
            </>
          ) : (
            t("settings.visionPrompts.noUpdate")
          )}
        </span>
        {dirty ? (
          <span className="vision-prompt__draft">
            {t("settings.visionPrompts.unsavedDraft")}
          </span>
        ) : null}
      </div>

      <div className="vision-prompt__note" role="note">
        <Icon name="history" size={15} />
        <span>{t("settings.visionPrompts.existingFilesNote")}</span>
      </div>

      <section
        className="vision-prompt-contract"
        aria-labelledby={contractId}
      >
        <div className="vision-prompt-contract__head">
          <Icon name="info" size={15} />
          <div>
            <h3 id={contractId}>
              {t("settings.visionPrompts.contractTitle")}
            </h3>
            <p>{t("settings.visionPrompts.contractBody")}</p>
          </div>
        </div>
        <ul
          className="vision-prompt-contract__keys"
          aria-label={t("settings.visionPrompts.contractKeysAria")}
        >
          {settings.required_keys.map((key) => (
            <li key={key}>
              <code>{key}</code>
            </li>
          ))}
        </ul>
        <p className="vision-prompt-contract__hint">
          {t("settings.visionPrompts.placeholderHint", {
            token: "{language}",
          })}
        </p>
      </section>

      <form
        className="vision-prompt-form"
        onSubmit={handleSubmit}
        aria-busy={saving}
        noValidate
      >
        <div
          className="vision-prompt__tabs"
          role="tablist"
          aria-label={t("settings.visionPrompts.tabsAria")}
          onKeyDown={handleTabKeyDown}
        >
          {VISION_PROMPT_MODES.map((mode) => {
            const selected = activeMode === mode;
            const label =
              mode === "image"
                ? t("settings.visionPrompts.tabImage")
                : t("settings.visionPrompts.tabDocument");
            return (
              <button
                key={mode}
                ref={tabRefs[mode]}
                type="button"
                role="tab"
                id={`${tabBaseId}-tab-${mode}`}
                aria-selected={selected}
                aria-controls={`${tabBaseId}-panel-${mode}`}
                tabIndex={selected ? 0 : -1}
                className={
                  selected
                    ? "vision-prompt__tab is-active"
                    : "vision-prompt__tab"
                }
                onClick={() => selectMode(mode)}
              >
                <span className="vision-prompt__tab-label">{label}</span>
                <span
                  className={
                    isDefaultForMode(mode)
                      ? "vision-prompt__tab-source"
                      : "vision-prompt__tab-source is-custom"
                  }
                >
                  {isDefaultForMode(mode)
                    ? t("settings.visionPrompts.builtIn")
                    : t("settings.visionPrompts.custom")}
                </span>
                {fieldErrors[mode] ? (
                  <span className="visually-hidden">
                    {t("settings.visionPrompts.tabError")}
                  </span>
                ) : null}
              </button>
            );
          })}
        </div>

        {VISION_PROMPT_MODES.map((mode) => (
          <div
            key={mode}
            id={`${tabBaseId}-panel-${mode}`}
            role="tabpanel"
            aria-labelledby={`${tabBaseId}-tab-${mode}`}
            hidden={activeMode !== mode}
            className="vision-prompt__panel"
          >
            <VisionPromptEditor
              mode={mode}
              label={
                mode === "image"
                  ? t("settings.visionPrompts.imageLabel")
                  : t("settings.visionPrompts.documentLabel")
              }
              description={
                mode === "image"
                  ? t("settings.visionPrompts.imageDescription")
                  : t("settings.visionPrompts.documentDescription")
              }
              value={drafts[mode]}
              maxChars={settings.max_chars}
              error={fieldErrors[mode]}
              warnings={
                fieldErrors[mode] === null
                  ? visionPromptWarnings(drafts[mode], t)
                  : []
              }
              disabled={saving}
              isDefault={isDefaultForMode(mode)}
              restoreDisabled={
                drafts[mode].trim() === promptFor(settings.defaults, mode)
              }
              textareaRef={textareaRefs[mode]}
              onChange={(value) => updateDraft(mode, value)}
              onRestoreDefault={() => restoreDefault(mode)}
            />
          </div>
        ))}

        {error ? <RuntimeError message={error} /> : null}

        <div className="vision-prompt__actions">
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={handleDiscard}
            disabled={!dirty || saving}
          >
            {t("settings.visionPrompts.discard")}
          </Button>
          <div className="vision-prompt__save">
            {dirty ? (
              <span
                className={
                  hasErrors
                    ? "vision-prompt__save-note is-invalid"
                    : "vision-prompt__save-note"
                }
              >
                {hasErrors
                  ? t("settings.visionPrompts.invalidNote")
                  : t("settings.visionPrompts.unsavedChanges")}
              </span>
            ) : null}
            <Button
              type="submit"
              variant="ink"
              size="sm"
              disabled={!dirty || saving}
            >
              <Icon name="check" size={14} />
              {saving
                ? t("settings.visionPrompts.saving")
                : t("settings.visionPrompts.save")}
            </Button>
          </div>
        </div>
      </form>

      <details className="vision-prompt__tech">
        <summary>{t("settings.visionPrompts.technical")}</summary>
        <p className="vision-prompt__tech-note">
          {t("settings.visionPrompts.technicalNote", {
            token: "{language}",
          })}
        </p>
        <dl className="vision-prompt__hashes">
          <div className="vision-prompt__hash">
            <dt>{t("settings.visionPrompts.imageFingerprint")}</dt>
            <dd>
              {settings.image_prompt_sha256 ? (
                <>
                  <code title={settings.image_prompt_sha256}>
                    {shortSha256(settings.image_prompt_sha256)}
                  </code>
                  <CopyButton
                    value={settings.image_prompt_sha256}
                    label={t("settings.visionPrompts.copyFingerprint")}
                    title={t("settings.visionPrompts.fullFingerprint")}
                    iconOnly
                  />
                </>
              ) : (
                t("settings.visionPrompts.fingerprintUnavailable")
              )}
            </dd>
          </div>
          <div className="vision-prompt__hash">
            <dt>{t("settings.visionPrompts.documentFingerprint")}</dt>
            <dd>
              {settings.document_prompt_sha256 ? (
                <>
                  <code title={settings.document_prompt_sha256}>
                    {shortSha256(settings.document_prompt_sha256)}
                  </code>
                  <CopyButton
                    value={settings.document_prompt_sha256}
                    label={t("settings.visionPrompts.copyFingerprint")}
                    title={t("settings.visionPrompts.fullFingerprint")}
                    iconOnly
                  />
                </>
              ) : (
                t("settings.visionPrompts.fingerprintUnavailable")
              )}
            </dd>
          </div>
        </dl>
      </details>
    </VisionPromptPanelFrame>
  );
}

/**
 * Loads, edits, and saves the two global vision prompts. This panel is a
 * sibling of the ingestion runtime form and deliberately uses its own query and
 * PUT endpoint, so resetting runtime values never touches custom prompts.
 */
export function VisionPromptSettingsPanel() {
  const { t } = useI18n();
  const queryClient = useQueryClient();
  const toast = useToast();
  const [mutationError, setMutationError] = useState<string | null>(null);

  const settingsQuery = useGetIngestVisionPrompts({
    query: { staleTime: 60_000 },
  });

  const updatePrompts = useUpdateIngestVisionPrompts({
    mutation: {
      onSuccess: async (settings) => {
        queryClient.setQueryData(
          getGetIngestVisionPromptsQueryKey(),
          settings,
        );
        setMutationError(null);
        toast.success(t("settings.visionPrompts.savedToast"));
        await queryClient.invalidateQueries({
          queryKey: getGetIngestVisionPromptsQueryKey(),
          refetchType: "active",
        });
      },
      onError: (error) => {
        setMutationError(apiErrorMessage(error));
      },
    },
  });

  if (settingsQuery.isPending) {
    return (
      <VisionPromptPanelFrame>
        <div
          className="runtime-loading"
          role="status"
          aria-busy="true"
          aria-label={t("settings.visionPrompts.loadReadingAria")}
        >
          <span className="settings-skeleton settings-skeleton--line" />
          <span className="settings-skeleton settings-skeleton--line is-short" />
          <span className="settings-skeleton settings-skeleton--field" />
          <span className="settings-skeleton settings-skeleton--field" />
        </div>
      </VisionPromptPanelFrame>
    );
  }

  if (settingsQuery.isError || !settingsQuery.data) {
    return (
      <VisionPromptPanelFrame>
        <div className="settings-inline-error" role="alert">
          <Icon name="info" size={16} />
          <div>
            <strong>{t("settings.visionPrompts.loadErrorTitle")}</strong>
            <p>{apiErrorMessage(settingsQuery.error)}</p>
            <Button
              type="button"
              variant="ghost"
              size="sm"
              onClick={() => void settingsQuery.refetch()}
              disabled={settingsQuery.isFetching}
            >
              <Icon name="ring" size={14} />
              {settingsQuery.isFetching
                ? t("core.common.retrying")
                : t("core.common.retry")}
            </Button>
          </div>
        </div>
      </VisionPromptPanelFrame>
    );
  }

  return (
    <VisionPromptSettingsForm
      settings={settingsQuery.data}
      saving={updatePrompts.isPending}
      error={mutationError}
      onSave={(values) => {
        setMutationError(null);
        updatePrompts.mutate({ data: values });
      }}
      onDiscard={() => setMutationError(null)}
    />
  );
}
