import { useSearchParams } from "react-router-dom";

import { ButtonLink } from "../component/Button";
import { Icon } from "../component/Icon";
import { PageHeader } from "../component/PageHeader";
import { useI18n } from "../i18n";
import { LoreTable } from "./component/LoreTable";
import { TemplateEditor } from "./component/TemplateEditor";
import { WorldDocEditor } from "./component/WorldDocEditor";
import {
  CanonPanel,
  ConfigPanel,
  PresetsPanel,
  SeedPanel,
} from "./component/WorldPanels";
import "./companion-admin.css";

const TABS = [
  "presets",
  "lore",
  "docs",
  "canon",
  "config",
  "templates",
  "seed",
] as const;
type WorldTab = (typeof TABS)[number];

function isTab(value: string | null): value is WorldTab {
  return value !== null && (TABS as readonly string[]).includes(value);
}

/**
 * Root's "Companions & World" area: the librarians, their memories, the world
 * documents and canon, pacing, story-writing templates, and the seed status.
 * The tab lives in the URL so links and the back button work.
 */
export function CompanionWorldPage() {
  const { t } = useI18n();
  const [params, setParams] = useSearchParams();
  const requested = params.get("tab");
  const tab: WorldTab = isTab(requested) ? requested : "presets";

  return (
    <div className="content-container ca-world">
      <PageHeader
        eyebrow={t("companionAdmin.world.eyebrow")}
        title={t("companionAdmin.world.title")}
        description={t("companionAdmin.world.description")}
        actions={
          <ButtonLink to="/accounts" variant="ghost" size="sm">
            <Icon name="users" size={14} />
            {t("companionAdmin.world.back")}
          </ButtonLink>
        }
      />
      <div
        className="ca-sections ca-sections--world"
        role="tablist"
        aria-label={t("companionAdmin.world.tabsLabel")}
      >
        {TABS.map((item) => (
          <button
            key={item}
            type="button"
            role="tab"
            aria-selected={tab === item}
            className={`ca-sections__tab${tab === item ? " is-active" : ""}`}
            onClick={() => setParams({ tab: item }, { replace: true })}
          >
            {t(`companionAdmin.world.tabs.${item}`)}
          </button>
        ))}
      </div>
      <div className="ca-section-body" role="tabpanel">
        {tab === "presets" ? <PresetsPanel /> : null}
        {tab === "lore" ? <LoreTable /> : null}
        {tab === "docs" ? <WorldDocEditor /> : null}
        {tab === "canon" ? <CanonPanel /> : null}
        {tab === "config" ? <ConfigPanel /> : null}
        {tab === "templates" ? <TemplateEditor /> : null}
        {tab === "seed" ? <SeedPanel /> : null}
      </div>
    </div>
  );
}
