/**
 * Review-items API client (M3.8, spec #rules / #rules-lifecycle).
 *
 * The per-feature hook convention (`useLensApi`, `useConfigureApi`): memoize a
 * method object so a component's load effect is not re-triggered every render.
 */

import { useMemo } from 'react';
import { useAuth } from '@clerk/clerk-react';

import { apiFetch, type TokenGetter } from '../api/client';

/** The §3 resolution catalogue — the effects a card can offer. */
export type ResolutionType =
  | 'NO_QUOTE'
  | 'RESOLVE'
  | 'ADD_OPERATION'
  | 'SET_PROCESS'
  | 'ASSIGN_ESTIMATOR';

export interface ResolutionOption {
  type: ResolutionType;
  parameters: { name: string; value: unknown }[];
  custom_label: string | null;
}

export interface ReviewItemOut {
  id: string;
  rule_id: string;
  rule_name: string;
  component_id: string;
  quote_id: string;
  quote_item_id: string;
  status: 'open' | 'resolved';
  assignee_id: string | null;
  resolution_type: ResolutionType | null;
  resolution_label: string | null;
  resolved_at: string | null;
  resolved_by: string | null;
  detail: Record<string, unknown>;
  resolution_options: ResolutionOption[];
}

/** Quote level: findings grouped by rule across all parts — what SET ALL acts on. */
export interface ReviewItemGroupOut {
  rule_id: string;
  rule_name: string;
  unresolved_count: number;
  items: ReviewItemOut[];
}

export interface PriorDecisionOut {
  id: string;
  component_id: string;
  resolution_type: string;
  resolution_label: string | null;
  resolved_at: string | null;
  resolved_by: string | null;
}

export interface ReviewMessageOut {
  id: string;
  author_id: string | null;
  body: string;
  created_at: string;
}

export interface ReviewApi {
  listForComponent: (componentId: string) => Promise<ReviewItemOut[]>;
  listForQuote: (quoteId: string) => Promise<ReviewItemGroupOut[]>;
  generate: (componentId: string) => Promise<ReviewItemOut[]>;
  resolve: (
    itemId: string,
    resolutionType: ResolutionType,
    customLabel?: string | null,
  ) => Promise<ReviewItemOut>;
  assign: (itemId: string, assigneeId: string | null) => Promise<ReviewItemOut>;
  setAll: (
    quoteId: string,
    ruleId: string,
    resolutionType: ResolutionType,
    customLabel?: string | null,
  ) => Promise<{ resolved_count: number }>;
  priorDecisions: (itemId: string) => Promise<PriorDecisionOut[]>;
  listMessages: (itemId: string) => Promise<ReviewMessageOut[]>;
  postMessage: (itemId: string, body: string) => Promise<ReviewMessageOut>;
}

export function useReviewApi(): ReviewApi {
  const { getToken } = useAuth();
  return useMemo<ReviewApi>(() => {
    const token: TokenGetter = () => getToken();
    return {
      listForComponent: (componentId) =>
        apiFetch(`/api/components/${componentId}/review-items`, token),
      listForQuote: (quoteId) => apiFetch(`/api/quotes/${quoteId}/review-items`, token),
      generate: (componentId) =>
        apiFetch(`/api/components/${componentId}/review-items/generate`, token, {
          method: 'POST',
        }),
      resolve: (itemId, resolutionType, customLabel) =>
        apiFetch(`/api/review-items/${itemId}/resolve`, token, {
          method: 'POST',
          body: { resolution_type: resolutionType, custom_label: customLabel ?? null },
        }),
      assign: (itemId, assigneeId) =>
        apiFetch(`/api/review-items/${itemId}`, token, {
          method: 'PATCH',
          body: { assignee_id: assigneeId },
        }),
      setAll: (quoteId, ruleId, resolutionType, customLabel) =>
        apiFetch(`/api/quotes/${quoteId}/review-items/set-all`, token, {
          method: 'POST',
          body: {
            rule_id: ruleId,
            resolution_type: resolutionType,
            custom_label: customLabel ?? null,
          },
        }),
      priorDecisions: (itemId) => apiFetch(`/api/review-items/${itemId}/prior-decisions`, token),
      listMessages: (itemId) => apiFetch(`/api/review-items/${itemId}/messages`, token),
      postMessage: (itemId, body) =>
        apiFetch(`/api/review-items/${itemId}/messages`, token, { method: 'POST', body: { body } }),
    };
  }, [getToken]);
}

/** The card's button label for one resolution (spec #rules: "1–N suggested actions"). */
export function resolutionLabel(
  option: ResolutionOption,
  t: (key: string, opts?: Record<string, unknown>) => string,
): string {
  if (option.custom_label) return option.custom_label;
  return t(`review.resolution.${option.type}`);
}
