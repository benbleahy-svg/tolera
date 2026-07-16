/**
 * NestingPage (M4.3): the overview table renders interrogated sheet-metal
 * rows, selection drives the footer + prepare dialog, GENERATE posts the
 * per-break stock + settings, and the Nest result object shows the aggregate
 * metrics with EUR formatting.
 */

import { describe, expect, it, vi } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { renderWithProviders } from '../test/render';
import { NestingPage } from './NestingPage';
import type { NestOut, NestingOverview, NestingOverviewRow } from './types';

function row(overrides: Partial<NestingOverviewRow>): NestingOverviewRow {
  return {
    component_id: 'c-1',
    part_id: 'p-1',
    part_number: 'BR-100',
    part_name: null,
    item_id: 'item-1',
    position: 1,
    material_id: 'mat-1',
    material_name: '1.4301 Blech',
    thickness_mm: 2.0,
    flat_x_mm: 95.87,
    flat_y_mm: 50.0,
    flat_area_mm2: 4814.16,
    contour_length_mm: 320.5,
    quantities: [10],
    make_quantities: [10],
    eligible: true,
    nest_id: null,
    nest_label: null,
    ...overrides,
  };
}

const NEST: NestOut = {
  id: 'nest-1',
  label: 'Nest #1',
  kind: 'sheet',
  set_id: 'set-1',
  quantity: 10,
  config: {
    thickness_mm: 2.0,
    component_ids: ['c-1'],
    stock: {
      length_mm: 3000,
      width_mm: 1500,
      erp_code: '',
      sheet_cost: '250.00',
      currency: 'EUR',
    },
  },
  result: {
    net_sheet_used: 0.0469157,
    charged_sheets: 0.0469157,
    gross_sheets: 1,
    material_cost: '11.7289',
    currency: 'EUR',
    used_area_mm2: 48141.6,
    scrap_area_mm2: 240703.2,
    drop_area_mm2: 4211155.2,
    total_contour_length_mm: 3205.0,
    components: [
      {
        component_id: 'c-1',
        parts_per_sheet: 847,
        used_area_mm2: 48141.6,
        cost_share_pct: '100.00',
        allocated_cost: '11.7289',
      },
    ],
  },
};

const getNestingOverview = vi.fn<() => Promise<NestingOverview>>(() =>
  Promise.resolve({
    sheet_metal: [row({}), row({ component_id: 'c-2', item_id: 'item-2', part_number: 'BR-200' })],
    linear_metal: [],
    nests: [],
  }),
);
const createNest = vi.fn(() => Promise.resolve({ nests: [NEST] }));
const deleteNest = vi.fn(() => Promise.resolve());

vi.mock('./api', () => ({
  useEstimatingApi: () => ({
    getNestingOverview,
    createNest,
    deleteNest,
  }),
}));

vi.mock('react-router-dom', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react-router-dom')>();
  return { ...actual, useParams: () => ({ quoteId: 'q-1' }) };
});

describe('NestingPage', () => {
  it('renders the overview rows with interrogated flat data', async () => {
    renderWithProviders(<NestingPage />);
    expect(await screen.findByText('BR-100')).toBeInTheDocument();
    expect(screen.getByText('BR-200')).toBeInTheDocument();
    // unfolded dims + thickness, German number formatting (metric-native)
    expect(screen.getAllByText('95,87 × 50').length).toBe(2);
    expect(screen.getAllByText('4.814,16').length).toBe(2);
  });

  it('selection opens the prepare dialog and GENERATE posts the nest config', async () => {
    const user = userEvent.setup();
    renderWithProviders(<NestingPage />);
    await screen.findByText('BR-100');

    await user.click(screen.getByRole('checkbox', { name: 'BR-100' }));
    await user.click(screen.getByRole('checkbox', { name: 'BR-200' }));
    await user.click(screen.getByRole('button', { name: /nests/i }));

    // one stock row for the single shared break, with the metric defaults;
    // German-first comma decimal is normalized for the API
    const cost = await screen.findByLabelText(/10$/, { selector: 'input[inputmode]' });
    await user.type(cost, '250,00');
    await user.click(screen.getByRole('button', { name: /erstellen|generate/i }));

    await waitFor(() => expect(createNest).toHaveBeenCalledTimes(1));
    const [quoteId, body] = createNest.mock.calls[0] as unknown as [string, any];
    expect(quoteId).toBe('q-1');
    expect(body.component_ids).toEqual(['c-1', 'c-2']);
    expect(body.stock).toEqual([
      { quantity: 10, length_mm: 3000, width_mm: 1500, erp_code: '', sheet_cost: '250.00' },
    ]);
    expect(body.settings.edge_buffer_mm).toBe(3.0);
    expect(body.settings.drop_threshold_pct).toBe(25.0);
  });

  it('shows the Nest result object with metrics and allocation', async () => {
    // persistent (not Once): StrictMode double-mounts fetch twice
    getNestingOverview.mockResolvedValue({
      sheet_metal: [row({ nest_id: 'nest-1', nest_label: 'Nest #1' })],
      linear_metal: [],
      nests: [NEST],
    });
    const user = userEvent.setup();
    renderWithProviders(<NestingPage />);

    await user.click((await screen.findAllByRole('button', { name: /Nest #1/ }))[0]);
    const dialog = await screen.findByRole('dialog', { name: 'Nest #1' });
    expect(dialog).toBeInTheDocument();
    // EUR, German locale; fractional charged sheets (drop rule)
    expect(screen.getAllByText(/11,73\s*€/).length).toBeGreaterThan(0);
    expect(screen.getByText('847')).toBeInTheDocument();
  });
});
