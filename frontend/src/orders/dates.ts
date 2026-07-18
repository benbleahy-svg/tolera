/**
 * Date formatting for the Orders tab. Two kinds of value cross the wire:
 *  - **date-only** calendar dates (`expected_ship_date`, line `ships_on` → "2026-07-15"):
 *    `new Date("2026-07-15")` parses as **UTC midnight**, which renders as the
 *    *previous* day west of UTC. Parse these as a **local** calendar date instead.
 *  - **timestamps** (`created_at`, `shipped_at` → full ISO with a `Z`): parsed as
 *    the correct instant by `new Date`, then shown as a local date.
 * Both render with the German locale (CLAUDE.md §5 number/date formatting).
 */

const EM_DASH = '—';

/** True for a bare "YYYY-MM-DD" calendar date (no time component). */
function isDateOnly(iso: string): boolean {
  return /^\d{4}-\d{2}-\d{2}$/.test(iso);
}

/**
 * Format an ISO date/timestamp with the given locale. A bare date-only string is
 * read as a **local** calendar date (no UTC shift); a full timestamp is read as an
 * instant. Null/empty → em dash.
 */
export function formatOrderDate(iso: string | null, locale: string): string {
  if (!iso) return EM_DASH;
  let d: Date;
  if (isDateOnly(iso)) {
    const [y, m, day] = iso.split('-').map(Number);
    d = new Date(y, m - 1, day); // local midnight — stable calendar date in any TZ
  } else {
    d = new Date(iso);
  }
  if (Number.isNaN(d.getTime())) return EM_DASH;
  return d.toLocaleDateString(locale);
}

/** The locale to use for order dates/numbers — German-first (CLAUDE.md §5). */
export function orderDateLocale(language: string): string {
  return language === 'de' ? 'de-DE' : language;
}
