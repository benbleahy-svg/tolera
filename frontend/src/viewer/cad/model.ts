/**
 * Viewer-neutral tessellation model — the `MeshProvider` seam's currency.
 *
 * Deliberately carries nothing occt-import-js-specific: per DECISIONS.md
 * [2026-07-14] OPEN (viewer-mesh provenance), the mesh source may switch to
 * GeometryService's server tessellation in M4, and nothing derived from this
 * shape is ever persisted.
 */

/**
 * A B-rep topological face, as an inclusive triangle range into the owning
 * body's `indices` buffer (triangle t spans indices[3t … 3t+2]). This is what
 * makes a tessellated mesh pickable per-face: a ray hit reports a triangle
 * index, which falls inside exactly one face range.
 */
export interface CadFace {
  first: number;
  last: number;
}

export interface CadBody {
  /** Display identity only — NOT stable across tessellators; never persist. */
  id: string;
  /** Body name from the CAD file, or '' when the file carries none. */
  name: string;
  positions: Float32Array;
  normals: Float32Array | null;
  indices: Uint32Array;
  /** B-rep faces as triangle ranges (empty when the tessellator omits them). */
  faces: CadFace[];
  /** Native model color (RGB 0–1) when the file carries one. */
  color: [number, number, number] | null;
}

/**
 * A reference to a picked topological entity. Session-transient and opaque —
 * derived from the client tessellation's face ordering, which is NOT stable
 * across tessellators; per DECISIONS.md [2026-07-14] it must never be
 * persisted. `kind` reserves 'edge' for M2.8 so the shape never reshapes.
 */
export interface EntityRef {
  kind: 'face' | 'edge';
  bodyId: string;
  index: number;
}

/** Stable-within-session string key for an EntityRef (React keys, dedup). */
export function entityKey(ref: EntityRef): string {
  return `${ref.bodyId}:${ref.kind}:${ref.index}`;
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
