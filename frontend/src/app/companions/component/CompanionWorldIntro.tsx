import { useI18n } from "../../i18n";
import type { TranslationKey } from "../../i18n";
import "../companions-world.css";

/** Built-in librarians in display order; names are proper nouns and stay Latin. */
const LIBRARIANS: readonly { id: string; name: string; line: TranslationKey }[] = [
  { id: "vellum", name: "Vellum", line: "companion.world.vellum" },
  { id: "atlas", name: "Atlas", line: "companion.world.atlas" },
  { id: "herbaria", name: "Herbaria", line: "companion.world.herbaria" },
  { id: "horologe", name: "Horologe", line: "companion.world.horologe" },
  { id: "nocturne", name: "Nocturne", line: "companion.world.nocturne" },
  { id: "quill", name: "Quill", line: "companion.world.quill" },
];

/**
 * A short, quiet introduction to the librarians' world: the Curator's
 * epigraph, two sentences of premise, and each librarian's wing and temper.
 */
export function CompanionWorldIntro() {
  const { t } = useI18n();
  return (
    <section className="companions-world" aria-labelledby="companions-world-title">
      <p className="eyebrow">{t("companion.world.eyebrow")}</p>
      <h2 id="companions-world-title">{t("companion.world.title")}</h2>
      <img
        className="companions-world__door"
        src="/companions/world/illusory-door.avif"
        alt=""
        width={1024}
        height={683}
        loading="lazy"
        decoding="async"
      />
      <figure className="companions-world__spirit">
        <blockquote>
          <p>{t("insights.about.librarians.spirit")}</p>
        </blockquote>
        <figcaption>{t("insights.about.librarians.spiritBy")}</figcaption>
      </figure>
      <p>{t("companion.world.body1")}</p>
      <p>{t("companion.world.body2")}</p>
      <ul className="companions-world__roster" aria-label={t("companion.world.rosterAria")}>
        {LIBRARIANS.map((librarian) => (
          <li key={librarian.id}>
            <strong>{librarian.name}</strong>
            <span>{t(librarian.line)}</span>
          </li>
        ))}
      </ul>
      <img
        className="companions-world__dinner"
        src="/companions/world/dinner-of-recipes.avif"
        alt=""
        width={896}
        height={597}
        loading="lazy"
        decoding="async"
      />
    </section>
  );
}
