/**
 * Buyer-portal API (M5.1). The Digital Quote page is PUBLIC and unauthenticated:
 * the null token getter sends no Authorization header (the shared `apiFetch`
 * seam supports it). A plain function (not a hook) so feature tests can
 * `vi.mock('./api')` wholesale. A non-OK response surfaces as `ApiError`
 * (401 = invalid/revoked link).
 */

import { apiFetch } from '../api/client';
import type { BuyerQuote, CheckoutRequest, CheckoutResult } from './types';

const NO_TOKEN = () => Promise.resolve(null);

export function fetchBuyerQuote(token: string): Promise<BuyerQuote> {
  return apiFetch<BuyerQuote>(`/api/public/quotes/${encodeURIComponent(token)}`, NO_TOKEN);
}

/** Submit the PO checkout (M5.2). Public + unauthenticated (token in the path);
 *  the server re-derives all prices and creates the Order. */
export function submitCheckout(token: string, request: CheckoutRequest): Promise<CheckoutResult> {
  return apiFetch<CheckoutResult>(
    `/api/public/quotes/${encodeURIComponent(token)}/checkout`,
    NO_TOKEN,
    { method: 'POST', body: request },
  );
}
