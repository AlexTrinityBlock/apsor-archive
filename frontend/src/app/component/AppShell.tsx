import {
  Suspense,
  useCallback,
  useEffect,
  useRef,
  useState,
  type CSSProperties,
} from "react";
import { NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";

import { useGetHealth } from "../generated-apis-types";
import { useAuth } from "../auth/AuthProvider";
import { ChangePasswordDialog } from "../auth/component/ChangePasswordDialog";
import { ImpersonateUserDialog } from "../auth/component/ImpersonateUserDialog";
import { StopImpersonationDialog } from "../auth/component/StopImpersonationDialog";
import { useScrollLock } from "../hook/useScrollLock";
import { useVisualViewport } from "../hook/useVisualViewport";
import { useDrawerAccessibility } from "../hook/useDrawerAccessibility";
import {
  localizeStatus,
  useI18n,
  type Translate,
  type TranslationKey,
} from "../i18n";
import { Button } from "./Button";
import { Icon, type IconName } from "./Icon";
import { RouteFallback } from "./RouteFallback";
import { routeLabelKey, workspaceSegment } from "./route-title";
import { useToast } from "./Toast";
import { BrandMark } from "./BrandMark";


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
      { to: "/companion", labelKey: "core.nav.companion", icon: "companion" },
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

/** Name the browser tab after the active workspace. */
function applyDocumentTitle(
  t: Translate,
  pageLabelKey: TranslationKey | null,
): void {
  const app = t("core.app.name");
  document.title =
    pageLabelKey === null
      ? `${app} — ${t("core.app.studio")}`
      : t("core.route.title", { page: t(pageLabelKey), app });
}

/**
 * Collapsed-rail tooltips are fixed-position pseudo elements; anchor each to
 * its item's vertical centre when it is hovered or focused.
 */
function placeRailTooltip(element: HTMLElement): void {
  const rect = element.getBoundingClientRect();
  element.style.setProperty(
    "--rail-tooltip-top",
    `${Math.round(rect.top + rect.height / 2)}px`,
  );
}

function pageClassName(pathname: string): string {
  return pathname.startsWith("/chat") || pathname.startsWith("/library")
    ? "app-page app-page--fixed"
    : "app-page";
}

interface RailAccountIdentityProps {
  readonly username: string;
  readonly displayName: string;
  readonly isImpersonating: boolean;
  readonly canSwitchUser: boolean;
  readonly onSwitch: () => void;
}

/**
 * Footer identity. Root gets a button into the user switcher; every other
 * state is a plain identity block. The target account always stays visible
 * while impersonating, with a small reviewing marker.
 */
function RailAccountIdentity({
  username,
  displayName,
  isImpersonating,
  canSwitchUser,
  onSwitch,
}: RailAccountIdentityProps) {
  const { t } = useI18n();

  return (
    <div
      className={["rail-account", isImpersonating ? "is-impersonating" : null]
        .filter(Boolean)
        .join(" ")}
    >
      {canSwitchUser ? (
        <button
          type="button"
          className="rail-account__identity rail-account__identity--switch"
          onClick={onSwitch}
          aria-haspopup="dialog"
          aria-label={t("core.impersonation.switchUserAria", {
            name: displayName,
          })}
          title={t("core.impersonation.switchUserTitle")}
        >
          <span className="rail-account__mark" aria-hidden="true">
            {displayName.slice(0, 2).toUpperCase()}
          </span>
          <span className="rail-account__copy">
            <span className="rail-account__username">{username}</span>
            <strong>{displayName}</strong>
          </span>
          <span className="rail-account__cue" aria-hidden="true">
            <Icon name="chevron-down" size={12} />
          </span>
        </button>
      ) : (
        <div
          className="rail-account__identity"
          title={
            isImpersonating
              ? t("core.impersonation.bannerTitle", { name: displayName })
              : displayName
          }
        >
          <span className="rail-account__mark" aria-hidden="true">
            {displayName.slice(0, 2).toUpperCase()}
          </span>
          <span className="rail-account__copy">
            <span className="rail-account__username">{username}</span>
            <strong>{displayName}</strong>
            {isImpersonating ? (
              <span className="rail-account__viewing">
                {t("core.impersonation.viewingAs")}
              </span>
            ) : null}
          </span>
        </div>
      )}
    </div>
  );
}

interface ImpersonationBannerProps {
  readonly targetName: string;
  readonly rootName: string;
  readonly onStop: () => void;
}

interface StopDialogContext {
  readonly targetName: string;
  readonly targetUsername: string;
  readonly rootName: string;
}

/** Persistent account reminder above the page canvas while impersonating. */
function ImpersonationBanner({
  targetName,
  rootName,
  onStop,
}: ImpersonationBannerProps) {
  const { t } = useI18n();

  return (
    <div
      className="impersonation-banner"
      role="region"
      aria-label={t("core.impersonation.bannerAria")}
    >
      <span className="impersonation-banner__icon" aria-hidden="true">
        <Icon name="user" size={16} />
      </span>
      <div className="impersonation-banner__copy">
        <strong>
          {t("core.impersonation.bannerTitle", { name: targetName })}
        </strong>
        <span>
          {t("core.impersonation.bannerDescription", { root: rootName })}
        </span>
      </div>
      <Button
        type="button"
        variant="ink"
        size="sm"
        className="impersonation-banner__action"
        onClick={onStop}
      >
        {t("core.impersonation.returnToRoot")}
      </Button>
    </div>
  );
}

/** Expose the mobile drawer as a dialog only while it is acting as one. */
function drawerDialogAttributes(open: boolean) {
  return open ? { role: "dialog" as const, "aria-modal": true } : {};
}

/**
 * The fixed archive shell: a collapsible mono rail on desktop, a drawer on
 * mobile, and a single main canvas. The global command palette and floating
 * agent dock were deliberately removed by the template audit matrix.
 */
export function AppShell() {
  const { t } = useI18n();
  const toast = useToast();
  const navigate = useNavigate();
  const [railCollapsed, setRailCollapsed] = useState(readRailPreference);
  const [passwordDialogOpen, setPasswordDialogOpen] = useState(false);
  const [impersonateDialogOpen, setImpersonateDialogOpen] = useState(false);
  const [stopDialog, setStopDialog] = useState<StopDialogContext | null>(null);
  const mobileMenuButtonRef = useRef<HTMLButtonElement>(null);
  const railCloseButtonRef = useRef<HTMLButtonElement>(null);
  const returnFocusToMenuRef = useRef(false);
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
  const { user, logout, isSubmitting, impersonation, isImpersonating } =
    useAuth();
  const isRoot = user?.role === "root";
  const canSwitchUser = isRoot && !isImpersonating;
  const navSections = buildNavSections(isRoot);
  const displayName = user?.display_name || user?.username || t("core.nav.owner");
  const rootName =
    impersonation?.display_name ||
    impersonation?.username ||
    t("core.impersonation.root");

  useScrollLock(drawerOpen);
  // One app-level owner mirrors the visual viewport for the mobile shell and
  // every full-screen editor that consumes the root variables.
  useVisualViewport();

  // `html`/`body` never scroll; the page canvas does. Reset it, move focus to
  // the main landmark, and announce the new page only when the workspace
  // changes, so in-workspace URL updates (folders, previews) keep their place.
  // Chat owns focus itself (the composer), so it is skipped.
  const pageRef = useRef<HTMLDivElement>(null);
  const currentWorkspace = workspaceSegment(location.pathname);
  const previousWorkspace = useRef<string | null>(null);
  useEffect(() => {
    const previous = previousWorkspace.current;
    previousWorkspace.current = currentWorkspace;
    if (previous === null || previous === currentWorkspace) {
      return;
    }
    if (pageRef.current) {
      pageRef.current.scrollTop = 0;
    }
    if (currentWorkspace !== "chat") {
      document
        .getElementById("main-content")
        ?.focus({ preventScroll: true });
    }
  }, [currentWorkspace]);

  const titleRoutes = navSections.flatMap((section) =>
    section.items.filter((item) => item.action === undefined),
  );
  const pageLabelKey = routeLabelKey(location.pathname, titleRoutes);
  useEffect(() => {
    applyDocumentTitle(t, pageLabelKey);
  }, [pageLabelKey, t]);

  useEffect(() => {
    try {
      window.localStorage.setItem(RAIL_STORAGE_KEY, String(railCollapsed));
    } catch {
      // A private browser may reject storage; the rail still works for the tab.
    }
  }, [railCollapsed]);

  const openDrawer = useCallback(() => {
    returnFocusToMenuRef.current = false;
    setDrawer({ open: true, path: window.location.pathname });
  }, []);
  const closeDrawer = useCallback(() => {
    setDrawer((current) => ({ ...current, open: false }));
  }, []);

  useDrawerAccessibility({
    open: drawerOpen,
    closeButtonRef: railCloseButtonRef,
    menuButtonRef: mobileMenuButtonRef,
    returnFocusRef: returnFocusToMenuRef,
    onClose: closeDrawer,
  });

  const openImpersonateDialog = useCallback(() => {
    returnFocusToMenuRef.current = false;
    closeDrawer();
    setImpersonateDialogOpen(true);
  }, [closeDrawer]);
  const closeImpersonateDialog = useCallback(() => {
    setImpersonateDialogOpen(false);
    // The opener lived in the drawer, which closed before the dialog mounted.
    // Return focus to the visible mobile navigation control instead.
    if (window.matchMedia("(max-width: 980px)").matches) {
      window.requestAnimationFrame(() => mobileMenuButtonRef.current?.focus());
    }
  }, []);
  const toggleRail = useCallback(
    () => setRailCollapsed((previous) => !previous),
    [],
  );

  const openStopDialog = useCallback(() => {
    if (!user) {
      return;
    }
    setStopDialog({
      targetName: displayName,
      targetUsername: user.username,
      rootName,
    });
  }, [displayName, rootName, user]);

  const handleStopped = useCallback(() => {
    setStopDialog(null);
    toast.success(t("core.impersonation.returnedToRoot"));
    navigate("/accounts");
  }, [navigate, t, toast]);

  const workspaceKey = `${user?.user_id ?? "anonymous"}:${impersonation?.actor_user_id ?? "none"}`;

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
      <a className="skip-link" href="#main-content" inert={drawerOpen}>
        {t("core.nav.skipToArchive")}
      </a>

      <header className="mobile-bar" inert={drawerOpen}>
        <button
          ref={mobileMenuButtonRef}
          type="button"
          className="mobile-bar__button"
          onClick={openDrawer}
          aria-expanded={drawerOpen}
          aria-controls="archive-navigation"
          aria-label={t("core.nav.openNavigation")}
        >
          <Icon name="panel-left-open" size={20} />
        </button>
        <NavLink to="/" className="mobile-bar__brand" end>
          <span className="brand-seal brand-seal--image brand-seal--small" aria-hidden="true">
            <BrandMark size={28} />
          </span>
          <span>{t("core.app.name")}</span>
        </NavLink>
      </header>

      {drawerOpen ? (
        <button
          type="button"
          className="rail-scrim"
          onClick={() => {
            returnFocusToMenuRef.current = true;
            closeDrawer();
          }}
          aria-label={t("core.nav.closeNavigation")}
        />
      ) : null}

      <aside
        id="archive-navigation"
        className={drawerOpen ? "nav-rail is-open" : "nav-rail"}
        aria-label={t("core.nav.ariaArchive")}
        {...drawerDialogAttributes(drawerOpen)}
      >
        <div className="rail-header">
          <NavLink
            to="/"
            className="brand-cluster"
            onClick={() => {
              returnFocusToMenuRef.current = false;
              closeDrawer();
            }}
            title={t("core.app.name")}
          >
            <span className="brand-seal brand-seal--image" aria-hidden="true">
              <BrandMark size={36} />
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
            <Icon
              name={railCollapsed ? "panel-left-open" : "panel-left-close"}
              size={14}
            />
          </button>
          <button
            ref={railCloseButtonRef}
            type="button"
            className="rail-close-btn"
            onClick={() => {
              returnFocusToMenuRef.current = true;
              closeDrawer();
            }}
            aria-label={t("core.nav.closeNavigation")}
          >
            <Icon name="panel-left-close" size={18} />
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
                        returnFocusToMenuRef.current = false;
                        closeDrawer();
                        if (isLogout) {
                          void logout();
                        } else {
                          setPasswordDialogOpen(true);
                        }
                      }}
                      data-tooltip={`${label} (${item.index})`}
                      onPointerEnter={(event) =>
                        placeRailTooltip(event.currentTarget)
                      }
                      onFocus={(event) => placeRailTooltip(event.currentTarget)}
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
                    onClick={() => {
                      returnFocusToMenuRef.current = false;
                      closeDrawer();
                    }}
                    data-tooltip={`${label} (${item.index})`}
                    onPointerEnter={(event) =>
                      placeRailTooltip(event.currentTarget)
                    }
                    onFocus={(event) => placeRailTooltip(event.currentTarget)}
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
            <RailAccountIdentity
              username={user.username}
              displayName={displayName}
              isImpersonating={isImpersonating}
              canSwitchUser={canSwitchUser}
              onSwitch={openImpersonateDialog}
            />
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

      <main id="main-content" className="app-main" tabIndex={-1} inert={drawerOpen}>
        {isImpersonating ? (
          <ImpersonationBanner
            targetName={displayName}
            rootName={rootName}
            onStop={openStopDialog}
          />
        ) : null}
        <div
          key={workspaceKey}
          ref={pageRef}
          className={pageClassName(location.pathname)}
        >
          <Suspense fallback={<RouteFallback />}>
            <Outlet />
          </Suspense>
        </div>
      </main>

      {passwordDialogOpen ? (
        <ChangePasswordDialog onClose={() => setPasswordDialogOpen(false)} />
      ) : null}

      {impersonateDialogOpen && canSwitchUser ? (
        <ImpersonateUserDialog onClose={closeImpersonateDialog} />
      ) : null}

      {stopDialog ? (
        <StopImpersonationDialog
          targetName={stopDialog.targetName}
          targetUsername={stopDialog.targetUsername}
          rootName={stopDialog.rootName}
          onClose={() => setStopDialog(null)}
          onStopped={handleStopped}
        />
      ) : null}
    </div>
  );
}
