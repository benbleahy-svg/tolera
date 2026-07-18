/**
 * Orders-list + detail API (M5.6). `useOrdersApi` binds each call to the Clerk
 * session token once (the M1.3 `useQuotesApi` pattern); pages call it without
 * threading auth, and tests mock this module wholesale (no Clerk).
 *
 * The order PDF is a binary download (the M5.4 `GET /api/orders/:id/pdf`), so it
 * goes through `apiDownload` (blob), not the JSON `apiFetch`.
 */

import { useMemo } from 'react';
import { useAuth } from '@clerk/clerk-react';

import { apiDownload, apiFetch, type TokenGetter } from '../api/client';
import type {
  ErpPushResult,
  OrderDetail,
  OrderSearchRequest,
  OrderSearchResponse,
} from './types';

export interface OrdersApi {
  searchOrders: (req: OrderSearchRequest) => Promise<OrderSearchResponse>;
  getOrder: (id: string) => Promise<OrderDetail>;
  /** Download the order-confirmation PDF (M5.4 order variant) as a Blob. */
  downloadOrderPdf: (id: string) => Promise<Blob>;
  /** ERP push — a v1 stub (returns `not_configured`); the adapter is M6. */
  pushToErp: (id: string) => Promise<ErpPushResult>;
}

/** Build an orders API client bound to the current Clerk session token. */
export function useOrdersApi(): OrdersApi {
  const { getToken } = useAuth();
  return useMemo<OrdersApi>(() => {
    const token: TokenGetter = () => getToken();
    return {
      searchOrders: (req) =>
        apiFetch('/api/orders/search', token, { method: 'POST', body: req }),
      getOrder: (id) => apiFetch(`/api/orders/${id}`, token),
      downloadOrderPdf: (id) => apiDownload(`/api/orders/${id}/pdf`, token),
      pushToErp: (id) => apiFetch(`/api/orders/${id}/push-to-erp`, token, { method: 'POST' }),
    };
  }, [getToken]);
}
