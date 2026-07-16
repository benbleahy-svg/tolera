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
const getTriageBrief = vi.fn();

vi.mock('../quotes/api', () => ({
  useQuotesApi: () => ({
    searchQuotes: vi.fn(),
    listSavedViews: vi.fn(),
    createSavedView: vi.fn(),
    updateSavedView: vi.fn(),
    deleteSavedView: vi.fn(),
    getTriageBrief,
  }),
}));

function triageBrief(overrides: Record<string, unknown> = {}) {
  return {
    version: 1,
    generated_at: '2026-07-16T09:00:00Z',
    ai: { enabled: true, reason: 'ok' },
    parts: {
      count: 3,
      files: { step: 1, dxf: 0, pdf: 2, other: 0, total: 3, summary: '1 STEP + 2 PDF' },
    },
    missing_files: ['PP-5531'],
    detected_processes: [{ family: 'machining', name: 'CNC-Fräsen', likelihood: 'likely', source: 'ai' }],
    est_time_to_quote: { low_min: 120, high_min: 180, display: 'ca. 2-3 Std.', deterministic: true },
    customer: { known: false, name: 'Arch Medial', prior_quotes: 0, one_liner: 'Neukunde · Arch Medial' },
    compliance_flags: [
      { code: 'export_control', severity: 'warn', source: 'keyword', detail: 'Exportkontroll-Hinweis' },
    ],
    need_by: { date: '2026-07-22', days_until: 6, urgency: 'mittel' },
    ...overrides,
  };
}

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

// The M3.10 suggested-actions strip renders inside the dashboard; stub its API
// so this suite stays focused on notifications/tasks (the strip has its own).
// Stable object per the real useMemo hook — a fresh object each render would
// re-fire the strip's load effect in a loop.
const ruleSuggestApi = {
  listSuggestedActions: vi.fn().mockResolvedValue([]),
  dismissSuggestedAction: vi.fn(),
  getRuleSuggestion: vi.fn(),
};
vi.mock('../review/api', async () => {
  const actual = await vi.importActual<typeof import('../review/api')>('../review/api');
  return { ...actual, useRuleSuggestApi: () => ruleSuggestApi };
});

vi.mock('../configure/api', () => ({
  useConfigureApi: () => ({ importRules: vi.fn() }),
}));

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
    getTriageBrief.mockReset();
    listNotifications.mockResolvedValue([]);
    markNotification.mockResolvedValue({});
    getTriageBrief.mockResolvedValue({ brief: null });
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

  it('renders the email-ingest notification as a triage card with signals (M3.9)', async () => {
    listTasks.mockResolvedValue([]);
    getTriageBrief.mockResolvedValue({ brief: triageBrief() });
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

    // The structured triage card replaces the plain notification text.
    expect(await screen.findByTestId('triage-card')).toBeInTheDocument();
    expect(screen.getByTestId('triage-parts')).toHaveTextContent('1 STEP + 2 PDF');
    expect(screen.getByTestId('triage-missing')).toHaveTextContent('PP-5531'); // ⚠ blocker
    expect(screen.getByTestId('triage-compliance')).toBeInTheDocument(); // never suppressed
    expect(screen.getByTestId('triage-est-time')).toHaveTextContent('ca. 2-3 Std.');
    expect(getTriageBrief).toHaveBeenCalledWith('q1');
    // The deep-link to the quote is preserved.
    expect(screen.getByRole('link', { name: 'Angebot öffnen' })).toHaveAttribute(
      'href',
      '/quotes/q1',
    );
  });

  it('shows the AI-disabled state without suppressing compliance (M3.9)', async () => {
    listTasks.mockResolvedValue([]);
    getTriageBrief.mockResolvedValue({
      brief: triageBrief({ ai: { enabled: false, reason: 'master_disabled' } }),
    });
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
    expect(await screen.findByText('KI-Verarbeitung deaktiviert')).toBeInTheDocument();
    // Compliance + missing-file blocker still surface with AI off.
    expect(screen.getByTestId('triage-compliance')).toBeInTheDocument();
    expect(screen.getByTestId('triage-missing')).toBeInTheDocument();
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
