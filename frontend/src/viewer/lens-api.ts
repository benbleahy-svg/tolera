/**
 * Lens findings API client (M3.2) — the Found-in-Files panel's surface over
 * the M3.1 extraction endpoints + the M3.2 finding actions. Same shape as
 * `usePartsApi`: a memoised object over `apiFetch` with the Clerk token.
 */

import { useMemo } from 'react';
import { useAuth } from '@clerk/clerk-react';

import { apiFetch, type TokenGetter } from '../api/client';
import type { Finding } from './lens';

export interface ExtractStatus {
  state: 'queued' | 'in_progress' | 'succeeded' | 'skipped' | 'failed';
  finding_count: number | null;
  dropped_count: number | null;
  error: { code: string; message: string } | null;
}

export interface FindingAction {
  finding: Finding;
  applied_field: string | null;
}

export interface AddMissingBody {
  category: Finding['category'];
  type: string;
  value?: string;
  raw_text?: string;
  units?: string;
  page?: number;
  bbox?: { x: number; y: number; width: number; height: number };
}

export interface LensApi {
  listFindings: (partId: string, fileId: string) => Promise<Finding[]>;
  /** Kick off the M3.1 two-pass extraction (202 + task id). */
  extract: (partId: string, fileId: string) => Promise<{ task_id: string }>;
  extractStatus: (partId: string, fileId: string, taskId: string) => Promise<ExtractStatus>;
  /** Explicit Accept — flips status and fills the target field atomically. */
  acceptFinding: (
    partId: string,
    fileId: string,
    findingId: string,
    applyTo?: 'part_number' | 'revision' | 'description' | 'size_x' | 'size_y' | 'size_z',
  ) => Promise<FindingAction>;
  /** "Mark as inaccurate" — rejects + persists the false-positive label. */
  rejectFinding: (partId: string, fileId: string, findingId: string) => Promise<FindingAction>;
  /** User-supplied value — persists the {predicted, corrected} pair. */
  replaceFinding: (
    partId: string,
    fileId: string,
    findingId: string,
    value: string,
    units?: string,
  ) => Promise<FindingAction>;
  /** "Add missing extraction" — the false-negative label. */
  addMissing: (partId: string, fileId: string, body: AddMissingBody) => Promise<Finding>;
}

export function useLensApi(): LensApi {
  const { getToken } = useAuth();
  return useMemo<LensApi>(() => {
    const token: TokenGetter = () => getToken();
    return {
      listFindings: (partId, fileId) =>
        apiFetch(`/api/parts/${partId}/files/${fileId}/findings`, token),
      extract: (partId, fileId) =>
        apiFetch(`/api/parts/${partId}/files/${fileId}/extract`, token, { method: 'POST' }),
      extractStatus: (partId, fileId, taskId) =>
        apiFetch(`/api/parts/${partId}/files/${fileId}/extract/${taskId}`, token),
      acceptFinding: (partId, fileId, findingId, applyTo) =>
        apiFetch(`/api/parts/${partId}/files/${fileId}/findings/${findingId}/accept`, token, {
          method: 'POST',
          body: applyTo ? { apply_to: applyTo } : {},
        }),
      rejectFinding: (partId, fileId, findingId) =>
        apiFetch(`/api/parts/${partId}/files/${fileId}/findings/${findingId}/reject`, token, {
          method: 'POST',
        }),
      replaceFinding: (partId, fileId, findingId, value, units) =>
        apiFetch(`/api/parts/${partId}/files/${fileId}/findings/${findingId}/replace`, token, {
          method: 'POST',
          body: units ? { value, units } : { value },
        }),
      addMissing: (partId, fileId, body) =>
        apiFetch(`/api/parts/${partId}/files/${fileId}/findings`, token, {
          method: 'POST',
          body,
        }),
    };
  }, [getToken]);
}
