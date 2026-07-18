import { beforeEach, describe, expect, it, vi } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Route, Routes } from 'react-router-dom';

import { renderWithProviders } from '../test/render';
import { EstimatingPage } from './EstimatingPage';
import type { ComponentCosting, OperationDefOut, OperationOut, QuoteCellOut } from './types';

const getQuote = vi.fn();
const getCosting = vi.fn();
const materialTree = vi.fn();
const searchMaterials = vi.fn();
const updateMaterial = vi.fn();
const listProcesses = vi.fn();
const listOperationDefs = vi.fn();
const listFinishDefs = vi.fn<() => Promise<OperationDefOut[]>>(() => Promise.resolve([]));
const setLineItemPriority = vi.fn();
const addLineItem = vi.fn();
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
const listAddOnDefs = vi.fn(() => Promise.resolve([]));
const addAddOn = vi.fn();
const updateAddOn = vi.fn();
const removeAddOn = vi.fn();
const setAddOnPrice = vi.fn();
const setLeadTime = vi.fn();
const setExpediteOptions = vi.fn();
const applyLeadTimesToAll = vi.fn();
const getBulkCreatePrefill = vi.fn(() =>
  Promise.resolve({ status: 'none', found_in: null, rfq_files: [], rows: [] }),
);
const bulkCreateLineItems = vi.fn();
const getNestingOverview = vi.fn(() =>
  Promise.resolve({ sheet_metal: [], linear_metal: [], nests: [] }),
);
const getRequoteDiff = vi.fn(() => Promise.resolve({ entries: [] }));
const postRequoteChoice = vi.fn(() => Promise.resolve({ entries: [] }));
const importRouter = vi.fn(() => Promise.resolve({}));
const getQuoteTotals = vi.fn(() =>
  Promise.resolve({
    currency: 'EUR',
    country: 'DE',
    vat_label: 'MwSt.',
    vat_rate_pct: '19',
    items: [],
    net_minor: 0,
    vat_minor: 0,
    gross_minor: 0,
    has_unpriced_lines: false,
  }),
);

// The matches chip (M2.12) carries its own API hook — stub it out here; it has
// its own tests in parts/MatchingParts.test.tsx.
vi.mock('../parts/MatchingParts', () => ({ PartMatchesChip: () => null }));

// The communications timeline (M3.5) has its own suite; stub it here so the
// page render never touches Clerk via useEmailApi.
vi.mock('./CommunicationsSection', () => ({ CommunicationsSection: () => null }));
// M3.8's panel resolves its own API hook (and therefore Clerk); this page
// test is about the estimating grid, and the panel has its own suite.
vi.mock('../review/ReviewItemsPanel', () => ({ ReviewItemsPanel: () => null }));

// M3.10 hooks the page uses for the rule-suggestion chip; stub so the render
// never touches Clerk. Rule-suggest probing is covered by its own suites. Stable
// object per the real useMemo hook (a fresh object each render is a dep churn).
const ruleSuggestApi = {
  listSuggestedActions: vi.fn().mockResolvedValue([]),
  dismissSuggestedAction: vi.fn(),
  getRuleSuggestion: vi.fn().mockResolvedValue({ suggestion: null }),
};
vi.mock('../review/api', async () => {
  const actual = await vi.importActual<typeof import('../review/api')>('../review/api');
  return { ...actual, useRuleSuggestApi: () => ruleSuggestApi };
});
vi.mock('../configure/api', () => ({ useConfigureApi: () => ({ importRules: vi.fn() }) }));
// M5.7 — the Facilitate Order entry uses the orders API (Clerk-bound); stub it so
// these Clerk-free unit tests don't touch auth.
vi.mock('../orders/api', () => ({ useOrdersApi: () => ({ facilitateOrder: vi.fn() }) }));

// M4.9: the BOM banner probe — no suggestion/children by default (no banner).
// One hoisted instance: EstimatingPage keys an effect on the api object, so a
// fresh object per render would retrigger it forever (CodeRabbit 2026-07-17).
const bomApiMock = {
  getBomStatus: vi
    .fn()
    .mockResolvedValue({ suggestion: null, has_children: false, has_draft: false }),
};
vi.mock('../bom/api', () => ({
  useBomApi: () => bomApiMock,
}));

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
    listFinishDefs,
    setLineItemPriority,
    addLineItem,
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
    listAddOnDefs,
    addAddOn,
    updateAddOn,
    removeAddOn,
    setAddOnPrice,
    setLeadTime,
    setExpediteOptions,
    applyLeadTimesToAll,
    getQuoteTotals,
    getBulkCreatePrefill,
    bulkCreateLineItems,
    getNestingOverview,
    // M4.10 — the Assembly Components section renders nothing on an empty tree
    getAssemblyComponents: vi.fn(() =>
      Promise.resolve({
        quantities: [],
        root_node_id: null,
        tree: [],
        summary: { flat_qty_total: 0, totals: [] },
      }),
    ),
    getRequoteDiff,
    postRequoteChoice,
    importRouter,
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
    source: 'manual',
    source_quote_id: null,
    missing_rate: false,
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
    has_missing_rates: false,
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
  missing_rates_item_count: 0,
  items: [
    {
      id: 'item-1',
      position: 1,
      root_component_id: 'c1',
      part_id: 'p1',
      workflow_status: 'not_started',
      priority: null,
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
      <Route path="/quotes/edit/:id/:lineItemId" element={<EstimatingPage />} />
    </Routes>,
    { route: '/quotes/edit/q1/item-1' },
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
    add_ons: [],
    lead_times: [],
    totals: [
      {
        quantity: 1,
        unit_cost: '25.0000',
        total_excl_discounts: '30.0000',
        total_markup: null,
        total_markup_pct: null,
        calc_unit_price: '30.00',
        manual_unit_price: null,
        unit_price: '30.00',
        total_price: '30.00',
        total_discount: '0.0000',
        total_discount_pct: '0.0000',
        total_profit: '5.0000',
        profit_margin_pct: '16.6700',
        total_required_add_ons: '0.0000',
        total_with_required_add_ons: null,
      },
      {
        quantity: 10,
        unit_cost: '16.0000',
        total_excl_discounts: '192.0000',
        total_markup: null,
        total_markup_pct: null,
        calc_unit_price: '19.20',
        manual_unit_price: null,
        unit_price: '19.20',
        total_price: '192.00',
        total_discount: '0.0000',
        total_discount_pct: '0.0000',
        total_profit: '32.0000',
        profit_margin_pct: '16.6700',
        total_required_add_ons: '0.0000',
        total_with_required_add_ons: null,
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

  it('renders the estimating-grid anatomy: time columns, per-unit lines, yield + make qty footers', async () => {
    getCosting.mockResolvedValue(
      costing([op('Drehen', [cell(1, '25.0000'), cell(10, '160.0000')])]),
    );
    await renderPage();
    await screen.findByText('Drehen');
    // Setup Time / Run Time columns on the grid (DemoA/8, DemoB/15): flat setup
    // shows the € cost, runtime shows resolved minutes
    expect(screen.getAllByText('Rüstzeit').length).toBeGreaterThan(0);
    expect(screen.getAllByText('Laufzeit').length).toBeGreaterThan(0);
    expect(screen.getAllByText('15 Min.').length).toBeGreaterThan(0);
    // per-unit beneath the qty-10 total: 160/10 = 16,00 €
    expect(screen.getAllByText('16,00 €').length).toBeGreaterThan(0);
    // named summary rows + yield/make-quantity footers (operations router)
    expect(screen.getByText('Materialsumme')).toBeInTheDocument();
    expect(screen.getByText('Summe Arbeitsgänge')).toBeInTheDocument();
    expect(screen.getByText('Ausbeute (%)')).toBeInTheDocument();
    expect(screen.getByText('Fertigungsmenge')).toBeInTheDocument();
    expect(screen.getAllByText('100,00 %').length).toBe(2);
    // an empty Materials section still renders its table skeleton with a zero summary
    expect(screen.getAllByText('0,00 €').length).toBeGreaterThan(0);
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

  // ------------------------------------------------------------- M5.0 shell
  it('renders the line-item sidebar and the add-line-item affordance', async () => {
    getCosting.mockResolvedValue(costing([]));
    await renderPage();
    // The sidebar carries the quote title and the add-item button.
    expect(await screen.findByRole('button', { name: 'Position hinzufügen' })).toBeInTheDocument();
    expect(screen.getByLabelText('Positionen')).toBeInTheDocument();
  });

  it('sets a line-item priority via the ACTIONS menu', async () => {
    getCosting.mockResolvedValue(costing([]));
    setLineItemPriority.mockResolvedValue(QUOTE);
    await renderPage();
    await userEvent.click(await screen.findByText('AKTIONEN'));
    await userEvent.selectOptions(screen.getByLabelText('Priorität'), '7');
    await waitFor(() =>
      expect(setLineItemPriority).toHaveBeenCalledWith('q1', 'item-1', 7),
    );
  });

  it('renders the first line item when the URL omits the line item', async () => {
    // `/quotes/edit/:id` (the old-route redirect target) resolves to the first item:
    // its component costing loads and the sidebar marks it active.
    getCosting.mockResolvedValue(
      costing([op('Drehen', [cell(1, '25.0000'), cell(10, '160.0000')])]),
    );
    await renderWithProviders(
      <Routes>
        <Route path="/quotes/edit/:id" element={<EstimatingPage />} />
        <Route path="/quotes/edit/:id/:lineItemId" element={<EstimatingPage />} />
      </Routes>,
      { route: '/quotes/edit/q1' },
    );
    expect(await screen.findByText('Drehen')).toBeInTheDocument();
    expect(getCosting).toHaveBeenCalledWith('c1');
    const active = screen.getByRole('button', { current: true });
    expect(active).toHaveTextContent('1');
  });

  it('deep-links to a non-first line item and loads only its costing', async () => {
    // A two-item quote opened directly at item-2 must resolve the active item from
    // the URL synchronously — item-2's component costing loads, item-1's does not.
    getQuote.mockResolvedValue({
      ...QUOTE,
      items: [
        QUOTE.items[0],
        {
          id: 'item-2',
          position: 2,
          root_component_id: 'c2',
          part_id: 'p2',
          workflow_status: 'not_started',
          priority: null,
          quantities: [{ quantity: 1, make_quantity: 1, deliver_quantity: 1 }],
        },
      ],
    });
    getCosting.mockImplementation((cid: string) =>
      Promise.resolve(costing([op(cid === 'c2' ? 'Fräsen' : 'Drehen', [cell(1, '25.0000')])])),
    );
    await renderWithProviders(
      <Routes>
        <Route path="/quotes/edit/:id/:lineItemId" element={<EstimatingPage />} />
      </Routes>,
      { route: '/quotes/edit/q1/item-2' },
    );
    expect(await screen.findByText('Fräsen')).toBeInTheDocument();
    expect(getCosting).toHaveBeenCalledWith('c2');
    expect(getCosting).not.toHaveBeenCalledWith('c1');
    expect(screen.getByRole('button', { current: true })).toHaveTextContent('2');
  });

  it('attaches a requested finish from the finish library', async () => {
    getCosting.mockResolvedValue(costing([]));
    listFinishDefs.mockResolvedValue([
      {
        id: 'fd1',
        name: 'Eloxieren',
        category: 'operation',
        calculation_mode: 'labour_only',
        run_rate: null,
        labour_rate: null,
        setup_basis: 'flat',
        setup_cost: null,
        setup_time_mins: null,
        surcharge_pct: '0',
        is_outside_service: false,
        is_finish: true,
        is_pre_installed: false,
        sort_order: 0,
        cost_formula: null,
        variable_visibility: {},
      },
    ]);
    addOperation.mockResolvedValue(costing([]));
    await renderPage();
    await userEvent.click(await screen.findByText('Oberfläche hinzufügen'));
    await userEvent.click(await screen.findByLabelText('Eloxieren'));
    await waitFor(() =>
      expect(addOperation).toHaveBeenCalledWith('c1', { operation_def_id: 'fd1' }),
    );
  });
});
