/**
 * BOM Builder API (M4.9) — bound to the Clerk session token once (the
 * `useQuotesApi` pattern; tests mock this module or pass functions as props).
 */

import { useMemo } from 'react';
import { useAuth } from '@clerk/clerk-react';

import { apiFetch, type TokenGetter } from '../api/client';
import type { BomDoc, BomStatus, BuilderState, CheckResult, PublishedNode } from './types';

export interface BomApi {
  getBuilderState: (quoteItemId: string) => Promise<BuilderState>;
  saveDraft: (
    quoteItemId: string,
    payload: BomDoc,
  ) => Promise<{ updated_at: string; unique_parts: number }>;
  discardDraft: (quoteItemId: string) => Promise<void>;
  checkBom: (quoteItemId: string, payload: BomDoc) => Promise<CheckResult>;
  publishBom: (quoteItemId: string, payload: BomDoc) => Promise<{ tree: PublishedNode }>;
  getBomStatus: (quoteItemId: string) => Promise<BomStatus>;
}

export function makeBomApi(getToken: TokenGetter): BomApi {
  return {
    getBuilderState: (quoteItemId) =>
      apiFetch(`/api/quote-items/${quoteItemId}/bom-builder`, getToken),
    saveDraft: (quoteItemId, payload) =>
      apiFetch(`/api/quote-items/${quoteItemId}/bom-builder/draft`, getToken, {
        method: 'PUT',
        body: { payload },
      }),
    discardDraft: (quoteItemId) =>
      apiFetch(`/api/quote-items/${quoteItemId}/bom-builder/draft`, getToken, {
        method: 'DELETE',
      }),
    checkBom: (quoteItemId, payload) =>
      apiFetch(`/api/quote-items/${quoteItemId}/bom-builder/check`, getToken, {
        method: 'POST',
        body: { payload },
      }),
    publishBom: (quoteItemId, payload) =>
      apiFetch(`/api/quote-items/${quoteItemId}/bom-builder/publish`, getToken, {
        method: 'POST',
        body: { payload },
      }),
    getBomStatus: (quoteItemId) =>
      apiFetch(`/api/quote-items/${quoteItemId}/bom-status`, getToken),
  };
}

export function useBomApi(): BomApi {
  const { getToken } = useAuth();
  return useMemo(() => makeBomApi(getToken), [getToken]);
}
