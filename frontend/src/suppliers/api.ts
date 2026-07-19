/**
 * Supplier Directory API types + the `useVendorsApi` hook (M6.3).
 *
 * Mirrors the FastAPI `/api/vendors` + `/api/vendor-contacts` contract. The hook
 * binds each call to the Clerk session token once, so pages call
 * `api.listVendors()` without threading auth through — and tests mock this module
 * wholesale (no Clerk), exactly as `contacts/api.ts` does.
 *
 * `notes` appears on `Vendor` because this is the **internal** contract. Nothing
 * vendor-facing is served from here: the portal/email payloads (M6.2/M6.4/M6.5)
 * render from the backend's `VendorExternalOut`, which cannot express notes.
 */

import { useMemo } from 'react';
import { useAuth } from '@clerk/clerk-react';

import { apiFetch, type TokenGetter } from '../api/client';

export type VendorStatus = 'active' | 'inactive';

export interface Capabilities {
  processes: string[];
  materials: string[];
}

export interface Vendor {
  id: string;
  name: string;
  address: string | null;
  vat_id: string | null;
  phone: string | null;
  website: string | null;
  erp_vendor_id: string | null;
  /** Identity is owned by the connected ERP — the UI renders those fields read-only. */
  erp_managed: boolean;
  status: VendorStatus;
  capabilities: Capabilities;
  notes: string | null;
  active_rfq_count: number;
  archived: boolean;
  created_at: string;
  updated_at: string;
}

export interface VendorContact {
  id: string;
  vendor_id: string;
  name: string | null;
  email: string;
  phone: string | null;
  is_primary: boolean;
  cc: boolean;
  created_at: string;
  updated_at: string;
}

export interface VendorContactCreate {
  email: string;
  name?: string | null;
  phone?: string | null;
  is_primary?: boolean;
  cc?: boolean;
}

export interface VendorCreate {
  name: string;
  address?: string | null;
  vat_id?: string | null;
  phone?: string | null;
  website?: string | null;
  status?: VendorStatus;
  capabilities?: Capabilities;
  notes?: string | null;
  primary_contact?: VendorContactCreate;
}

export interface VendorListParams {
  q?: string;
  process?: string;
  material?: string;
  status?: VendorStatus;
  includeArchived?: boolean;
}

/** One archived RFQ on the vendor's history tab — populated from M6.4 onward. */
export interface VendorRfqHistoryEntry {
  id: string;
  [key: string]: unknown;
}

export interface VendorsApi {
  listVendors: (params?: VendorListParams) => Promise<Vendor[]>;
  createVendor: (body: VendorCreate) => Promise<Vendor>;
  getVendor: (id: string) => Promise<Vendor>;
  updateVendor: (id: string, body: Partial<VendorCreate>) => Promise<Vendor>;
  archiveVendor: (id: string) => Promise<Vendor>;
  restoreVendor: (id: string) => Promise<Vendor>;
  listVendorContacts: (vendorId: string) => Promise<VendorContact[]>;
  createVendorContact: (vendorId: string, body: VendorContactCreate) => Promise<VendorContact>;
  updateVendorContact: (
    contactId: string,
    body: Partial<VendorContactCreate>,
  ) => Promise<VendorContact>;
  deleteVendorContact: (contactId: string) => Promise<void>;
  listRfqHistory: (vendorId: string) => Promise<VendorRfqHistoryEntry[]>;
}

function vendorsQuery(params?: VendorListParams): string {
  const search = new URLSearchParams();
  if (params?.q) search.set('q', params.q);
  if (params?.process) search.set('process', params.process);
  if (params?.material) search.set('material', params.material);
  if (params?.status) search.set('status', params.status);
  if (params?.includeArchived) search.set('include_archived', 'true');
  const qs = search.toString();
  return qs ? `?${qs}` : '';
}

/** Build a Supplier Directory client bound to the current Clerk session token. */
export function useVendorsApi(): VendorsApi {
  const { getToken } = useAuth();
  return useMemo<VendorsApi>(() => {
    const token: TokenGetter = () => getToken();
    return {
      listVendors: (params) => apiFetch(`/api/vendors${vendorsQuery(params)}`, token),
      createVendor: (body) => apiFetch('/api/vendors', token, { method: 'POST', body }),
      getVendor: (id) => apiFetch(`/api/vendors/${id}`, token),
      updateVendor: (id, body) => apiFetch(`/api/vendors/${id}`, token, { method: 'PATCH', body }),
      archiveVendor: (id) => apiFetch(`/api/vendors/${id}/archive`, token, { method: 'POST' }),
      restoreVendor: (id) => apiFetch(`/api/vendors/${id}/restore`, token, { method: 'POST' }),
      listVendorContacts: (vendorId) => apiFetch(`/api/vendors/${vendorId}/contacts`, token),
      createVendorContact: (vendorId, body) =>
        apiFetch(`/api/vendors/${vendorId}/contacts`, token, { method: 'POST', body }),
      updateVendorContact: (contactId, body) =>
        apiFetch(`/api/vendor-contacts/${contactId}`, token, { method: 'PATCH', body }),
      deleteVendorContact: (contactId) =>
        apiFetch(`/api/vendor-contacts/${contactId}`, token, { method: 'DELETE' }),
      listRfqHistory: (vendorId) => apiFetch(`/api/vendors/${vendorId}/rfq-history`, token),
    };
  }, [getToken]);
}
