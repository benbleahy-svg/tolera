/**
 * AssemblyComponentsSection (M4.10, spec #assembly): grouped rows with the
 * FLAT/CHILD BOM switch and rollup captions, the Component Summary, the ⋮
 * menu (convert only on manufactured rows), the Bulk Update modal with the
 * delete-operations warning, and the Smart Match convert modal (CONVERT
 * disabled until a match is selected; DemoL/03 indicators).
 */

import { describe, expect, it, vi } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { renderWithProviders } from '../test/render';
import AssemblyComponentsSection from './AssemblyComponentsSection';
import type { EstimatingApi } from './api';
import type { AssemblyComponentsOut, PurchaseMatchesOut } from './types';

const LISTING: AssemblyComponentsOut = {
  quantities: [1, 5],
  root_node_id: 'root-node',
  tree: [
    {
      node_id: 'n-a',
      part_id: 'p-a',
      component_id: 'c-a',
      part_number: 'A-1',
      revision: null,
      description: null,
      filename: 'a.step',
      group: 'manufactured',
      obtain_method: 'MANUFACTURED',
      is_assembly: false,
      node_qty: 2,
      flat_qty: 2,
      position: 0,
      process_id: null,
      material_id: null,
      piece_price: null,
      purchased_component_id: null,
      brand: null,
      self_costs: ['4.00', '20.00'],
      rollup_costs: ['4.00', '20.00'],
      children: [],
    },
    {
      node_id: 'n-s',
      part_id: 'p-s',
      component_id: 'c-s',
      part_number: 'S-1',
      revision: null,
      description: null,
      filename: 's.step',
      group: 'subassembly',
      obtain_method: 'MANUFACTURED',
      is_assembly: true,
      node_qty: 1,
      flat_qty: 1,
      position: 1,
      process_id: null,
      material_id: null,
      piece_price: null,
      purchased_component_id: null,
      brand: null,
      self_costs: ['0.00', '0.00'],
      rollup_costs: ['0.40', '2.00'],
      children: [
        {
          node_id: 'n-b',
          part_id: 'p-b',
          component_id: 'c-b',
          part_number: 'B-1',
          revision: null,
          description: null,
          filename: 'b.step',
          group: 'purchased',
          obtain_method: 'PURCHASED',
          is_assembly: false,
          node_qty: 4,
          flat_qty: 4,
          position: 0,
          process_id: null,
          material_id: null,
          piece_price: '0.1000',
          purchased_component_id: 'pc-1',
          brand: 'PEM',
          self_costs: ['0.40', '2.00'],
          rollup_costs: ['0.40', '2.00'],
          children: [],
        },
      ],
    },
  ],
  summary: { flat_qty_total: 7, totals: ['4.40', '22.00'] },
};

const MATCHES: PurchaseMatchesOut = {
  component: {
    id: 'c-a',
    part_number: 'A-1',
    revision: null,
    filename: 'a.step',
    obtain_method: 'MANUFACTURED',
    piece_price: null,
    purchased_component_id: null,
  },
  smart: [
    {
      purchased_component: {
        id: 'pc-9',
        oem_part_number: 'F-440-1',
        internal_part_number: 'f-440-1',
        piece_price: '0.1250',
        currency: 'EUR',
        description: null,
        brand: 'PEM',
        custom_fields: {},
        oem_product_id: null,
      },
      oem_part_number_match: true,
      oem_geometric_match: false,
      historical_geometric_matches: 21,
    },
  ],
  unlinked_oem: [],
  all: [],
};

function makeApi(): EstimatingApi {
  return {
    getAssemblyComponents: vi.fn().mockResolvedValue(LISTING),
    getPurchaseMatches: vi.fn().mockResolvedValue(MATCHES),
    convertToPurchased: vi.fn().mockResolvedValue({}),
    bulkUpdateComponents: vi.fn().mockResolvedValue({ updated: 2 }),
    listProcesses: vi
      .fn()
      .mockResolvedValue([{ id: 'proc-1', name: 'Tube Laser', external_name: null }]),
    listPurchasedComponents: vi.fn().mockResolvedValue([]),
    deleteComponent: vi.fn().mockResolvedValue({ deleted: true }),
    copyPricing: vi.fn().mockResolvedValue({ copied_operations: 1 }),
    reorderAssemblyComponents: vi.fn().mockResolvedValue({ reordered: 2 }),
    addPurchasedComponents: vi.fn().mockResolvedValue({ added: 1 }),
  } as unknown as EstimatingApi;
}

function renderSection(api: EstimatingApi) {
  return renderWithProviders(
    <AssemblyComponentsSection
      api={api}
      quoteItemId="item-1"
      editable
      formatMoney={(v) => (v == null ? '—' : `${v} €`)}
    />,
  );
}

describe('AssemblyComponentsSection', () => {
  it('renders groups, rollup caption, brand chip and the summary', async () => {
    renderSection(makeApi());
    expect(await screen.findByText('Unterbaugruppen (1)')).toBeInTheDocument();
    expect(screen.getByText('Fertigungsteile (1)')).toBeInTheDocument();
    expect(screen.getByText('Kaufteile (1)')).toBeInTheDocument();
    // CHILD BOM default: rollup caption + per-break rollup costs
    expect(
      screen.getByText('Kosten inkl. Unterkomponenten (Roll-up zum Elternteil)'),
    ).toBeInTheDocument();
    expect(screen.getByText('PEM')).toBeInTheDocument();
    expect(screen.getByText('Komponenten-Summe')).toBeInTheDocument();
    expect(screen.getByText('4.40 €')).toBeInTheDocument();
    expect(screen.getByText('22.00 €')).toBeInTheDocument();
  });

  it('switches to FLAT BOM with the no-rollup caption', async () => {
    renderSection(makeApi());
    await screen.findByText('Fertigungsteile (1)');
    await userEvent.click(screen.getByRole('tab', { name: 'FLACHE STÜCKLISTE' }));
    expect(screen.getByText('Kosten ohne Roll-up')).toBeInTheDocument();
  });

  it('offers convert only on manufactured rows and gates CONVERT on selection', async () => {
    const api = makeApi();
    renderSection(api);
    await screen.findByText('Fertigungsteile (1)');
    // purchased row (B-1): menu has no convert entry
    await userEvent.click(screen.getByRole('button', { name: 'Menü für B-1' }));
    expect(screen.queryByRole('menuitem', { name: 'In Kaufteil umwandeln' })).toBeNull();
    // manufactured row (A-1): convert opens Smart Match
    await userEvent.click(screen.getByRole('button', { name: 'Menü für A-1' }));
    await userEvent.click(screen.getByRole('menuitem', { name: 'In Kaufteil umwandeln' }));
    await screen.findByText('Bereits verwendete Kaufteile');
    // DemoL/03 indicators incl. the historical count
    expect(screen.getByText(/OEM-Teilenummer stimmt überein/)).toBeInTheDocument();
    expect(screen.getByText(/Frühere Geometrie-Treffer \(21\)/)).toBeInTheDocument();
    const cta = screen.getByRole('button', { name: 'UMWANDELN' });
    expect(cta).toBeDisabled();
    await userEvent.click(screen.getByRole('radio'));
    expect(cta).toBeEnabled();
    await userEvent.click(cta);
    await waitFor(() =>
      expect(api.convertToPurchased).toHaveBeenCalledWith('c-a', {
        purchased_component_id: 'pc-9',
      }),
    );
  });

  it('bulk update shows the delete-operations warning and submits the selection', async () => {
    const api = makeApi();
    renderSection(api);
    await screen.findByText('Fertigungsteile (1)');
    await userEvent.click(screen.getByRole('checkbox', { name: 'A-1 auswählen' }));
    await userEvent.click(screen.getByRole('checkbox', { name: 'B-1 auswählen' }));
    await userEvent.click(screen.getByRole('button', { name: 'MASSEN-BEARBEITUNG' }));
    expect(
      await screen.findByText('Diese Aktion löscht alle vorhandenen Arbeitsgänge.'),
    ).toBeInTheDocument();
    const confirm = screen.getByRole('button', { name: 'BESTÄTIGEN' });
    expect(confirm).toBeDisabled();
    await userEvent.selectOptions(await screen.findByRole('combobox'), 'proc-1');
    await userEvent.click(confirm);
    await waitFor(() =>
      expect(api.bulkUpdateComponents).toHaveBeenCalledWith(
        expect.arrayContaining(['c-a', 'c-b']),
        'proc-1',
        null,
      ),
    );
  });
});
