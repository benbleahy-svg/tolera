/**
 * Bulk Create Line Items dialog (M3.4 — DemoB/04): prefilled spreadsheet from
 * the Lens suggestion payload, purple autofill banner + ORIGINAL RFQ chip,
 * ADD ROW, and the explicit Accept mapping rows to the editable columns only.
 */

import { describe, expect, it, vi } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { renderWithProviders } from '../test/render';
import { BulkCreateDialog } from './BulkCreateDialog';
import type { BulkCreatePrefill, QuoteSummary } from './types';

function prefill(over: Partial<BulkCreatePrefill> = {}): BulkCreatePrefill {
  return {
    status: 'completed',
    found_in: 'original-rfq.eml',
    rfq_files: [{ filename: 'original-rfq.eml', original_rfq: true }],
    rows: [
      {
        part_number: '3601215',
        revision: null,
        description: 'OFFSET CONNECTOR',
        quantities: [1, 5, 20],
        requested_date: null,
        confidence: 0.9,
        matched_part_id: 'p-1',
        matched_filenames: ['3601215_OFFSET CONNECTOR.pdf'],
      },
      {
        part_number: 'PP-330-410',
        revision: null,
        description: null,
        quantities: [10, 25],
        requested_date: null,
        confidence: 0.9,
        matched_part_id: null,
        matched_filenames: [],
      },
    ],
    ...over,
  };
}

const quoteAfter = { id: 'q1', items: [{}, {}] } as unknown as QuoteSummary;

function setup(data: BulkCreatePrefill) {
  const getPrefill = vi.fn().mockResolvedValue(data);
  const create = vi.fn().mockResolvedValue(quoteAfter);
  const onCreated = vi.fn();
  const onClose = vi.fn();
  renderWithProviders(
    <BulkCreateDialog
      quoteId="q1"
      getPrefill={getPrefill}
      create={create}
      onCreated={onCreated}
      onClose={onClose}
    />,
  );
  return { getPrefill, create, onCreated, onClose };
}

describe('BulkCreateDialog', () => {
  it('prefills the spreadsheet and shows the autofill banner + ORIGINAL RFQ chip', async () => {
    setup(prefill());
    // German-first: the banner + chip render from the suggestion payload.
    expect(await screen.findByText(/automatisch ausgefüllt/i)).toBeInTheDocument();
    expect(screen.getByText(/Gefunden in original-rfq.eml/i)).toBeInTheDocument();
    expect(screen.getByText('ORIGINAL-RFQ')).toBeInTheDocument();
    expect(screen.getByDisplayValue('3601215')).toBeInTheDocument();
    expect(screen.getByDisplayValue('1, 5, 20')).toBeInTheDocument();
    expect(screen.getByDisplayValue('PP-330-410')).toBeInTheDocument();
  });

  it('accepts only on the explicit button, mapping editable columns', async () => {
    const { create, onCreated } = setup(prefill());
    await screen.findByDisplayValue('3601215');
    expect(create).not.toHaveBeenCalled(); // nothing happens before Accept
    await userEvent.click(screen.getByRole('button', { name: /Positionen anlegen/i }));
    await waitFor(() => expect(onCreated).toHaveBeenCalledWith(quoteAfter));
    expect(create).toHaveBeenCalledWith('q1', [
      {
        part_number: '3601215',
        revision: null,
        description: 'OFFSET CONNECTOR',
        quantities: [1, 5, 20],
        matched_part_id: 'p-1',
      },
      {
        part_number: 'PP-330-410',
        revision: null,
        description: null,
        quantities: [10, 25],
        matched_part_id: null,
      },
    ]);
  });

  it('drops the reviewed binding when the part number is edited', async () => {
    const { create } = setup(prefill());
    const input = await screen.findByDisplayValue('3601215');
    await userEvent.type(input, '-B');
    await userEvent.click(screen.getByRole('button', { name: /Positionen anlegen/i }));
    await waitFor(() => expect(create).toHaveBeenCalled());
    const rows = create.mock.calls[0][1];
    expect(rows[0].part_number).toBe('3601215-B');
    expect(rows[0].matched_part_id).toBeNull(); // edited → binding invalidated
  });

  it('parses German grouped quantities ("1.000" is 1000, never 1)', async () => {
    const { create } = setup(prefill({ rows: [], status: 'none', found_in: null, rfq_files: [] }));
    await waitFor(() => expect(screen.getAllByRole('row')).toHaveLength(2));
    await userEvent.type(screen.getByLabelText(/Teilenummer, Zeile 1/i), 'X-1');
    await userEvent.type(screen.getByLabelText(/Stückzahlen, Zeile 1/i), "1.000, 2'500, 5");
    await userEvent.click(screen.getByRole('button', { name: /Positionen anlegen/i }));
    await waitFor(() => expect(create).toHaveBeenCalled());
    expect(create.mock.calls[0][1][0].quantities).toEqual([5, 1000, 2500]);
  });

  it('adds an editable row and sends blank quantities as empty (server defaults to 1)', async () => {
    const { create } = setup(prefill({ rows: [], status: 'none', found_in: null, rfq_files: [] }));
    await waitFor(() => expect(screen.getAllByRole('row')).toHaveLength(2)); // head + 1
    const submit = screen.getByRole('button', { name: /Positionen anlegen/i });
    expect(submit).toBeDisabled(); // no part number yet
    await userEvent.type(screen.getByLabelText(/Teilenummer, Zeile 1/i), 'X-99');
    await userEvent.click(screen.getByRole('button', { name: /Zeile hinzufügen/i }));
    expect(screen.getAllByRole('row')).toHaveLength(3);
    await userEvent.click(submit);
    await waitFor(() =>
      expect(create).toHaveBeenCalledWith('q1', [
        {
          part_number: 'X-99',
          revision: null,
          description: null,
          quantities: [],
          matched_part_id: null,
        },
      ]),
    );
  });

  it('shows the manual-entry note when the parse failed', async () => {
    setup(prefill({ status: 'failed', rows: [] }));
    expect(await screen.findByText(/manuell erfassen/i)).toBeInTheDocument();
  });
});
