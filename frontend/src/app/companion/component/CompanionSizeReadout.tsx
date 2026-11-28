import type { CSSProperties } from "react";

import { useI18n } from "../../i18n";

interface CompanionSizeReadoutProps {
  /** Preset name when snapped, otherwise a percentage. */
  readonly label: string;
  readonly percent: number;
  /** Level 0..1 for the marker on the three-tick track. */
  readonly level: number;
  /** Whether the figure now overlaps the reading column. */
  readonly coversText: boolean;
  readonly visible: boolean;
  readonly showPercent: boolean;
}

/** The small live size bubble above the figure while it is being resized. */
export function CompanionSizeReadout({
  label,
  percent,
  level,
  coversText,
  visible,
  showPercent,
}: CompanionSizeReadoutProps) {
  const { t } = useI18n();
  return (
    <div
      className={`companion-readout${visible ? " is-visible" : ""}`}
      aria-hidden="true"
      style={{ "--companion-level": level } as CSSProperties}
    >
      <span className="companion-readout__value">
        {label}
        {showPercent ? (
          <span className="companion-readout__percent">
            {t("companion.size.percent", { percent })}
          </span>
        ) : null}
      </span>
      <span className="companion-readout__track">
        <span className="companion-readout__tick" />
        <span className="companion-readout__tick" />
        <span className="companion-readout__tick" />
        <span className="companion-readout__marker" />
      </span>
      {coversText ? (
        <span className="companion-readout__note">{t("companion.overlay.resize.stepsAside")}</span>
      ) : null}
    </div>
  );
}
