/**
 * "Recently opened" strip (M6.1, spec #newscope §2) — the user's last 8 quotes
 * for instant resume, most recent first. Thumbnails arrive with the part-preview
 * work; v1 shows number + status, which is what the strip is actually used for
 * (finding the thing you had open five minutes ago).
 */

import { useTranslation } from 'react-i18next';
import { Link } from 'react-router-dom';

import type { RecentRow } from './workQueueApi';

export function RecentlyOpened({ rows }: { rows: RecentRow[] }): React.ReactElement | null {
  const { t } = useTranslation();
  if (rows.length === 0) {
    // Nothing opened yet — an empty strip is noise on a first-run dashboard.
    return null;
  }
  return (
    <section aria-label={t('work_queue.recents')} className="dashboard-recents">
      <h2>{t('work_queue.recents')}</h2>
      <ul>
        {rows.map((row) => (
          <li key={`${row.entity_type}:${row.entity_id}`} data-testid="recent-row">
            <Link to={`/quotes/${row.entity_id}`}>
              <span className="recent-label">{row.label || row.entity_id.slice(0, 8)}</span>
              {row.status && (
                <span className={`recent-status recent-status-${row.status}`}>
                  {/* Statuses the M1 catalog doesn't localize yet (on_hold,
                      cancelled, no_quote) fall back to the raw value rather
                      than rendering a key. */}
                  {t(`quotes.status.${row.status}`, { defaultValue: row.status })}
                </span>
              )}
            </Link>
          </li>
        ))}
      </ul>
    </section>
  );
}
