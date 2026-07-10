import { beforeEach, describe, expect, it, vi } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Route, Routes } from 'react-router-dom';

import { renderWithProviders } from '../test/render';
import { EstimatingPage } from './EstimatingPage';
import type { ComponentCosting, OperationOut, QuoteCellOut } from './types';

const getQuote = vi.fn();
const getCosting = vi.fn();
const materialTree = vi.fn();
const searchMaterials = vi.fn();
const updateMaterial = vi.fn();
const listProcesses = vi.fn();
const listOperationDefs = vi.fn();
const setComponentMaterial = vi.fn();
const setComponentProcess = vi.fn();
const addOperation = vi.fn();
const updateOperation = vi.fn();
const duplicateOperation = vi.fn();
const removeOperation = vi.fn();
const reorderOperations = vi.fn();
const setCellOverride = vi.fn();
const kalkCheck = vi.fn();
const getKalkReport = vi.fn().mockResolvedValue([]);
const setVariableOverrides = vi.fn();
const getPricing = vi.fn();
const addPricingItem = vi.fn();
const removePricingItem = vi.fn();
const setPricingItemPct = vi.fn();
const addDiscount = vi.fn();
const removeDiscount = vi.fn();
const setDiscountPct = vi.fn();
const setUnitPriceOverride = vi.fn();
const refreshPricing = vi.fn();

// Mock the estimating API module so the page never touches Clerk/network.
vi.mock('./api', () => ({
  useEstimatingApi: () => ({
    getQuote,
    getCosting,
    materialTree,
    searchMaterials,
    updateMaterial,
    listProcesses,
    listOperationDefs,
    setComponentMaterial,
    setComponentProcess,
    addOperation,
    updateOperation,
    duplicateOperation,
    removeOperation,
    reorderOperations,
    setCellOverride,
    kalkCheck,
    getKalkReport,
    setVariableOverrides,
    getPricing,
    addPricingItem,
    removePricingItem,
    setPricingItemPct,
    addDiscount,
    removeDiscount,
    setDiscountPct,
    setUnitPriceOverride,
    refreshPricing,
  }),
}));

function cell(quantity: number, calc: string | null, manual: string | null = null): QuoteCellOut {
  return {
    quantity,
    calc_cost: calc,
    manual_cost: manual,
    effective_cost: manual ?? calc,
  };
}

function op(name: string, cells: QuoteCellOut[], extra: Partial<OperationOut> = {}): OperationOut {
  return {
    id: `op-${name}`,
    operation_def_id: null,
    name,
    category: 'operation',
    position: 1,
    calculation_mode: 'labour_only',
    run_rate: '60',
    labour_rate: null,
    setup_basis: 'flat',
    setup_cost: '10',
    calc_setup_mins: null,
    manual_setup_mins: null,
    calc_runtime_mins: '15',
    manual_runtime_mins: null,
    calc_attend_mins: null,
    manual_attend_mins: null,
    surcharge_pct: '0',
    yield_factor: '1',
    is_outside_service: false,
    is_finish: false,
    is_from_factory: false,
    notes: null,
    cost_formula: null,
    variable_overrides: {},
    cells,
    ...extra,
  };
}

function costing(operations: OperationOut[]): ComponentCosting {
  return {
    component_id: 'c1',
    material_id: null,
    process_id: null,
    quantities: [1, 10],
    operations,
    buckets: [
      {
        quantity: 1,
        material_total: '0.0000',
        inside_total: '25.0000',
        outside_total: '0.0000',
        total: '25.0000',
        has_unpriced_rows: false,
      },
      {
        quantity: 10,
        material_total: '0.0000',
        inside_total: '160.0000',
        outside_total: '0.0000',
        total: '160.0000',
        has_unpriced_rows: false,
      },
    ],
  };
}

const QUOTE = {
  id: 'q1',
  number: 'A-0001',
  status: 'draft',
  currency: 'EUR',
  items: [
    {
      id: 'item-1',
      position: 1,
      root_component_id: 'c1',
      part_id: 'p1',
      quantities: [
        { quantity: 1, make_quantity: 1, deliver_quantity: 1 },
        { quantity: 10, make_quantity: 10, deliver_quantity: 10 },
      ],
    },
  ],
};

function renderPage() {
  return renderWithProviders(
    <Routes>
      <Route path="/quotes/:quoteId" element={<EstimatingPage />} />
    </Routes>,
    { route: '/quotes/q1' },
  );
}

function pricingSummary(): import('./types').PricingSummary {
  const costingRow = (quantity: number, factor: number) => ({
    quantity,
    material: null,
    inside: (25 * factor).toFixed(4),
    outside: null,
    purchased_component: null,
    child_override: null,
    total: (25 * factor).toFixed(4),
    unit_cost: '25.0000',
    custom_rows: [],
  });
  const itemCell = (quantity: number, amount: string) => ({
    quantity,
    calc_pct: '20.0000',
    manual_pct: null,
    pct: '20.0000',
    calc_profit: amount,
    manual_profit: null,
    amount,
    calc_custom_cost: null,
    unreachable: false,
  });
  return {
    component_id: 'c1',
    quantities: [1, 10],
    costing: [costingRow(1, 1), costingRow(10, 6.4)],
    pricing_items: [
      {
        id: 'pi-1',
        source_def_id: null,
        name: 'General Markup',
        calc_type: 'markup',
        category: 'general',
        is_custom: false,
        custom_category_name: null,
        color: null,
        formula: null,
        default_pct: '20',
        position: 0,
        is_from_factory: false,
        cells: [itemCell(1, '5.0000'), itemCell(10, '32.0000')],
      },
    ],
    discounts: [],
    totals: [
      {
        quantity: 1,
        unit_cost: '25.0000',
        total_excl_discounts: '30.0000',
        calc_unit_price: '30.00',
        manual_unit_price: null,
        unit_price: '30.00',
        total_price: '30.00',
        total_discount: '0.0000',
        total_discount_pct: '0.0000',
        total_profit: '5.0000',
        profit_margin_pct: '16.6700',
      },
      {
        quantity: 10,
        unit_cost: '16.0000',
        total_excl_discounts: '192.0000',
        calc_unit_price: '19.20',
        manual_unit_price: null,
        unit_price: '19.20',
        total_price: '192.00',
        total_discount: '0.0000',
        total_discount_pct: '0.0000',
        total_profit: '32.0000',
        profit_margin_pct: '16.6700',
      },
    ],
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  getQuote.mockResolvedValue(QUOTE);
  getPricing.mockResolvedValue(pricingSummary());
  listProcesses.mockResolvedValue([
    { id: 'proc-mill', name: 'Milling', external_name: null },
    { id: 'proc-lathe', name: 'Lathe', external_name: null },
  ]);
  materialTree.mockResolvedValue([]);
  listOperationDefs.mockResolvedValue([]);
});

describe('EstimatingPage', () => {
  it('renders operation rows with per-quantity cells and the roll-up summary', async () => {
    getCosting.mockResolvedValue(
      costing([op('Drehen', [cell(1, '25.0000'), cell(10, '160.0000')])]),
    );
    await renderPage();
    // German-first UI (de-DE pilot): the row, its money cells, the summary table.
    expect(await screen.findByText('Drehen')).toBeInTheDocument();
    expect(screen.getAllByText('25,00 €').length).toBeGreaterThan(0);
    expect(screen.getAllByText('160,00 €').length).toBeGreaterThan(0);
    expect(screen.getByText('Kalkulation (Costing)')).toBeInTheDocument();
    expect(screen.getByText('Interne Fertigung gesamt')).toBeInTheDocument();
    // pricing renders below costing: the stack row + the discounted total
    expect(screen.getByText('General Markup')).toBeInTheDocument();
    expect(screen.getByText('Preisbildung (Pricing)')).toBeInTheDocument();
  });

  it('marks overridden cells and keeps the calc visible in the drawer', async () => {
    getCosting.mockResolvedValue(
      costing([op('Drehen', [cell(1, '25.0000'), cell(10, '210.0000', '140.0000')])]),
    );
    await renderPage();
    // The overridden cell shows the override (effective) with the * marker.
    expect(await screen.findByText(/140,00 €\s*\*/)).toBeInTheDocument();
    // Open the drawer: the Calculated value is retained underneath the override.
    await userEvent.click(screen.getByRole('button', { name: 'Drehen' }));
    expect(screen.getByText(/Berechnet: 210,00 €/)).toBeInTheDocument();
    const overrideInput = screen.getByLabelText('Kosten-Override für Losgröße 10');
    expect(overrideInput).toHaveValue('140.0000');
  });

  it('clears a cell override back to Calculated', async () => {
    getCosting.mockResolvedValue(
      costing([op('Drehen', [cell(1, '25.0000'), cell(10, '210.0000', '140.0000')])]),
    );
    setCellOverride.mockResolvedValue(
      costing([op('Drehen', [cell(1, '25.0000'), cell(10, '210.0000')])]),
    );
    await renderPage();
    await userEvent.click(await screen.findByRole('button', { name: 'Drehen' }));
    const overrideInput = screen.getByLabelText('Kosten-Override für Losgröße 10');
    await userEvent.clear(overrideInput);
    await userEvent.click(screen.getAllByRole('button', { name: 'Übernehmen' })[1]);
    await waitFor(() => expect(setCellOverride).toHaveBeenCalledWith('op-Drehen', 10, null));
  });

  it('adds an unknown operation name via create-on-the-fly (auto-save path)', async () => {
    getCosting.mockResolvedValue(costing([]));
    addOperation.mockResolvedValue(
      costing([op('Sondervorgang', [cell(1, null), cell(10, null)])]),
    );
    await renderPage();
    await userEvent.click(await screen.findByRole('button', { name: 'ARBEITSGANG HINZUFÜGEN' }));
    await userEvent.type(
      screen.getByLabelText('Arbeitsgang suchen oder neu anlegen …'),
      'Sondervorgang',
    );
    await userEvent.click(await screen.findByText('„Sondervorgang“ neu anlegen'));
    await waitFor(() =>
      expect(addOperation).toHaveBeenCalledWith('c1', { name: 'Sondervorgang' }),
    );
  });

  it('clearing the surcharge input saves the default 0, not an empty string', async () => {
    // surcharge_pct is NOT NULL server-side: a cleared input must reset to '0'
    // (""/null would be a 422 the estimator can't act on) — Greptile M1.7 review.
    getCosting.mockResolvedValue(
      costing([op('Drehen', [cell(1, '25.0000'), cell(10, '160.0000')], { surcharge_pct: '10' })]),
    );
    updateOperation.mockResolvedValue(costing([]));
    await renderPage();
    await userEvent.click(await screen.findByRole('button', { name: 'Drehen' }));
    await userEvent.clear(screen.getByLabelText('Zuschlag (%)'));
    await userEvent.click(screen.getByRole('button', { name: 'Änderungen speichern' }));
    await waitFor(() => expect(updateOperation).toHaveBeenCalled());
    expect(updateOperation.mock.calls[0][1]).toMatchObject({ surcharge_pct: '0' });
  });

  it('change process offers UPDATE (destructive) and KEEP OPS commits', async () => {
    getCosting.mockResolvedValue(costing([op('Drehen', [cell(1, '25.0000'), cell(10, null)])]));
    setComponentProcess.mockResolvedValue(costing([]));
    await renderPage();
    await userEvent.click(await screen.findByRole('button', { name: 'Prozess ändern' }));
    expect(
      screen.getByText('AKTUALISIEREN löscht alle vorhandenen Arbeitsgänge dieser Position.'),
    ).toBeInTheDocument();
    await userEvent.selectOptions(screen.getByLabelText('Prozess'), 'proc-mill');
    await userEvent.click(screen.getByRole('button', { name: 'Aktualisieren' }));
    await waitFor(() =>
      expect(setComponentProcess).toHaveBeenCalledWith('c1', 'proc-mill', false),
    );
  });
});
