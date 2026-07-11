/**
 * PricingSection (M1.10): the Costing table with custom colored rows, the
 * Pricing stack with %-over-amount cells + click-to-override, the target-margin
 * unreachable badge, discounts, and the output totals — rendered to the DemoE
 * frame layout, German-first.
 */

import { describe, expect, it, vi } from 'vitest';
import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { renderWithProviders } from '../test/render';
import { PricingSection } from './PricingSection';
import type { PricingSummary } from './types';

const noop = () => undefined;

function summary(): PricingSummary {
  const cell = (over: Partial<PricingSummary['pricing_items'][0]['cells'][0]> = {}) => ({
    quantity: 1,
    calc_pct: '60.0000',
    manual_pct: null,
    pct: '60.0000',
    calc_profit: '404.5248',
    manual_profit: null,
    amount: '404.5248',
    calc_custom_cost: null,
    unreachable: false,
    ...over,
  });
  return {
    component_id: 'c1',
    quantities: [1],
    costing: [
      {
        quantity: 1,
        material: '674.2080',
        inside: '1019.8000',
        outside: '0.0000',
        purchased_component: '8.3700',
        child_override: '0.0000',
        total: '1702.3780',
        unit_cost: '1702.3780',
        custom_rows: [
          {
            pricing_item_id: 'pi-diff',
            name: 'Difficult Material',
            color: '#8b1e3f',
            cost: '539.3680',
          },
        ],
      },
    ],
    pricing_items: [
      {
        id: 'pi-raw',
        source_def_id: null,
        name: 'Raw Material Markup',
        calc_type: 'markup',
        category: 'material',
        is_custom: false,
        custom_category_name: null,
        color: null,
        formula: null,
        default_pct: '60',
        position: 0,
        is_from_factory: false,
        cells: [cell()],
      },
      {
        id: 'pi-diff',
        source_def_id: null,
        name: 'Difficult Material Markup',
        calc_type: 'markup',
        category: 'general',
        is_custom: true,
        custom_category_name: 'Difficult Material',
        color: '#8b1e3f',
        formula: 'set_custom_cost(0)\nPERCENTAGE = 10',
        default_pct: null,
        position: 1,
        is_from_factory: false,
        cells: [
          cell({ calc_pct: '10.0000', pct: '10.0000', calc_profit: '53.9368', amount: '53.9368' }),
        ],
      },
      {
        id: 'pi-target',
        source_def_id: null,
        name: 'Zielmarge',
        calc_type: 'target_margin',
        category: 'general',
        is_custom: false,
        custom_category_name: null,
        color: null,
        formula: null,
        default_pct: '5',
        position: 2,
        is_from_factory: false,
        cells: [
          cell({
            calc_pct: '5.0000',
            pct: '5.0000',
            calc_profit: '0.0000',
            amount: '0.0000',
            unreachable: true,
          }),
        ],
      },
    ],
    discounts: [
      {
        id: 'd-1',
        source_def_id: null,
        name: 'Treuerabatt',
        formula: null,
        default_pct: '5',
        position: 0,
        is_from_factory: false,
        cells: [{ quantity: 1, calc_pct: '5.0000', manual_pct: null, pct: '5.0000' }],
      },
    ],
    add_ons: [],
    lead_times: [],
    totals: [
      {
        quantity: 1,
        unit_cost: '1702.3780',
        total_excl_discounts: '2160.8396',
        calc_unit_price: '2160.84',
        manual_unit_price: null,
        unit_price: '2052.80',
        total_price: '2052.80',
        total_discount: '108.0400',
        total_discount_pct: '5.0000',
        total_profit: '350.4220',
        profit_margin_pct: '17.0704',
        total_required_add_ons: '0.0000',
        total_with_required_add_ons: null,
      },
    ],
  };
}

function renderSection(overrides: Partial<Parameters<typeof PricingSection>[0]> = {}) {
  return renderWithProviders(
    <PricingSection
      pricing={summary()}
      formatMoney={(v) => (v == null ? '—' : `${Number(v).toFixed(2)} €`)}
      editable
      onAddItem={noop}
      onRemoveItem={noop}
      onItemPctOverride={noop}
      onAddDiscount={noop}
      onRemoveDiscount={noop}
      onDiscountPctOverride={noop}
      onUnitPriceOverride={noop}
      {...overrides}
    />,
  );
}

describe('PricingSection', () => {
  it('renders the five categories, total, and the custom colored row (DemoE 07)', async () => {
    await renderSection();
    expect(screen.getByText('Rohmaterial gesamt')).toBeInTheDocument();
    expect(screen.getByText('Kaufteile gesamt')).toBeInTheDocument();
    expect(screen.getByText('Kalkulierte Gesamtkosten')).toBeInTheDocument();
    // the custom category shows as its own costing row + chip
    expect(screen.getAllByText('Difficult Material').length).toBeGreaterThan(1);
    // qty 1: total and per-unit coincide — both cells show the figure
    expect(screen.getAllByText('539.37 €').length).toBeGreaterThan(0);
    expect(screen.getAllByText('1702.38 €').length).toBeGreaterThan(0);
  });

  it('shows pricing items as % over amount and totals excl./incl. discounts', async () => {
    await renderSection();
    expect(screen.getByText('Raw Material Markup')).toBeInTheDocument();
    expect(screen.getByText('60,00 %')).toBeInTheDocument();
    expect(screen.getByText('404.52 €')).toBeInTheDocument();
    expect(screen.getByText('Gesamt (ohne Rabatte)')).toBeInTheDocument();
    // discounted output rows
    expect(screen.getByText('Treuerabatt')).toBeInTheDocument();
    expect(screen.getAllByText('2052.80 €').length).toBeGreaterThan(0);
  });

  it('flags an unreachable target margin', async () => {
    await renderSection();
    expect(screen.getByText('nicht erreichbar')).toBeInTheDocument();
  });

  it('overrides a pricing-item % through the cell input', async () => {
    const onItemPctOverride = vi.fn();
    await renderSection({ onItemPctOverride });
    await userEvent.click(
      screen.getByRole('button', {
        name: 'Prozentsatz-Override für Raw Material Markup, Losgröße 1',
      }),
    );
    const input = screen.getByRole('textbox', {
      name: 'Prozentsatz-Override für Raw Material Markup, Losgröße 1',
    });
    await userEvent.clear(input);
    await userEvent.type(input, '65{Enter}');
    expect(onItemPctOverride).toHaveBeenCalledWith('pi-raw', 1, '65');
  });

  it('creates a custom pricing item through the modal', async () => {
    const onAddItem = vi.fn();
    await renderSection({ onAddItem });
    await userEvent.click(screen.getByRole('button', { name: 'PREISPOSITION HINZUFÜGEN' }));
    await userEvent.type(screen.getByLabelText('Name'), 'Laser Markup');
    await userEvent.selectOptions(screen.getByLabelText('Kostenkategorie'), 'custom');
    await userEvent.type(screen.getByLabelText('Kategoriename'), 'Laser Workcenter');
    await userEvent.type(
      screen.getByLabelText('Kalk-Formel (set_custom_cost)'),
      'set_custom_cost(0)',
    );
    await userEvent.type(screen.getByLabelText('Prozentsatz (%)'), '10');
    await userEvent.click(screen.getByRole('button', { name: 'Hinzufügen' }));
    expect(onAddItem).toHaveBeenCalledWith(
      expect.objectContaining({
        name: 'Laser Markup',
        calc_type: 'markup',
        is_custom: true,
        custom_category_name: 'Laser Workcenter',
        default_pct: '10',
      }),
    );
  });

  it('overrides a discount % through the cell input (Greptile finding)', async () => {
    const onDiscountPctOverride = vi.fn();
    await renderSection({ onDiscountPctOverride });
    await userEvent.click(
      screen.getByRole('button', { name: 'Rabatt-Override für Treuerabatt, Losgröße 1' }),
    );
    const input = screen.getByRole('textbox', {
      name: 'Rabatt-Override für Treuerabatt, Losgröße 1',
    });
    await userEvent.clear(input);
    await userEvent.type(input, '7,5{Enter}');
    expect(onDiscountPctOverride).toHaveBeenCalledWith('d-1', 1, '7.5');
  });

  it('disables mutation affordances when not editable', async () => {
    await renderSection({ editable: false });
    expect(screen.getByRole('button', { name: 'PREISPOSITION HINZUFÜGEN' })).toBeDisabled();
    expect(
      screen.getByRole('button', {
        name: 'Prozentsatz-Override für Raw Material Markup, Losgröße 1',
      }),
    ).toBeDisabled();
  });
});
