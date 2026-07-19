import { beforeEach, describe, expect, it, vi } from 'vitest';
import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { makeMe, renderWithProviders } from '../test/render';
import { VendorDetailPage } from './VendorDetailPage';

const getVendor = vi.fn();
const listVendorContacts = vi.fn();
const listRfqHistory = vi.fn();
const updateVendor = vi.fn();

vi.mock('./api', () => ({
  useVendorsApi: () => ({ getVendor, listVendorContacts, listRfqHistory, updateVendor }),
}));

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>('react-router-dom');
  return { ...actual, useParams: () => ({ vendorId: 'ven-1' }) };
});

function vendor(extra: Record<string, unknown> = {}) {
  return {
    id: 'ven-1',
    name: 'Galvanik Süd',
    address: 'Südring 9\n70565 Stuttgart',
    vat_id: 'DE123456789',
    phone: null,
    website: null,
    erp_vendor_id: null,
    erp_managed: false,
    status: 'active',
    capabilities: { processes: ['plating'], materials: ['steel'] },
    notes: 'Interner Vermerk.',
    active_rfq_count: 0,
    archived: false,
    created_at: '2026-07-19T00:00:00Z',
    updated_at: '2026-07-19T00:00:00Z',
    ...extra,
  };
}

describe('VendorDetailPage', () => {
  beforeEach(() => {
    getVendor.mockReset().mockResolvedValue(vendor());
    listVendorContacts.mockReset().mockResolvedValue([
      {
        id: 'c-1',
        vendor_id: 'ven-1',
        name: 'Bernd Klose',
        email: 'klose@galvanik-sued.example',
        phone: null,
        is_primary: true,
        cc: false,
        created_at: '2026-07-19T00:00:00Z',
        updated_at: '2026-07-19T00:00:00Z',
      },
    ]);
    listRfqHistory.mockReset().mockResolvedValue([]);
    updateVendor.mockReset().mockResolvedValue(vendor());
  });

  it('renders the four spec tabs and the Overview contacts', async () => {
    await renderWithProviders(<VendorDetailPage />, { route: '/suppliers/ven-1' });

    expect(await screen.findByRole('tab', { name: 'Übersicht' })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: 'Anfragehistorie' })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: 'Fähigkeiten' })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: 'Notizen' })).toBeInTheDocument();
    expect(screen.getByText(/klose@galvanik-sued\.example/)).toBeInTheDocument();
    expect(screen.getByDisplayValue('DE123456789')).toBeInTheDocument();
  });

  it('labels the Notes tab as internal-only', async () => {
    await renderWithProviders(<VendorDetailPage />, { route: '/suppliers/ven-1' });
    await userEvent.click(await screen.findByRole('tab', { name: 'Notizen' }));

    expect(
      screen.getByText('Interne Notizen — für den Lieferanten nie sichtbar.'),
    ).toBeInTheDocument();
    expect(screen.getByDisplayValue('Interner Vermerk.')).toBeInTheDocument();
  });

  it('shows the RFQ-History empty state until M6.4 populates it', async () => {
    await renderWithProviders(<VendorDetailPage />, { route: '/suppliers/ven-1' });
    await userEvent.click(await screen.findByRole('tab', { name: 'Anfragehistorie' }));

    expect(screen.getByText('Noch keine Anfragen an diesen Lieferanten.')).toBeInTheDocument();
  });

  it('explains that an ERP-sourced vendor is maintained in the ERP', async () => {
    getVendor.mockResolvedValue(vendor({ erp_vendor_id: 'ERP-4711', erp_managed: true }));
    await renderWithProviders(<VendorDetailPage />, { route: '/suppliers/ven-1' });

    expect(await screen.findByRole('note')).toHaveTextContent('ERP-4711');
  });

  it('locks an ERP vendor’s identity fields but keeps capabilities editable', async () => {
    getVendor.mockResolvedValue(vendor({ erp_vendor_id: 'ERP-4711', erp_managed: true }));
    await renderWithProviders(<VendorDetailPage />, {
      route: '/suppliers/ven-1',
      me: makeMe({ effective_permissions: ['view_all', 'config_edit'], roles: ['admin'] }),
    });

    // Identity is ERP-owned — disabled, and no save action on the Overview tab.
    expect(await screen.findByDisplayValue('Galvanik Süd')).toBeDisabled();
    expect(screen.getByDisplayValue('DE123456789')).toBeDisabled();
    expect(screen.queryByRole('button', { name: 'Speichern' })).not.toBeInTheDocument();

    // BF-only data never writes back to the ERP, so it stays editable.
    await userEvent.click(screen.getByRole('tab', { name: 'Fähigkeiten' }));
    expect(screen.getByDisplayValue('plating')).toBeEnabled();
    expect(screen.getByRole('button', { name: 'Speichern' })).toBeInTheDocument();
  });

  it('saves edited identity fields on a manually created vendor', async () => {
    await renderWithProviders(<VendorDetailPage />, {
      route: '/suppliers/ven-1',
      me: makeMe({ effective_permissions: ['view_all', 'config_edit'], roles: ['admin'] }),
    });

    const vatId = await screen.findByDisplayValue('DE123456789');
    await userEvent.clear(vatId);
    await userEvent.type(vatId, 'DE999999999');
    await userEvent.click(screen.getByRole('button', { name: 'Speichern' }));

    expect(updateVendor).toHaveBeenCalledWith(
      'ven-1',
      expect.objectContaining({ vat_id: 'DE999999999', name: 'Galvanik Süd' }),
    );
  });

  it('saves edited capability tags', async () => {
    await renderWithProviders(<VendorDetailPage />, {
      route: '/suppliers/ven-1',
      me: makeMe({ effective_permissions: ['view_all', 'config_edit'], roles: ['admin'] }),
    });
    await userEvent.click(await screen.findByRole('tab', { name: 'Fähigkeiten' }));

    const processes = screen.getByDisplayValue('plating');
    await userEvent.clear(processes);
    await userEvent.type(processes, 'plating, anodize');
    await userEvent.click(screen.getByRole('button', { name: 'Speichern' }));

    expect(updateVendor).toHaveBeenCalledWith('ven-1', {
      capabilities: { processes: ['plating', 'anodize'], materials: ['steel'] },
    });
  });

  it('hides the save action without config_edit', async () => {
    await renderWithProviders(<VendorDetailPage />, {
      route: '/suppliers/ven-1',
      me: makeMe({ effective_permissions: ['view_all'], roles: ['viewer'] }),
    });
    await userEvent.click(await screen.findByRole('tab', { name: 'Fähigkeiten' }));

    expect(screen.queryByRole('button', { name: 'Speichern' })).not.toBeInTheDocument();
  });
});
