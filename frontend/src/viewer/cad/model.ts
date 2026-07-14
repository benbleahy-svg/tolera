/**
 * Viewer-neutral tessellation model — the `MeshProvider` seam's currency.
 *
 * Deliberately carries nothing occt-import-js-specific: per DECISIONS.md
 * [2026-07-14] OPEN (viewer-mesh provenance), the mesh source may switch to
 * GeometryService's server tessellation in M4, and nothing derived from this
 * shape is ever persisted.
 */

export interface CadBody {
  /** Display identity only — NOT stable across tessellators; never persist. */
  id: string;
  /** Body name from the CAD file, or '' when the file carries none. */
  name: string;
  positions: Float32Array;
  normals: Float32Array | null;
  indices: Uint32Array;
  /** Native model color (RGB 0–1) when the file carries one. */
  color: [number, number, number] | null;
}

export interface CadModel {
  bodies: CadBody[];
  /** Axis-aligned bounds over all bodies, in model units (mm for STEP). */
  bbox: { min: [number, number, number]; max: [number, number, number] };
}

/** What the tree panel shows per body — display identity only (see CadBody.id). */
export interface BodySummary {
  id: string;
  name: string;
}

/**
 * The seam the viewer loads meshes through (worker-backed in production).
 * Abort the signal to cancel a parse in flight (terminates the worker).
 */
export type MeshProvider = (bytes: Uint8Array, signal?: AbortSignal) => Promise<CadModel>;
