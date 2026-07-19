import { beforeEach, describe, expect, it, vi } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { renderWithProviders } from '../test/render';
import { VendorRfqBatchModal } from './VendorRfqBatchModal';

const compose = vi.fn();
const sendBatch = vi.fn();

// One stable object, like the real hook (useMemo on getToken): the modal's compose
// effect keys on the api identity, so a per-render mock would refetch forever.
const API = { compose, sendBatch, setCostingMode: vi.fn() };
vi.mock('./api', () => ({ useVendorRfqApi: () => API }));

const LINE = {
  quote_item_id: 'item-1',
  part_number: 'BR-1042',
  revision: 'B',
  description: null,
  process: 'CNC',
  outside_processes: ['eloxieren'],
  quantities: [10, 50],
  costing_mode: 'make' as const,
  export_controlled: false,
  files: [
    { id: 'file-orig', filename: 'zeichnung.pdf', size_bytes: 10, is_redacted: false },
    { id: 'file-red', filename: 'zeichnung-redacted.pdf', size_bytes: 10, is_redacted: true },
  ],
  default_file_ids: ['file-red'],
};

const SUGGESTED = {
  id: 'ven-1',
  name: 'Eloxal Nord',
  is_new: false,
  suggested: true,
  reasons: ['process_match'],
  process_match: true,
  material_match: false,
  contact_id: 'con-1',
  contact_email: 'rfq@eloxal-nord.example',
};

const NEWCOMER = {
  ...SUGGESTED,
  id: 'ven-2',
  name: 'Eloxal Süd',
  is_new: true,
  suggested: false,
  contact_id: 'con-2',
  contact_email: 'rfq@eloxal-sued.example',
};

describe('VendorRfqBatchModal', () => {
  beforeEach(() => {
    compose.mockReset().mockResolvedValue({
      quote_id: 'quote-1',
      required_processes: ['eloxieren'],
      lines: [LINE],
      vendors: [SUGGESTED, NEWCOMER],
    });
    sendBatch.mockReset().mockResolvedValue({ rfqs: [{ rfq_id: 'rfq-1' }] });
  });

  const open = () =>
    renderWithProviders(
      <VendorRfqBatchModal
        quoteId="quote-1"
        quoteItemIds={['item-1']}
        onClose={() => {}}
        onSent={() => {}}
      />,
      { route: '/quotes/edit/quote-1/item-1' },
    );

  it('pre-checks the ranked suggestions and labels zero-history vendors New', async () => {
    await open();

    const suggested = await screen.findByRole('checkbox', { name: /Eloxal Nord/ });
    expect(suggested).toBeChecked();
    // A New vendor is shown, not hidden — and is not pre-checked here.
    const newcomer = screen.getByRole('checkbox', { name: /Eloxal Süd/ });
    expect(newcomer).not.toBeChecked();
    expect(screen.getByText('Neu')).toBeInTheDocument();
  });

  it('defaults a vendor to the redacted copy rather than the original drawing', async () => {
    await open();

    await screen.findByRole('checkbox', { name: /Eloxal Nord/ });
    expect(screen.getByRole('checkbox', { name: /zeichnung-redacted\.pdf/ })).toBeChecked();
    expect(screen.getByRole('checkbox', { name: /^zeichnung\.pdf/ })).not.toBeChecked();
  });

  it('sends one recipient per checked vendor, each with its own file allowlist', async () => {
    await open();

    await userEvent.click(await screen.findByRole('checkbox', { name: /Eloxal Süd/ }));
    await userEvent.click(screen.getAllByRole('button', { name: /senden/i }).slice(-1)[0]);

    await waitFor(() => expect(sendBatch).toHaveBeenCalled());
    const body = sendBatch.mock.calls[0][0];
    expect(body.quote_item_ids).toEqual(['item-1']);
    expect(body.recipients).toHaveLength(2);
    expect(body.recipients.map((r: { vendor_id: string }) => r.vendor_id)).toEqual([
      'ven-1',
      'ven-2',
    ]);
    // The per-vendor allowlist is what the token is minted from — never "all files".
    for (const recipient of body.recipients) {
      expect(recipient.part_file_ids).toEqual(['file-red']);
    }
  });

  it('cannot send with no vendor checked', async () => {
    compose.mockResolvedValue({
      quote_id: 'quote-1',
      required_processes: ['eloxieren'],
      lines: [LINE],
      vendors: [{ ...SUGGESTED, suggested: false }],
    });
    await open();

    await screen.findByRole('checkbox', { name: /Eloxal Nord/ });
    expect(screen.getAllByRole('button', { name: /senden/i }).slice(-1)[0]).toBeDisabled();
  });

  it('warns when a selected line is export-controlled', async () => {
    compose.mockResolvedValue({
      quote_id: 'quote-1',
      required_processes: ['eloxieren'],
      lines: [{ ...LINE, export_controlled: true }],
      vendors: [SUGGESTED],
    });
    await open();

    expect(await screen.findByRole('status')).toHaveTextContent(/exportkontrolliert/);
  });
});
