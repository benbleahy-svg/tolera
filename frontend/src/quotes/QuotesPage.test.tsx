import { beforeEach, describe, expect, it, vi } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { makeMe, renderWithProviders } from '../test/render';
import { QuotesPage } from './QuotesPage';
import type { QuoteSearchRequest } from './types';

const searchQuotes = vi.fn();
const listSavedViews = vi.fn();
const createSavedView = vi.fn();
const updateSavedView = vi.fn();
const deleteSavedView = vi.fn();

// Mock the quotes API module so the page never touches Clerk/network.
vi.mock('./api', () => ({
  useQuotesApi: () => ({
    searchQuotes,
    listSavedViews,
    createSavedView,
    updateSavedView,
    deleteSavedView,
  }),
}));

const SYSTEM = [
  { key: 'all-quotes', label_key: 'quotes.views.all', is_default: true },
  { key: 'my-quotes', label_key: 'quotes.views.mine', is_default: false },
];

function quote(number: string, status = 'draft', extra: Record<string, unknown> = {}) {
  return {
    id: `q-${number}`,
    number,
    status,
    account_id: null,
    salesperson_id: null,
    estimator_id: null,
    rfq_number: null,
    due_date: null,
    created_at: '2026-06-25T00:00:00Z',
    ...extra,
  };
}

function savedView(name: string, filters: unknown[] = []) {
  return {
    id: `v-${name}`,
    owner_id: 'u1',
    view_scope: 'quotes',
    name,
    filters,
    sort: [],
    visibility: 'private',
    created_at: '2026-06-25T00:00:00Z',
    updated_at: '2026-06-25T00:00:00Z',
  };
}

describe('QuotesPage', () => {
  beforeEach(() => {
    searchQuotes.mockReset();
    listSavedViews.mockReset();
    createSavedView.mockReset();
    deleteSavedView.mockReset();
    listSavedViews.mockResolvedValue({ system: SYSTEM, custom: [] });
    searchQuotes.mockResolvedValue({ rows: [], total: 0, limit: 20, offset: 0 });
  });

  it('lists quotes returned by the search', async () => {
    searchQuotes.mockResolvedValue({
      rows: [quote('Q-1'), quote('Q-2')],
      total: 2,
      limit: 20,
      offset: 0,
    });
    await renderWithProviders(<QuotesPage />, { route: '/quotes' });

    expect(await screen.findByText('Q-1')).toBeInTheDocument();
    expect(screen.getByText('Q-2')).toBeInTheDocument();
  });

  it('narrows rows when a status filter is applied', async () => {
    const all = [quote('Q-1', 'draft'), quote('Q-2', 'sent')];
    searchQuotes.mockImplementation((req: QuoteSearchRequest) => {
      const status = req.filters?.[0]?.value;
      const rows = status ? all.filter((q) => q.status === status) : all;
      return Promise.resolve({ rows, total: rows.length, limit: 20, offset: 0 });
    });
    await renderWithProviders(<QuotesPage />, { route: '/quotes' });
    expect(await screen.findByText('Q-2')).toBeInTheDocument();

    await userEvent.selectOptions(screen.getByLabelText('Status'), 'draft');

    await waitFor(() => expect(screen.queryByText('Q-2')).not.toBeInTheDocument());
    expect(screen.getByText('Q-1')).toBeInTheDocument();
    expect(searchQuotes).toHaveBeenLastCalledWith(
      expect.objectContaining({ filters: [{ field: 'status', op: 'eq', value: 'draft' }] }),
    );
  });

  it('saves the current filters as a named view that then appears in the sidebar', async () => {
    listSavedViews
      .mockResolvedValueOnce({ system: SYSTEM, custom: [] }) // initial load
      .mockResolvedValue({ system: SYSTEM, custom: [savedView('My drafts')] }); // after save
    createSavedView.mockResolvedValue(savedView('My drafts'));
    await renderWithProviders(<QuotesPage />, { route: '/quotes' });

    await userEvent.click(await screen.findByRole('button', { name: 'Ansicht speichern' }));
    await userEvent.type(screen.getByLabelText('Name der Ansicht'), 'My drafts');
    await userEvent.click(screen.getByRole('button', { name: 'Speichern' }));

    expect(createSavedView).toHaveBeenCalledWith({ name: 'My drafts', filters: [], sort: [] });
    // Reload (listSavedViews refetch) surfaces the new view in the sidebar.
    expect(await screen.findByRole('button', { name: 'My drafts' })).toBeInTheDocument();
  });

  it('shows Create Quote only to an editor', async () => {
    await renderWithProviders(<QuotesPage />); // default makeMe = estimator (quote_edit)
    expect(await screen.findByText('Angebot erstellen')).toBeInTheDocument();
  });

  it('hides Create Quote without quote_edit', async () => {
    await renderWithProviders(<QuotesPage />, {
      me: makeMe({ effective_permissions: ['view_all'], roles: ['viewer'] }),
    });
    // A view-only user still sees the sidebar default, but not the create action.
    expect(await screen.findByRole('button', { name: 'Alle Angebote' })).toBeInTheDocument();
    expect(screen.queryByText('Angebot erstellen')).not.toBeInTheDocument();
  });
});
