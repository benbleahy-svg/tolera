import { describe, expect, it, vi } from 'vitest';
import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { renderWithProviders } from '../test/render';
import { FacilitateOrderDrawer, type FacilitatePricedLine } from './FacilitateOrderDrawer';

const LINES: FacilitatePricedLine[] = [
  {
    quote_item_id: 'qi-1',
    part_label: 'ABC-123 Rev B',
    breaks: [
      { quantity: 1, lead_time_days: 10, unit_price_minor: 20000, total_price_minor: 20000 },
      { quantity: 10, lead_time_days: 14, unit_price_minor: 18000, total_price_minor: 180000 },
    ],
  },
];

async function renderDrawer(onSubmit = vi.fn()) {
  await renderWithProviders(
    <FacilitateOrderDrawer
      lines={LINES}
      currency="EUR"
      placedOn="2026-07-01"
      onSubmit={onSubmit}
      onClose={vi.fn()}
    />,
  );
  return onSubmit;
}

describe('FacilitateOrderDrawer', () => {
  it('defaults Ships-On to placement + the chosen break lead time', async () => {
    await renderDrawer();
    // First break (10-day lead) selected → 2026-07-01 + 10 = 2026-07-11.
    const shipsOn = screen.getByLabelText('Versand am') as HTMLInputElement;
    expect(shipsOn.value).toBe('2026-07-11');
  });

  it('submits the chosen break with a discount and additional charge', async () => {
    const user = userEvent.setup();
    const onSubmit = await renderDrawer();

    // Choose the qty-10 break (2nd radio).
    const radios = screen.getAllByRole('radio');
    await user.click(radios[1]);

    // Add a 10% discount.
    await user.click(screen.getByRole('button', { name: '+ Rabatt hinzufügen' }));
    const discRows = screen.getAllByPlaceholderText('Bezeichnung');
    await user.type(discRows[0], 'Kundentreue');
    await user.type(screen.getByLabelText('Prozent'), '10');

    // Add a 500 charge.
    await user.click(screen.getByRole('button', { name: '+ Zusätzliche Kosten hinzufügen' }));
    const allLabels = screen.getAllByPlaceholderText('Bezeichnung');
    await user.type(allLabels[1], 'Werkzeug');
    await user.type(screen.getByLabelText('Preis'), '500');

    // Step 2 → submit.
    await user.click(screen.getByRole('button', { name: 'Weiter zu Versand & Zahlung' }));
    await user.click(screen.getByRole('button', { name: 'Auftrag prüfen & erstellen' }));

    expect(onSubmit).toHaveBeenCalledTimes(1);
    const req = onSubmit.mock.calls[0][0];
    expect(req.selections).toHaveLength(1);
    expect(req.selections[0]).toMatchObject({
      quote_item_id: 'qi-1',
      quantity: 10,
      discounts: [{ label: 'Kundentreue', percent: '10' }],
      additional_charges: [{ label: 'Werkzeug', amount: '500' }],
    });
  });

  it('carries the PO number only when Purchase Order is the payment method', async () => {
    const user = userEvent.setup();
    const onSubmit = await renderDrawer();
    await user.click(screen.getByRole('button', { name: 'Weiter zu Versand & Zahlung' }));
    await user.click(screen.getByLabelText('Bestellung (PO)'));
    await user.type(screen.getByLabelText('Bestellnummer'), 'PO-9');
    await user.click(screen.getByRole('button', { name: 'Auftrag prüfen & erstellen' }));

    expect(onSubmit.mock.calls[0][0].po_number).toBe('PO-9');
  });

  it('excludes a removed line from the order', async () => {
    const user = userEvent.setup();
    const onSubmit = await renderDrawer();
    await user.click(screen.getByRole('button', { name: 'Position entfernen' }));
    // With the only line removed, Continue is disabled — nothing to order.
    expect(screen.getByRole('button', { name: 'Weiter zu Versand & Zahlung' })).toBeDisabled();
    expect(onSubmit).not.toHaveBeenCalled();
  });
});
