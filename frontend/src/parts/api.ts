/**
 * Parts + part-files API types + the `usePartsApi` hook (M1.2).
 *
 * Mirrors the FastAPI `/api/parts` contract: a minimal part owner plus file
 * upload/list/download/set-primary/delete. JSON calls reuse `apiFetch`; upload
 * goes through `apiUpload` (multipart) and download through `apiDownload` (blob,
 * then a browser save). Tests mock this module wholesale (no Clerk/network).
 */

import { apiDownload, apiFetch, apiUpload, type TokenGetter } from '../api/client';
import { useApiClient } from '../api/hooks';

export type FileRole = 'primary' | 'supporting';

export interface Part {
  id: string;
  primary_file_id: string | null;
  archived: boolean;
  created_at: string;
  updated_at: string;
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
  created_at: string;
}

export interface PartsApi {
  listParts: () => Promise<Part[]>;
  createPart: () => Promise<Part>;
  getPart: (id: string) => Promise<Part>;
  listFiles: (partId: string) => Promise<PartFile[]>;
  uploadFiles: (partId: string, files: File[]) => Promise<PartFile[]>;
  setPrimary: (partId: string, fileId: string) => Promise<PartFile>;
  deleteFile: (partId: string, fileId: string) => Promise<void>;
  downloadFile: (partId: string, fileId: string, filename: string) => Promise<void>;
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

function makePartsApi(token: TokenGetter): PartsApi {
  return {
    listParts: () => apiFetch('/api/parts', token),
    createPart: () => apiFetch('/api/parts', token, { method: 'POST' }),
    getPart: (id) => apiFetch(`/api/parts/${id}`, token),
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
  };
}

/** Build a parts API client bound to the current Clerk session token. */
export function usePartsApi(): PartsApi {
  return useApiClient(makePartsApi);
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
