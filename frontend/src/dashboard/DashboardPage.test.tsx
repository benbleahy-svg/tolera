import { beforeEach, describe, expect, it, vi } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { renderWithProviders } from '../test/render';
import { DashboardPage } from './DashboardPage';

const listTasks = vi.fn();
const listMembers = vi.fn();
const updateTask = vi.fn();
const listNotifications = vi.fn();
const markNotification = vi.fn();

vi.mock('../collab/api', async () => {
  const actual = await vi.importActual<typeof import('../collab/api')>('../collab/api');
  return {
    ...actual,
    useCollabApi: () => ({
      listTasks,
      listMembers,
      updateTask,
      listNotifications,
      markNotification,
      listChannels: vi.fn(),
      createChannel: vi.fn(),
      listMessages: vi.fn(),
      postMessage: vi.fn(),
      editMessage: vi.fn(),
      deleteMessage: vi.fn(),
      assignTask: vi.fn(),
    }),
  };
});

const MEMBERS = [{ id: 'u2', email: 'engineer@fechner.example', first_name: 'Max', last_name: 'Bauer' }];

function task(overrides: Record<string, unknown> = {}) {
  return {
    id: 't1',
    part_id: 'p1',
    quote_id: null,
    annotation_id: 'a1',
    assignee_id: 'u2',
    created_by: 'u1',
    message: 'Maskierung prüfen',
    due_date: null,
    status: 'open' as const,
    resolved_at: null,
    created_at: '2026-07-14T00:00:00Z',
    ...overrides,
  };
}

describe('DashboardPage', () => {
  beforeEach(() => {
    listTasks.mockReset();
    listMembers.mockReset();
    updateTask.mockReset();
    listMembers.mockResolvedValue(MEMBERS);
    updateTask.mockResolvedValue(task({ status: 'resolved' }));
    listNotifications.mockReset();
    markNotification.mockReset();
    listNotifications.mockResolvedValue([]);
    markNotification.mockResolvedValue({});
  });

  it('surfaces assigned tasks with assignee + status', async () => {
    listTasks.mockResolvedValue([
      task(),
      task({ id: 't2', message: 'Beschichtung klären', status: 'overdue', due_date: '2000-01-01' }),
    ]);
    await renderWithProviders(<DashboardPage />);

    expect(await screen.findByText('Maskierung prüfen')).toBeInTheDocument();
    expect(screen.getAllByText('Max Bauer')).toHaveLength(2);
    expect(screen.getByText('Offen')).toBeInTheDocument();
    expect(screen.getByText('Überfällig')).toBeInTheDocument();
    expect(screen.getAllByTestId('task-row')).toHaveLength(2);
  });

  it('shows an empty state when there are no tasks', async () => {
    listTasks.mockResolvedValue([]);
    await renderWithProviders(<DashboardPage />);
    expect(await screen.findByText('Keine offenen Aufgaben.')).toBeInTheDocument();
  });

  it('resolves a task', async () => {
    listTasks.mockResolvedValue([task()]);
    await renderWithProviders(<DashboardPage />);
    await userEvent.click(await screen.findByRole('button', { name: 'Erledigen' }));
    await waitFor(() => expect(updateTask).toHaveBeenCalledWith('t1', 'resolved'));
  });

  it('renders the email-ingest notification with a quote link (M3.3)', async () => {
    listTasks.mockResolvedValue([]);
    listNotifications.mockResolvedValue([
      {
        id: 'n1',
        kind: 'quote_email_ingested',
        payload: { quote_id: 'q1', quote_number: '17', rfq_id: 'r1' },
        read_at: null,
        created_at: '2026-07-15T00:00:00Z',
      },
    ]);
    await renderWithProviders(<DashboardPage />);

    expect(
      await screen.findByText(
        'Neues Angebot aus E-Mail-Weiterleitung: Angebot #17 erstellt',
      ),
    ).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Angebot öffnen' })).toHaveAttribute(
      'href',
      '/quotes/q1',
    );
  });

  it('marks a notification as read', async () => {
    listTasks.mockResolvedValue([]);
    listNotifications.mockResolvedValue([
      {
        id: 'n1',
        kind: 'quote_email_ingested',
        payload: { quote_id: 'q1', quote_number: '17' },
        read_at: null,
        created_at: '2026-07-15T00:00:00Z',
      },
    ]);
    await renderWithProviders(<DashboardPage />);
    await userEvent.click(
      await screen.findByRole('button', { name: 'Als gelesen markieren' }),
    );
    await waitFor(() => expect(markNotification).toHaveBeenCalledWith('n1', true));
  });

  it('shows the notifications empty state', async () => {
    listTasks.mockResolvedValue([]);
    await renderWithProviders(<DashboardPage />);
    expect(await screen.findByText('Keine Benachrichtigungen.')).toBeInTheDocument();
  });
});
