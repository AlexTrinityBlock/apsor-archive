import type { CSSProperties, ReactNode } from "react";

import { Button } from "../../component/Button";
import { Icon } from "../../component/Icon";
import { Panel } from "../../component/Panel";
import { SwitchField } from "../../component/SwitchField";
import { useToast } from "../../component/Toast";
import { useI18n, type TranslationKey } from "../../i18n";
import {
  selectCharacter,
  useCompanionCatalog,
  useCompanionPreference,
} from "../../companion/api";
import { CompanionPreview } from "../../companion/component/CompanionPreview";
import { CompanionStory } from "../../companion/component/CompanionStory";
import { CustomCompanionEditor } from "../../companion/component/CustomCompanionEditor";
import { useReducedMotion } from "../../companion/hook/useReducedMotion";
import type { CompanionCharacter } from "../../companion/manifest";
import {
  effectiveMotion,
  type CompanionMotion,
  type CompanionOpacityMode,
  type CompanionSize,
} from "../../companion/preference";
import { removeKey } from "../../companion/storage";

interface Choice<T extends string> {
  readonly id: T;
  readonly label: TranslationKey;
  readonly hint: TranslationKey;
}

const MOTIONS: readonly Choice<CompanionMotion>[] = [
  { id: "full", label: "companion.settings.motionFull", hint: "companion.settings.motionFullHint" },
  {
    id: "reduced",
    label: "companion.settings.motionReduced",
    hint: "companion.settings.motionReducedHint",
  },
  { id: "off", label: "companion.settings.motionOff", hint: "companion.settings.motionOffHint" },
];

const SIZES: readonly Choice<CompanionSize>[] = [
  { id: "compact", label: "companion.page.sizeCompact", hint: "companion.page.sizeCompactHint" },
  { id: "medium", label: "companion.page.sizeMedium", hint: "companion.page.sizeMediumHint" },
  { id: "full", label: "companion.page.sizeFull", hint: "companion.page.sizeFullHint" },
];

const OPACITIES: readonly Choice<CompanionOpacityMode>[] = [
  {
    id: "opaque",
    label: "companion.page.opacityOpaque",
    hint: "companion.page.opacityOpaqueHint",
  },
  {
    id: "translucent",
    label: "companion.page.opacityTranslucent",
    hint: "companion.page.opacityTranslucentHint",
  },
  { id: "auto", label: "companion.page.opacityAuto", hint: "companion.page.opacityAutoHint" },
];

interface CharacterGroup {
  readonly key: string;
  readonly label: TranslationKey;
  readonly items: readonly CompanionCharacter[];
}

function groupCharacters(
  presets: readonly CompanionCharacter[],
  custom: readonly CompanionCharacter[],
): readonly CharacterGroup[] {
  const groups: CharacterGroup[] = [
    { key: "custom", label: "companion.settings.groupCustom", items: custom },
    {
      key: "female",
      label: "companion.settings.groupFemale",
      items: presets.filter((item) => item.gender === "female"),
    },
    {
      key: "male",
      label: "companion.settings.groupMale",
      items: presets.filter((item) => item.gender === "male"),
    },
    {
      key: "other",
      label: "companion.settings.groupOther",
      items: presets.filter((item) => item.gender === "unspecified"),
    },
  ];
  return groups.filter((group) => group.items.length > 0);
}

interface SegmentedProps<T extends string> {
  readonly name: string;
  readonly legend: string;
  readonly choices: readonly Choice<T>[];
  readonly value: T;
  readonly onChange: (value: T) => void;
  /** Optional small visual shown above each choice's label. */
  readonly visual?: (id: T) => ReactNode;
}

/** A radio group drawn as a segmented control, with the selected hint below. */
function Segmented<T extends string>({
  name,
  legend,
  choices,
  value,
  onChange,
  visual,
}: SegmentedProps<T>) {
  const { t } = useI18n();
  const selected = choices.find((choice) => choice.id === value) ?? choices[0];
  return (
    <fieldset className="companions-segmented">
      <legend>{legend}</legend>
      <div className="companions-segmented__track">
        {choices.map((choice) => (
          <label
            key={choice.id}
            className={`companions-segmented__option${choice.id === value ? " is-selected" : ""}`}
          >
            <input
              className="visually-hidden"
              type="radio"
              name={name}
              value={choice.id}
              checked={choice.id === value}
              onChange={() => onChange(choice.id)}
            />
            {visual ? <span aria-hidden="true">{visual(choice.id)}</span> : null}
            <span className="companions-segmented__label">{t(choice.label)}</span>
          </label>
        ))}
      </div>
      {selected !== undefined ? (
        <p className="companions-segmented__hint">{t(selected.hint)}</p>
      ) : null}
    </fieldset>
  );
}

/** A tiny scene: lines of text with the figure standing over them. */
function OpacitySwatch({
  mode,
  portrait,
}: {
  readonly mode: CompanionOpacityMode;
  readonly portrait: string | null;
}) {
  return (
    <span className={`companions-swatch is-${mode}`}>
      <span className="companions-swatch__text" />
      <span className="companions-swatch__text" />
      <span className="companions-swatch__text is-short" />
      <span className="companions-swatch__figure">
        {portrait !== null ? <img src={portrait} alt="" width={30} height={30} /> : null}
      </span>
    </span>
  );
}

/** A size glyph: three bars of rising height, the chosen one filled. */
function SizeSwatch({ size }: { readonly size: CompanionSize }) {
  return (
    <span className={`companions-size-swatch is-${size}`}>
      <span />
    </span>
  );
}

/**
 * The companion workspace body: visibility, look (size and opacity), motion,
 * character choice with a live preview, the selected companion's story, and
 * the custom-companion editor.
 */
export function CompanionControls() {
  const { t } = useI18n();
  const toast = useToast();
  const [preference, update] = useCompanionPreference();
  const catalog = useCompanionCatalog();
  const systemReduced = useReducedMotion();
  const motion = effectiveMotion(preference.motion, systemReduced);
  const selected = selectCharacter(catalog, preference.companionId);

  const resetPosition = () => {
    for (const breakpoint of ["phone", "tablet", "desktop"]) {
      removeKey(`position.${breakpoint}`);
    }
    removeKey("minimized");
    toast.info(t("companion.settings.positionReset"));
  };

  let picker: ReactNode;
  if (catalog.isLoading) {
    picker = <p className="companion-settings__status">{t("companion.settings.loading")}</p>;
  } else if (catalog.isError) {
    picker = (
      <div className="companion-settings__status" role="alert">
        <span>{t("companion.settings.loadError")}</span>
        <Button variant="ghost" size="sm" onClick={catalog.refetch}>
          {t("companion.settings.retry")}
        </Button>
      </div>
    );
  } else if (catalog.presets.length === 0 && catalog.custom.length === 0) {
    picker = <p className="companion-settings__status">{t("companion.settings.empty")}</p>;
  } else {
    picker = groupCharacters(catalog.presets, catalog.custom).map((group) => (
      <div key={group.key} className="companion-settings__group">
        <p className="companion-settings__group-label">{t(group.label)}</p>
        <div className="companion-settings__grid">
          {group.items.map((character) => {
            const checked = selected?.id === character.id;
            return (
              <label
                key={character.id}
                className={`companion-card${checked ? " is-selected" : ""}`}
                style={{ "--companion-accent": character.accent } as CSSProperties}
              >
                <input
                  className="visually-hidden"
                  type="radio"
                  name="companion-character"
                  value={character.id}
                  checked={checked}
                  onChange={() => update({ companionId: character.id })}
                />
                <span className="companion-card__portrait" aria-hidden="true">
                  {character.portrait !== null ? (
                    <img src={character.portrait} alt="" width={72} height={72} loading="lazy" />
                  ) : (
                    <Icon name="user" size={22} />
                  )}
                </span>
                <span className="companion-card__name">{character.name}</span>
                {checked ? (
                  <span className="companion-card__mark">
                    <Icon name="check" size={12} />
                    <span className="visually-hidden">{t("companion.settings.selected")}</span>
                  </span>
                ) : null}
              </label>
            );
          })}
        </div>
      </div>
    ));
  }

  const portrait = selected?.portrait ?? null;

  return (
    <div className="companions-workspace">
      <div className="companions-workspace__top">
        <Panel eyebrow={t("companion.page.lookEyebrow")} title={t("companion.page.lookTitle")}>
          <div className="companions-look">
            <SwitchField
              label={t("companion.settings.enabled")}
              hint={t("companion.settings.enabledHint")}
              checked={preference.enabled}
              disabled={false}
              onChange={(enabled) => update({ enabled })}
            />
            <Segmented
              name="companion-size"
              legend={t("companion.page.sizeLegend")}
              choices={SIZES}
              value={preference.size}
              onChange={(size) => update({ size })}
              visual={(id) => <SizeSwatch size={id} />}
            />
            <Segmented
              name="companion-opacity"
              legend={t("companion.page.opacityLegend")}
              choices={OPACITIES}
              value={preference.opacityMode}
              onChange={(opacityMode) => update({ opacityMode })}
              visual={(id) => <OpacitySwatch mode={id} portrait={portrait} />}
            />
            <Segmented
              name="companion-motion"
              legend={t("companion.settings.motionLegend")}
              choices={MOTIONS}
              value={preference.motion}
              onChange={(value) => update({ motion: value })}
            />
            {systemReduced && preference.motion === "full" ? (
              <p className="companion-settings__note">{t("companion.settings.motionSystemNote")}</p>
            ) : null}
            <div className="companion-settings__reset">
              <Button variant="secondary" size="sm" onClick={resetPosition}>
                {t("companion.settings.resetPosition")}
              </Button>
              <span className="companion-settings__note">
                {t("companion.settings.resetPositionHint")}
              </span>
            </div>
          </div>
        </Panel>

        {selected !== null ? (
          <div className="companions-workspace__preview">
            <CompanionPreview
              character={selected}
              motion={motion}
              size={preference.size}
              opacityMode={preference.opacityMode}
              title={t("companion.settings.previewTitle")}
            />
          </div>
        ) : null}
      </div>

      <Panel eyebrow={t("companion.page.chooseEyebrow")} title={t("companion.settings.chooseLegend")}>
        <div className="companion-settings__picker">{picker}</div>
      </Panel>

      {selected !== null ? <CompanionStory key={selected.id} character={selected} /> : null}

      <CustomCompanionEditor motion={motion} />
    </div>
  );
}
