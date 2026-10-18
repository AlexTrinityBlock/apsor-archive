import { Suspense, useCallback, useEffect, useState, type CSSProperties } from "react";
import { Link, NavLink, Outlet, useLocation } from "react-router-dom";

import { useGetHealth, useListMemories } from "../generated-apis-types";
import { useAuth } from "../auth/AuthProvider";
import { useCommandK } from "../hook/useCommandK";
import { useScrollLock } from "../hook/useScrollLock";
import { CommandPalette } from "./CommandPalette";
import { Icon, type IconName } from "./Icon";
import { RouteFallback } from "./RouteFallback";
import { ThemeToggle } from "./ThemeToggle";
import { TreeMark } from "./TreeMark";

interface NavItem {
  readonly to: string;
  readonly label: string;
  readonly index: string;
  readonly icon: IconName;
  readonly end?: boolean;
}

interface NavSection {
  readonly label: string;
  readonly items: readonly NavItem[];
}

const NAV_SECTIONS: readonly NavSection[] = [
  {
    label: "Index",
    items: [
      { to: "/", label: "Overview", index: "01", icon: "overview", end: true },
      { to: "/search", label: "Search", index: "02", icon: "search" },
      { to: "/timeline", label: "Timeline", index: "03", icon: "timeline" },
    ],
  },
  {
    label: "Collections",
    items: [
      { to: "/library", label: "File library", index: "04", icon: "library" },
      { to: "/tree", label: "Knowledge tree", index: "05", icon: "tree" },
      { to: "/media", label: "Media", index: "06", icon: "ring" },
      { to: "/memory/1015", label: "Memory", index: "07", icon: "memory" },
    ],
  },
  {
    label: "Studio",
    items: [
      { to: "/chat", label: "Chat", index: "08", icon: "chat" },
      { to: "/ask", label: "Quick ask", index: "09", icon: "ask" },
      { to: "/method", label: "Method", index: "10", icon: "method" },
      { to: "/settings", label: "Settings", index: "11", icon: "settings" },
    ],
  },
];

const MOBILE_NAV: readonly NavItem[] = [
  { to: "/", label: "Overview", index: "01", icon: "overview", end: true },
  { to: "/search", label: "Search", index: "02", icon: "search" },
  { to: "/timeline", label: "Timeline", index: "03", icon: "timeline" },
  { to: "/library", label: "Library", index: "04", icon: "library" },
];

type StatusTone = "ok" | "degraded" | "error" | "loading";

const STATUS_DOT_STYLES: Record<StatusTone, CSSProperties | undefined> = {
  ok: undefined,
  loading: undefined,
  degraded: {
    backgroundColor: "var(--ochre)",
    boxShadow: "0 0 0 3px var(--ochre-wash)",
  },
  error: {
    backgroundColor: "var(--vermilion)",
    boxShadow: "0 0 0 3px var(--vermilion-wash)",
  },
};

/**
 * The fixed archive shell: a deep-green index rail on desktop, a compact top
 * bar and bottom shelf on mobile, and one command palette for both.
 */
export function AppShell() {
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const location = useLocation();
  const healthQuery = useGetHealth({
    query: {
      enabled: true,
      staleTime: 60_000,
      refetchInterval: 60_000,
    },
  });
  const latestMemories = useListMemories({ limit: 1 });
  const latestMemoryId = latestMemories.data?.resources[0]?.memory_id;
  const memoryHref = latestMemoryId ? `/memory/${latestMemoryId}` : "/memory/new";
  const { user, logout, isSubmitting } = useAuth();

  const openPalette = useCallback(() => setPaletteOpen(true), []);
  const closePalette = useCallback(() => setPaletteOpen(false), []);

  useCommandK(openPalette);
  useScrollLock(drawerOpen);

  useEffect(() => {
    window.scrollTo(0, 0);
  }, [location.pathname]);

  useEffect(() => {
    if (!drawerOpen) {
      return;
    }
    const handleEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setDrawerOpen(false);
      }
    };
    window.addEventListener("keydown", handleEscape);
    return () => window.removeEventListener("keydown", handleEscape);
  }, [drawerOpen]);

  const closeDrawer = useCallback(() => setDrawerOpen(false), []);

  const health = healthQuery.data;
  let statusTone: StatusTone = "loading";
  let statusDetail = "checking local services";
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
    statusDetail = `db ${health.database} · cache ${health.cache} · AI ${aiState}`;
  }
  const statusDotClassName =
    statusTone === "loading" ? "status-dot status-dot--pending" : "status-dot";
  const statusDotStyle = STATUS_DOT_STYLES[statusTone];

  return (
    <div className="app-shell">
      <a className="skip-link" href="#main-content">
        Skip to the archive
      </a>

      <header className="mobile-bar">
        <button
          type="button"
          className="mobile-bar__button"
          onClick={() => setDrawerOpen(true)}
          aria-expanded={drawerOpen}
          aria-controls="archive-navigation"
          aria-label="Open navigation"
        >
          <Icon name="menu" size={20} />
        </button>
        <Link to="/" className="mobile-bar__brand">
          <TreeMark size={26} />
          <span>DendroMatrix</span>
        </Link>
        <button
          type="button"
          className="mobile-bar__button"
          onClick={openPalette}
          aria-label="Open command palette"
        >
          <Icon name="command" size={19} />
        </button>
      </header>

      {drawerOpen ? (
        <button
          type="button"
          className="sidebar-scrim"
          onClick={closeDrawer}
          aria-label="Close navigation"
        />
      ) : null}

      <aside
        id="archive-navigation"
        className={drawerOpen ? "sidebar is-open" : "sidebar"}
        aria-label="Archive navigation"
      >
        <div className="sidebar__top">
          <Link to="/" className="brand" onClick={closeDrawer}>
            <span className="brand__mark">
              <TreeMark size={42} />
            </span>
            <span className="brand__copy">
              <span className="brand__name">DendroMatrix</span>
              <span className="brand__subtitle">Annual ring archive</span>
            </span>
          </Link>
          <button
            type="button"
            className="sidebar__close"
            onClick={closeDrawer}
            aria-label="Close navigation"
          >
            <Icon name="close" size={18} />
          </button>
          <div className="sidebar__edition">
            <span>Vol. 01</span>
            <span aria-hidden="true">/</span>
            <span>Local archive</span>
            <span aria-hidden="true">/</span>
            <span>2026</span>
          </div>
        </div>

        <div className="sidebar__nav">
          <nav aria-label="Primary">
            {NAV_SECTIONS.map((section) => (
              <div className="nav-section" key={section.label}>
                <p className="nav-section__label">{section.label}</p>
                <ul className="nav-list">
                  {section.items.map((item) => {
                    const isMemoryRoute = item.to.startsWith("/memory/");
                    const destination = isMemoryRoute ? memoryHref : item.to;
                    return (
                      <li key={item.to}>
                        <NavLink
                          to={destination}
                          end={item.end}
                          onClick={closeDrawer}
                          className={({ isActive }) =>
                            isActive || (isMemoryRoute && location.pathname.startsWith("/memory"))
                              ? "nav-link is-active"
                              : "nav-link"
                          }
                        >
                          <span className="nav-link__icon" aria-hidden="true">
                            <Icon name={item.icon} size={17} />
                          </span>
                          <span className="nav-link__label">{item.label}</span>
                          <span className="nav-link__index" aria-hidden="true">
                            {item.index}
                          </span>
                        </NavLink>
                      </li>
                    );
                  })}
                </ul>
              </div>
            ))}
          </nav>
        </div>

        <div className="sidebar__foot">
          <button type="button" className="command-trigger" onClick={openPalette}>
            <Icon name="command" size={16} />
            <span>Command menu</span>
            <span className="command-trigger__keys" aria-hidden="true">
              <kbd>⌘</kbd>
              <kbd>K</kbd>
            </span>
          </button>

          <ThemeToggle />

          {user ? (
            <div className="account-chip">
              <span className="account-chip__mark" aria-hidden="true">
                {user.username.slice(0, 2).toUpperCase()}
              </span>
              <span className="account-chip__copy">
                <span>Signed in</span>
                <strong>{user.username}</strong>
              </span>
              <button
                type="button"
                className="account-chip__action"
                onClick={() => void logout()}
                disabled={isSubmitting}
                aria-label="Sign out"
                title="Sign out"
              >
                <Icon name="logout" size={16} />
              </button>
            </div>
          ) : null}

          <div className="system-status" aria-label="System status">
            <span
              className={statusDotClassName}
              style={statusDotStyle}
              aria-hidden="true"
            />
            <span className="system-status__copy">
              <span className="system-status__label">Local archive</span>
              <span className="system-status__detail">{statusDetail}</span>
            </span>
          </div>

          <div className="sidebar__colophon">
            <span>v{health?.version ?? "—"}</span>
            <span aria-hidden="true">·</span>
            <span>Local-first</span>
          </div>
        </div>
      </aside>

      <main id="main-content" className="app-main" tabIndex={-1}>
        <div className="app-page">
          <Suspense fallback={<RouteFallback />}>
            <Outlet />
          </Suspense>
        </div>
      </main>

      <nav className="mobile-tabs" aria-label="Primary mobile">
        {MOBILE_NAV.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.end}
            className={({ isActive }) => (isActive ? "mobile-tab is-active" : "mobile-tab")}
          >
            <Icon name={item.icon} size={20} />
            <span>{item.label}</span>
          </NavLink>
        ))}
        <button
          type="button"
          className="mobile-tab mobile-tab--more"
          onClick={() => setDrawerOpen(true)}
          aria-expanded={drawerOpen}
          aria-controls="archive-navigation"
        >
          <Icon name="menu" size={20} />
          <span>More</span>
        </button>
      </nav>

      {paletteOpen ? (
        <CommandPalette onClose={closePalette} memoryHref={memoryHref} />
      ) : null}
    </div>
  );
}
