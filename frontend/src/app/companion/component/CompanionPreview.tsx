import { useId, useRef, useState } from "react";

import { useI18n } from "../../i18n";
import { ACTION_LABEL_KEYS, COMPANION_ACTIONS, type CompanionAction } from "../actions";
import { STRING_SPAN, figureSize } from "../layout";
import type { CompanionCharacter } from "../manifest";
import type { CompanionMotion } from "../preference";
import { CompanionStage, type DragMotion } from "./CompanionStage";

interface CompanionPreviewProps {
  readonly character: CompanionCharacter;
  readonly motion: CompanionMotion;
  readonly title: string;
}

/** A framed, static-positioned stage with a pose picker for settings. */
export function CompanionPreview({ character, motion, title }: CompanionPreviewProps) {
  const { t } = useI18n();
  const selectId = useId();
  const [action, setAction] = useState<CompanionAction>("idle");
  const dragMotion = useRef<DragMotion>({ vx: 0 });
  const figure = figureSize("desktop");

  return (
    <figure className="companion-preview">
      <div className="companion-preview__stage" aria-hidden="true">
        <CompanionStage
          character={character}
          action={action}
          motion={motion}
          width={figure.width}
          figureHeight={figure.height}
          span={STRING_SPAN}
          dragMotion={dragMotion}
          active
        />
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
