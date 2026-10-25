import type { ReactNode } from "react";

import { Icon } from "./Icon";
import { Loader } from "./Loader";
import { Panel } from "./Panel";
import { translateApiError } from "../i18n/errors";
import { useI18n } from "../i18n/I18nProvider";
import "./shared.css";

interface QueryStateProps {
  readonly loading: boolean;
  readonly error: unknown;
  readonly empty?: boolean;
  readonly emptyState?: ReactNode;
  readonly loadingLabel?: string;
  readonly children: ReactNode;
}

/** A consistent loading / failure / empty frame for data-backed panels. */
export function QueryState({
  loading,
  error,
  empty = false,
  emptyState,
  loadingLabel,
  children,
}: QueryStateProps) {
  const { t } = useI18n();
  const resolvedLoadingLabel =
    loadingLabel ?? t("core.queryState.defaultLoadingLabel");

  if (loading) {
    return (
      <Panel tone="plain" className="query-state">
        <div className="query-state__loading">
          <Loader label={resolvedLoadingLabel} />
        </div>
      </Panel>
    );
  }
  if (error) {
    return (
      <Panel tone="plain" className="query-state query-state--error" role="alert">
        <div className="query-state__error">
          <span className="query-state__error-icon" aria-hidden="true">
            <Icon name="info" size={18} />
          </span>
          <div className="query-state__error-copy">
            <p className="eyebrow">{t("core.queryState.readInterrupted")}</p>
            <h2>{t("core.queryState.didNotAnswer")}</h2>
            <p className="query-state__detail">
              {translateApiError(error, t, "core.queryState.genericError")}
            </p>
          </div>
        </div>
      </Panel>
    );
  }
  if (empty) {
    return <>{emptyState}</>;
  }
  return <>{children}</>;
}
