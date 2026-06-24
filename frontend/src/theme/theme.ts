/**
 * Theme mode (light/dark) application + persistence.
 *
 * The design system ships **both** the light and dark Claude palettes as CSS
 * custom properties; a `data-mode` attribute on `<html>` selects one. Per
 * DECISIONS.md 2026-06-24 ("Default colour mode") the v1 default is **light**
 * (the spec's stated active default); the dark palette is shipped + selectable
 * via the toggle. `data-theme` is always `"claude"` (the only v1 theme; the
 * token architecture leaves room for per-tenant re-theming later).
 */

export type Mode = 'light' | 'dark';

export const THEME_STORAGE_KEY = 'bf-mode';
const THEME = 'claude';

/** The persisted mode, or the spec default (light) when none is stored. */
export function getInitialMode(): Mode {
  try {
    return localStorage.getItem(THEME_STORAGE_KEY) === 'dark' ? 'dark' : 'light';
  } catch {
    return 'light';
  }
}

/** Apply a mode to `<html>` and persist it. */
export function applyMode(mode: Mode): void {
  const root = document.documentElement;
  root.setAttribute('data-theme', THEME);
  root.setAttribute('data-mode', mode);
  try {
    localStorage.setItem(THEME_STORAGE_KEY, mode);
  } catch {
    /* storage unavailable (private mode / tests) — mode still applies for the session */
  }
}
