import {
  Suspense,
  useCallback,
  useEffect,
  useState,
  type CSSProperties,
} from "react";
import { Link, NavLink, Outlet, useLocation } from "react-router-dom";

import { useGetHealth } from "../generated-apis-types";
import { useAuth } from "../auth/AuthProvider";
import { useScrollLock } from "../hook/useScrollLock";
import { localizeStatus, useI18n, type TranslationKey } from "../i18n";
import { Icon, type IconName } from "./Icon";
import { RouteFallback } from "./RouteFallback";
import { TreeMark } from "./TreeMark";

interface NavItem {
  readonly to: string;
  readonly labelKey: TranslationKey;
  readonly index: string;
  readonly icon: IconName;
  readonly end?: boolean;
}

/**
 * The flat seven-workspace rail defined by the template audit matrix.
 * Order is part of the interface: Chat is the entry point, Settings the exit.
 */
const NAV_ITEMS: readonly NavItem[] = [
  { to: "/chat", labelKey: "core.nav.chat", index: "01", icon: "chat" },
  { to: "/library", labelKey: "core.nav.library", index: "02", icon: "library" },
  { to: "/timeline", labelKey: "core.nav.timeline", index: "03", icon: "timeline" },
  { to: "/memory", labelKey: "core.nav.memory", index: "04", icon: "memory" },
  { to: "/search", labelKey: "core.nav.search", index: "05", icon: "search" },
  {
    to: "/dashboard",
    labelKey: "core.nav.dashboard",
    index: "06",
    icon: "database",
    end: true,
  },
  { to: "/settings", labelKey: "core.nav.settings", index: "07", icon: "settings" },
];

type StatusTone = "ok" | "degraded" | "error" | "loading";

const STATUS_DOT_STYLES: Record<StatusTone, CSSProperties | undefined> = {
  ok: undefined,
  loading: undefined,
  degraded: {
    backgroundColor: "var(--accent-ochre)",
    boxShadow: "0 0 0 3px rgba(180, 83, 9, 0.12)",
  },
  error: {
    backgroundColor: "var(--accent-seal)",
    boxShadow: "0 0 0 3px rgba(200, 75, 49, 0.12)",
  },
};

const RAIL_STORAGE_KEY = "apsor-archive.rail.collapsed";

function readRailPreference(): boolean {
  try {
    return window.localStorage.getItem(RAIL_STORAGE_KEY) === "true";
  } catch {
    return false;
  }
}

/**
 * The fixed archive shell: a collapsible mono rail on desktop, a drawer on
 * mobile, and a single main canvas. The global command palette and floating
 * agent dock were deliberately removed by the template audit matrix.
 */
export function AppShell() {
  const { t } = useI18n();
  const [railCollapsed, setRailCollapsed] = useState(readRailPreference);
  const location = useLocation();
  const [drawer, setDrawer] = useState({
    open: false,
    path: location.pathname,
  });
  const drawerOpen = drawer.open && drawer.path === location.pathname;
  const healthQuery = useGetHealth({
    query: {
      enabled: true,
      staleTime: 60_000,
      refetchInterval: 60_000,
    },
  });
  const { user, logout, isSubmitting } = useAuth();
  const displayName = user?.display_name || user?.username || t("core.nav.owner");

  useScrollLock(drawerOpen);

  useEffect(() => {
    window.scrollTo(0, 0);
  }, [location.pathname]);

  useEffect(() => {
    try {
      window.localStorage.setItem(RAIL_STORAGE_KEY, String(railCollapsed));
    } catch {
      // A private browser may reject storage; the rail still works for the tab.
    }
  }, [railCollapsed]);

  useEffect(() => {
    if (!drawerOpen) {
      return;
    }
    const handleEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setDrawer((current) => ({ ...current, open: false }));
      }
    };
    window.addEventListener("keydown", handleEscape);
    return () => window.removeEventListener("keydown", handleEscape);
  }, [drawerOpen]);

  const openDrawer = useCallback(
    () => setDrawer({ open: true, path: location.pathname }),
    [location.pathname],
  );
  const closeDrawer = useCallback(
    () => setDrawer((current) => ({ ...current, open: false })),
    [],
  );
  const toggleRail = useCallback(
    () => setRailCollapsed((previous) => !previous),
    [],
  );

  const health = healthQuery.data;
  let statusTone: StatusTone = "loading";
  let statusDetail = t("core.nav.checkingServices");
  if (healthQuery.isError) {
    statusTone = "error";
    statusDetail = t("core.nav.apiOffline");
  } else if (health) {
    if (health.status !== "ok" || health.database !== "ok") {
      statusTone = "error";
    } else if (health.cache !== "ok") {
      statusTone = "degraded";
    } else {
      statusTone = "ok";
    }
    const aiState =
      health.ai === "configured"
        ? localizeStatus(t, "configured")
        : localizeStatus(t, "missing");
    statusDetail = t("core.status.detail", {
      database: localizeStatus(t, health.database),
      cache: localizeStatus(t, health.cache),
      ai: aiState,
    });
  }
  const statusDotClassName =
    statusTone === "loading"
      ? "status-dot status-dot--pending"
      : "status-dot";
  const statusDotStyle = STATUS_DOT_STYLES[statusTone];

  return (
    <div className={railCollapsed ? "app-shell rail-collapsed" : "app-shell"}>
      <a className="skip-link" href="#main-content">
        {t("core.nav.skipToArchive")}
      </a>

      <header className="mobile-bar">
        <button
          type="button"
          className="mobile-bar__button"
          onClick={openDrawer}
          aria-expanded={drawerOpen}
          aria-controls="archive-navigation"
          aria-label={t("core.nav.openNavigation")}
        >
          <Icon name="menu" size={20} />
        </button>
        <NavLink to="/" className="mobile-bar__brand" end>
          <TreeMark size={26} />
          <span>{t("core.app.name")}</span>
        </NavLink>
        <span
          className={statusDotClassName}
          style={statusDotStyle}
          aria-label={statusDetail}
          title={statusDetail}
        />
      </header>

      {drawerOpen ? (
        <button
          type="button"
          className="rail-scrim"
          onClick={closeDrawer}
          aria-label={t("core.nav.closeNavigation")}
        />
      ) : null}

      <aside
        id="archive-navigation"
        className={drawerOpen ? "nav-rail is-open" : "nav-rail"}
        aria-label={t("core.nav.ariaArchive")}
      >
        <div className="rail-header">
          <NavLink
            to="/"
            className="brand-cluster"
            onClick={closeDrawer}
            title={t("core.app.name")}
          >
            <span className="brand-seal" aria-hidden="true">
              <TreeMark size={24} />
            </span>
            <span className="brand-meta">
              <span className="brand-title">{t("core.app.name")}</span>
              <span className="brand-sub">{t("core.app.studio")}</span>
            </span>
          </NavLink>
          <button
            type="button"
            className="rail-toggle-btn"
            onClick={toggleRail}
            aria-label={
              railCollapsed
                ? t("core.nav.expandRail")
                : t("core.nav.collapseRail")
            }
            title={
              railCollapsed
                ? t("core.nav.expandRail")
                : t("core.nav.collapseRail")
            }
          >
            <Icon name={railCollapsed ? "chevron-right" : "chevron-down"} size={12} />
          </button>
          <button
            type="button"
            className="rail-close-btn"
            onClick={closeDrawer}
            aria-label={t("core.nav.closeNavigation")}
          >
            <Icon name="close" size={18} />
          </button>
        </div>

        <nav className="rail-menu" aria-label={t("core.nav.ariaPrimary")}>
          {NAV_ITEMS.map((item) => {
            const label = t(item.labelKey);
            return (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.end}
                onClick={closeDrawer}
                data-tooltip={`${label} (${item.index})`}
                className={({ isActive }) =>
                  isActive ? "rail-item active" : "rail-item"
                }
              >
                <span className="rail-item-icon" aria-hidden="true">
                  <Icon name={item.icon} size={18} />
                </span>
                <span className="rail-item-text">{label}</span>
                <span className="rail-item-badge" aria-hidden="true">
                  {item.index}
                </span>
              </NavLink>
            );
          })}
        </nav>

        <div className="rail-footer">
          {user ? (
            <div className="rail-account">
              <Link
                className="rail-account__identity"
                to="/profile"
                onClick={closeDrawer}
                title={t("core.nav.openProfile")}
              >
                <span className="rail-account__mark" aria-hidden="true">
                  {displayName.slice(0, 2).toUpperCase()}
                </span>
                <span className="rail-account__copy">
                  <span>{t("core.nav.userProfile")}</span>
                  <strong>{displayName}</strong>
                </span>
              </Link>
              <button
                type="button"
                className="rail-account__action"
                onClick={() => void logout()}
                disabled={isSubmitting}
                aria-label={t("core.nav.signOut")}
                title={t("core.nav.signOut")}
              >
                <Icon name="logout" size={15} />
              </button>
            </div>
          ) : null}

          <div className="rail-status" aria-label={t("core.nav.systemStatus")}>
            <span
              className={statusDotClassName}
              style={statusDotStyle}
              aria-hidden="true"
            />
            <span className="rail-status__copy">
              <span className="rail-status__label">
                {t("core.nav.localArchive")}
              </span>
              <span className="rail-status__detail">{statusDetail}</span>
            </span>
          </div>

          <button
            type="button"
            className="rail-footer-btn"
            onClick={toggleRail}
            title={t("core.nav.expandOrCollapseSidebar")}
          >
            <Icon name="chevron-right" size={14} />
            <span>
              {railCollapsed
                ? t("core.nav.expandSidebar")
                : t("core.nav.collapseSidebar")}
            </span>
          </button>

          <div className="rail-colophon">
            <span>
              {t("core.nav.version", {
                version: health?.version ?? t("core.common.notAvailable"),
              })}
            </span>
            <span aria-hidden="true">·</span>
            <span>{t("core.nav.localFirst")}</span>
          </div>
        </div>
      </aside>

      <main id="main-content" className="app-main" tabIndex={-1}>
        <div
          className={
            location.pathname.startsWith("/chat") ||
            location.pathname.startsWith("/library")
              ? "app-page app-page--fixed"
              : "app-page"
          }
        >
          <Suspense fallback={<RouteFallback />}>
            <Outlet />
          </Suspense>
        </div>
      </main>

    </div>
  );
}
