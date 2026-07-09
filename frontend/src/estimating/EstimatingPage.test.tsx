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

beforeEach(() => {
  vi.clearAllMocks();
  getQuote.mockResolvedValue(QUOTE);
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
    expect(screen.getByText('Kostenübersicht (je Losgröße)')).toBeInTheDocument();
    expect(screen.getByText('Eigenfertigung')).toBeInTheDocument();
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
