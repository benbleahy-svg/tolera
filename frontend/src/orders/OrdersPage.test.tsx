import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { renderWithProviders } from '../test/render';
import { OrdersPage } from './OrdersPage';
import type { OrderRow, OrderSearchRequest } from './types';

const searchOrders = vi.fn();
const getOrder = vi.fn();
const downloadOrderPdf = vi.fn();
const pushToErp = vi.fn();
const listAccounts = vi.fn();

// Mock both APIs the page uses so it never touches Clerk/network.
vi.mock('./api', () => ({
  useOrdersApi: () => ({ searchOrders, getOrder, downloadOrderPdf, pushToErp }),
}));
vi.mock('../contacts/api', () => ({
  useCrmApi: () => ({ listAccounts }),
}));

const VIEWS = [
  { key: 'all-orders', label_key: 'orders.views.all', is_default: true },
  { key: 'buyer-portal', label_key: 'orders.views.buyer_portal', is_default: false },
  { key: 'facilitated', label_key: 'orders.views.facilitated', is_default: false },
  { key: 'awaiting-shipment', label_key: 'orders.views.awaiting_shipment', is_default: false },
];

function order(number: string, extra: Partial<OrderRow> = {}): OrderRow {
  return {
    id: `o-${number}`,
    number,
    quote_id: `q-${number}`,
    quote_number: `Q-${number}`,
    account_id: 'acc-1',
    account_name: 'Alpha GmbH',
    contact_name: 'Eva Schmidt',
    po_number: 'PO-4711',
    created_at: '2026-07-01T00:00:00Z',
    parts_count: 3,
    net_minor: 22500,
    currency: 'EUR',
    source: 'buyer_portal',
    expected_ship_date: '2026-07-15',
    shipped_at: null,
    can_edit: false,
    ...extra,
  };
}

function response(rows: OrderRow[]) {
  return { rows, total: rows.length, limit: 20, offset: 0, views: VIEWS };
}

describe('OrdersPage', () => {
  beforeEach(() => {
    searchOrders.mockReset();
    listAccounts.mockReset();
    downloadOrderPdf.mockReset();
    listAccounts.mockResolvedValue([{ id: 'acc-1', name: 'Alpha GmbH' }]);
    searchOrders.mockResolvedValue(response([order('O-1')]));
  });

  // Unconditional cleanup: a test that fails mid-way must not leak a stubbed
  // global (e.g. URL) into later tests.
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('renders the spec columns incl. NET total, source chip and parts', async () => {
    await renderWithProviders(<OrdersPage />);

    // Order # links to detail; Quote # links to the source quote.
    const link = await screen.findByRole('link', { name: 'O-1' });
    expect(link).toHaveAttribute('href', '/orders/o-O-1');
    expect(screen.getByRole('link', { name: 'Q-O-1' })).toHaveAttribute(
      'href',
      '/quotes/edit/q-O-1',
    );
    // Scope to the grid — "Alpha GmbH" / "Käuferportal" also appear in the
    // Account dropdown / view tabs, so assert them inside the table.
    const grid = within(screen.getByRole('table'));
    expect(grid.getByText('Alpha GmbH')).toBeInTheDocument();
    expect(grid.getByText('Eva Schmidt')).toBeInTheDocument();
    expect(grid.getByText('PO-4711')).toBeInTheDocument();
    expect(grid.getByText('3')).toBeInTheDocument(); // parts count
    // Order Total is NET (225,00 €), German locale minor-unit formatting.
    expect(grid.getByText('225,00 €')).toBeInTheDocument();
    // Source chip (German-first): buyer_portal → Käuferportal.
    expect(grid.getByText('Käuferportal')).toBeInTheDocument();
  });

  it('has NO create-order button', async () => {
    await renderWithProviders(<OrdersPage />);
    await screen.findByRole('link', { name: 'O-1' });
    expect(
      screen.queryByRole('button', { name: /auftrag erstellen|create order/i }),
    ).not.toBeInTheDocument();
  });

  it('a view tab issues a system_view search', async () => {
    const user = userEvent.setup();
    await renderWithProviders(<OrdersPage />);
    await screen.findByRole('link', { name: 'O-1' });

    await user.click(screen.getByRole('button', { name: 'Käuferportal' }));
    await waitFor(() => {
      const last = searchOrders.mock.calls.at(-1)![0] as OrderSearchRequest;
      expect(last.system_view).toBe('buyer-portal');
    });
  });

  it('the search box composes a free-text search', async () => {
    const user = userEvent.setup();
    await renderWithProviders(<OrdersPage />);
    await screen.findByRole('link', { name: 'O-1' });

    await user.type(screen.getByRole('searchbox'), 'PO-99');
    await waitFor(() => {
      const last = searchOrders.mock.calls.at(-1)![0] as OrderSearchRequest;
      expect(last.search).toBe('PO-99');
    });
  });

  it('the Account filter narrows by account_id (adhoc filter)', async () => {
    const user = userEvent.setup();
    await renderWithProviders(<OrdersPage />);
    await screen.findByRole('link', { name: 'O-1' });

    await user.selectOptions(screen.getByRole('combobox', { name: /kunde/i }), 'acc-1');
    await waitFor(() => {
      const last = searchOrders.mock.calls.at(-1)![0] as OrderSearchRequest;
      expect(last.filters).toEqual([{ field: 'account_id', op: 'eq', value: 'acc-1' }]);
      expect(last.system_view).toBeUndefined();
    });
  });

  it('offers the Edit action only when the order is editable', async () => {
    const user = userEvent.setup();
    searchOrders.mockResolvedValue(
      response([order('O-1', { can_edit: false }), order('O-2', { can_edit: true, id: 'o-O-2' })]),
    );
    await renderWithProviders(<OrdersPage />);
    await screen.findByRole('link', { name: 'O-1' });

    const menus = screen.getAllByText('⋮');
    // Row 1 (not editable): open its menu → no Edit action.
    await user.click(menus[0]);
    expect(within(menus[0].closest('details')!).queryByText('Auftrag bearbeiten')).toBeNull();
    // Row 2 (editable): Edit action present.
    await user.click(menus[1]);
    expect(
      within(menus[1].closest('details')!).getByText('Auftrag bearbeiten'),
    ).toBeInTheDocument();
  });

  it('Download order PDF triggers a blob download', async () => {
    const user = userEvent.setup();
    downloadOrderPdf.mockResolvedValue(new Blob(['%PDF-'], { type: 'application/pdf' }));
    // jsdom lacks URL.createObjectURL — stub it.
    const createURL = vi.fn(() => 'blob:x');
    const revokeURL = vi.fn();
    vi.stubGlobal('URL', { ...URL, createObjectURL: createURL, revokeObjectURL: revokeURL });
    await renderWithProviders(<OrdersPage />);
    await screen.findByRole('link', { name: 'O-1' });

    await user.click(screen.getAllByText('⋮')[0]);
    await user.click(screen.getByText('Auftrags-PDF herunterladen'));
    await waitFor(() => expect(downloadOrderPdf).toHaveBeenCalledWith('o-O-1'));
  });

  it('shows the empty state when there are no orders', async () => {
    searchOrders.mockResolvedValue(response([]));
    await renderWithProviders(<OrdersPage />);
    expect(await screen.findByText('Keine Aufträge gefunden.')).toBeInTheDocument();
  });
});
