import { Link } from "react-router-dom";

import { useI18n } from "../../i18n";
import type { TranslationKey } from "../../i18n";
import { LibrarianPortrait } from "./LibrarianPortrait";
import "../about-lore.css";

/** Built-in presets in display order; names are proper nouns and stay Latin. */
const LIBRARIANS: readonly {
  id: string;
  name: string;
  line: TranslationKey;
}[] = [
  { id: "vellum", name: "Vellum", line: "insights.about.librarians.vellum" },
  { id: "atlas", name: "Atlas", line: "insights.about.librarians.atlas" },
  {
    id: "herbaria",
    name: "Herbaria",
    line: "insights.about.librarians.herbaria",
  },
  {
    id: "horologe",
    name: "Horologe",
    line: "insights.about.librarians.horologe",
  },
  {
    id: "nocturne",
    name: "Nocturne",
    line: "insights.about.librarians.nocturne",
  },
  { id: "quill", name: "Quill", line: "insights.about.librarians.quill" },
];

/** The per-account companion workspace. */
const COMPANION_SETTINGS_HREF = "/companion";

/** "Meet the librarians": the Curator's epigraph, then six portraits. */
export function LibrarianRoster() {
  const { t } = useI18n();
  return (
    <>
      <figure className="about-spirit">
        <blockquote>
          <p>{t("insights.about.librarians.spirit")}</p>
        </blockquote>
        <figcaption>{t("insights.about.librarians.spiritBy")}</figcaption>
      </figure>
      <ul
        className="about-roster"
        aria-label={t("insights.about.librarians.listAria")}
      >
        {LIBRARIANS.map((librarian) => (
          <li className="about-roster__item" key={librarian.id}>
            <LibrarianPortrait
              id={librarian.id}
              alt={t("insights.about.librarians.portraitAlt", {
                name: librarian.name,
              })}
              size={72}
            />
            <div>
              <h3>{librarian.name}</h3>
              <p>{t(librarian.line)}</p>
            </div>
          </li>
        ))}
      </ul>
      <p className="about-roster__cta">
        <Link className="text-link" to={COMPANION_SETTINGS_HREF}>
          {t("insights.about.librarians.chooseLink")}
        </Link>
      </p>
    </>
  );
}
