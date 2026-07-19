/**
 * The manager KPI glance row (M6.1, spec #newscope §2: "KPI glance row — open
 * quotes, due this week, win rate 30d — for managers").
 *
 * Rendered only for admin/manager sessions; the API enforces the same gate, so
 * hiding it here is presentation, not security. Charts and analytics tiles are
 * explicitly out of scope (deferred to M7) — three numbers, no dashboarding.
 */

import { useTranslation } from 'react-i18next';

import type { Kpis } from './workQueueApi';

export function KpiRow({ kpis, locale }: { kpis: Kpis; locale: string }): React.ReactElement {
  const { t } = useTranslation();
  const winRate =
    kpis.win_rate_30d_pct === null
      ? '—'
      : `${Number(kpis.win_rate_30d_pct).toLocaleString(locale, {
          minimumFractionDigits: 1,
          maximumFractionDigits: 1,
        })} %`;
  return (
    <section aria-label={t('work_queue.kpis')} className="dashboard-kpis">
      <dl>
        <div className="kpi" data-testid="kpi-open-quotes">
          <dt>{t('work_queue.kpi_open_quotes')}</dt>
          <dd>{kpis.open_quotes.toLocaleString(locale)}</dd>
        </div>
        <div className="kpi" data-testid="kpi-due-this-week">
          <dt>{t('work_queue.kpi_due_this_week')}</dt>
          <dd>{kpis.due_this_week.toLocaleString(locale)}</dd>
        </div>
        <div className="kpi" data-testid="kpi-win-rate">
          <dt>{t('work_queue.kpi_win_rate')}</dt>
          <dd>{winRate}</dd>
        </div>
      </dl>
    </section>
  );
}
