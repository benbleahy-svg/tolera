/**
 * Dashboard (M2.11 slice + M3.3 notifications) — the landing surface where
 * **Assign Task** and the intake notifications land.
 *
 * The full Dashboard redesign is M6; M3.3 adds only the notifications list so
 * "New Quote created from Email Forwarding: Created Quote #N" (spec #wingman)
 * renders and deep-links to the quote. The M3.9 Triage Brief later replaces
 * the plain email-ingest card with a structured triage card. Org-scoped by RLS.
 */

import { useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router-dom';

import {
  type Member,
  memberLabel,
  type Notification,
  type Task,
  useCollabApi,
} from '../collab/api';

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
  const api = useCollabApi();
  const [tasks, setTasks] = useState<Task[]>([]);
  const [members, setMembers] = useState<Member[]>([]);
  const [notifications, setNotifications] = useState<Notification[]>([]);
  const [error, setError] = useState<string | null>(null);

  const reload = useCallback(async () => {
    try {
      const [ts, mem, notes] = await Promise.all([
        api.listTasks(),
        api.listMembers(),
        api.listNotifications(),
      ]);
      setTasks(ts);
      setMembers(mem);
      setNotifications(notes);
    } catch {
      setError(t('collab.load_error'));
    }
  }, [api, t]);

  useEffect(() => {
    void reload();
  }, [reload]);

  const assigneeName = (id: string | null): string => {
    const m = members.find((x) => x.id === id);
    return m ? memberLabel(m) : t('collab.unknown_member');
  };

  const resolve = async (task: Task) => {
    await api.updateTask(task.id, task.status === 'resolved' ? 'open' : 'resolved');
    await reload();
  };

  const markRead = async (n: Notification) => {
    try {
      await api.markNotification(n.id, true);
      // Only the notification list changed — don't refetch tasks/members.
      setNotifications(await api.listNotifications());
    } catch {
      setError(t('collab.load_error'));
    }
  };

  return (
    <div className="dashboard">
      <h1>{t('nav.dashboard')}</h1>
      <section aria-label={t('dashboard.notifications')}>
        <h2>{t('dashboard.notifications')}</h2>
        {error && <p role="alert">{error}</p>}
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
                <span>{notificationText(n, t)}</span>
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
      <section aria-label={t('dashboard.tasks')}>
        <h2>{t('dashboard.tasks')}</h2>
        {tasks.length === 0 ? (
          <p className="dashboard-empty">{t('dashboard.no_tasks')}</p>
        ) : (
          <table className="dashboard-tasks">
            <thead>
              <tr>
                <th>{t('dashboard.task')}</th>
                <th>{t('dashboard.assignee')}</th>
                <th>{t('dashboard.due')}</th>
                <th>{t('dashboard.status')}</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {tasks.map((task) => (
                <tr key={task.id} className={`task-${task.status}`} data-testid="task-row">
                  <td>{task.message ?? t('dashboard.untitled_task')}</td>
                  <td>{assigneeName(task.assignee_id)}</td>
                  <td>{task.due_date ?? '—'}</td>
                  <td>
                    <span className={`task-status task-status-${task.status}`}>
                      {t(`dashboard.status_${task.status}`)}
                    </span>
                  </td>
                  <td>
                    <button type="button" onClick={() => void resolve(task)}>
                      {task.status === 'resolved'
                        ? t('dashboard.reopen')
                        : t('dashboard.resolve')}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </div>
  );
}
