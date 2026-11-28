import type { CSSProperties } from "react";

import { useI18n } from "../../i18n";
import { selectCharacter, useCompanionCatalog, useCompanionPreference } from "../api";
import { readSurfacedLore } from "../story";
import "../companion.css";

/**
 * Inside a search step's details: lore the search surfaced, labelled as the
 * librarian's own memory. It is deliberately not a citation and not archive
 * evidence; the answer itself only ever retells it in the librarian's voice.
 */
export function CompanionLoreTrace({ data }: { readonly data: unknown }) {
  const lore = readSurfacedLore(data);
  if (lore.length === 0) {
    return null;
  }
  return <LoreTraceBody lore={lore} />;
}

function LoreTraceBody({
  lore,
}: {
  readonly lore: ReturnType<typeof readSurfacedLore>;
}) {
  const { t } = useI18n();
  const [preference] = useCompanionPreference();
  const catalog = useCompanionCatalog();
  const character = selectCharacter(catalog, preference.companionId);

  return (
    <aside
      className="companion-lore-trace"
      style={character ? ({ "--companion-accent": character.accent } as CSSProperties) : undefined}
    >
      <header className="companion-lore-trace__head">
        {character?.portrait ? (
          <img
            className="companion-lore-trace__portrait"
            src={character.portrait}
            alt=""
            width={22}
            height={22}
          />
        ) : null}
        <span className="companion-lore-trace__spool" aria-hidden="true" />
        <span className="companion-lore-trace__title">
          {t("companion.lore.traceTitle")}
          {character ? <span className="companion-lore-trace__name"> · {character.name}</span> : null}
        </span>
      </header>
      <p className="companion-lore-trace__note">{t("companion.lore.traceNote")}</p>
      <ul className="companion-lore-trace__list">
        {lore.map((item) => (
          <li key={item.id} className="companion-lore-trace__item">
            {item.text}
          </li>
        ))}
      </ul>
    </aside>
  );
}
