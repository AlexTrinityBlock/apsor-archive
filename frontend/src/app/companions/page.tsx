import { PageHeader } from "../component/PageHeader";
import { useI18n } from "../i18n";
import { CompanionControls } from "./component/CompanionControls";
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
    <div className="page companions-page">
      <PageHeader
        eyebrow={t("companion.page.eyebrow")}
        title={t("companion.page.title")}
        description={t("companion.page.description")}
      />
      <CompanionControls />
    </div>
  );
}
