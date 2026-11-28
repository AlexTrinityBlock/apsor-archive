import { Icon } from "../component/Icon";
import { PageHeader } from "../component/PageHeader";
import { useI18n } from "../i18n";
import { CompanionControls } from "./component/CompanionControls";
import { CompanionWorldIntro } from "./component/CompanionWorldIntro";
import "../companion/companion.css";
import "./companions.css";

/**
 * Companion workspace (`/companion`): each account picks its librarian and
 * decides how it looks and moves beside the chat, edits its story, and builds
 * custom companions. Everything here is per account.
 */
export function CompanionPage() {
  const { t } = useI18n();
  return (
    <div className="page content-container companions-page">
      <PageHeader
        eyebrow={t("companion.page.eyebrow")}
        title={t("companion.page.title")}
        description={t("companion.page.description")}
      />
      <p className="companions-admin-notice" role="note">
        <Icon name="info" size={14} />
        <span>{t("companion.page.adminNotice")}</span>
      </p>
      <CompanionControls />
      <CompanionWorldIntro />
    </div>
  );
}
