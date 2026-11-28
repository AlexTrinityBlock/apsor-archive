import type { CSSProperties, ReactNode } from "react";

import { Button } from "../../component/Button";
import { Icon } from "../../component/Icon";
import { Panel } from "../../component/Panel";
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
import { effectiveMotion, type CompanionMotion } from "../../companion/preference";
import { removeKey } from "../../companion/storage";
import { SwitchField } from "./SwitchField";
import "../../companion/companion.css";

const MOTIONS: readonly {
  readonly id: CompanionMotion;
  readonly label: TranslationKey;
  readonly hint: TranslationKey;
}[] = [
  { id: "full", label: "companion.settings.motionFull", hint: "companion.settings.motionFullHint" },
  {
    id: "reduced",
    label: "companion.settings.motionReduced",
    hint: "companion.settings.motionReducedHint",
  },
  { id: "off", label: "companion.settings.motionOff", hint: "companion.settings.motionOffHint" },
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

/**
 * Settings → Companion: visibility, motion level, character choice with a
 * live pose preview, position reset, the selected companion's story (persona
 * and lore), and the custom-companion editor.
 */
export function CompanionPanel() {
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

  return (
    <Panel eyebrow={t("companion.settings.eyebrow")} title={t("companion.settings.title")}>
      <div className="companion-settings">
        <p className="companion-settings__intro">{t("companion.settings.description")}</p>

        <div className="companion-settings__layout">
          <div className="companion-settings__controls">
            <SwitchField
              label={t("companion.settings.enabled")}
              hint={t("companion.settings.enabledHint")}
              checked={preference.enabled}
              disabled={false}
              onChange={(enabled) => update({ enabled })}
            />

            <fieldset className="companion-settings__motion">
              <legend>{t("companion.settings.motionLegend")}</legend>
              {MOTIONS.map((item) => (
                <label
                  key={item.id}
                  className={`companion-settings__option${
                    preference.motion === item.id ? " is-selected" : ""
                  }`}
                >
                  <input
                    type="radio"
                    name="companion-motion"
                    value={item.id}
                    checked={preference.motion === item.id}
                    onChange={() => update({ motion: item.id })}
                  />
                  <span className="companion-settings__option-copy">
                    <span className="companion-settings__option-label">{t(item.label)}</span>
                    <span className="companion-settings__option-hint">{t(item.hint)}</span>
                  </span>
                </label>
              ))}
              {systemReduced && preference.motion === "full" ? (
                <p className="companion-settings__note">{t("companion.settings.motionSystemNote")}</p>
              ) : null}
            </fieldset>

            <fieldset className="companion-settings__picker">
              <legend>{t("companion.settings.chooseLegend")}</legend>
              {picker}
            </fieldset>

            <div className="companion-settings__reset">
              <Button variant="secondary" size="sm" onClick={resetPosition}>
                {t("companion.settings.resetPosition")}
              </Button>
              <span className="companion-settings__note">
                {t("companion.settings.resetPositionHint")}
              </span>
            </div>
          </div>

          {selected !== null ? (
            <div className="companion-settings__preview">
              <CompanionPreview
                character={selected}
                motion={motion}
                title={t("companion.settings.previewTitle")}
              />
            </div>
          ) : null}
        </div>

        {selected !== null ? <CompanionStory key={selected.id} character={selected} /> : null}

        <CustomCompanionEditor motion={motion} />
      </div>
    </Panel>
  );
}
