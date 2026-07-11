/**
 * Add-Ons + Lead Times + quote totals (M1.11, spec #addons / #dach-tax):
 * required toggle + price cells with the roll-up rows; per-break lead time
 * with expedite rows (days faster + % markup); the VAT panel in German
 * locale — Netto / MwSt. 19 % / Brutto as `1.234,56 €`.
 */

import { describe, expect, it, vi } from 'vitest';
import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { renderWithProviders } from '../test/render';
import { AddOnsSection } from './AddOnsSection';
import { LeadTimesSection } from './LeadTimesSection';
import { QuoteTotalsPanel } from './QuoteTotalsPanel';
import type { PricingSummary, QuoteTotals } from './types';

const noop = () => undefined;

const formatMoney = (value: string | null): string =>
  value == null
    ? '—'
    : new Intl.NumberFormat('de-DE', { style: 'currency', currency: 'EUR' }).format(Number(value));

function summary(): PricingSummary {
  return {
    component_id: 'c1',
    quantities: [1],
    costing: [],
    pricing_items: [],
    discounts: [],
    add_ons: [
      {
        id: 'ao-fai',
        source_def_id: null,
        name: 'First Article Inspection (FAI)',
        formula: null,
        default_price: '100.0000',
        default_is_required: true,
        calc_is_required: null,
        manual_is_required: null,
        is_required: true,
        position: 0,
        is_from_factory: false,
        cells: [{ quantity: 1, calc_price: '100.0000', manual_price: null, price: '100.0000' }],
      },
    ],
    lead_times: [
      {
        quantity: 1,
        calc_lead_time_days: 4,
        manual_lead_time_days: 10,
        lead_time_days: 10,
        expedites: [
          {
            id: 'ex-1',
            days_faster: 3,
            markup_pct: '10.000',
            lead_time_days: 7,
            unit_price: '1980.00',
            total_price: '1980.00',
          },
        ],
      },
    ],
    totals: [
      {
        quantity: 1,
        unit_cost: '1000.0000',
        total_excl_discounts: '2000.0000',
        calc_unit_price: '2000.00',
        manual_unit_price: null,
        unit_price: '1800.00',
        total_price: '1800.00',
        total_discount: '200.0000',
        total_discount_pct: '10.0000',
        total_profit: '800.0000',
        profit_margin_pct: '44.4400',
        total_required_add_ons: '100.0000',
        total_with_required_add_ons: '1900.0000',
      },
    ],
  };
}

describe('AddOnsSection', () => {
  it('renders the required toggle, the price cell, and the roll-up rows', async () => {
    await renderWithProviders(
      <AddOnsSection
        pricing={summary()}
        formatMoney={formatMoney}
        editable
        loadDefs={() => Promise.resolve([])}
        onAdd={noop}
        onRemove={noop}
        onToggleRequired={noop}
        onPriceOverride={noop}
      />,
    );
    expect(screen.getByText('First Article Inspection (FAI)')).toBeInTheDocument();
    expect(screen.getByText('Summe erforderliche Add-Ons')).toBeInTheDocument();
    // 1.900,00 € — the add-on lands AFTER the discount (1800 + 100)
    expect(screen.getByText('1.900,00 €')).toBeInTheDocument();
  });

  it('toggles required-ness via the manual override', async () => {
    const onToggle = vi.fn();
    await renderWithProviders(
      <AddOnsSection
        pricing={summary()}
        formatMoney={formatMoney}
        editable
        loadDefs={() => Promise.resolve([])}
        onAdd={noop}
        onRemove={noop}
        onToggleRequired={onToggle}
        onPriceOverride={noop}
      />,
    );
    await userEvent.click(
      screen.getByRole('button', {
        name: 'Erforderlich umschalten: First Article Inspection (FAI)',
      }),
    );
    expect(onToggle).toHaveBeenCalledWith('ao-fai', false);
  });
});

describe('LeadTimesSection', () => {
  it('shows the overridden lead time and the expedite row (days + marked-up price)', async () => {
    await renderWithProviders(
      <LeadTimesSection
        pricing={summary()}
        formatMoney={formatMoney}
        editable
        onLeadTimeOverride={noop}
        onSetExpediteOptions={noop}
        onApplyToAll={noop}
      />,
    );
    expect(screen.getByText(/10 Tage/)).toBeInTheDocument();
    expect(screen.getByText(/7 Tage/)).toBeInTheDocument();
    expect(screen.getByText(/1\.980,00 €/)).toBeInTheDocument();
  });
});

describe('QuoteTotalsPanel', () => {
  it('renders Netto / MwSt. / Brutto in German locale from minor units', async () => {
    const totals: QuoteTotals = {
      currency: 'EUR',
      country: 'DE',
      vat_label: 'MwSt.',
      vat_rate_pct: '19',
      items: [{ quote_item_id: 'qi1', component_id: 'c1', quantity: 1, net_minor: 210000 }],
      net_minor: 210000,
      vat_minor: 39900,
      gross_minor: 249900,
    };
    await renderWithProviders(<QuoteTotalsPanel totals={totals} />);
    expect(screen.getByText('Netto')).toBeInTheDocument();
    expect(screen.getByText('MwSt. (19 %)')).toBeInTheDocument();
    expect(screen.getByText('2.100,00 €')).toBeInTheDocument();
    expect(screen.getByText('399,00 €')).toBeInTheDocument();
    expect(screen.getByText('2.499,00 €')).toBeInTheDocument();
  });

  it('formats CHF with the de-CH convention', async () => {
    const totals: QuoteTotals = {
      currency: 'CHF',
      country: 'CH',
      vat_label: 'MWST',
      vat_rate_pct: '8.1',
      items: [],
      net_minor: 210000,
      vat_minor: 17010,
      gross_minor: 227010,
    };
    await renderWithProviders(<QuoteTotalsPanel totals={totals} />);
    expect(screen.getByText(/MWST \(8[.,]1 %\)/)).toBeInTheDocument();
    // de-CH money: CHF 2'100.00 (apostrophe thousands separator)
    expect(screen.getByText(/2['’]100\.00/)).toBeInTheDocument();
  });
});
