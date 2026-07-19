/**
 * Tolera Source (Würth) sourcing API types + the `useSourcingApi` hook (M6.7).
 *
 * Mirrors the FastAPI `/api/sourcing` contract. Prices arrive as integer minor
 * units plus the supplier's own currency — format with `formatMinor`, never
 * arithmetic on a float.
 *
 * `degraded: true` is the supplier-unreachable answer, not an error: the panel
 * shows a badge and the page keeps costing (spec `#sourcing-adapters`).
 */

import { useMemo } from 'react';
import { useAuth } from '@clerk/clerk-react';

import { apiFetch, type TokenGetter } from '../api/client';

export type AvailabilityStatus = 'available' | 'at_risk' | 'insufficient' | 'unknown';

export interface QuantityQuote {
  quantity: number;
  /** Minor units (cents) of `AvailabilityItem.currency`. */
  unit_price_minor: number;
  extended_price_minor: number;
  status: AvailabilityStatus;
}

export interface AvailabilityItem {
  oem_part_number: string;
  found: boolean;
  currency: string;
  description: string | null;
  brand: string | null;
  quantity_available: number | null;
  lead_time_days: number | null;
  quotes: QuantityQuote[];
}

export interface AvailabilityOut {
  supplier: string;
  degraded: boolean;
  item: AvailabilityItem;
}

export interface SourcingRfqOut {
  supplier: string;
  reference: string;
  accepted: boolean;
  supplier_reference: string | null;
  estimated_response_hours: number | null;
}

function makeApi(getToken: TokenGetter) {
  return {
    availability: (purchasedComponentId: string, quantities: number[]) =>
      apiFetch<AvailabilityOut>(
        `/api/sourcing/purchased-components/${purchasedComponentId}/availability` +
          `?quantities=${quantities.join(',')}`,
        getToken,
      ),
    sendRfq: (body: {
      purchased_component_ids: string[];
      quantities: number[];
      message?: string;
    }) =>
      apiFetch<SourcingRfqOut>('/api/sourcing/rfq', getToken, {
        method: 'POST',
        body,
      }),
  };
}

export type SourcingApi = ReturnType<typeof makeApi>;

export function useSourcingApi(): SourcingApi {
  const { getToken } = useAuth();
  return useMemo(() => makeApi(getToken), [getToken]);
}
