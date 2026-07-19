import { beforeEach, describe, expect, it, vi } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { makeMe, renderWithProviders } from '../test/render';
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

// M6.1 — the page now leads with the work queue; stub its API (stable object,
// or the load effect re-fires every render).
const getQueue = vi.fn();
const getRecents = vi.fn();
const getKpis = vi.fn();
const workQueueApi = {
  getQueue,
  getRecents,
  getKpis,
  getSettings: vi.fn(),
  saveSettings: vi.fn(),
  recordRecent: vi.fn(),
};
vi.mock('./workQueueApi', async () => {
  const actual = await vi.importActual<typeof import('./workQueueApi')>('./workQueueApi');
  return { ...actual, useWorkQueueApi: () => workQueueApi };
});

function queueRow(overrides: Record<string, unknown> = {}) {
  return {
    source: 'quote_action' as const,
    id: 'q1',
    quote_id: 'q1',
    label: '1001',
    reason_chips: [{ key: 'work_queue.chip.due_in', params: { count: 2 } }],
    urgency: '0.2000',
    factors: [
      { key: 'due', raw: '2', normalized: '0.5', weight: '0.4000', contribution: '0.2000' },
      { key: 'value', raw: '0', normalized: '0', weight: '0.2500', contribution: '0.0000' },
      { key: 'unresolved', raw: '0', normalized: '0', weight: '0.2500', contribution: '0.0000' },
      { key: 'flags', raw: '0', normalized: '0', weight: '0.1000', contribution: '0.0000' },
    ],
    deep_link: '/quotes/q1',
    org_id: 'org-fechner',
    org_name: 'Fechner GmbH',
    org_slug: 'fechner',
    cross_org: false,
    ...overrides,
  };
}

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
    getQueue.mockReset();
    getRecents.mockReset();
    getKpis.mockReset();
    getQueue.mockResolvedValue({
      rows: [],
      weights: {
        weight_due: '0.4000',
        weight_value: '0.2500',
        weight_unresolved: '0.2500',
        weight_flags: '0.1000',
        vendor_rfq_queue_enabled: false,
      },
      generated_on: '2026-07-19',
    });
    getRecents.mockResolvedValue({ rows: [] });
    getKpis.mockResolvedValue({ open_quotes: 4, due_this_week: 2, win_rate_30d_pct: '50.0' });
  });

  it('merges every source into one prioritised queue with its reason chips', async () => {
    getQueue.mockResolvedValue({
      rows: [
        queueRow({ urgency: '0.6000', reason_chips: [{ key: 'work_queue.chip.overdue', params: { count: 3 } }] }),
        queueRow({
          source: 'task',
          id: 't1',
          label: 'Maskierung prüfen',
          urgency: '0.1000',
          reason_chips: [{ key: 'work_queue.chip.task_assigned', params: {} }],
        }),
        queueRow({
          source: 'review_item',
          id: 'r1',
          label: 'Fehlende Zeichnung',
          urgency: '0.0500',
          reason_chips: [{ key: 'work_queue.chip.unresolved', params: { count: 3 } }],
        }),
      ],
      weights: {
        weight_due: '0.4000',
        weight_value: '0.2500',
        weight_unresolved: '0.2500',
        weight_flags: '0.1000',
        vendor_rfq_queue_enabled: false,
      },
      generated_on: '2026-07-19',
    });
    await renderWithProviders(<DashboardPage />);

    const rows = await screen.findAllByTestId('queue-row');
    expect(rows).toHaveLength(3);
    // Server order is the urgency order — the client never re-sorts.
    expect(rows.map((r) => r.dataset.source)).toEqual(['quote_action', 'task', 'review_item']);
    expect(screen.getByText('seit 3 Tagen überfällig')).toBeInTheDocument();
    expect(screen.getByText('3 offene Prüfpunkte')).toBeInTheDocument();
    expect(screen.getByText('Maskierung prüfen')).toBeInTheDocument();
  });

  it('explains a row: the factors expand and add up to its score', async () => {
    getQueue.mockResolvedValue({
      rows: [queueRow()],
      weights: {
        weight_due: '0.4000',
        weight_value: '0.2500',
        weight_unresolved: '0.2500',
        weight_flags: '0.1000',
        vendor_rfq_queue_enabled: false,
      },
      generated_on: '2026-07-19',
    });
    await renderWithProviders(<DashboardPage />);

    // German locale formatting for the score (0,20 — not 0.20).
    const score = await screen.findByRole('button', { name: '0,20' });
    expect(screen.queryByTestId('queue-factors')).not.toBeInTheDocument();
    await userEvent.click(score);
    expect(screen.getByTestId('queue-factors')).toBeInTheDocument();
    expect(screen.getByTestId('factor-due')).toHaveTextContent('0.2000');
    expect(screen.getByTestId('factor-flags')).toHaveTextContent('0.0000');
  });

  it('labels a cross-org row and does not pretend it can switch org yet', async () => {
    getQueue.mockResolvedValue({
      rows: [
        queueRow({
          source: 'mention',
          id: 'n9',
          quote_id: null,
          deep_link: '/',
          org_id: 'org-helvetia',
          org_name: 'Helvetia AG',
          org_slug: 'helvetia',
          cross_org: true,
          reason_chips: [{ key: 'work_queue.chip.mentioned', params: {} }],
        }),
      ],
      weights: {
        weight_due: '0.4000',
        weight_value: '0.2500',
        weight_unresolved: '0.2500',
        weight_flags: '0.1000',
        vendor_rfq_queue_enabled: false,
      },
      generated_on: '2026-07-19',
    });
    await renderWithProviders(<DashboardPage />);

    expect(await screen.findByTestId('queue-org-badge')).toHaveTextContent('Helvetia AG');
    // The org switch is M5.12; the row says so rather than offering a dead link.
    expect(screen.queryByRole('link', { name: 'Öffnen' })).not.toBeInTheDocument();
  });

  it('shows the queue empty state', async () => {
    await renderWithProviders(<DashboardPage />);
    expect(await screen.findByText('Nichts offen — Ihre Warteschlange ist leer.')).toBeInTheDocument();
  });

  it('shows the Recently-opened strip when there is something to resume', async () => {
    getRecents.mockResolvedValue({
      rows: [
        {
          entity_type: 'quote',
          entity_id: 'q7',
          label: '1407',
          status: 'draft',
          deep_link: '/quotes/q7',
          opened_at: '2026-07-19T09:00:00Z',
        },
      ],
    });
    await renderWithProviders(<DashboardPage />);
    expect(await screen.findByTestId('recent-row')).toHaveTextContent('1407');
    expect(screen.getByRole('link', { name: /1407/ })).toHaveAttribute('href', '/quotes/q7');
  });

  it('keeps the queue up when the KPI call fails', async () => {
    // The KPI row is secondary and role-gated: its failure must not blank the
    // work queue behind a load error.
    getKpis.mockRejectedValue(new Error('403'));
    getQueue.mockResolvedValue({
      rows: [queueRow()],
      weights: {
        weight_due: '0.4000',
        weight_value: '0.2500',
        weight_unresolved: '0.2500',
        weight_flags: '0.1000',
        vendor_rfq_queue_enabled: false,
      },
      generated_on: '2026-07-19',
    });
    await renderWithProviders(<DashboardPage />, { me: makeMe({ roles: ['manager'] }) });

    expect(await screen.findByTestId('queue-row')).toBeInTheDocument();
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
    expect(screen.queryByTestId('kpi-open-quotes')).not.toBeInTheDocument();
  });

  it('links each urgency toggle to its own factor panel', async () => {
    getQueue.mockResolvedValue({
      rows: [queueRow()],
      weights: {
        weight_due: '0.4000',
        weight_value: '0.2500',
        weight_unresolved: '0.2500',
        weight_flags: '0.1000',
        vendor_rfq_queue_enabled: false,
      },
      generated_on: '2026-07-19',
    });
    await renderWithProviders(<DashboardPage />);

    const toggle = await screen.findByRole('button', { name: '0,20' });
    await userEvent.click(toggle);
    expect(toggle).toHaveAttribute('aria-controls', screen.getByTestId('queue-factors').id);
  });

  it('shows the KPI row for a manager and not for an estimator', async () => {
    const { unmount } = await renderWithProviders(<DashboardPage />);
    await screen.findByText('Nichts offen — Ihre Warteschlange ist leer.');
    expect(screen.queryByTestId('kpi-open-quotes')).not.toBeInTheDocument();
    expect(getKpis).not.toHaveBeenCalled();
    unmount();

    await renderWithProviders(<DashboardPage />, {
      me: makeMe({ roles: ['manager'] }),
    });
    expect(await screen.findByTestId('kpi-open-quotes')).toHaveTextContent('4');
    expect(screen.getByTestId('kpi-win-rate')).toHaveTextContent('50,0 %');
  });

  it('renders the email-ingest notification as a triage card with signals (M3.9)', async () => {
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
    await renderWithProviders(<DashboardPage />);
    expect(await screen.findByText('Keine Benachrichtigungen.')).toBeInTheDocument();
  });
});
