import { beforeEach, describe, expect, it, vi } from 'vitest';
import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { renderWithProviders } from '../test/render';
import { ToleraSourcePanel } from './ToleraSourcePanel';

const availability = vi.fn();
const sendRfq = vi.fn();

// One stable object, like the real hook (useMemo on getToken) — a per-render
// mock would make the lookup effect refetch forever.
const API = { availability, sendRfq };
vi.mock('./api', () => ({ useSourcingApi: () => API }));

const PRICED = {
  supplier: 'wuerth',
  degraded: false,
  item: {
    oem_part_number: '0057 8 30',
    found: true,
    currency: 'EUR',
    description: 'Sechskantschraube DIN 933 M8x30',
    brand: 'Würth',
    quantity_available: 12500,
    lead_time_days: 2,
    quotes: [
      { quantity: 100, unit_price_minor: 19, extended_price_minor: 1900, status: 'available' },
      { quantity: 9000, unit_price_minor: 13, extended_price_minor: 117000, status: 'at_risk' },
    ],
  },
};

describe('ToleraSourcePanel', () => {
  beforeEach(() => {
    availability.mockReset().mockResolvedValue(PRICED);
    sendRfq.mockReset().mockResolvedValue({
      supplier: 'wuerth',
      reference: 'TS-RFQ-abc',
      accepted: true,
      supplier_reference: 'WUE-1',
      estimated_response_hours: 24,
      mode: 'fixture',
    });
  });

  const open = (quantities = [100, 9000]) =>
    renderWithProviders(
      <ToleraSourcePanel
        purchasedComponentId="pc-1"
        partName="Sechskantschraube M8x30"
        quantities={quantities}
        onClose={() => {}}
      />,
    );

  it('renders a price per quantity break, formatted from minor units', async () => {
    await open();

    // 100 x 19 cents = 19,00 €; 9000 x 13 cents = 1.170,00 €
    expect(await screen.findByText('0,19 €')).toBeInTheDocument();
    expect(screen.getByText('1.170,00 €')).toBeInTheDocument();
    expect(availability).toHaveBeenCalledWith('pc-1', [100, 9000]);
  });

  it('shows the inventory verdict per break', async () => {
    await open();

    expect(await screen.findByText('Verfügbar')).toBeInTheDocument();
    expect(screen.getByText('Bestand knapp')).toBeInTheDocument();
  });

  it('says the supplier price is a suggestion, not a costing change', async () => {
    await open();

    expect(await screen.findByText(/Vorschläge/)).toBeInTheDocument();
  });

  it('degrades to a badge — never an error — when the supplier is unreachable', async () => {
    availability.mockResolvedValue({
      supplier: 'wuerth',
      degraded: true,
      item: { ...PRICED.item, found: false, currency: '', quotes: [] },
    });

    await open();

    expect(await screen.findByRole('status')).toHaveTextContent(/nicht verfügbar/);
    expect(screen.queryByRole('table')).not.toBeInTheDocument();
  });

  it('degrades the same way when the lookup call itself rejects', async () => {
    availability.mockRejectedValue(new Error('offline'));

    await open();

    expect(await screen.findByRole('status')).toHaveTextContent(/nicht verfügbar/);
  });

  it('reports an uncatalogued part without pretending it has no price', async () => {
    availability.mockResolvedValue({
      supplier: 'wuerth',
      degraded: false,
      item: { ...PRICED.item, found: false, quotes: [] },
    });

    await open();

    expect(await screen.findByRole('status')).toHaveTextContent(/nicht gelistet/);
  });

  it('sends an RFQ for the shown quantities and confirms with the reference', async () => {
    await open();
    await screen.findByRole('table');

    await userEvent.click(screen.getByRole('button', { name: 'Anfrage senden' }));

    expect(sendRfq).toHaveBeenCalledWith({
      purchased_component_ids: ['pc-1'],
      quantities: [100, 9000],
    });
    expect(await screen.findByText(/TS-RFQ-abc/)).toBeInTheDocument();
  });

  it('labels a fixture-mode send so it is not mistaken for a real one', async () => {
    await open();
    await screen.findByRole('table');

    await userEvent.click(screen.getByRole('button', { name: 'Anfrage senden' }));

    expect(await screen.findByText(/Testmodus/)).toBeInTheDocument();
  });

  it('shows a quantity the supplier does not quote instead of dropping the row', async () => {
    availability.mockResolvedValue({
      ...PRICED,
      item: {
        ...PRICED.item,
        quotes: [
          { quantity: 1, unit_price_minor: null, extended_price_minor: null, status: 'available' },
        ],
      },
    });

    await open([1]);

    expect(await screen.findAllByText('kein Preis')).toHaveLength(2);
  });

  it('surfaces a failed send instead of silently claiming success', async () => {
    sendRfq.mockRejectedValue(new Error('503'));
    await open();
    await screen.findByRole('table');

    await userEvent.click(screen.getByRole('button', { name: 'Anfrage senden' }));

    expect(await screen.findByRole('alert')).toHaveTextContent(/nicht gesendet/);
  });
});
