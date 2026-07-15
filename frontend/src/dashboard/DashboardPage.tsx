/**
 * Dashboard (M2.11 slice) — the work-queue surface where **Assign Task** lands.
 *
 * The full Dashboard redesign is M6; this block only emits collaboration tasks
 * onto the existing landing surface: the active org's tasks, newest first, with
 * ``overdue`` derived server-side, and a one-click resolve. Org-scoped by RLS.
 */

import { useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';

import { type Member, memberLabel, type Task, useCollabApi } from '../collab/api';

export function DashboardPage(): React.ReactElement {
  const { t } = useTranslation();
  const api = useCollabApi();
  const [tasks, setTasks] = useState<Task[]>([]);
  const [members, setMembers] = useState<Member[]>([]);
  const [error, setError] = useState<string | null>(null);

  const reload = useCallback(async () => {
    try {
      const [ts, mem] = await Promise.all([api.listTasks(), api.listMembers()]);
      setTasks(ts);
      setMembers(mem);
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

  return (
    <div className="dashboard">
      <h1>{t('nav.dashboard')}</h1>
      <section aria-label={t('dashboard.tasks')}>
        <h2>{t('dashboard.tasks')}</h2>
        {error && <p role="alert">{error}</p>}
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
