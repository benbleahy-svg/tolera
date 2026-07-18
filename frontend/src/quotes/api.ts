/**
 * Quotes-list + saved-view API (M1.3). The `useQuotesApi` hook binds each call to
 * the Clerk session token once (the M1.1 `useCrmApi` pattern); pages call it without
 * threading auth, and tests mock this module wholesale (no Clerk).
 */

import { useMemo } from 'react';
import { useAuth } from '@clerk/clerk-react';

import { apiFetch, type TokenGetter } from '../api/client';
import type {
  QuoteSearchRequest,
  QuoteSearchResponse,
  SavedView,
  SavedViewCreate,
  SavedViewList,
  TriageBriefResponse,
} from './types';

/** Bulk Refresh Pricing result: sync returns the tallies inline; a large selection
 *  hands off to Celery (mode "async" + a task id). */
export interface BulkRefreshResult {
  mode: 'sync' | 'async';
  refreshed_quotes?: number;
  refreshed_items?: number;
  skipped?: number;
  task_id?: string | null;
  quote_count?: number;
}

export interface QuotesApi {
  searchQuotes: (req: QuoteSearchRequest) => Promise<QuoteSearchResponse>;
  listSavedViews: () => Promise<SavedViewList>;
  createSavedView: (body: SavedViewCreate) => Promise<SavedView>;
  updateSavedView: (id: string, body: Partial<SavedViewCreate>) => Promise<SavedView>;
  deleteSavedView: (id: string) => Promise<void>;
  getTriageBrief: (quoteId: string) => Promise<TriageBriefResponse>;
  /** M5.0 — Bulk Refresh Pricing over a quotes-list multi-selection. */
  bulkRefreshPricing: (quoteIds: string[]) => Promise<BulkRefreshResult>;
}

/** Build a quotes API client bound to the current Clerk session token. */
export function useQuotesApi(): QuotesApi {
  const { getToken } = useAuth();
  return useMemo<QuotesApi>(() => {
    const token: TokenGetter = () => getToken();
    return {
      searchQuotes: (req) =>
        apiFetch('/api/quotes/search', token, { method: 'POST', body: req }),
      listSavedViews: () => apiFetch('/api/saved-views?scope=quotes', token),
      createSavedView: (body) => apiFetch('/api/saved-views', token, { method: 'POST', body }),
      updateSavedView: (id, body) =>
        apiFetch(`/api/saved-views/${id}`, token, { method: 'PATCH', body }),
      deleteSavedView: (id) =>
        apiFetch(`/api/saved-views/${id}`, token, { method: 'DELETE' }),
      getTriageBrief: (quoteId) =>
        apiFetch(`/api/quotes/${quoteId}/triage-brief`, token),
      bulkRefreshPricing: (quoteIds) =>
        apiFetch('/api/quotes/bulk-refresh-pricing', token, {
          method: 'POST',
          body: { quote_ids: quoteIds },
        }),
    };
  }, [getToken]);
}
