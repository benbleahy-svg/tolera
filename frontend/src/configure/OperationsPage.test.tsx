/**
 * Configure → Operations (M1.14, spec #operation-rates-banner): the
 * quick-start banner shows the unrated count, APPLY TO ALL fills every
 * unrated def with one rate, and the inline rate input saves per def.
 */

import { describe, expect, it, vi } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { renderWithProviders } from '../test/render';
import type { OperationDefOut } from '../estimating/types';

const listOperationDefs = vi.fn();
const updateOperationDef = vi.fn(() => Promise.resolve({}));
const getConfigCompleteness = vi.fn();
const applyRateToAll = vi.fn(() => Promise.resolve({ updated: 2 }));

vi.mock('./api', () => ({
  useConfigureApi: () => ({
    listOperationDefs,
    updateOperationDef,
    getConfigCompleteness,
    applyRateToAll,
  }),
}));

import { OperationsPage } from './OperationsPage';

function def(name: string, runRate: string | null): OperationDefOut {
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
