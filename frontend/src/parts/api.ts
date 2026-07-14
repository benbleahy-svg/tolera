/**
 * Parts + part-files API types + the `usePartsApi` hook (M1.2).
 *
 * Mirrors the FastAPI `/api/parts` contract: a minimal part owner plus file
 * upload/list/download/set-primary/delete. JSON calls reuse `apiFetch`; upload
 * goes through `apiUpload` (multipart) and download through `apiDownload` (blob,
 * then a browser save). Tests mock this module wholesale (no Clerk/network).
 */

import { useMemo } from 'react';
import { useAuth } from '@clerk/clerk-react';

import { apiDownload, apiFetch, apiUpload, type TokenGetter } from '../api/client';

export type FileRole = 'primary' | 'supporting';

export interface Part {
  id: string;
  primary_file_id: string | null;
  name: string | null;
  part_number: string | null;
  revision: string | null;
  archived: boolean;
  created_at: string;
  updated_at: string;
  /** Library-card fields (M2.12) — filled by the list endpoint, null elsewhere. */
  primary_filename?: string | null;
  primary_file_type?: string | null;
  process?: string | null;
}

/** One prior quote using a matched part — the import click-through (M2.12). */
export interface MatchQuoteRef {
  quote_id: string;
  number: string;
  quote_item_id: string;
  component_id: string;
}

export interface MatchCard {
  part_id: string;
  part_number: string | null;
  revision: string | null;
  name: string | null;
  primary_filename: string | null;
  archived: boolean;
  quote_count: number;
  quotes: MatchQuoteRef[];
}

export type MatchBucketKey =
  | 'exact_file'
  | 'exact_geometric'
  | 'file_name'
  | 'part_number'
  | 'similar_geometries'
  | 'historical';

export interface MatchBucket {
  key: MatchBucketKey;
  status: 'ready' | 'pending_m4';
  count: number;
  matches: MatchCard[];
}

export interface PartMatches {
  part_id: string;
  subject: {
    part_number: string | null;
    revision: string | null;
    name: string | null;
    primary_filename: string | null;
  };
  total: number;
  buckets: MatchBucket[];
}

export interface PartFile {
  id: string;
  part_id: string;
  filename: string;
  file_type: string;
  content_type: string | null;
  size_bytes: number;
  role: FileRole;
  is_redacted: boolean;
  /** The file this one was derived from (M2.5 split pages), if any. */
  source_file_id: string | null;
  created_at: string;
}

/** Task state for a server-side PDF split, as the viewer's toasts consume it. */
export interface SplitStatus {
  state: 'queued' | 'in_progress' | 'succeeded' | 'failed';
  progress: { done: number; total: number } | null;
  file_ids: string[] | null;
  error: { code: string; message: string } | null;
}

export interface PartsApi {
  listParts: (params?: { tab?: 'team' | 'archived'; q?: string }) => Promise<Part[]>;
  createPart: () => Promise<Part>;
  getPart: (id: string) => Promise<Part>;
  /** Library-level upload: auto-bundles same-stem files into one part (M2.12). */
  uploadLibraryParts: (files: File[]) => Promise<Part[]>;
  archivePart: (id: string) => Promise<Part>;
  restorePart: (id: string) => Promise<Part>;
  deletePart: (id: string) => Promise<void>;
  mergeParts: (partIds: string[], primaryPartId: string) => Promise<Part>;
  getMatches: (partId: string) => Promise<PartMatches>;
  /** Copy a historical component's router onto `componentId` and reprice. */
  importRouter: (componentId: string, sourceComponentId: string) => Promise<unknown>;
  listFiles: (partId: string) => Promise<PartFile[]>;
  uploadFiles: (partId: string, files: File[]) => Promise<PartFile[]>;
  setPrimary: (partId: string, fileId: string) => Promise<PartFile>;
  deleteFile: (partId: string, fileId: string) => Promise<void>;
  downloadFile: (partId: string, fileId: string, filename: string) => Promise<void>;
  fetchFileBytes: (partId: string, fileId: string) => Promise<Uint8Array>;
  saveRedactedCopy: (
    partId: string,
    fileId: string,
    bytes: Uint8Array,
    filename: string,
  ) => Promise<PartFile>;
  splitFile: (partId: string, fileId: string) => Promise<{ task_id: string }>;
  splitStatus: (partId: string, fileId: string, taskId: string) => Promise<SplitStatus>;
  getAnnotations: (partId: string, fileId: string) => Promise<{ objects: unknown[] }>;
  putAnnotations: (
    partId: string,
    fileId: string,
    objects: unknown[],
  ) => Promise<{ objects: unknown[] }>;
}

/** Trigger a browser "save as" for a fetched blob (download UX). */
function saveBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}

/** Build a parts API client bound to the current Clerk session token. */
export function usePartsApi(): PartsApi {
  const { getToken } = useAuth();
  return useMemo<PartsApi>(() => {
    const token: TokenGetter = () => getToken();
    return {
      listParts: (params) => {
        const search = new URLSearchParams();
        if (params?.tab) search.set('tab', params.tab);
        if (params?.q) search.set('q', params.q);
        const suffix = search.size ? `?${search.toString()}` : '';
        return apiFetch(`/api/parts${suffix}`, token);
      },
      createPart: () => apiFetch('/api/parts', token, { method: 'POST' }),
      getPart: (id) => apiFetch(`/api/parts/${id}`, token),
      uploadLibraryParts: (files) => {
        const form = new FormData();
        for (const file of files) form.append('files', file, file.name);
        return apiUpload('/api/parts/upload', token, form);
      },
      archivePart: (id) => apiFetch(`/api/parts/${id}/archive`, token, { method: 'POST' }),
      restorePart: (id) => apiFetch(`/api/parts/${id}/restore`, token, { method: 'POST' }),
      deletePart: (id) => apiFetch(`/api/parts/${id}`, token, { method: 'DELETE' }),
      mergeParts: (partIds, primaryPartId) =>
        apiFetch('/api/parts/merge', token, {
          method: 'POST',
          body: { part_ids: partIds, primary_part_id: primaryPartId },
        }),
      getMatches: (partId) => apiFetch(`/api/parts/${partId}/matches`, token),
      importRouter: (componentId, sourceComponentId) =>
        apiFetch(`/api/components/${componentId}/import-router`, token, {
          method: 'POST',
          body: { source_component_id: sourceComponentId },
        }),
      listFiles: (partId) => apiFetch(`/api/parts/${partId}/files`, token),
      uploadFiles: (partId, files) => {
        const form = new FormData();
        for (const file of files) form.append('files', file, file.name);
        return apiUpload(`/api/parts/${partId}/files`, token, form);
      },
      setPrimary: (partId, fileId) =>
        apiFetch(`/api/parts/${partId}/files/${fileId}/primary`, token, { method: 'POST' }),
      deleteFile: (partId, fileId) =>
        apiFetch(`/api/parts/${partId}/files/${fileId}`, token, { method: 'DELETE' }),
      downloadFile: async (partId, fileId, filename) => {
        const blob = await apiDownload(`/api/parts/${partId}/files/${fileId}/download`, token);
        saveBlob(blob, filename);
      },
      fetchFileBytes: async (partId, fileId) => {
        const blob = await apiDownload(`/api/parts/${partId}/files/${fileId}/download`, token);
        return new Uint8Array(await blob.arrayBuffer());
      },
      saveRedactedCopy: (partId, fileId, bytes, filename) => {
        const form = new FormData();
        form.append('file', new File([bytes as BlobPart], filename, { type: 'application/pdf' }));
        return apiUpload(`/api/parts/${partId}/files/${fileId}/redacted-copy`, token, form);
      },
      splitFile: (partId, fileId) =>
        apiFetch(`/api/parts/${partId}/files/${fileId}/split`, token, { method: 'POST' }),
      splitStatus: (partId, fileId, taskId) =>
        apiFetch(`/api/parts/${partId}/files/${fileId}/split/${taskId}`, token),
      getAnnotations: (partId, fileId) =>
        apiFetch(`/api/parts/${partId}/files/${fileId}/annotations`, token),
      putAnnotations: (partId, fileId, objects) =>
        apiFetch(`/api/parts/${partId}/files/${fileId}/annotations`, token, {
          method: 'PUT',
          body: { objects },
        }),
    };
  }, [getToken]);
}

/** Format a byte count for display, localized (German-first: `1,2 MB`, not `1.2 MB`). */
export function formatBytes(bytes: number, locale = 'de-DE'): string {
  if (bytes < 1024) return `${bytes} B`;
  const units = ['KB', 'MB', 'GB'];
  let value = bytes / 1024;
  let unit = 0;
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024;
    unit += 1;
  }
  const formatted = new Intl.NumberFormat(locale, { maximumFractionDigits: 1 }).format(value);
  return `${formatted} ${units[unit]}`;
}
