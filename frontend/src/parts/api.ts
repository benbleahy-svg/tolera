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
  description: string | null;
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
  status: 'ready' | 'processing';
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

/** A part's manual geometry (effective metric values + override provenance). */
export interface PartGeometry {
  part_id: string;
  size_x: number | null;
  size_y: number | null;
  size_z: number | null;
  max_dim: number | null;
  med_dim: number | null;
  min_dim: number | null;
  area: number | null;
  volume: number | null;
  weight: number | null;
  overrides: Record<string, { input: string; unit: string }>;
}

/** One GeometryService run on a part's PRIMARY CAD file (M4.1). */
/** One recognized feature (INTERROGATION-ENGINE-SPEC §2): `bend` in M4.2;
 * the milling/lathe/tube catalogs follow (M4.4–M4.6). */
export interface InterrogationFeature {
  name: string;
  /** Lathe adds non-numeric properties: `thru` (boolean), `direction` (axis). */
  properties: Record<string, number | number[] | boolean | string>;
  /** Face/edge ids for the viewer overlay — empty until the mesh export lands. */
  geometry_refs: string[];
}

/** Sheet-metal `family_scalars` (M4.2) — the recognizer emits only what it
 * measured: `size_x`/`size_y`/`flat_pattern` are absent when the body is
 * outside the v1 analytic-unfold envelope (never fabricated). */
export interface SheetMetalScalars {
  thickness: number;
  bend_count: number;
  /** Mid-surface flat-pattern area, mm². */
  flat_area: number;
  /** Flat-pattern contour length (outer + cutouts), mm. */
  total_cut_length: number;
  pierce_count: number;
  /** Unfolded (developed) size, mm — k-factor unfold. */
  size_x?: number;
  size_y?: number;
  flat_pattern?: {
    size_x: number;
    size_y: number;
    bend_lines: { position: number; angle: number }[];
  };
}

/** One detected mill setup (M4.4). Times are HOURS (KB milling-process). */
export interface MillingSetup {
  direction: number[];
  setup_time: number;
  runtime: number;
  confidence: 'High' | 'Medium' | 'Low';
  features: InterrogationFeature[];
  feedback: unknown[];
}

export interface MillingScalars {
  setup_count: number;
  setups: MillingSetup[];
  /** Aggregate runtime across setups, hours. */
  runtime: number;
  /** Aggregate setup time across setups, hours. */
  setup_time: number;
}

/** Lathe `family_scalars` (M4.5) — v2.15 attributes-only scope: recommended
 * cylindrical stock + the setup-side count. Cuts and live-tooling callouts
 * arrive as `features` (external_cut / internal_cut / setup / lathe_stock /
 * off_axis_hole / asymmetric_cavity); no runtime, no confidence. */
export interface LatheScalars {
  setup_count: number;
  /** Recommended stock radius, mm. */
  stock_radius: number;
  /** Recommended stock length, mm. */
  stock_length: number;
}

/** The 5 tube-laser stock profiles the engine classifies (M4.6). */
export type TubeStockProfile =
  | 'round'
  | 'rectangular'
  | 'rectangular_radiused'
  | 'angle'
  | 'u_channel';

/** A classified tube profile with its section dims + laser cut metrics. Cut
 * details arrive as `features` (cut / angled_cut / cutout / countersink). */
export interface TubeProfileScalars {
  stock_type: TubeStockProfile;
  /** Wall thickness, mm. */
  thickness: number;
  /** Stock length along the tube axis, mm. */
  length: number;
  width?: number;
  height?: number;
  diameter?: number;
  internal_radius?: number;
  outside_corner_radius?: number;
  is_outside_corner_round?: boolean;
  /** Angle between the legs (angle profile), degrees. */
  leg_angle?: number;
  /** Total laser cut length (end cuts + cutouts), mm. */
  total_cut_length: number;
  pierce_count: number;
  /** An end cut beyond max_angled_cut_threshold (or a non-lasered
   * countersink) → secondary machining op. */
  machining_required: boolean;
}

/** Tube-laser `family_scalars` (M4.6): a discriminated union — a body that
 * matches none of the 5 profiles reports `incompatible` and NOTHING else
 * (never a fabricated guess), so the incompatible branch carries no dims. */
export type TubeLaserScalars = { stock_type: 'incompatible' } | TubeProfileScalars;

/** One fired DFM warning (M4.7, INTERROGATION-ENGINE-SPEC §2 Warning):
 * carries the threshold that fired so the UI can show "why" and the value is
 * auditable. `instances` backs the expandable per-instance rows; face-id
 * `geometry_refs` stay empty until the server-mesh export correlates them. */
export interface DfmWarning {
  type: string;
  count: number;
  threshold_used: Record<string, number>;
  geometry_refs: unknown[];
  can_disable: boolean;
  instances: Record<string, number | string | boolean | null>[];
}

export interface InterrogationRun {
  id: string;
  part_id: string;
  file_id: string;
  family: string | null;
  material_id: string | null;
  /** Versioned geometry signature (`gs1:<sha256>`), set once the body parsed. */
  geom_hash: string | null;
  /** Fingerprint of the resolved interrogation-profile inputs ('' = engine defaults). */
  inputs_hash: string;
  status: 'queued' | 'running' | 'succeeded' | 'failed';
  error_code: string | null;
  error_detail: string | null;
  result: {
    family?: string | null;
    dimensions: {
      size_x: number;
      size_y: number;
      size_z: number;
      max_dim: number;
      med_dim: number;
      min_dim: number;
      area: number;
      volume: number;
      weight: number | null;
      bbox_source: 'obb' | 'aabb';
    };
    family_scalars?:
      | SheetMetalScalars
      | MillingScalars
      | LatheScalars
      | TubeLaserScalars
      | Record<string, never>;
    features?: InterrogationFeature[];
    /** DFM warnings fired by the M4.7 evaluator (only fired types appear). */
    feedback?: DfmWarning[];
    /** Engine trust rating where runtime is estimated (milling — M4.4). */
    confidence?: 'High' | 'Medium' | 'Low' | null;
  } | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
}

/** The part's interrogation state: `none` until a CAD PRIMARY queues a run;
 * `queued`/`running` render as the "interrogating…" state. */
export interface InterrogationStatus {
  part_id: string;
  status: 'none' | InterrogationRun['status'];
  run: InterrogationRun | null;
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
  /** Patch identity fields (part#/rev/description…) — the click-to-fill target. */
  updatePart: (
    id: string,
    changes: Partial<Pick<Part, 'name' | 'part_number' | 'revision' | 'description'>>,
  ) => Promise<Part>;
  getGeometry: (partId: string) => Promise<PartGeometry>;
  /** Latest interrogation run for a part (M4.1: the interrogating… state). */
  getInterrogation: (partId: string) => Promise<InterrogationStatus>;
  /** Set manual dims; values evaluate server-side (math + units, stored metric). */
  updateGeometry: (
    partId: string,
    changes: Partial<Record<'size_x' | 'size_y' | 'size_z', string | number | null>> & {
      unit?: 'mm' | 'in';
    },
  ) => Promise<PartGeometry>;
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
      updatePart: (id, changes) =>
        apiFetch(`/api/parts/${id}`, token, { method: 'PATCH', body: changes }),
      getGeometry: (partId) => apiFetch(`/api/parts/${partId}/geometry`, token),
      getInterrogation: (partId) => apiFetch(`/api/parts/${partId}/interrogation`, token),
      updateGeometry: (partId, changes) =>
        apiFetch(`/api/parts/${partId}/geometry`, token, { method: 'PATCH', body: changes }),
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
