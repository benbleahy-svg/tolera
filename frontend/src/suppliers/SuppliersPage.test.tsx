import { beforeEach, describe, expect, it, vi } from 'vitest';
import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { makeMe, renderWithProviders } from '../test/render';
import { SuppliersPage } from './SuppliersPage';

const listVendors = vi.fn();

// Mock the vendors API module so the page never touches Clerk/network (the test
// render helper is deliberately Clerk-free).
vi.mock('./api', () => ({
  useVendorsApi: () => ({ listVendors }),
}));

function vendor(name: string, extra: Record<string, unknown> = {}) {
  return {
    id: `ven-${name}`,
    name,
    address: null,
    vat_id: null,
    phone: null,
    website: null,
    erp_vendor_id: null,
    erp_managed: false,
    status: 'active',
    capabilities: { processes: [], materials: [] },
    notes: null,
    active_rfq_count: 0,
    archived: false,
    created_at: '2026-07-19T00:00:00Z',
    updated_at: '2026-07-19T00:00:00Z',
    ...extra,
  };
}

describe('SuppliersPage', () => {
  beforeEach(() => {
    listVendors.mockReset();
  });

  it('lists the spec columns — name, capability chips and the active-RFQ count', async () => {
    listVendors.mockResolvedValue([
      vendor('Eloxal Werk Ost', {
        capabilities: { processes: ['anodize'], materials: ['aluminium'] },
        active_rfq_count: 0,
      }),
      vendor('Härterei Nord'),
    ]);
    await renderWithProviders(<SuppliersPage />, { route: '/suppliers' });

    expect(await screen.findByText('Eloxal Werk Ost')).toBeInTheDocument();
    expect(screen.getByText('Härterei Nord')).toBeInTheDocument();
    expect(screen.getByText('anodize')).toBeInTheDocument();
    expect(screen.getByText('aluminium')).toBeInTheDocument();
    // German-first headers.
    expect(screen.getByText('Offene Anfragen')).toBeInTheDocument();
  });

  it('marks archived vendors distinctly, even when they are still active', async () => {
    listVendors.mockResolvedValue([
      vendor('Alt-Lieferant', { archived: true }), // archived but status 'active'
      vendor('Ruhend', { status: 'inactive' }),
    ]);
    await renderWithProviders(<SuppliersPage />, { route: '/suppliers' });

    expect(await screen.findByText('Archiviert')).toBeInTheDocument();
    expect(screen.getByText('Inaktiv')).toBeInTheDocument();
  });

  it('passes the process filter through to the API', async () => {
    listVendors.mockResolvedValue([]);
    await renderWithProviders(<SuppliersPage />, { route: '/suppliers' });
    await screen.findByText('Noch keine Lieferanten.');

    await userEvent.type(screen.getByLabelText('Nach Verfahren filtern'), 'anodize');

    await vi.waitFor(() => {
      expect(listVendors).toHaveBeenCalledWith(expect.objectContaining({ process: 'anodize' }));
    });
  });

  it('shows ADD VENDOR for a config editor', async () => {
    listVendors.mockResolvedValue([]);
    await renderWithProviders(<SuppliersPage />, {
      me: makeMe({ effective_permissions: ['view_all', 'config_edit'], roles: ['admin'] }),
    });

    expect(await screen.findByText('Lieferant hinzufügen')).toBeInTheDocument();
  });

  it('hides ADD VENDOR without config_edit', async () => {
    listVendors.mockResolvedValue([]);
    await renderWithProviders(<SuppliersPage />, {
      me: makeMe({ effective_permissions: ['view_all'], roles: ['viewer'] }),
    });

    expect(await screen.findByText('Noch keine Lieferanten.')).toBeInTheDocument();
    expect(screen.queryByText('Lieferant hinzufügen')).not.toBeInTheDocument();
  });
});
