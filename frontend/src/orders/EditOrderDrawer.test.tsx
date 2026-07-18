import { beforeEach, describe, expect, it, vi } from 'vitest';
import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Route, Routes } from 'react-router-dom';

import { renderWithProviders } from '../test/render';
import { OrderDetailPage } from './OrderDetailPage';
import type { OrderDetail, OrderHistoryEvent } from './types';

const getOrder = vi.fn();
const getOrderHistory = vi.fn();
const editOrder = vi.fn();
const downloadOrderPdf = vi.fn();

vi.mock('./api', () => ({
  useOrdersApi: () => ({
    getOrder,
    getOrderHistory,
    editOrder,
    downloadOrderPdf,
    searchOrders: vi.fn(),
    pushToErp: vi.fn(),
    facilitateOrder: vi.fn(),
  }),
}));

function detail(extra: Partial<OrderDetail> = {}): OrderDetail {
  return {
    id: 'o-1',
    number: 'O-1',
    source: 'facilitated',
    quote_id: 'q-1',
    quote_number: 'Q-1',
    account_id: 'acc-1',
    account_name: 'Alpha GmbH',
    contact_id: 'c-1',
    contact_name: 'Eva Schmidt',
    po_number: 'PO-1',
    company_name: 'Alpha GmbH',
    billing_address: 'Alte Str. 1\n10115 Berlin',
    shipping_method: 'bill_at_shipment',
    notes: null,
    created_at: '2026-07-01T00:00:00Z',
    shipped_at: null,
    currency: 'EUR',
    net_minor: 100000,
    vat_minor: 19000,
    gross_minor: 119000,
    vat_rate_pct: 19,
    vat_label: 'MwSt',
    reverse_charge: false,
    kleinunternehmer: false,
    tax_note: null,
    supplier_ust_id_nr: null,
    buyer_ust_id_nr: null,
    tax_rate_lines: null,
    expected_ship_date: '2026-07-15',
    can_edit: true,
    lines: [
      {
        id: 'l-1',
        quote_item_id: 'qi-1',
        position: 1,
        part_label: 'ABC-123 Rev B',
        quantity: 10,
        unit_price_minor: 10000,
        total_price_minor: 100000,
        expedites_fee_minor: 0,
        lead_time_days: 10,
        ships_on: '2026-07-15',
        add_ons: null,
      },
    ],
    ...extra,
  };
}

const HISTORY: OrderHistoryEvent[] = [
  {
    id: 'h-1',
    kind: 'created',
    actor_user_id: 'u-1',
    changes: { lines: 1 },
    buyer_notified: false,
    created_at: '2026-07-01T00:00:00Z',
  },
];

async function renderDetail(route: string) {
  return renderWithProviders(
    <Routes>
      <Route path="/orders/:orderId" element={<OrderDetailPage />} />
    </Routes>,
    { route },
  );
}

describe('EditOrderDrawer', () => {
  beforeEach(() => {
    getOrder.mockReset().mockResolvedValue(detail());
    getOrderHistory.mockReset().mockResolvedValue(HISTORY);
    editOrder.mockReset().mockResolvedValue({
      order_id: 'o-1',
      changes: { po_number: ['PO-1', 'PO-2'] },
      buyer_notified: false,
      net_minor: 100000,
      vat_minor: 19000,
      gross_minor: 119000,
    });
    downloadOrderPdf.mockReset();
  });

  it('auto-opens on ?edit=1 and shows the created history entry', async () => {
    await renderDetail('/orders/o-1?edit=1');
    expect(await screen.findByRole('dialog', { name: 'Auftrag bearbeiten' })).toBeInTheDocument();
    expect(await screen.findByText('Auftrag erstellt')).toBeInTheDocument();
  });

  it('sends only the changed PO number and refetches on save', async () => {
    const user = userEvent.setup();
    await renderDetail('/orders/o-1?edit=1');
    await screen.findByRole('dialog', { name: 'Auftrag bearbeiten' });
    const beforeSave = getOrder.mock.calls.length;

    const poInput = screen.getByLabelText('Bestellnummer');
    await user.clear(poInput);
    await user.type(poInput, 'PO-2');
    await user.click(screen.getByRole('button', { name: 'Änderungen speichern' }));

    expect(editOrder).toHaveBeenCalledWith('o-1', { po_number: 'PO-2' });
    // onSaved bumps the reload key → the detail refetches.
    expect(getOrder.mock.calls.length).toBeGreaterThan(beforeSave);
  });

  it('records the notify-buyer intent when checked', async () => {
    const user = userEvent.setup();
    await renderDetail('/orders/o-1?edit=1');
    await screen.findByRole('dialog', { name: 'Auftrag bearbeiten' });

    const billing = screen.getByLabelText('Rechnungsadresse');
    await user.clear(billing);
    await user.type(billing, 'Neue Str. 5');
    await user.click(screen.getByLabelText('Käufer über die Änderung benachrichtigen'));
    await user.click(screen.getByRole('button', { name: 'Änderungen speichern' }));

    expect(editOrder).toHaveBeenCalledWith('o-1', {
      billing_address: 'Neue Str. 5',
      notify_buyer: true,
    });
  });

  it('blocks an empty edit with a no-changes message', async () => {
    const user = userEvent.setup();
    await renderDetail('/orders/o-1?edit=1');
    await screen.findByRole('dialog', { name: 'Auftrag bearbeiten' });

    await user.click(screen.getByRole('button', { name: 'Änderungen speichern' }));
    expect(editOrder).not.toHaveBeenCalled();
    expect(screen.getByText('Keine Änderungen vorgenommen.')).toBeInTheDocument();
  });
});
