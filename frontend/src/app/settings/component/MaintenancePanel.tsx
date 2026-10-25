import { useAuth } from "../../auth/AuthProvider";
import { Badge } from "../../component/Badge";
import { ButtonLink } from "../../component/Button";
import { Icon } from "../../component/Icon";
import { Panel } from "../../component/Panel";
import { useGetHealth } from "../../generated-apis-types";
import { useI18n } from "../../i18n";

/** Access notes, version, and colophon. */
export function MaintenancePanel() {
  const { t } = useI18n();
  const { user } = useAuth();
  const healthQuery = useGetHealth({ query: { staleTime: 30_000 } });

  const version = healthQuery.data?.version;
  let versionLabel = t("settings.maintenance.readingVersion");
  if (healthQuery.isError) {
    versionLabel = t("settings.maintenance.versionUnavailable");
  } else if (version) {
    versionLabel = t("settings.maintenance.version", { version });
  }

  return (
    <Panel
      title={
        <span className="settings-panel__title">
          <Icon name="archive" size={16} />
          {t("settings.maintenance.title")}
        </span>
      }
      action={<Badge tone="neutral">{versionLabel}</Badge>}
      className="settings-panel"
    >
      <div className="maintenance-grid">
        <section className="maintenance-block">
          <p className="mono-label">{t("settings.maintenance.access")}</p>
          <h3 className="maintenance-block__title">
            {t("settings.maintenance.accessTitle")}
          </h3>
          <p className="maintenance-block__copy">
            {t("settings.maintenance.accessCopyBefore")}
            <strong>
              {user?.username ?? t("settings.maintenance.keeperFallback")}
            </strong>
            {t("settings.maintenance.accessCopyAfter")}
          </p>
        </section>
      </div>

      <div className="maintenance-colophon">
        <span>
          Apsor Archive <code>{versionLabel}</code>
        </span>
        <span>React 19 + Vite · PostgreSQL · local-first</span>
        <ButtonLink to="/about" variant="ghost" size="sm">
          {t("settings.maintenance.readMethod")}
          <Icon name="arrow-right" size={14} />
        </ButtonLink>
      </div>
    </Panel>
  );
}
