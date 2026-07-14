/**
 * Pure 3D measure math (M2.8) — distance / caliper / angle between two picked
 * faces, with the exact-vs-approximate trust signal.
 *
 * A distance is **exact** (rendered without a `~` prefix) only when the two
 * faces sit in one of three special relative orientations — **parallel planes**,
 * **concentric cylinders**, **perpendicular cylinder+plane** — and **`~`
 * approximate** otherwise. Per DECISIONS.md [2026-07-14] the classification is
 * driven by the mesh-fit {@link FacePrimitive}s from M2.7, so "exact" here means
 * *fit-exact* (as exact as the tessellation); it swaps to true B-rep-exact
 * behind the same GeometryService seam at M4 with no change to callers.
 *
 * Caliper behaviour: parallel planes measure the perpendicular gap; concentric
 * cylinders measure center-to-center. Circular faces (cylinder/sphere) are
 * always measured from their parametric center; planar/free-form faces fall
 * back to the actual ray-hit point for the approximate point-to-point case.
 */
import type { FacePrimitive, Vec3 } from './selection';
import { add, dot, len, scale, sub } from './vec3';

/** A picked face plus the exact ray-hit point on its surface. */
export interface MeasurePick {
  primitive: FacePrimitive;
  hitPoint: Vec3;
}

export type MeasureRelationship =
  | 'parallel-planes'
  | 'concentric-cylinders'
  | 'perpendicular-cyl-plane'
  | 'none';

export interface MeasureResult {
  /** distance in mm */
  distanceMm: number;
  /** true iff the pair is a special orientation → shown without a `~` prefix. */
  exact: boolean;
  relationship: MeasureRelationship;
  /** angle between two planar faces in degrees (0..90); null otherwise. */
  angleDeg: number | null;
  /**
   * The two points the distance is measured between — the in-scene leader is
   * drawn along these, so `|endpoints[1] − endpoints[0]| === distanceMm`.
   */
  endpoints: readonly [Vec3, Vec3];
}

/** Directions within this angle (deg) count as parallel / collinear. */
const PARALLEL_ANGLE_DEG = 1.5;
const PARALLEL_DOT = Math.cos((PARALLEL_ANGLE_DEG * Math.PI) / 180);
/** Two parallel cylinder axes are coaxial when their lines are within this gap. */
const COAXIAL_GAP_MM = 0.25;

/** Unit vector; a zero-length input normalizes to zero → "not collinear". */
function normalize(a: Vec3): Vec3 {
  const l = len(a);
  return l > 0 ? [a[0] / l, a[1] / l, a[2] / l] : [0, 0, 0];
}
/** true when two (unit-ish) directions are parallel or anti-parallel. */
function isCollinear(a: Vec3, b: Vec3): boolean {
  return Math.abs(dot(normalize(a), normalize(b))) >= PARALLEL_DOT;
}

/** Perpendicular distance between two parallel lines (point p/dir d, point q). */
function lineGap(p: Vec3, dir: Vec3, q: Vec3): number {
  const d = normalize(dir);
  const w = sub(q, p);
  const along = dot(w, d);
  const perp = sub(w, scale(d, along));
  return len(perp);
}

type Plane = Extract<FacePrimitive, { type: 'plane' }>;
type Cylinder = Extract<FacePrimitive, { type: 'cylinder' }>;

/** Order a mixed pair into { plane, cyl }, or null if it isn't one of each.
 * Single source of the plane/cylinder discrimination, shared by classify +
 * measure so the two can't drift (and to drop the `as Extract` casts). */
function splitPlaneAndCylinder(a: FacePrimitive, b: FacePrimitive): { plane: Plane; cyl: Cylinder } | null {
  const plane = a.type === 'plane' ? a : b.type === 'plane' ? b : null;
  const cyl = a.type === 'cylinder' ? a : b.type === 'cylinder' ? b : null;
  return plane && cyl ? { plane, cyl } : null;
}

export function classifyRelationship(a: FacePrimitive, b: FacePrimitive): MeasureRelationship {
  if (a.type === 'plane' && b.type === 'plane') {
    return isCollinear(a.normal, b.normal) ? 'parallel-planes' : 'none';
  }
  if (a.type === 'cylinder' && b.type === 'cylinder') {
    return isCollinear(a.axis, b.axis) && lineGap(a.center, a.axis, b.center) <= COAXIAL_GAP_MM
      ? 'concentric-cylinders'
      : 'none';
  }
  const split = splitPlaneAndCylinder(a, b);
  if (split) {
    // cylinder ⊥ plane ⟺ its axis is parallel to the plane normal
    return isCollinear(split.cyl.axis, split.plane.normal) ? 'perpendicular-cyl-plane' : 'none';
  }
  return 'none';
}

/** The point a face contributes to an approximate measurement. Circular faces
 * use their parametric center; planar/free-form faces use the actual hit point. */
function referencePoint(pick: MeasurePick): Vec3 {
  const p = pick.primitive;
  return p.type === 'cylinder' || p.type === 'sphere' ? p.center : pick.hitPoint;
}

/** Angle (deg, 0..90) between two planar faces, else null. */
function angleBetween(a: FacePrimitive, b: FacePrimitive): number | null {
  if (a.type !== 'plane' || b.type !== 'plane') return null;
  const c = Math.min(1, Math.abs(dot(normalize(a.normal), normalize(b.normal))));
  return (Math.acos(c) * 180) / Math.PI;
}

export function measure(a: MeasurePick, b: MeasurePick): MeasureResult {
  const relationship = classifyRelationship(a.primitive, b.primitive);
  const angleDeg = angleBetween(a.primitive, b.primitive);

  let endpoints: readonly [Vec3, Vec3];
  switch (relationship) {
    case 'parallel-planes': {
      const pa = a.primitive as Plane;
      const pb = b.primitive as Plane;
      const n = normalize(pa.normal);
      const signed = dot(sub(pb.point, pa.point), n); // perpendicular gap (signed)
      // caliper segment: from a point on plane A, straight along the normal to plane B
      endpoints = [pa.point, add(pa.point, scale(n, signed))];
      break;
    }
    case 'concentric-cylinders': {
      const ca = a.primitive as Cylinder;
      const cb = b.primitive as Cylinder;
      endpoints = [ca.center, cb.center];
      break;
    }
    case 'perpendicular-cyl-plane': {
      // never null in this branch, but fall through defensively if it were
      const split = splitPlaneAndCylinder(a.primitive, b.primitive);
      if (!split) {
        endpoints = [referencePoint(a), referencePoint(b)];
        break;
      }
      const n = normalize(split.plane.normal);
      const signed = dot(sub(split.cyl.center, split.plane.point), n);
      // from the cylinder's parametric center, perpendicular onto the plane
      endpoints = [split.cyl.center, add(split.cyl.center, scale(n, -signed))];
      break;
    }
    default:
      endpoints = [referencePoint(a), referencePoint(b)];
  }

  const distanceMm = len(sub(endpoints[1], endpoints[0]));
  return { distanceMm, exact: relationship !== 'none', relationship, angleDeg, endpoints };
}
