/**
 * BOM Builder modal (M4.9 — DemoD/07–11): extraction seeds editable rows, the
 * Add-Files banner applies title-block matches, the purple sparkle accepts a
 * child BOM (counter climbs), CHECK BOM surfaces issues without committing,
 * and CHECK AND PUBLISH is the only committing action.
 */

import { describe, expect, it, vi } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { renderWithProviders } from '../test/render';
import type { BomApi } from './api';
import { BomBuilderModal } from './BomBuilderModal';
import type { BuilderState } from './types';

function builderState(over: Partial<BuilderState> = {}): BuilderState {
  return {
    quote_item_id: 'qi-1',
    root_part_id: 'p-root',
    root_component_id: 'c-root',
    draft: null,
    initial: {
      schema_version: 1,
      root: {
        row_id: 'root',
        row_type: 'assembly_root',
        part_number: '002-00001',
        revision: '000',
        description: null,
        qty: 1,
        primary_file_id: 'f-root',
        supporting_file_ids: [],
        children: [
          {
            row_id: 'x-1',
            row_type: 'manufactured',
            part_number: '002-00008-000',
            revision: '000',
            description: 'Frame weldment',
            qty: 1,
            primary_file_id: null,
            supporting_file_ids: [],
            children: [],
          },
          {
            row_id: 'x-2',
            row_type: 'purchased',
            part_number: '002-00006-000',
            revision: null,
            description: 'Hex nut M6',
            qty: 16,
            primary_file_id: null,
            supporting_file_ids: [],
            children: [],
          },
        ],
      },
    },
    suggestion: { finding_id: 'find-1', file_id: 'f-root', filename: 'assembly.pdf', page: 1 },
    quote_files: [
      {
        id: 'f-root',
        part_id: 'p-root',
        filename: 'assembly.pdf',
        role: 'primary',
        part_number_extracted: null,
        has_bom_table: true,
      },
      {
        id: 'f-sub',
        part_id: 'p-root',
        filename: '002-00008-000 drawing.pdf',
        role: 'supporting',
        part_number_extracted: '002-00008-000',
        has_bom_table: true,
      },
    ],
    child_suggestions: [
      {
        finding_id: 'find-2',
        file_id: 'f-sub',
        page: 1,
        root_part_number: '002-00008-000',
        rows: [
          {
            item_no: '1',
            part_number: '002-00009-000',
            revision: '000',
            qty: 2,
            description: 'Corner bracket',
            type_hint: null,
          },
          {
            item_no: '2',
            part_number: '002-00006-000',
            revision: null,
            qty: 14,
            description: 'Hex nut M6',
            type_hint: 'purchased',
          },
        ],
      },
    ],
    unique_parts: 3,
    cap: 1000,
    ...over,
  };
}

function makeApi(state: BuilderState): BomApi {
  return {
    getBuilderState: vi.fn().mockResolvedValue(state),
    saveDraft: vi
      .fn()
      .mockResolvedValue({ updated_at: '2026-07-17T12:00:00Z', unique_parts: 3 }),
    discardDraft: vi.fn().mockResolvedValue(undefined),
    checkBom: vi.fn().mockResolvedValue({ errors: [], notices: [], unique_parts: 3 }),
    publishBom: vi.fn().mockResolvedValue({ tree: { children: [] } }),
    getBomStatus: vi.fn().mockResolvedValue({
      suggestion: null,
      has_children: false,
      has_draft: false,
    }),
  };
}

function setup(state = builderState()) {
  const api = makeApi(state);
  const onPublished = vi.fn();
  const onClose = vi.fn();
  renderWithProviders(
    <BomBuilderModal quoteItemId="qi-1" api={api} onPublished={onPublished} onClose={onClose} />,
  );
  return { api, onPublished, onClose };
}

describe('BomBuilderModal', () => {
  it('seeds the grid from the extracted root BOM and shows the counter', async () => {
    setup();
    expect(await screen.findByDisplayValue('002-00008-000')).toBeInTheDocument();
    expect(screen.getByDisplayValue('002-00006-000')).toBeInTheDocument();
    // 3 unique parts (root + 2 children), cap 1000.
    expect(screen.getByText('3')).toBeInTheDocument();
    expect(screen.getByText(/\/1000/)).toBeInTheDocument();
  });

  it('applies Add-Files matches from the purple banner', async () => {
    const { api } = setup();
    const accept = await screen.findByRole('button', { name: /zuordnen/i });
    // "1 quote file matches 1 part" — only the sub drawing pairs.
    expect(screen.getByText(/1(.+)1/)).toBeInTheDocument();
    await userEvent.click(accept);
    // The matched drawing now ALSO shows as the row's primary-file chip
    // (the Quote Files pane already listed it once).
    await waitFor(() =>
      expect(screen.getAllByText('002-00008-000 drawing.pdf')).toHaveLength(2),
    );
    // The edit autosaves the draft (debounced).
    await waitFor(() => expect(api.saveDraft).toHaveBeenCalled(), { timeout: 3000 });
  });

  it('accepts a child BOM via the sparkle: nested rows + counter climbs', async () => {
    setup();
    const accept = await screen.findByRole('button', { name: /zuordnen/i });
    await userEvent.click(accept);
    const sparkle = await screen.findByRole('button', {
      name: /unterbaugruppen-vorschlag/i,
    });
    await userEvent.click(sparkle);
    expect(await screen.findByDisplayValue('002-00009-000')).toBeInTheDocument();
    // The shared hex nut links as ONE part: root + sub + nut + bracket = 4.
    expect(screen.getByText('4')).toBeInTheDocument();
    // The accepted row became a subassembly.
    const typeSelects = screen.getAllByLabelText(/typ/i);
    expect((typeSelects[0] as HTMLSelectElement).value).toBe('subassembly');
  });

  it('CHECK BOM surfaces errors without publishing', async () => {
    const state = builderState();
    const api = makeApi(state);
    (api.checkBom as ReturnType<typeof vi.fn>).mockResolvedValue({
      errors: [{ code: 'row_incomplete', message: 'Zeile 3 ist unvollständig.', row_ids: [] }],
      notices: [],
      unique_parts: 3,
    });
    renderWithProviders(
      <BomBuilderModal quoteItemId="qi-1" api={api} onPublished={vi.fn()} onClose={vi.fn()} />,
    );
    await screen.findByDisplayValue('002-00008-000');
    await userEvent.click(screen.getByRole('button', { name: 'STÜCKLISTE PRÜFEN' }));
    expect(await screen.findByText('Zeile 3 ist unvollständig.')).toBeInTheDocument();
    expect(api.publishBom).not.toHaveBeenCalled();
  });

  it('CHECK AND PUBLISH publishes the current document', async () => {
    const { api, onPublished } = setup();
    await screen.findByDisplayValue('002-00008-000');
    await userEvent.click(screen.getByRole('button', { name: 'PRÜFEN UND VERÖFFENTLICHEN' }));
    await waitFor(() => expect(onPublished).toHaveBeenCalled());
    const sent = (api.publishBom as ReturnType<typeof vi.fn>).mock.calls[0];
    expect(sent[0]).toBe('qi-1');
    expect(sent[1].root.children).toHaveLength(2);
  });

  it('undo reverts the last edit', async () => {
    setup();
    const accept = await screen.findByRole('button', { name: /zuordnen/i });
    await userEvent.click(accept);
    await waitFor(() =>
      expect(screen.getAllByText('002-00008-000 drawing.pdf')).toHaveLength(2),
    );
    await userEvent.click(screen.getByRole('button', { name: 'RÜCKGÄNGIG' }));
    await waitFor(() =>
      expect(screen.getAllByText('002-00008-000 drawing.pdf')).toHaveLength(1),
    );
  });
});
