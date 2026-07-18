import { beforeEach, describe, expect, it, vi } from 'vitest';
import { screen, within } from '@testing-library/react';
import { Route, Routes } from 'react-router-dom';

import { renderWithProviders } from '../test/render';
import { OrderDetailPage } from './OrderDetailPage';
import type { OrderDetail } from './types';

const getOrder = vi.fn();
const downloadOrderPdf = vi.fn();

vi.mock('./api', () => ({
  useOrdersApi: () => ({ getOrder, downloadOrderPdf, searchOrders: vi.fn(), pushToErp: vi.fn() }),
}));

function detail(extra: Partial<OrderDetail> = {}): OrderDetail {
  return {
    id: 'o-1',
    number: 'O-1',
    source: 'buyer_portal',
    quote_id: 'q-1',
    quote_number: 'Q-1',
    account_id: 'acc-1',
    account_name: 'Alpha GmbH',
    contact_id: 'c-1',
    contact_name: 'Eva Schmidt',
    po_number: 'PO-1',
    company_name: 'Alpha GmbH',
    billing_address: null,
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
    can_edit: false,
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

async function render(order: OrderDetail) {
  getOrder.mockResolvedValue(order);
  return renderWithProviders(
    <Routes>
      <Route path="/orders/:orderId" element={<OrderDetailPage />} />
    </Routes>,
    { route: '/orders/o-1' },
  );
}

describe('OrderDetailPage', () => {
  beforeEach(() => {
    getOrder.mockReset();
    downloadOrderPdf.mockReset();
  });

  it('renders the part label + net→VAT→gross for a plain domestic order', async () => {
    await render(detail());
    expect(await screen.findByText('ABC-123 Rev B')).toBeInTheDocument();
    // Single aggregate VAT line at 19% (no persisted breakdown).
    expect(screen.getByText(/MwSt\. \(19/)).toBeInTheDocument();
  });

  it('renders every persisted rate line for a mixed-rate order', async () => {
    await render(
      detail({
        net_minor: 30000,
        vat_minor: 3990,
        gross_minor: 33990,
        tax_rate_lines: [
          { rate_pct: 19, net_minor: 20000, vat_minor: 3800 },
          { rate_pct: 7, net_minor: 10000, vat_minor: 700 },
        ],
      }),
    );
    await screen.findByText('ABC-123 Rev B');
    const totals = screen.getByText(/Gesamtbetrag/).closest('dl')!;
    // Both §14 rate lines are shown, not a single aggregate.
    expect(within(totals).getByText(/MwSt\. \(19/)).toBeInTheDocument();
    expect(within(totals).getByText(/MwSt\. \(7/)).toBeInTheDocument();
  });

  it('shows the reverse-charge note instead of a VAT line', async () => {
    await render(
      detail({
        vat_minor: 0,
        gross_minor: 100000,
        reverse_charge: true,
        tax_note: 'Steuerschuldnerschaft des Leistungsempfängers',
      }),
    );
    await screen.findByText('ABC-123 Rev B');
    expect(
      screen.getByText('Steuerschuldnerschaft des Leistungsempfängers'),
    ).toBeInTheDocument();
    expect(screen.queryByText(/MwSt\. \(/)).not.toBeInTheDocument();
  });

  it('falls back to the line position when a part has no label', async () => {
    const d = detail();
    d.lines[0].part_label = null;
    await render(d);
    expect(await screen.findByText('Position 1')).toBeInTheDocument();
  });
});
