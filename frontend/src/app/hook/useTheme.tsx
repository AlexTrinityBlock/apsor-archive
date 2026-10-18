import {
  createContext,
  use,
  useCallback,
  useEffect,
  useMemo,
  useState,
  useSyncExternalStore,
  type ReactNode,
} from "react";

import type { ResolvedTheme, ThemePreference } from "../type/ui";

const STORAGE_KEY = "dendromatrix.theme";
const DARK_QUERY = "(prefers-color-scheme: dark)";

interface ThemeContextValue {
  readonly preference: ThemePreference;
  readonly theme: ResolvedTheme;
  readonly isDark: boolean;
  readonly setPreference: (preference: ThemePreference) => void;
  readonly toggle: () => void;
}

const ThemeContext = createContext<ThemeContextValue | null>(null);

function isPreference(value: string | null): value is ThemePreference {
  return value === "light" || value === "dark" || value === "system";
}

function readStoredPreference(): ThemePreference {
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    return isPreference(stored) ? stored : "light";
  } catch {
    return "light";
  }
}

function getSystemSnapshot(): ResolvedTheme {
  return window.matchMedia(DARK_QUERY).matches ? "dark" : "light";
}

function getServerSnapshot(): ResolvedTheme {
  return "light";
}

function subscribeToSystem(onChange: () => void): () => void {
  const query = window.matchMedia(DARK_QUERY);
  query.addEventListener("change", onChange);
  return () => query.removeEventListener("change", onChange);
}

function applyTheme(theme: ResolvedTheme, preference: ThemePreference): void {
  document.documentElement.dataset.theme = theme;
  document.documentElement.dataset.themePreference = preference;
  const meta = document.querySelector<HTMLMetaElement>('meta[name="theme-color"]');
  if (meta) {
    meta.content = theme === "dark" ? "#10160f" : "#f3edde";
  }
}

/**
 * Provides the paper / night archive palette.
 *
 * The initial palette is written by the inline script in index.html before the
 * first paint. The resolved theme is derived from the preference plus a live
 * subscription to the system palette, while localStorage is updated on change.
 */
export function ThemeProvider({ children }: { children: ReactNode }) {
  const [preference, setPreferenceState] = useState<ThemePreference>(readStoredPreference);
  const systemTheme = useSyncExternalStore(subscribeToSystem, getSystemSnapshot, getServerSnapshot);
  const theme: ResolvedTheme = preference === "system" ? systemTheme : preference;

  const setPreference = useCallback((next: ThemePreference) => {
    setPreferenceState(next);
    try {
      localStorage.setItem(STORAGE_KEY, next);
    } catch {
      // A blocked storage API should not prevent a theme change for this visit.
    }
  }, []);

  useEffect(() => {
    applyTheme(theme, preference);
  }, [preference, theme]);

  const toggle = useCallback(() => {
    setPreference(theme === "dark" ? "light" : "dark");
  }, [setPreference, theme]);

  const value = useMemo<ThemeContextValue>(
    () => ({
      preference,
      theme,
      isDark: theme === "dark",
      setPreference,
      toggle,
    }),
    [preference, setPreference, theme, toggle],
  );

  return <ThemeContext value={value}>{children}</ThemeContext>;
}

/** Reads the current archive theme and exposes a persisted setter. */
export function useTheme(): ThemeContextValue {
  const value = use(ThemeContext);
  if (!value) {
    throw new Error("useTheme must be used inside <ThemeProvider>.");
  }
  return value;
}
