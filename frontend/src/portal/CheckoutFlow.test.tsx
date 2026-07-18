/**
 * Checkout flow (M5.2): drive the PO wizard end-to-end from the buyer portal —
 * select a line, Company & PO → Shipping → Review → place order → Confirmation.
 * The api module is mocked wholesale; the confirmation shows the server's
 * authoritative VAT breakdown (never computed client-side).
 */

import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { I18nextProvider } from 'react-i18next';
import { MemoryRouter, Route, Routes } from 'react-router-dom';

import i18n from '../i18n';
import { BuyerPortalPage } from './BuyerPortalPage';
import { fetchBuyerQuote, submitCheckout } from './api';
import type { BuyerQuote, CheckoutResult } from './types';

vi.mock('./api');

const mockFetch = vi.mocked(fetchBuyerQuote);
const mockCheckout = vi.mocked(submitCheckout);

function makeQuote(over: Partial<BuyerQuote> = {}): BuyerQuote {
  return {
    quote_number: 'Q-2026-001',
    rfq_number: null,
    currency: 'EUR',
    expiration_date: null,
    is_expired: false,
    requotes_enabled: false,
    shop: { name: 'Fechner GmbH', slug: 'fechner', country: 'DE', currency: 'EUR', locale: 'de-DE' },
    price_range: { min_unit: '200.0000', max_unit: '200.0000' },
    line_items: [
      {
        quote_item_id: 'li-1',
        position: 0,
        is_no_quote: false,
        has_model: false,
        part_number: 'PN-1000',
        breaks: [
          { quantity: 1, unit_price: '200.0000', total_price: '200.0000', lead_time_days: 10, expedites: [] },
        ],
        add_ons: [
          { id: 'a-req', display_name: 'Zertifikat', is_required: true, prices: [{ quantity: 1, price: '80.0000' }] },
        ],
      },
    ],
    ...over,
  };
}

function result(over: Partial<CheckoutResult> = {}): CheckoutResult {
  return {
    order_id: 'ord-1',
    order_number: '1',
    currency: 'EUR',
    net_minor: 28000,
    vat_minor: 5320,
    gross_minor: 33320,
    vat_rate_pct: '19',
    vat_label: 'MwSt.',
    reverse_charge: false,
    kleinunternehmer: false,
    tax_note: null,
    po_number: 'PO-4711',
    shipping_method: 'bill_at_shipment',
    lines: [],
    ...over,
  };
}

function renderPortal() {
  return render(
    <I18nextProvider i18n={i18n}>
      <MemoryRouter initialEntries={['/q/test-token']}>
        <Routes>
          <Route path="/q/:token" element={<BuyerPortalPage />} />
        </Routes>
      </MemoryRouter>
    </I18nextProvider>,
  );
}

async function selectAndProceed() {
  await screen.findByText('Fechner GmbH');
  await userEvent.click(screen.getByRole('radio', { name: 'Menge 1 wählen' }));
  await userEvent.click(screen.getByRole('button', { name: 'Zur Bestellung' }));
}

describe('CheckoutFlow', () => {
  beforeEach(async () => {
    await i18n.changeLanguage('de');
    mockFetch.mockReset();
    mockCheckout.mockReset();
  });

  it('drives the PO wizard to a confirmation with the server VAT breakdown', async () => {
    mockFetch.mockResolvedValue(makeQuote());
    mockCheckout.mockResolvedValue(result());
    renderPortal();

    await selectAndProceed();

    // Step 1 — Company & PO
    await userEvent.type(screen.getByLabelText(/Bestellnummer/), 'PO-4711');
    await userEvent.click(screen.getByRole('button', { name: 'Weiter' }));
    // Step 2 — Shipping
    await userEvent.click(screen.getByRole('button', { name: 'Weiter' }));
    // Step 3 — Review → place order
    await userEvent.click(screen.getByRole('button', { name: 'Bestellung aufgeben' }));

    // Step 4 — Confirmation with the authoritative totals
    expect(await screen.findByText('Vielen Dank für Ihre Bestellung')).toBeInTheDocument();
    expect(screen.getByText('Bestellung #1')).toBeInTheDocument();
    expect(screen.getByText('333,20 €')).toBeInTheDocument(); // gross

    // The request carried IDs + quantity + PO only (server re-derives prices).
    expect(mockCheckout).toHaveBeenCalledTimes(1);
    const [, req] = mockCheckout.mock.calls[0];
    expect(req.po_number).toBe('PO-4711');
    expect(req.selections).toEqual([{ quote_item_id: 'li-1', quantity: 1 }]);
    expect(req.shipping_method).toBe('bill_at_shipment');
  });

  it('shows the reverse-charge note instead of a VAT line', async () => {
    mockFetch.mockResolvedValue(makeQuote());
    mockCheckout.mockResolvedValue(
      result({
        reverse_charge: true,
        vat_minor: 0,
        gross_minor: 28000,
        vat_rate_pct: '0',
        tax_note: 'Steuerschuldnerschaft des Leistungsempfängers',
      }),
    );
    renderPortal();

    await selectAndProceed();
    await userEvent.type(screen.getByLabelText(/Bestellnummer/), 'PO-RC');
    await userEvent.type(screen.getByLabelText(/USt-IdNr/), 'ATU12345678');
    await userEvent.click(screen.getByRole('button', { name: 'Weiter' }));
    await userEvent.click(screen.getByRole('button', { name: 'Weiter' }));
    await userEvent.click(screen.getByRole('button', { name: 'Bestellung aufgeben' }));

    expect(
      await screen.findByText('Steuerschuldnerschaft des Leistungsempfängers'),
    ).toBeInTheDocument();
    // buyer VAT-ID forwarded to the server
    const [, req] = mockCheckout.mock.calls[0];
    expect(req.buyer_ust_id_nr).toBe('ATU12345678');
  });

  it('disables the checkout CTA on a soft-expired quote', async () => {
    mockFetch.mockResolvedValue(makeQuote({ is_expired: true }));
    renderPortal();

    await screen.findByText('Fechner GmbH');
    await userEvent.click(screen.getByRole('radio', { name: 'Menge 1 wählen' }));
    expect(screen.getByRole('button', { name: 'Zur Bestellung' })).toBeDisabled();
  });
});
