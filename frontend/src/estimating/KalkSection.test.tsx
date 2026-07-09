/**
 * KalkSection (M1.9): the formula editor's CHECK flow (line-numbered errors),
 * and the variables panel — declared variables render with their calculated
 * values, drop-downs offer options, per-quantity variables get one input per
 * break, and saving submits the override map.
 */

import { describe, expect, it, vi } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { renderWithProviders } from '../test/render';
import { KalkSection } from './KalkSection';
import type { KalkQtyReport } from './types';

function report(quantity: number): KalkQtyReport {
  return {
    quantity,
    output: { COST: 60 * quantity, DAYS: 0, no_quote: false },
    declared_variables: [
      {
        name: 'Stundensatz',
        kind: 'var',
        value_type: 'currency',
        default: 60,
        description: 'EUR/hr',
        default_visible: true,
        frozen: true,
        quantity_specific: false,
        value: 60,
      },
      {
        name: 'Finish',
        kind: 'drop_down',
        value_type: 'string',
        default: 'roh',
        description: '',
        default_visible: true,
        frozen: true,
        quantity_specific: false,
        value: 'roh',
        options: ['roh', 'eloxiert'],
      },
      {
        name: 'Minuten pro Teil',
        kind: 'var',
        value_type: 'number',
        default: 6,
        description: '',
        default_visible: true,
        frozen: true,
        quantity_specific: true,
        value: 6,
      },
    ],
    variable_groups: [{ name: 'Preise', default_collapsed: false, members: ['Stundensatz'] }],
    applied_overrides: [],
    notes: null,
    operation_name: null,
    errors: [],
  };
}

function renderSection(overrides: Partial<Parameters<typeof KalkSection>[0]> = {}) {
  const props = {
    formula: 'COST = 1',
    variableOverrides: {},
    loadReport: vi.fn().mockResolvedValue([report(1), report(5)]),
    onCheck: vi.fn(),
    onSaveFormula: vi.fn(),
    onSaveOverrides: vi.fn(),
    ...overrides,
  };
  renderWithProviders(<KalkSection {...props} />);
  return props;
}

describe('KalkSection', () => {
  it('CHECK surfaces line-numbered errors and a clean pass', async () => {
    const user = userEvent.setup();
    const props = renderSection({
      formula: null,
      onCheck: vi
        .fn()
        .mockResolvedValueOnce({
          ok: false,
          errors: [{ code: 'unknown_name', message: "unknown name 'x'", line: 2, col: 8 }],
        })
        .mockResolvedValueOnce({ ok: true, errors: [] }),
    });
    await user.type(await screen.findByPlaceholderText(/COST = setup_time/), 'COST = x');
    await user.click(screen.getByRole('button', { name: 'Prüfen' }));
    expect(await screen.findByRole('status')).toHaveTextContent("Zeile 2: unknown name 'x'");

    await user.click(screen.getByRole('button', { name: 'Prüfen' }));
    expect(await screen.findByRole('status')).toHaveTextContent('Formel ist gültig.');
    expect(props.onCheck).toHaveBeenCalledTimes(2);
  });

  it('renders declared variables with groups, drop-down options, and per-qty inputs', async () => {
    renderSection();
    // grouped variable under its group heading
    expect(await screen.findByText('Preise')).toBeInTheDocument();
    expect(screen.getByLabelText('Stundensatz')).toBeInTheDocument();
    // drop-down renders its options
    const dropdown = screen.getByLabelText('Finish');
    expect(dropdown).toHaveDisplayValue('Berechnet: roh');
    // quantity-specific variable: one input per break
    expect(screen.getByLabelText('Minuten pro Teil @1')).toBeInTheDocument();
    expect(screen.getByLabelText('Minuten pro Teil @5')).toBeInTheDocument();
  });

  it('saves plain, drop-down, and per-quantity overrides in the API shape', async () => {
    const user = userEvent.setup();
    const props = renderSection();
    await user.type(await screen.findByLabelText('Stundensatz'), '90');
    await user.selectOptions(screen.getByLabelText('Finish'), 'eloxiert');
    await user.type(screen.getByLabelText('Minuten pro Teil @5'), '4');
    await user.click(screen.getByRole('button', { name: 'Variablen übernehmen' }));
    await waitFor(() =>
      expect(props.onSaveOverrides).toHaveBeenCalledWith({
        Stundensatz: 90,
        Finish: 'eloxiert',
        'Minuten pro Teil': { '5': 4 },
      }),
    );
  });

  it('surfaces evaluation errors from the report', async () => {
    const failing = { ...report(1), errors: [{ code: 'runtime_error', message: 'kaputt', line: 3, col: null }] };
    renderSection({ loadReport: vi.fn().mockResolvedValue([failing]) });
    expect(await screen.findByRole('alert')).toHaveTextContent('Zeile 3: kaputt');
  });

  it('saving the formula sends null when cleared', async () => {
    const user = userEvent.setup();
    const props = renderSection({ loadReport: vi.fn().mockResolvedValue([]) });
    await user.clear(await screen.findByPlaceholderText(/COST = setup_time/));
    await user.click(screen.getByRole('button', { name: 'Formel speichern' }));
    expect(props.onSaveFormula).toHaveBeenCalledWith(null);
  });
});
