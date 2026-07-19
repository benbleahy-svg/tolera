/**
 * Work-queue API types + the `useWorkQueueApi` hook (M6.1).
 *
 * Mirrors the FastAPI `/api/work-queue` contract: the merged queue with its
 * urgency factors, the org's weights, the Recently-opened strip, and the manager
 * KPI row. Reason chips arrive as an i18n **key + params** — the wording lives in
 * the catalogs, never on the wire, so the German-first UI owns the copy.
 *
 * Money never appears here: quote value reaches the client only as a band inside
 * the `value` factor. Tests mock this module wholesale (no Clerk/network).
 */

import { useMemo } from 'react';
import { useAuth } from '@clerk/clerk-react';

import { apiFetch, type TokenGetter } from '../api/client';

export type QueueSource = 'quote_action' | 'task' | 'review_item' | 'vendor_rfq' | 'mention';

export interface ReasonChip {
  key: string;
  params: Record<string, unknown>;
}

/** One term of the urgency score — what the hover panel explains. */
export interface UrgencyFactor {
  key: 'due' | 'value' | 'unresolved' | 'flags';
  raw: string;
  normalized: string;
  weight: string;
  contribution: string;
}

export interface QueueRow {
  source: QueueSource;
  id: string;
  quote_id: string | null;
  label: string;
  reason_chips: ReasonChip[];
  urgency: string;
  factors: UrgencyFactor[];
  deep_link: string;
  org_id: string;
  org_name: string;
  org_slug: string;
  /** Belongs to another org the user is a member of — labelled, switch-on-select. */
  cross_org: boolean;
}

export interface QueueWeights {
  weight_due: string;
  weight_value: string;
  weight_unresolved: string;
  weight_flags: string;
  vendor_rfq_queue_enabled: boolean;
}

export interface WorkQueue {
  rows: QueueRow[];
  weights: QueueWeights;
  generated_on: string;
}

export interface RecentRow {
  entity_type: 'quote' | 'part';
  entity_id: string;
  label: string;
  status: string | null;
  opened_at: string;
}

export interface Kpis {
  open_quotes: number;
  due_this_week: number;
  win_rate_30d_pct: string | null;
}

export interface WorkQueueApi {
  getQueue: () => Promise<WorkQueue>;
  getSettings: () => Promise<QueueWeights>;
  saveSettings: (patch: Partial<QueueWeights>) => Promise<QueueWeights>;
  getRecents: () => Promise<{ rows: RecentRow[] }>;
  recordRecent: (entityType: 'quote' | 'part', entityId: string) => Promise<void>;
  getKpis: () => Promise<Kpis>;
}

export function useWorkQueueApi(): WorkQueueApi {
  const { getToken } = useAuth();
  return useMemo<WorkQueueApi>(() => {
    const token: TokenGetter = () => getToken();
    return {
      getQueue: () => apiFetch('/api/work-queue', token),
      getSettings: () => apiFetch('/api/work-queue/settings', token),
      saveSettings: (patch) =>
        apiFetch('/api/work-queue/settings', token, { method: 'PUT', body: patch }),
      getRecents: () => apiFetch('/api/work-queue/recents', token),
      recordRecent: (entityType, entityId) =>
        apiFetch('/api/work-queue/recents', token, {
          method: 'POST',
          body: { entity_type: entityType, entity_id: entityId },
        }),
      getKpis: () => apiFetch('/api/work-queue/kpis', token),
    };
  }, [getToken]);
}
