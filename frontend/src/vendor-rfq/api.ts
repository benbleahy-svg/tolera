/**
 * Vendor RFQ batch-send API types + the `useVendorRfqApi` hook (M6.4).
 *
 * Mirrors the FastAPI `/api/vendor-rfqs` contract: `compose` is everything the
 * modal renders (lines, files incl. redacted variants, ranked vendors), `sendBatch`
 * is the blind multi-send. Bound to the Clerk session token once, like
 * `suppliers/api.ts`; tests mock this module wholesale.
 *
 * Nothing here is vendor-facing — this is the estimator's side of the funnel. The
 * vendor sees only the M6.2 portal payload.
 */

import { useMemo } from 'react';
import { useAuth } from '@clerk/clerk-react';

import { apiFetch, type TokenGetter } from '../api/client';

export type CostingMode = 'make' | 'buy';

export interface ComposeFile {
  id: string;
  filename: string;
  size_bytes: number;
  /** An M2.4 redacted copy — pre-selected in place of its original. */
  is_redacted: boolean;
}

export interface ComposeLine {
  quote_item_id: string;
  part_number: string | null;
  revision: string | null;
  description: string | null;
  process: string | null;
  /** The outside-service steps this line needs quoted (drives vendor filtering). */
  outside_processes: string[];
  quantities: number[];
  costing_mode: CostingMode;
  export_controlled: boolean;
  files: ComposeFile[];
  default_file_ids: string[];
}

export interface ComposeVendor {
  id: string;
  name: string;
  /** Zero response history — rendered with the spec's **New** label, never hidden. */
  is_new: boolean;
  /** Pre-checked by the ranking (spec "AI-suggested vendors pre-checked"). */
  suggested: boolean;
  /** Why it ranked where it did — shown so a pre-check is explainable. */
  reasons: string[];
  process_match: boolean;
  material_match: boolean;
  contact_id: string | null;
  contact_email: string | null;
}

export interface ComposePayload {
  quote_id: string;
  required_processes: string[];
  lines: ComposeLine[];
  vendors: ComposeVendor[];
}

export interface SendRecipient {
  vendor_id: string;
  vendor_contact_id?: string | null;
  part_file_ids: string[];
}

export interface SendBatchBody {
  quote_id: string;
  quote_item_ids: string[];
  recipients: SendRecipient[];
  need_by_date?: string | null;
  message?: string | null;
  costing_mode?: CostingMode | null;
}

export interface SentRfq {
  rfq_id: string;
  number: string;
  status: string;
  vendor_id: string;
  vendor_name: string;
  contact_email: string | null;
  recipient_id: string;
  portal_token: string;
}

export interface VendorRfqApi {
  compose: (
    quoteId: string,
    quoteItemIds: string[],
    includeAllVendors?: boolean,
  ) => Promise<ComposePayload>;
  sendBatch: (body: SendBatchBody) => Promise<{ rfqs: SentRfq[] }>;
  setCostingMode: (
    quoteItemId: string,
    mode: CostingMode,
  ) => Promise<{ id: string; costing_mode: CostingMode }>;
}

export function useVendorRfqApi(): VendorRfqApi {
  const { getToken } = useAuth();
  return useMemo<VendorRfqApi>(() => {
    const token: TokenGetter = () => getToken();
    return {
      compose: (quoteId, quoteItemIds, includeAllVendors) => {
        const search = new URLSearchParams({ quote_id: quoteId });
        for (const id of quoteItemIds) search.append('quote_item_ids', id);
        if (includeAllVendors) search.set('include_all_vendors', 'true');
        return apiFetch(`/api/vendor-rfqs/compose?${search.toString()}`, token);
      },
      sendBatch: (body) => apiFetch('/api/vendor-rfqs/batch', token, { method: 'POST', body }),
      setCostingMode: (quoteItemId, mode) =>
        apiFetch(`/api/quote-items/${quoteItemId}/costing-mode`, token, {
          method: 'PATCH',
          body: { costing_mode: mode },
        }),
    };
  }, [getToken]);
}
