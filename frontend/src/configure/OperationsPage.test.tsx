/**
 * Configure → Operations (M1.14, spec #operation-rates-banner): the
 * quick-start banner shows the unrated count, APPLY TO ALL fills every
 * unrated def with one rate, and the inline rate input saves per def.
 * M4.14: the drawer's Variables table (VARIABLE | WERT | SICHTBARKEIT) —
 * def-level report load, hidden filtering, and the eye-toggle PUT.
 */

import { beforeEach, describe, expect, it, vi } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { renderWithProviders } from '../test/render';
import type {
  KalkDeclaredVariable,
  OpDefKalkReport,
  OperationDefOut,
} from '../estimating/types';

const listOperationDefs = vi.fn();
const updateOperationDef = vi.fn(() => Promise.resolve({}));
const getConfigCompleteness = vi.fn();
const applyRateToAll = vi.fn(() => Promise.resolve({ updated: 2 }));
const getOpDefKalkReport = vi.fn();
const setOpDefVariableVisibility = vi.fn();

vi.mock('./api', () => ({
  useConfigureApi: () => ({
    listOperationDefs,
    updateOperationDef,
    getConfigCompleteness,
    applyRateToAll,
    getOpDefKalkReport,
    setOpDefVariableVisibility,
  }),
}));

import { OperationsPage } from './OperationsPage';

function def(
  name: string,
  runRate: string | null,
  extra: Partial<OperationDefOut> = {},
): OperationDefOut {
  return {
    id: `def-${name}`,
    name,
    category: 'operation',
    calculation_mode: 'machine_plus_operator',
    run_rate: runRate,
    labour_rate: null,
    setup_basis: 'flat',
    setup_cost: null,
    setup_time_mins: null,
    surcharge_pct: '0.000',
    is_outside_service: false,
    is_finish: false,
    is_pre_installed: true,
    sort_order: 0,
    cost_formula: null,
    variable_visibility: {},
    ...extra,
  };
}

function declared(
  name: string,
  value: number,
  extra: Partial<KalkDeclaredVariable> = {},
): KalkDeclaredVariable {
  return {
    name,
    kind: 'var',
    value_type: 'number',
    default: value,
    description: '',
    default_visible: true,
    frozen: true,
    quantity_specific: false,
    value,
    ...extra,
  };
}

function defReport(
  variables: KalkDeclaredVariable[],
  visibility: Record<string, boolean> = {},
): OpDefKalkReport {
  return {
    declared_variables: variables,
    variable_groups: [],
    errors: [],
    variable_visibility: visibility,
  };
}

describe('OperationsPage', () => {
  it('shows the rates banner with the unrated count and applies one rate to all', async () => {
    listOperationDefs.mockResolvedValue([def('Fräsen', null), def('Drehen', null)]);
    getConfigCompleteness.mockResolvedValue({
      unrated_operation_defs: 2,
      unrated_materials: 3,
    });
    await renderWithProviders(<OperationsPage />);
    await waitFor(() =>
      expect(
        screen.getByText(/2 Arbeitsgänge ohne Stundensatz/),
      ).toBeInTheDocument(),
    );
    expect(screen.getByText(/3 Werkstoffe ohne Kostensatz/)).toBeInTheDocument();

    await userEvent.type(
      screen.getByLabelText('Schnellstart: ein Satz für alle (€/Std.)'),
      '85',
    );
    await userEvent.click(screen.getByRole('button', { name: 'AUF ALLE ANWENDEN' }));
    expect(applyRateToAll).toHaveBeenCalledWith('85');
  });

  it('hides the banner when everything is rated and saves an inline rate', async () => {
    listOperationDefs.mockResolvedValue([def('Fräsen', '85.0000')]);
    getConfigCompleteness.mockResolvedValue({
      unrated_operation_defs: 0,
      unrated_materials: 0,
    });
    await renderWithProviders(<OperationsPage />);
    await waitFor(() => expect(screen.getByDisplayValue('85.0000')).toBeInTheDocument());
    expect(screen.queryByText(/ohne Stundensatz/)).not.toBeInTheDocument();

    const input = screen.getByLabelText('Satz für Fräsen');
    await userEvent.clear(input);
    await userEvent.type(input, '120{Enter}');
    expect(updateOperationDef).toHaveBeenCalledWith('def-Fräsen', { run_rate: '120' });
  });
});

describe('OpDefDrawer Variables table (M4.14)', () => {
  beforeEach(() => {
    getOpDefKalkReport.mockReset();
    setOpDefVariableVisibility.mockReset();
  });

  async function openDrawer(defOut: OperationDefOut) {
    listOperationDefs.mockResolvedValue([defOut]);
    getConfigCompleteness.mockResolvedValue({ unrated_operation_defs: 0, unrated_materials: 0 });
    await renderWithProviders(<OperationsPage />);
    await waitFor(() => expect(screen.getByLabelText(`${defOut.name} bearbeiten`)).toBeInTheDocument());
    await userEvent.click(screen.getByLabelText(`${defOut.name} bearbeiten`));
  }

  it('renders declared variables with defaults and hides hidden ones behind the toggle', async () => {
    getOpDefKalkReport.mockResolvedValue(
      defReport([
        declared('Stundensatz', 60),
        declared('Ruestfaktor', 1.5, { default_visible: false }),
        declared('runtime', 0.1), // manual-minutes territory — never in the table
      ]),
    );
    await openDrawer(def('Fräsen', '80', { cost_formula: 'COST = 1\nDAYS = 0' }));

    await waitFor(() => expect(screen.getByText('Stundensatz')).toBeInTheDocument());
    expect(getOpDefKalkReport).toHaveBeenCalledWith('def-Fräsen');
    expect(screen.getByText('60')).toBeInTheDocument();
    expect(screen.queryByText('Ruestfaktor')).not.toBeInTheDocument();
    expect(screen.queryByText('runtime')).not.toBeInTheDocument();

    await userEvent.click(screen.getByLabelText(/Ausgeblendete Variablen anzeigen/));
    expect(screen.getByText('Ruestfaktor')).toBeInTheDocument();
  });

  it('toggles an eye and PUTs the map built from the server-reported base', async () => {
    // the report's stored map carries an earlier toggle the (stale) defs-list
    // row does not — the PUT must keep it (never wipe earlier eyes)
    getOpDefKalkReport.mockResolvedValue(
      defReport(
        [declared('Stundensatz', 60), declared('Ruestfaktor', 1.5, { default_visible: false })],
        { Ruestfaktor: false },
      ),
    );
    setOpDefVariableVisibility.mockResolvedValue(
      defReport([declared('Stundensatz', 60, { default_visible: false })], {
        Ruestfaktor: false,
        Stundensatz: false,
      }),
    );
    await openDrawer(def('Fräsen', '80', { cost_formula: 'COST = 1\nDAYS = 0' }));

    await waitFor(() => expect(screen.getByText('Stundensatz')).toBeInTheDocument());
    await userEvent.click(screen.getByLabelText('Sichtbarkeit von Stundensatz umschalten'));
    expect(setOpDefVariableVisibility).toHaveBeenCalledWith('def-Fräsen', {
      Ruestfaktor: false,
      Stundensatz: false,
    });
  });

  it('shows a German error when the eye toggle fails to save', async () => {
    getOpDefKalkReport.mockResolvedValue(defReport([declared('Stundensatz', 60)]));
    setOpDefVariableVisibility.mockRejectedValue(new Error('nope'));
    await openDrawer(def('Fräsen', '80', { cost_formula: 'COST = 1\nDAYS = 0' }));

    await waitFor(() => expect(screen.getByText('Stundensatz')).toBeInTheDocument());
    await userEvent.click(screen.getByLabelText('Sichtbarkeit von Stundensatz umschalten'));
    await waitFor(() =>
      expect(
        screen.getByText('Sichtbarkeit konnte nicht gespeichert werden.'),
      ).toBeInTheDocument(),
    );
  });

  it('surfaces a formula evaluation error as the CHECK-style message', async () => {
    getOpDefKalkReport.mockResolvedValue({
      declared_variables: [],
      variable_groups: [],
      errors: [{ code: 'runtime_error', message: 'division by zero', line: 2, col: 0 }],
      variable_visibility: {},
    });
    await openDrawer(def('Sägen', '80', { cost_formula: 'COST = 1 / 0\nDAYS = 0' }));
    await waitFor(() => expect(screen.getByText(/Zeile 2: division by zero/)).toBeInTheDocument());
  });

  it('shows no variables section for a def without a formula', async () => {
    await openDrawer(def('Entgraten', '80'));
    expect(getOpDefKalkReport).not.toHaveBeenCalled();
    expect(screen.queryByText('Variablen')).not.toBeInTheDocument();
  });
});
