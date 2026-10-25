import { useI18n } from "../i18n";
import { Loader } from "./Loader";
import "./shared.css";

/** Quiet fallback shown while a lazy route module is fetched. */
export function RouteFallback() {
  const { t } = useI18n();

  return (
    <div className="route-fallback" aria-busy="true">
      <Loader size={42} label={t("core.route.fallbackLabel")} />
      <p className="eyebrow">{t("core.route.fallbackEyebrow")}</p>
    </div>
  );
}
