import { ApiError } from "../../../apis/fetch-client";
import { Badge } from "../../component/Badge";
import { Button } from "../../component/Button";
import { Icon } from "../../component/Icon";
import { Loader } from "../../component/Loader";
import { useI18n } from "../../i18n";

/** The pre-query room: what the archive can retrieve and how to begin. */
export function SearchWelcome() {
  const { t } = useI18n();
  return (
    <section className="empty-state search-welcome">
      <div className="empty-state__icon">
        <Icon name="search" size={26} />
      </div>
      <p className="eyebrow">{t("insights.search.welcome.eyebrow")}</p>
      <h2>{t("insights.search.welcome.title")}</h2>
      <p className="empty-state__description">
        {t("insights.search.welcome.description")}
      </p>
      <div
        className="search-welcome__kinds"
        aria-label={t("insights.search.welcome.kindsAria")}
      >
        <span className="badge badge--moss">
          {t("insights.search.welcome.fileChunks")}
        </span>
        <span className="badge badge--vermilion">
          {t("insights.search.welcome.memoryCrystals")}
        </span>
        <span className="badge badge--ochre">
          {t("insights.search.welcome.summaries")}
        </span>
      </div>
    </section>
  );
}

/** A quiet in-progress state while both retrieval lanes report back. */
export function SearchLoading() {
  const { t } = useI18n();
  return (
    <section className="search-loading" role="status" aria-live="polite">
      <Loader size={34} label={t("insights.search.loading.aria")} />
      <div>
        <p className="eyebrow">{t("insights.search.loading.eyebrow")}</p>
        <p className="search-loading__copy">
          {t("insights.search.loading.copy")}
        </p>
      </div>
    </section>
  );
}

interface SearchNoResultsProps {
  readonly query: string;
  readonly includeHistory: boolean;
  readonly isFetching: boolean;
  readonly onIncludeHistory: () => void;
  readonly onClear: () => void;
}

/** A searched-but-empty room with honest next moves. */
export function SearchNoResults({
  query,
  includeHistory,
  isFetching,
  onIncludeHistory,
  onClear,
}: SearchNoResultsProps) {
  const { t } = useI18n();
  return (
    <section className="empty-state search-noresults">
      <div className="empty-state__icon">
        <Icon name="search" size={26} />
      </div>
      <p className="eyebrow">{t("insights.search.noResults.eyebrow")}</p>
      <h2>{t("insights.search.noResults.title", { query })}</h2>
      <p className="empty-state__description">
        {t("insights.search.noResults.descriptionBase")}{" "}
        {includeHistory
          ? t("insights.search.noResults.historyIncluded")
          : t("insights.search.noResults.historyExcluded")}
      </p>
      {isFetching ? (
        <p className="search-results__busy">
          <Loader
            size={12}
            label={t("insights.search.results.updatingAria")}
          />
          {t("insights.search.results.updating")}
        </p>
      ) : null}
      <div className="empty-state__actions">
        {!includeHistory ? (
          <Button variant="secondary" size="sm" onClick={onIncludeHistory}>
            <Icon name="history" size={15} />
            {t("insights.search.noResults.includeHistory")}
          </Button>
        ) : null}
        <Button variant="ghost" size="sm" onClick={onClear}>
          {t("insights.search.noResults.clearQuery")}
        </Button>
      </div>
    </section>
  );
}

interface SearchErrorProps {
  readonly error: unknown;
  readonly endpoint: string;
  readonly onRetry: () => void;
}

function errorParts(
  error: unknown,
  fallback: string,
): {
  readonly detail: string;
  readonly code: string;
  readonly status: number | null;
} {
  if (error instanceof ApiError) {
    return {
      detail: error.detail || fallback,
      code: error.code,
      status: error.status > 0 ? error.status : null,
    };
  }
  if (error instanceof Error) {
    return {
      detail: error.message || fallback,
      code: "unknown_error",
      status: null,
    };
  }
  return { detail: fallback, code: "unknown_error", status: null };
}

/** The failure state names the API error instead of hiding it behind a spinner. */
export function SearchError({ error, endpoint, onRetry }: SearchErrorProps) {
  const { t } = useI18n();
  const { detail, code, status } = errorParts(
    error,
    t("insights.search.error.didNotAnswer"),
  );

  return (
    <section className="empty-state search-error" role="alert">
      <div className="empty-state__icon">
        <Icon name="info" size={26} />
      </div>
      <p className="eyebrow">{t("insights.search.error.eyebrow")}</p>
      <h2>{t("insights.search.error.title")}</h2>
      <p className="empty-state__description">{detail}</p>

      <div className="search-error__meta">
        <Badge tone="vermilion">{code}</Badge>
        {status !== null ? (
          <span>
            {t("insights.search.error.httpStatus", {
              status: String(status),
            })}
          </span>
        ) : (
          <span>{t("insights.search.error.networkRequest")}</span>
        )}
      </div>

      <div className="endpoint-label">
        <span>GET</span>
        <code>{endpoint}</code>
      </div>

      <div className="empty-state__actions">
        <Button variant="secondary" size="sm" onClick={onRetry}>
          <Icon name="search" size={15} />
          {t("insights.search.error.retry")}
        </Button>
      </div>
    </section>
  );
}
