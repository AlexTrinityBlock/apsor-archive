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
import { Icon, type IconName } from "./Icon";
import { RouteFallback } from "./RouteFallback";
import { TreeMark } from "./TreeMark";

interface NavItem {
  readonly to: string;
  readonly label: string;
  readonly index: string;
  readonly icon: IconName;
  readonly end?: boolean;
}

/**
 * The flat seven-workspace rail defined by the template audit matrix.
 * Order is part of the interface: Chat is the entry point, Settings the exit.
 */
const NAV_ITEMS: readonly NavItem[] = [
  { to: "/chat", label: "Chat", index: "01", icon: "chat" },
  { to: "/library", label: "File library", index: "02", icon: "library" },
  { to: "/timeline", label: "Timeline", index: "03", icon: "timeline" },
  { to: "/memory", label: "Memory", index: "04", icon: "memory" },
  { to: "/search", label: "Search", index: "05", icon: "search" },
  { to: "/dashboard", label: "Dashboard", index: "06", icon: "database", end: true },
  { to: "/settings", label: "Settings", index: "07", icon: "settings" },
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
  const displayName = user?.display_name || user?.username || "Owner";

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
  let statusDetail = "Checking local services";
  if (healthQuery.isError) {
    statusTone = "error";
    statusDetail = "API offline";
  } else if (health) {
    if (health.status !== "ok" || health.database !== "ok") {
      statusTone = "error";
    } else if (health.cache !== "ok") {
      statusTone = "degraded";
    } else {
      statusTone = "ok";
    }
    const aiState = health.ai === "configured" ? "configured" : "missing";
    statusDetail = `DB ${health.database} · cache ${health.cache} · AI ${aiState}`;
  }
  const statusDotClassName =
    statusTone === "loading"
      ? "status-dot status-dot--pending"
      : "status-dot";
  const statusDotStyle = STATUS_DOT_STYLES[statusTone];

  return (
    <div className={railCollapsed ? "app-shell rail-collapsed" : "app-shell"}>
      <a className="skip-link" href="#main-content">
        Skip to the archive
      </a>

      <header className="mobile-bar">
        <button
          type="button"
          className="mobile-bar__button"
          onClick={openDrawer}
          aria-expanded={drawerOpen}
          aria-controls="archive-navigation"
          aria-label="Open navigation"
        >
          <Icon name="menu" size={20} />
        </button>
        <NavLink to="/" className="mobile-bar__brand" end>
          <TreeMark size={26} />
          <span>Apsor Archive</span>
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
          aria-label="Close navigation"
        />
      ) : null}

      <aside
        id="archive-navigation"
        className={drawerOpen ? "nav-rail is-open" : "nav-rail"}
        aria-label="Archive navigation"
      >
        <div className="rail-header">
          <NavLink to="/" className="brand-cluster" onClick={closeDrawer} title="Apsor Archive">
            <span className="brand-seal" aria-hidden="true">
              <TreeMark size={24} />
            </span>
            <span className="brand-meta">
              <span className="brand-title">Apsor Archive</span>
              <span className="brand-sub">Archive Studio</span>
            </span>
          </NavLink>
          <button
            type="button"
            className="rail-toggle-btn"
            onClick={toggleRail}
            aria-label={railCollapsed ? "Expand navigation rail" : "Collapse navigation rail"}
            title={railCollapsed ? "Expand navigation rail" : "Collapse navigation rail"}
          >
            <Icon name={railCollapsed ? "chevron-right" : "chevron-down"} size={12} />
          </button>
          <button
            type="button"
            className="rail-close-btn"
            onClick={closeDrawer}
            aria-label="Close navigation"
          >
            <Icon name="close" size={18} />
          </button>
        </div>

        <nav className="rail-menu" aria-label="Primary">
          {NAV_ITEMS.map((item) => {
            return (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.end}
                onClick={closeDrawer}
                data-tooltip={`${item.label} (${item.index})`}
                className={({ isActive }) =>
                  isActive ? "rail-item active" : "rail-item"
                }
              >
                <span className="rail-item-icon" aria-hidden="true">
                  <Icon name={item.icon} size={18} />
                </span>
                <span className="rail-item-text">{item.label}</span>
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
                title="Open User Profile"
              >
                <span className="rail-account__mark" aria-hidden="true">
                  {displayName.slice(0, 2).toUpperCase()}
                </span>
                <span className="rail-account__copy">
                  <span>User profile</span>
                  <strong>{displayName}</strong>
                </span>
              </Link>
              <button
                type="button"
                className="rail-account__action"
                onClick={() => void logout()}
                disabled={isSubmitting}
                aria-label="Sign out"
                title="Sign out"
              >
                <Icon name="logout" size={15} />
              </button>
            </div>
          ) : null}

          <div className="rail-status" aria-label="System status">
            <span
              className={statusDotClassName}
              style={statusDotStyle}
              aria-hidden="true"
            />
            <span className="rail-status__copy">
              <span className="rail-status__label">Local archive</span>
              <span className="rail-status__detail">{statusDetail}</span>
            </span>
          </div>

          <button
            type="button"
            className="rail-footer-btn"
            onClick={toggleRail}
            title="Expand or collapse sidebar"
          >
            <Icon name="chevron-right" size={14} />
            <span>{railCollapsed ? "Expand sidebar" : "Collapse sidebar"}</span>
          </button>

          <div className="rail-colophon">
            <span>v{health?.version ?? "—"}</span>
            <span aria-hidden="true">·</span>
            <span>Local-first</span>
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
