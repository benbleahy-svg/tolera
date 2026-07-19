/**
 * Vendor-RFQ portal API (M6.2). The page is PUBLIC and unauthenticated: the null
 * token getter sends no Authorization header (the shared `apiFetch` seam supports
 * it), and the RFQ token in the path is the only credential. Plain functions (not
 * hooks) so feature tests can `vi.mock('./api')` wholesale. A non-OK response
 * surfaces as `ApiError` (401 = invalid/revoked link).
 */

import { apiFetch } from '../api/client';
import type { VendorRfq, VendorResponseRequest, VendorResponseResult } from './types';

const NO_TOKEN = () => Promise.resolve(null);

export function fetchVendorRfq(token: string): Promise<VendorRfq> {
  return apiFetch<VendorRfq>(`/api/public/vendor-rfq/${encodeURIComponent(token)}`, NO_TOKEN);
}

export function submitVendorResponse(
  token: string,
  request: VendorResponseRequest,
): Promise<VendorResponseResult> {
  return apiFetch<VendorResponseResult>(
    `/api/public/vendor-rfq/${encodeURIComponent(token)}/response`,
    NO_TOKEN,
    { method: 'POST', body: request },
  );
}

/** The RFQ record sheet + a granted drawing — plain links, streamed by the server. */
export function vendorPdfUrl(token: string): string {
  return `/api/public/vendor-rfq/${encodeURIComponent(token)}/pdf`;
}

export function vendorFileUrl(token: string, fileId: string): string {
  return `/api/public/vendor-rfq/${encodeURIComponent(token)}/files/${encodeURIComponent(fileId)}`;
}
