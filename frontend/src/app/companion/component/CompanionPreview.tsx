import { useId, useRef, useState } from "react";

import { useI18n } from "../../i18n";
import { ACTION_LABEL_KEYS, COMPANION_ACTIONS, type CompanionAction } from "../actions";
import { FIGURE_HEADROOM } from "../layout";
import type { CompanionCharacter } from "../manifest";
import type { CompanionMotion, CompanionOpacityMode } from "../preference";
import { figureForLevel, previewRange } from "../size";
import { CompanionStage, type DragMotion } from "./CompanionStage";

interface CompanionPreviewProps {
  readonly character: CompanionCharacter;
  readonly motion: CompanionMotion;
  readonly title: string;
  /** Size level (0 compact .. 1 full) to preview, scaled into the frame. */
  readonly level?: number;
  /** Opacity mode to preview; auto shows its gentle fade. */
  readonly opacityMode?: CompanionOpacityMode;
}

/** Tallest figure the preview frame shows, so Full still fits the page. */
const PREVIEW_MAX_HEIGHT = 360;

/** A framed, static-positioned stage with a pose picker. */
export function CompanionPreview({
  character,
  motion,
  title,
  level = 0,
  opacityMode = "opaque",
}: CompanionPreviewProps) {
  const { t } = useI18n();
  const selectId = useId();
  const [action, setAction] = useState<CompanionAction>("idle");
  const dragMotion = useRef<DragMotion>({ vx: 0 });
  const figure = figureForLevel(level, previewRange(PREVIEW_MAX_HEIGHT));

  return (
    <figure className="companion-preview">
      <div
        className={`companion-preview__stage opacity-${opacityMode}`}
        aria-hidden="true"
        style={{ height: figure.height + FIGURE_HEADROOM + 24 }}
      >
        <div
          className="companion-preview__figure"
          style={{ width: figure.width, height: figure.height + FIGURE_HEADROOM }}
        >
          <CompanionStage
            character={character}
            action={action}
            motion={motion}
            width={figure.width}
            figureHeight={figure.height}
            span={FIGURE_HEADROOM}
            dragMotion={dragMotion}
            active
          />
        </div>
      </div>
      <figcaption className="companion-preview__caption">
        <span className="companion-preview__title">{title}</span>
        <label className="companion-preview__field" htmlFor={selectId}>
          <span>{t("companion.settings.previewAction")}</span>
          <select
            id={selectId}
            className="input companion-preview__select"
            value={action}
            onChange={(event) => setAction(event.currentTarget.value as CompanionAction)}
          >
            {COMPANION_ACTIONS.map((item) => (
              <option key={item} value={item}>
                {t(ACTION_LABEL_KEYS[item])}
              </option>
            ))}
          </select>
        </label>
      </figcaption>
    </figure>
  );
}
