/**
 * Quotes-list + saved-view API (M1.3). The `useQuotesApi` hook binds each call to
 * the Clerk session token once (the M1.1 `useCrmApi` pattern); pages call it without
 * threading auth, and tests mock this module wholesale (no Clerk).
 */

import { apiFetch, type TokenGetter } from '../api/client';
import { useApiClient } from '../api/hooks';
import type {
  QuoteSearchRequest,
  QuoteSearchResponse,
  SavedView,
  SavedViewCreate,
  SavedViewList,
} from './types';

export interface QuotesApi {
  searchQuotes: (req: QuoteSearchRequest) => Promise<QuoteSearchResponse>;
  listSavedViews: () => Promise<SavedViewList>;
  createSavedView: (body: SavedViewCreate) => Promise<SavedView>;
  updateSavedView: (id: string, body: Partial<SavedViewCreate>) => Promise<SavedView>;
  deleteSavedView: (id: string) => Promise<void>;
}

function makeQuotesApi(token: TokenGetter): QuotesApi {
  return {
    searchQuotes: (req) => apiFetch('/api/quotes/search', token, { method: 'POST', body: req }),
    listSavedViews: () => apiFetch('/api/saved-views?scope=quotes', token),
    createSavedView: (body) => apiFetch('/api/saved-views', token, { method: 'POST', body }),
    updateSavedView: (id, body) =>
      apiFetch(`/api/saved-views/${id}`, token, { method: 'PATCH', body }),
    deleteSavedView: (id) => apiFetch(`/api/saved-views/${id}`, token, { method: 'DELETE' }),
  };
}

/** Build a quotes API client bound to the current Clerk session token. */
export function useQuotesApi(): QuotesApi {
  return useApiClient(makeQuotesApi);
}
