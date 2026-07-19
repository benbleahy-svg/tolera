/**
 * Capability-chip input parsing (M6.3).
 *
 * Lives outside the component files so both the ADD VENDOR modal and the
 * Capabilities tab can share it without breaking React Fast Refresh (a module
 * that exports a component must export nothing else).
 *
 * Splitting only — the real normalization (trim, lowercase, de-duplicate) is the
 * server's job in `app.vendors._normalize_tags`, so the stored tags and the
 * directory filter can never disagree about what a chip means.
 */

/** Split a comma-separated chip input into raw tags, dropping blanks. */
export function splitTagInput(raw: string): string[] {
  return raw
    .split(',')
    .map((tag) => tag.trim())
    .filter(Boolean);
}
