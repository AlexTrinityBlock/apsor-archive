import {
  Suspense,
  useCallback,
  useEffect,
  useState,
  type CSSProperties,
} from "react";
import { NavLink, Outlet, useLocation } from "react-router-dom";

import { useGetHealth } from "../generated-apis-types";
import { useAuth } from "../auth/AuthProvider";
import { ChangePasswordDialog } from "../auth/component/ChangePasswordDialog";
import { useScrollLock } from "../hook/useScrollLock";
import { localizeStatus, useI18n, type TranslationKey } from "../i18n";
import { Icon, type IconName } from "./Icon";
import { RouteFallback } from "./RouteFallback";
import { TreeMark } from "./TreeMark";

interface NavItem {
  readonly to: string;
  readonly labelKey: TranslationKey;
  readonly icon: IconName;
  readonly end?: boolean;
  readonly rootOnly?: boolean;
  readonly action?: "password" | "logout";
}

interface NavSection {
  readonly id: "main" | "personal" | "system" | "session";
  readonly labelKey?: TranslationKey;
  readonly items: readonly NavItem[];
}

interface IndexedNavItem extends NavItem {
  readonly index: string;
}

interface IndexedNavSection extends Omit<NavSection, "items"> {
  readonly items: readonly IndexedNavItem[];
}

/**
 * The rail is grouped, not flat: archive workspaces, a personal block with the
 * self-only profile, then system pages. The personal block deliberately sits
 * above Settings so the account card in the footer only carries identity and
 * session actions.
 */
const NAV_SECTIONS: readonly NavSection[] = [
  {
    id: "main",
    items: [
      { to: "/chat", labelKey: "core.nav.chat", icon: "chat" },
      { to: "/library", labelKey: "core.nav.library", icon: "library" },
      { to: "/timeline", labelKey: "core.nav.timeline", icon: "timeline" },
      { to: "/memory", labelKey: "core.nav.memory", icon: "memory" },
      { to: "/search", labelKey: "core.nav.search", icon: "search" },
      {
        to: "/dashboard",
        labelKey: "core.nav.dashboard",
        icon: "database",
        end: true,
      },
    ],
  },
  {
    id: "personal",
    labelKey: "core.nav.personalSection",
    items: [
      { to: "/profile", labelKey: "core.nav.profile", icon: "user" },
    ],
  },
  {
    id: "system",
    items: [
      { to: "/settings", labelKey: "core.nav.settings", icon: "settings" },
      {
        to: "/change-password",
        labelKey: "core.nav.changePassword",
        icon: "key",
        action: "password",
      },
      {
        to: "/accounts",
        labelKey: "core.nav.accounts",
        icon: "users",
        rootOnly: true,
      },
      { to: "/about", labelKey: "core.nav.about", icon: "method" },
    ],
  },
  {
    id: "session",
    labelKey: "core.nav.sessionSection",
    items: [
      {
        to: "/logout",
        labelKey: "core.nav.signOut",
        icon: "logout",
        action: "logout",
      },
    ],
  },
];

/**
 * Filter role-only entries first, then number what is actually rendered. This
 * keeps the mono indices contiguous for non-root readers instead of leaving a
 * gap where Accounts would have been.
 */
function buildNavSections(isRoot: boolean): readonly IndexedNavSection[] {
  let position = 0;
  return NAV_SECTIONS.map((section) => ({
    ...section,
    items: section.items
      .filter((item) => !item.rootOnly || isRoot)
      .map((item) => {
        position += 1;
        return { ...item, index: String(position).padStart(2, "0") };
      }),
  })).filter((section) => section.items.length > 0);
}

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
  const [passwordDialogOpen, setPasswordDialogOpen] = useState(false);
  const location = useLocation();
  const [drawer, setDrawer] = useState({
    open: false,
    path: location.pathname,
  });
  // A redirect can land before the router context re-renders a layout. Use the
  // browser path for the drawer so a first-login redirect cannot leave the
  // mobile menu permanently closed.
  const currentPath = typeof window === "undefined" ? location.pathname : window.location.pathname;
  const drawerOpen = drawer.open && drawer.path === currentPath;
  const healthQuery = useGetHealth({
    query: {
      enabled: true,
      staleTime: 60_000,
      refetchInterval: 60_000,
    },
  });
  const { user, logout, isSubmitting } = useAuth();
  const isRoot = user?.role === "root";
  const navSections = buildNavSections(isRoot);
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
    () => setDrawer({ open: true, path: window.location.pathname }),
    [],
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
          {navSections.map((section) => (
            <div
              key={section.id}
              className={`rail-section rail-section--${section.id}`}
            >
              {section.labelKey ? (
                <p className="rail-section__label">{t(section.labelKey)}</p>
              ) : null}
              {section.items.map((item) => {
                const label = t(item.labelKey);
                const content = (
                  <>
                    <span className="rail-item-icon" aria-hidden="true">
                      <Icon name={item.icon} size={18} />
                    </span>
                    <span className="rail-item-text">{label}</span>
                    <span className="rail-item-badge" aria-hidden="true">
                      {item.index}
                    </span>
                  </>
                );
                if (item.action !== undefined) {
                  const isLogout = item.action === "logout";
                  return (
                    <button
                      key={item.to}
                      type="button"
                      className="rail-item rail-item--action"
                      onClick={() => {
                        closeDrawer();
                        if (isLogout) {
                          void logout();
                        } else {
                          setPasswordDialogOpen(true);
                        }
                      }}
                      data-tooltip={`${label} (${item.index})`}
                      aria-haspopup={isLogout ? undefined : "dialog"}
                      disabled={isLogout && isSubmitting}
                    >
                      {content}
                    </button>
                  );
                }
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
                    {content}
                  </NavLink>
                );
              })}
            </div>
          ))}
        </nav>

        <div className="rail-footer">
          {user ? (
            <div className="rail-account">
              <div className="rail-account__identity" title={displayName}>
                <span className="rail-account__mark" aria-hidden="true">
                  {displayName.slice(0, 2).toUpperCase()}
                </span>
                <span className="rail-account__copy">
                  <span className="rail-account__username">{user.username}</span>
                  <strong>{displayName}</strong>
                </span>
              </div>
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

      {passwordDialogOpen ? (
        <ChangePasswordDialog onClose={() => setPasswordDialogOpen(false)} />
      ) : null}
    </div>
  );
}
