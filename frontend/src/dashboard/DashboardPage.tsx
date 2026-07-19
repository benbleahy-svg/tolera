/**
 * Dashboard — the landing surface, redesigned around one question: **"What needs
 * me now."** (M6.1, spec #newscope §2).
 *
 * The **work queue** is the page: one merged, prioritised list across quotes
 * needing my action, tasks, review items, vendor RFQs and @mentions, ordered by
 * an explainable urgency score. Around it sit the *Recently opened* strip, the
 * manager KPI glance row, and the regions the reference dashboard is retained
 * for — the notifications feed (with the M3.9 triage card), the M3.10 suggested
 * actions, and the "view all" links.
 *
 * What the redesign **replaces** is the reference three-panel Workflows table;
 * it survives untouched as the "Workflows" saved view on /quotes (M1.3), which
 * the link below points at. Analytics tiles stay out (deferred to M7).
 */

import { useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router-dom';

import { type Notification, useCollabApi } from '../collab/api';
import { useSession } from '../session/session';
import { KpiRow } from './KpiRow';
import { RecentlyOpened } from './RecentlyOpened';
import { SuggestedActionsStrip } from './SuggestedActionsStrip';
import { TriageCard } from './TriageCard';
import { WorkQueue } from './WorkQueue';
import { type Kpis, type QueueRow, type RecentRow, useWorkQueueApi } from './workQueueApi';

/** Roles the KPI row is for — the API enforces the same set. */
const MANAGER_ROLES = ['admin', 'manager'];

/** Human copy per notification kind; unknown kinds fall back to the raw kind. */
function notificationText(
  n: Notification,
  t: (key: string, opts?: Record<string, unknown>) => string,
): string {
  switch (n.kind) {
    case 'quote_email_ingested':
      return t('dashboard.notif_quote_email', { number: n.payload.quote_number as string });
    case 'mention':
      return t('dashboard.notif_mention');
    case 'task_assigned':
      return t('dashboard.notif_task_assigned');
    default:
      return n.kind;
  }
}

export function DashboardPage(): React.ReactElement {
  const { t } = useTranslation();
  const session = useSession();
  const collab = useCollabApi();
  const api = useWorkQueueApi();
  const [rows, setRows] = useState<QueueRow[]>([]);
  const [recents, setRecents] = useState<RecentRow[]>([]);
  const [kpis, setKpis] = useState<Kpis | null>(null);
  const [notifications, setNotifications] = useState<Notification[]>([]);
  const [error, setError] = useState<string | null>(null);

  const isManager = session.roles.some((role) => MANAGER_ROLES.includes(role));
  const locale = session.active_org.locale;

  const reload = useCallback(async () => {
    try {
      const [queue, recent, notes] = await Promise.all([
        api.getQueue(),
        api.getRecents(),
        collab.listNotifications(),
      ]);
      setRows(queue.rows);
      setRecents(recent.rows);
      setNotifications(notes);
      // The KPI row is a separate, role-gated call: a non-manager must not have
      // a 403 take the whole dashboard down with it.
      setKpis(isManager ? await api.getKpis() : null);
      // A transient failure must not leave the alert up for the rest of the session.
      setError(null);
    } catch {
      setError(t('collab.load_error'));
    }
  }, [api, collab, isManager, t]);

  useEffect(() => {
    void reload();
  }, [reload]);

  const markRead = async (n: Notification) => {
    try {
      await collab.markNotification(n.id, true);
      // A read @mention leaves the queue too — reload both, not just the feed.
      await reload();
    } catch {
      setError(t('collab.load_error'));
    }
  };

  return (
    <div className="dashboard">
      <h1>{t('nav.dashboard')}</h1>
      {error && <p role="alert">{error}</p>}
      {kpis && <KpiRow kpis={kpis} locale={locale} />}
      <section aria-label={t('work_queue.title')} className="dashboard-queue">
        <h2>{t('work_queue.title')}</h2>
        <WorkQueue rows={rows} locale={locale} />
        <p className="dashboard-links">
          <Link to="/quotes?view=workflows">{t('work_queue.view_workflows')}</Link>
          <Link to="/quotes">{t('work_queue.view_all_quotes')}</Link>
        </p>
      </section>
      <RecentlyOpened rows={recents} />
      <SuggestedActionsStrip />
      <section aria-label={t('dashboard.notifications')}>
        <h2>{t('dashboard.notifications')}</h2>
        {notifications.length === 0 ? (
          <p className="dashboard-empty">{t('dashboard.no_notifications')}</p>
        ) : (
          <ul className="dashboard-notifications">
            {notifications.map((n) => (
              <li
                key={n.id}
                className={n.read_at ? 'notification-read' : 'notification-unread'}
                data-testid="notification-row"
              >
                {n.kind === 'quote_email_ingested' && typeof n.payload.quote_id === 'string' ? (
                  <TriageCard
                    quoteId={n.payload.quote_id}
                    quoteNumber={String(n.payload.quote_number ?? '')}
                  />
                ) : (
                  <span>{notificationText(n, t)}</span>
                )}
                {typeof n.payload.quote_id === 'string' && (
                  <Link to={`/quotes/${n.payload.quote_id}`}>{t('dashboard.open_quote')}</Link>
                )}
                {!n.read_at && (
                  <button type="button" onClick={() => void markRead(n)}>
                    {t('dashboard.mark_read')}
                  </button>
                )}
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
