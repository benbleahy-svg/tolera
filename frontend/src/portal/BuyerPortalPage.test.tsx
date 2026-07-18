/**
 * Buyer portal (M5.1): the public Digital Quote page — qty×lead-time radio grid
 * with expedite tiers, live NET order-summary, soft-expiry EXPIRED badge (still
 * selectable), and No-Quote lines. The api module is mocked wholesale (no auth).
 */

import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { I18nextProvider } from 'react-i18next';
import { MemoryRouter, Route, Routes } from 'react-router-dom';

import i18n from '../i18n';
import { BuyerPortalPage } from './BuyerPortalPage';
import { fetchBuyerQuote } from './api';
import type { BuyerLineItem, BuyerQuote } from './types';

vi.mock('./api');

const mockFetch = vi.mocked(fetchBuyerQuote);

function priced(): BuyerLineItem {
  return {
    quote_item_id: 'li-1',
    position: 1,
    is_no_quote: false,
    has_model: true,
    part_number: 'PN-1000',
    revision: 'B',
    description: 'Halterung',
    process: 'CNC-Fräsen',
    material: 'Aluminium',
    werkstoffnummer: '3.3547',
    dimensions: { x: '120.0', y: '80.0', z: '15.0' },
    dfm_warnings: ['Dünne Wandstärke'],
    breaks: [
      {
        quantity: 1,
        unit_price: '200.0000',
        total_price: '200.0000',
        lead_time_days: 15,
        expedites: [
          {
            id: 'x-1',
            days_faster: 5,
            lead_time_days: 10,
            unit_price: '260.0000',
            total_price: '260.0000',
            unit_surcharge: '60.0000',
          },
        ],
      },
      {
        quantity: 10,
        unit_price: '150.0000',
        total_price: '1500.0000',
        lead_time_days: 20,
        expedites: [
          {
            id: 'x-2',
            days_faster: 7,
            lead_time_days: 13,
            unit_price: '170.0000',
            total_price: '1700.0000',
            unit_surcharge: '20.0000',
          },
        ],
      },
    ],
    add_ons: [
      {
        id: 'a-1',
        display_name: 'Eloxieren',
        is_required: false,
        prices: [
          { quantity: 1, price: '25.0000' },
          { quantity: 10, price: '200.0000' },
        ],
      },
      {
        id: 'a-2',
        display_name: 'Erstmusterprüfbericht',
        is_required: true,
        prices: [
          { quantity: 1, price: '80.0000' },
          { quantity: 10, price: '80.0000' },
        ],
      },
    ],
  };
}

function noQuote(): BuyerLineItem {
  return {
    quote_item_id: 'li-nq',
    position: 2,
    is_no_quote: true,
    has_model: false,
    part_number: 'PN-2000',
  };
}

function makeQuote(over: Partial<BuyerQuote> = {}): BuyerQuote {
  return {
    quote_number: 'Q-2026-001',
    rfq_number: 'RFQ-77',
    currency: 'EUR',
    expiration_date: '2026-08-01T00:00:00Z',
    is_expired: false,
    requotes_enabled: true,
    shop: { name: 'Fechner GmbH', slug: 'fechner', country: 'DE', currency: 'EUR', locale: 'de-DE' },
    price_range: { min_unit: '150.0000', max_unit: '260.0000' },
    line_items: [priced()],
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

describe('BuyerPortalPage', () => {
  beforeEach(async () => {
    await i18n.changeLanguage('de');
    mockFetch.mockReset();
  });

  it('renders the shop, part identity, and one radio per break + expedite row', async () => {
    mockFetch.mockResolvedValue(makeQuote());
    renderPortal();

    expect(await screen.findByText('Fechner GmbH')).toBeInTheDocument();
    expect(screen.getByText('PN-1000')).toBeInTheDocument();
    expect(screen.getByText('CNC-Fräsen')).toBeInTheDocument();
    // 2 breaks + 2 expedite sub-rows
    expect(screen.getAllByRole('radio')).toHaveLength(4);
  });

  it('updates the order-summary net subtotal live when a break is selected', async () => {
    mockFetch.mockResolvedValue(makeQuote());
    renderPortal();

    await screen.findByText('Fechner GmbH');
    const summary = screen.getByRole('complementary', { name: 'Bestellübersicht' });
    // nothing chosen yet
    expect(within(summary).getByText(/Wählen Sie eine Option/)).toBeInTheDocument();

    await userEvent.click(screen.getByRole('radio', { name: 'Menge 1 wählen' }));

    // break total 200,00 € + required add-on 80,00 € = 280,00 € (net)
    expect(within(summary).getByText('280,00 €')).toBeInTheDocument();
  });

  it('shows the expedite surcharge delta over standard', async () => {
    mockFetch.mockResolvedValue(makeQuote());
    renderPortal();

    await screen.findByText('Fechner GmbH');
    expect(screen.getByText('+ 60,00 € / Stk.')).toBeInTheDocument();
  });

  it('shows the EXPIRED badge yet keeps the break radios enabled (soft expiry)', async () => {
    mockFetch.mockResolvedValue(makeQuote({ is_expired: true }));
    renderPortal();

    expect(await screen.findByText('ABGELAUFEN')).toBeInTheDocument();
    expect(screen.getByRole('radio', { name: 'Menge 1 wählen' })).not.toBeDisabled();
  });

  it('renders a No-Quote line with contact copy and no radio grid', async () => {
    mockFetch.mockResolvedValue(makeQuote({ line_items: [noQuote()] }));
    renderPortal();

    expect(
      await screen.findByText('Kein Angebot — bitte kontaktieren Sie uns'),
    ).toBeInTheDocument();
    expect(screen.queryAllByRole('radio')).toHaveLength(0);
  });

  it('shows an invalid-link message when the fetch fails (401)', async () => {
    mockFetch.mockRejectedValue(new Error('unauthorized'));
    renderPortal();

    expect(await screen.findByText('Dieser Angebotslink ist nicht gültig.')).toBeInTheDocument();
  });
});
