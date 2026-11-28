import {
  useEffect,
  useId,
  useMemo,
  useRef,
  useState,
  type ChangeEvent,
  type DragEvent,
} from "react";

import { Button } from "../../component/Button";
import { Icon } from "../../component/Icon";
import { useToast } from "../../component/Toast";
import { useI18n } from "../../i18n";
import { ACTION_LABEL_KEYS, COMPANION_ACTIONS, type CompanionAction } from "../actions";
import { useCustomCompanionActions } from "../api";
import {
  ACCEPTED_FRAME_TYPES,
  DEFAULT_DRAFT_FPS,
  MAX_FRAMES_PER_ACTION,
  MAX_FRAME_BYTES,
  draftCharacter,
  moveFrame,
  screenFrames,
  type DraftActions,
  type DraftFrame,
  type FrameRejection,
} from "../custom-draft";
import type { CompanionGender } from "../manifest";
import type { CompanionMotion } from "../preference";
import { CompanionPreview } from "./CompanionPreview";

let frameSequence = 0;

function nextFrameId(): string {
  frameSequence += 1;
  return `frame-${frameSequence}`;
}

interface ActionRowProps {
  readonly action: CompanionAction;
  readonly frames: readonly DraftFrame[];
  readonly fps: number;
  readonly onAdd: (action: CompanionAction, files: readonly File[]) => void;
  readonly onRemove: (action: CompanionAction, index: number) => void;
  readonly onMove: (action: CompanionAction, index: number, delta: -1 | 1) => void;
  readonly onFps: (action: CompanionAction, fps: number) => void;
}

function ActionRow({ action, frames, fps, onAdd, onRemove, onMove, onFps }: ActionRowProps) {
  const { t } = useI18n();
  const inputId = useId();
  const speedId = useId();
  const [over, setOver] = useState(false);
  const label = t(ACTION_LABEL_KEYS[action]);
  let countLabel = t("companion.editor.noFrames");
  if (frames.length > 0) {
    const key = frames.length === 1 ? "companion.editor.framesOne" : "companion.editor.framesOther";
    countLabel = t(key, { count: frames.length });
  }

  const onDrop = (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    setOver(false);
    onAdd(action, [...event.dataTransfer.files]);
  };

  const onChange = (event: ChangeEvent<HTMLInputElement>) => {
    onAdd(action, [...(event.currentTarget.files ?? [])]);
    event.currentTarget.value = "";
  };

  return (
    <li className="companion-editor__row">
      <div className="companion-editor__row-head">
        <span className="companion-editor__action">
          {label}
          {action === "idle" ? (
            <span className="companion-editor__required">{t("companion.editor.required")}</span>
          ) : null}
        </span>
        <span className="companion-editor__count">{countLabel}</span>
      </div>
      <div
        className={`companion-editor__drop${over ? " is-over" : ""}`}
        onDragOver={(event) => {
          event.preventDefault();
          setOver(true);
        }}
        onDragLeave={() => setOver(false)}
        onDrop={onDrop}
      >
        {frames.length > 0 ? (
          <ol className="companion-editor__frames">
            {frames.map((frame, index) => (
              <li key={frame.id} className="companion-editor__frame">
                <img src={frame.url} alt="" width={48} height={72} draggable={false} />
                <span className="companion-editor__frame-index" aria-hidden="true">
                  {index + 1}
                </span>
                <span className="companion-editor__frame-tools">
                  <button
                    type="button"
                    onClick={() => onMove(action, index, -1)}
                    disabled={index === 0}
                    aria-label={t("companion.editor.moveEarlier", { index: index + 1 })}
                    title={t("companion.editor.moveEarlier", { index: index + 1 })}
                  >
                    <Icon name="arrow-up" size={11} />
                  </button>
                  <button
                    type="button"
                    onClick={() => onMove(action, index, 1)}
                    disabled={index === frames.length - 1}
                    aria-label={t("companion.editor.moveLater", { index: index + 1 })}
                    title={t("companion.editor.moveLater", { index: index + 1 })}
                  >
                    <Icon name="arrow-down" size={11} />
                  </button>
                  <button
                    type="button"
                    onClick={() => onRemove(action, index)}
                    aria-label={t("companion.editor.removeFrame", { index: index + 1 })}
                    title={t("companion.editor.removeFrame", { index: index + 1 })}
                  >
                    <Icon name="close" size={11} />
                  </button>
                </span>
              </li>
            ))}
          </ol>
        ) : null}
        <p className="companion-editor__drop-hint">
          {t("companion.editor.dropHint")}{" "}
          <label htmlFor={inputId} className="companion-editor__choose">
            {t("companion.editor.chooseFiles")}
          </label>
          <input
            id={inputId}
            className="visually-hidden"
            type="file"
            accept={ACCEPTED_FRAME_TYPES.join(",")}
            multiple
            onChange={onChange}
            aria-label={t("companion.editor.chooseFilesFor", { action: label })}
          />
        </p>
      </div>
      {frames.length > 1 ? (
        <label className="companion-editor__speed" htmlFor={speedId}>
          <span>{t("companion.editor.speed")}</span>
          <input
            id={speedId}
            type="range"
            min={2}
            max={12}
            step={1}
            value={fps}
            onChange={(event) => onFps(action, Number(event.currentTarget.value))}
            aria-valuetext={t("companion.editor.speedValue", { fps })}
          />
          <span className="companion-editor__speed-value">
            {t("companion.editor.speedValue", { fps })}
          </span>
        </label>
      ) : null}
    </li>
  );
}

/**
 * Build a custom companion from uploaded images, one or more per action, and
 * preview it live. Saving goes through the companion data layer; until the
 * backend exists the draft stays in this tab and saving is disabled.
 */
export function CustomCompanionEditor({ motion }: { readonly motion: CompanionMotion }) {
  const { t } = useI18n();
  const toast = useToast();
  const nameId = useId();
  const genderId = useId();
  const api = useCustomCompanionActions();
  const [name, setName] = useState("");
  const [gender, setGender] = useState<CompanionGender>("unspecified");
  const [actions, setActions] = useState<DraftActions>({});
  const [errors, setErrors] = useState<readonly string[]>([]);
  const [saving, setSaving] = useState(false);
  const urls = useRef(new Set<string>());

  useEffect(() => {
    const owned = urls.current;
    return () => {
      for (const url of owned) {
        URL.revokeObjectURL(url);
      }
      owned.clear();
    };
  }, []);

  const describe = (rejection: FrameRejection): string => {
    switch (rejection.kind) {
      case "type":
        return t("companion.editor.unsupportedType", { file: rejection.file });
      case "size":
        return t("companion.editor.tooLarge", {
          file: rejection.file,
          size: `${MAX_FRAME_BYTES / 1024 / 1024} MB`,
        });
      default:
        return t("companion.editor.tooMany", { count: MAX_FRAMES_PER_ACTION });
    }
  };

  const addFrames = (action: CompanionAction, files: readonly File[]) => {
    const current = actions[action];
    const { accepted, rejected } = screenFrames(files, current?.frames.length ?? 0);
    const added = accepted.map((file) => {
      const url = URL.createObjectURL(file);
      urls.current.add(url);
      return { id: nextFrameId(), file, url };
    });
    setErrors(rejected.map(describe));
    if (added.length > 0) {
      setActions((state) => ({
        ...state,
        [action]: {
          frames: [...(state[action]?.frames ?? []), ...added],
          fps: state[action]?.fps ?? DEFAULT_DRAFT_FPS,
        },
      }));
    }
  };

  const removeFrame = (action: CompanionAction, index: number) => {
    const frame = actions[action]?.frames[index];
    if (frame !== undefined) {
      URL.revokeObjectURL(frame.url);
      urls.current.delete(frame.url);
    }
    setActions((state) => {
      const entry = state[action];
      if (entry === undefined) {
        return state;
      }
      return {
        ...state,
        [action]: { ...entry, frames: entry.frames.filter((_, position) => position !== index) },
      };
    });
  };

  const reorder = (action: CompanionAction, index: number, delta: -1 | 1) => {
    setActions((state) => {
      const entry = state[action];
      return entry === undefined
        ? state
        : { ...state, [action]: { ...entry, frames: moveFrame(entry.frames, index, delta) } };
    });
  };

  const setFps = (action: CompanionAction, fps: number) => {
    setActions((state) => {
      const entry = state[action];
      return entry === undefined ? state : { ...state, [action]: { ...entry, fps } };
    });
  };

  const clear = () => {
    for (const url of urls.current) {
      URL.revokeObjectURL(url);
    }
    urls.current.clear();
    setActions({});
    setErrors([]);
    setName("");
    setGender("unspecified");
  };

  const preview = useMemo(() => draftCharacter(name, gender, actions), [name, gender, actions]);

  const save = async () => {
    if (name.trim().length === 0) {
      setErrors([t("companion.editor.needsName")]);
      return;
    }
    if (preview === null) {
      setErrors([t("companion.editor.needsIdle")]);
      return;
    }
    setSaving(true);
    try {
      const frames: Partial<Record<CompanionAction, readonly File[]>> = {};
      for (const action of COMPANION_ACTIONS) {
        const entry = actions[action];
        if (entry !== undefined && entry.frames.length > 0) {
          frames[action] = entry.frames.map((frame) => frame.file);
        }
      }
      await api.save({ name: name.trim(), gender, frames });
      toast.success(t("companion.editor.saved"));
      clear();
    } catch {
      toast.error(t("companion.editor.saveError"));
    } finally {
      setSaving(false);
    }
  };

  return (
    <section className="companion-editor" aria-labelledby={`${nameId}-title`}>
      <header className="companion-editor__head">
        <h3 id={`${nameId}-title`} className="companion-editor__title">
          {t("companion.editor.title")}
        </h3>
        <p className="companion-editor__description">{t("companion.editor.description")}</p>
        {!api.supported ? (
          <p className="companion-editor__notice" role="note">
            <Icon name="info" size={14} />
            <span>{t("companion.editor.unavailable")}</span>
          </p>
        ) : null}
      </header>

      <div className="companion-editor__layout">
        <div className="companion-editor__form">
          <div className="companion-editor__identity">
            <label className="companion-editor__field" htmlFor={nameId}>
              <span>{t("companion.editor.name")}</span>
              <input
                id={nameId}
                className="input"
                value={name}
                maxLength={40}
                placeholder={t("companion.editor.namePlaceholder")}
                onChange={(event) => setName(event.currentTarget.value)}
              />
            </label>
            <label className="companion-editor__field" htmlFor={genderId}>
              <span>{t("companion.editor.gender")}</span>
              <select
                id={genderId}
                className="input"
                value={gender}
                onChange={(event) => setGender(event.currentTarget.value as CompanionGender)}
              >
                <option value="female">{t("companion.editor.genderFemale")}</option>
                <option value="male">{t("companion.editor.genderMale")}</option>
                <option value="unspecified">{t("companion.editor.genderUnspecified")}</option>
              </select>
            </label>
          </div>

          <fieldset className="companion-editor__actions">
            <legend>{t("companion.editor.actionsLegend")}</legend>
            <ul className="companion-editor__rows">
              {COMPANION_ACTIONS.map((action) => (
                <ActionRow
                  key={action}
                  action={action}
                  frames={actions[action]?.frames ?? []}
                  fps={actions[action]?.fps ?? DEFAULT_DRAFT_FPS}
                  onAdd={addFrames}
                  onRemove={removeFrame}
                  onMove={reorder}
                  onFps={setFps}
                />
              ))}
            </ul>
          </fieldset>

          {errors.length > 0 ? (
            <ul className="companion-editor__errors" role="alert">
              {errors.map((message) => (
                <li key={message}>{message}</li>
              ))}
            </ul>
          ) : null}

          <div className="companion-editor__footer">
            <Button variant="ghost" size="sm" onClick={clear} disabled={saving}>
              {t("companion.editor.clear")}
            </Button>
            <Button
              variant="ink"
              size="sm"
              onClick={() => void save()}
              disabled={!api.supported || saving}
              aria-busy={saving}
            >
              {saving ? t("companion.editor.saving") : t("companion.editor.save")}
            </Button>
          </div>
        </div>

        {preview !== null ? (
          <div className="companion-editor__preview">
            <CompanionPreview
              character={preview}
              motion={motion}
              title={t("companion.editor.preview")}
            />
          </div>
        ) : null}
      </div>
    </section>
  );
}
