import { beforeEach, describe, expect, it, vi } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { renderWithProviders } from '../test/render';
import { DashboardPage } from './DashboardPage';

const listTasks = vi.fn();
const listMembers = vi.fn();
const updateTask = vi.fn();

vi.mock('../collab/api', async () => {
  const actual = await vi.importActual<typeof import('../collab/api')>('../collab/api');
  return {
    ...actual,
    useCollabApi: () => ({
      listTasks,
      listMembers,
      updateTask,
      listChannels: vi.fn(),
      createChannel: vi.fn(),
      listMessages: vi.fn(),
      postMessage: vi.fn(),
      editMessage: vi.fn(),
      deleteMessage: vi.fn(),
      assignTask: vi.fn(),
      listNotifications: vi.fn(),
      markNotification: vi.fn(),
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
});
