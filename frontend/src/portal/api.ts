/**
 * Buyer-portal API (M5.1). The Digital Quote page is PUBLIC and unauthenticated:
 * the null token getter sends no Authorization header (the shared `apiFetch`
 * seam supports it). A plain function (not a hook) so feature tests can
 * `vi.mock('./api')` wholesale. A non-OK response surfaces as `ApiError`
 * (401 = invalid/revoked link).
 */

import { apiFetch } from '../api/client';
import type { BuyerQuote } from './types';

export function fetchBuyerQuote(token: string): Promise<BuyerQuote> {
  return apiFetch<BuyerQuote>(
    `/api/public/quotes/${encodeURIComponent(token)}`,
    () => Promise.resolve(null),
  );
}
