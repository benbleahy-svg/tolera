/**
 * Configure → Pricing (M1.10): the org pricing-item library — list with
 * category chips, the New Pricing Item modal (calc type + custom category),
 * the discount library, deletes.
 */

import { beforeEach, describe, expect, it, vi } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { renderWithProviders } from '../test/render';
import { PricingDefsPage } from './PricingDefsPage';
import type { DiscountDefOut, PricingItemDefOut } from './api';

const listPricingItemDefs = vi.fn();
const createPricingItemDef = vi.fn();
const updatePricingItemDef = vi.fn();
const deletePricingItemDef = vi.fn();
const listDiscountDefs = vi.fn();
const createDiscountDef = vi.fn();
const deleteDiscountDef = vi.fn();

vi.mock('./api', () => ({
  useConfigureApi: () => ({
    listPricingItemDefs,
    createPricingItemDef,
    updatePricingItemDef,
    deletePricingItemDef,
    listDiscountDefs,
    createDiscountDef,
    deleteDiscountDef,
  }),
}));

const DEFS: PricingItemDefOut[] = [
  {
    id: 'def-1',
    name: 'General Markup',
    calc_type: 'markup',
    category: 'general',
    is_custom: false,
    custom_category_name: null,
    color: null,
    formula: null,
    default_pct: '10',
    position: 0,
  },
  {
    id: 'def-2',
    name: 'Difficult Material Markup',
    calc_type: 'markup',
    category: 'general',
    is_custom: true,
    custom_category_name: 'Difficult Material',
    color: '#8b1e3f',
    formula: 'set_custom_cost(0)\nPERCENTAGE = 10',
    default_pct: null,
    position: 1,
  },
];

const DISCOUNTS: DiscountDefOut[] = [
  { id: 'dd-1', name: 'Treuerabatt', formula: null, default_pct: '5', position: 0 },
];

beforeEach(() => {
  vi.clearAllMocks();
  listPricingItemDefs.mockResolvedValue(DEFS);
  listDiscountDefs.mockResolvedValue(DISCOUNTS);
});

describe('PricingDefsPage', () => {
  it('lists pricing items with custom-category chips and discounts', async () => {
    renderWithProviders(<PricingDefsPage />);
    expect(await screen.findByText('General Markup')).toBeInTheDocument();
    // the custom def shows its category as a colored chip (DemoE frame 16)
    expect(screen.getByText('Difficult Material')).toBeInTheDocument();
    expect(screen.getByText('Treuerabatt')).toBeInTheDocument();
  });

  it('creates a target-margin def through the New Pricing Item modal', async () => {
    createPricingItemDef.mockResolvedValue({});
    renderWithProviders(<PricingDefsPage />);
    await screen.findByText('General Markup');
    await userEvent.click(screen.getByRole('button', { name: 'Neue Preisposition' }));
    await userEvent.type(screen.getByLabelText('Name'), 'Zielmarge');
    await userEvent.selectOptions(screen.getByLabelText('Berechnungsart'), 'target_margin');
    await userEvent.type(screen.getByLabelText('Prozentsatz (%)'), '20');
    await userEvent.click(screen.getByRole('button', { name: 'Hinzufügen' }));
    await waitFor(() =>
      expect(createPricingItemDef).toHaveBeenCalledWith(
        expect.objectContaining({
          name: 'Zielmarge',
          calc_type: 'target_margin',
          default_pct: '20',
        }),
      ),
    );
  });

  it('deletes a def and reloads', async () => {
    deletePricingItemDef.mockResolvedValue(undefined);
    renderWithProviders(<PricingDefsPage />);
    await screen.findByText('General Markup');
    await userEvent.click(
      screen.getByRole('button', { name: 'General Markup entfernen' }),
    );
    await waitFor(() => expect(deletePricingItemDef).toHaveBeenCalledWith('def-1'));
  });
});
