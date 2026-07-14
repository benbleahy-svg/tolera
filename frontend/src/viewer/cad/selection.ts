/**
 * Pure selection geometry for the 3D viewer (M2.7) — the read-only topology
 * inspection behind the selection-data overlay and whole-file readout.
 *
 * Works on the tessellated mesh only (positions + triangle-indexed faces),
 * NOT a B-rep kernel: classification and radii are fits over the triangle
 * soup. This is intentional and lives behind the MeshProvider seam — when the
 * viewer switches to GeometryService's server tessellation (DECISIONS.md
 * [2026-07-14]), authoritative face types can replace these fits without any
 * caller change. Units are model units (mm for STEP) throughout.
 */
import type { CadBody, CadFace, CadModel, EntityRef, Vec3 } from './model';

export type { Vec3 };

export type FaceType = 'plane' | 'cylinder' | 'cone' | 'sphere' | 'freeform';

export interface FaceProps {
  type: FaceType;
  /** mm² — always the summed triangle area of the face. */
  area: number;
  /** mm — axial extent (cylinder/cone); null otherwise. */
  height: number | null;
  /** mm — diameter (cylinder/cone mean/sphere); null otherwise. */
  diameter: number | null;
  /** deg — angular sweep of a curved face (cylinder/cone); null otherwise. */
  angle: number | null;
}

export interface WholeFileStats {
  volumeMm3: number;
  surfaceAreaMm2: number;
  /** kg, from density (g/cm³) × volume; null when density is absent/zero. */
  massKg: number | null;
}

type MutVec3 = [number, number, number];

/**
 * A face's geometric *placement* (not just its scalar props) — the analytic
 * primitive fitted to the face, carrying the data the M2.8 measure tool needs
 * to classify special relationships (parallel planes, concentric cylinders,
 * perpendicular cyl+plane) and to measure from a circular face's parametric
 * center. Like {@link FaceProps} these are mesh-only fits (never persisted);
 * GeometryService supplies authoritative B-rep placements in M4. All positions
 * are in model units (mm for STEP).
 */
export type FacePrimitive =
  | { type: 'plane'; area: number; point: Vec3; normal: Vec3 }
  | {
      type: 'cylinder';
      area: number;
      /** parametric center: on the axis, at the mid-point of the axial extent. */
      center: Vec3;
      axis: Vec3;
      radius: number;
      height: number;
      sweepDeg: number;
    }
  | { type: 'sphere'; area: number; center: Vec3; radius: number }
  | { type: 'freeform'; area: number; centroid: Vec3 };

function vertex(body: CadBody, i: number): Vec3 {
  return [body.positions[3 * i], body.positions[3 * i + 1], body.positions[3 * i + 2]];
}

function sub(a: Vec3, b: Vec3): Vec3 {
  return [a[0] - b[0], a[1] - b[1], a[2] - b[2]];
}

function cross(a: Vec3, b: Vec3): Vec3 {
  return [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]];
}

function dot(a: Vec3, b: Vec3): number {
  return a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
}

function len(a: Vec3): number {
  return Math.sqrt(dot(a, a));
}

/** Cross product of a triangle's edges: direction = normal, magnitude = 2·area. */
function triAreaVector(body: CadBody, tri: number): Vec3 {
  const i0 = body.indices[3 * tri];
  const i1 = body.indices[3 * tri + 1];
  const i2 = body.indices[3 * tri + 2];
  const v0 = vertex(body, i0);
  return cross(sub(vertex(body, i1), v0), sub(vertex(body, i2), v0));
}

export function faceArea(body: CadBody, face: CadFace): number {
  let area = 0;
  for (let t = face.first; t <= face.last; t += 1) area += len(triAreaVector(body, t)) / 2;
  return area;
}

export function wholeFileStats(model: CadModel, densityGCm3: number | null): WholeFileStats {
  let volume = 0;
  let surface = 0;
  for (const body of model.bodies) {
    const triangles = body.indices.length / 3;
    for (let t = 0; t < triangles; t += 1) {
      const a = triAreaVector(body, t);
      surface += len(a) / 2;
      // signed volume of the tetrahedron (origin, v0, v1, v2) = v0·(v1×v2)/6;
      // summed over a closed mesh this is the enclosed volume (divergence theorem).
      const v0 = vertex(body, body.indices[3 * t]);
      const v1 = vertex(body, body.indices[3 * t + 1]);
      const v2 = vertex(body, body.indices[3 * t + 2]);
      volume += dot(v0, cross(v1, v2)) / 6;
    }
  }
  const volumeMm3 = Math.abs(volume);
  // density g/cm³ × volume mm³ × (1e-3 cm³/mm³) = grams; ÷1000 → kg
  const massKg =
    densityGCm3 && densityGCm3 > 0 ? (densityGCm3 * volumeMm3 * 1e-3) / 1000 : null;
  return { volumeMm3, surfaceAreaMm2: surface, massKg };
}

/**
 * Axis-aligned X/Y/Z extents of the whole model, in model units. Whole-model
 * (matching the "whole-file" readout framing); per-active-body scoping arrives
 * with body isolation (M2.9) / assembly handling (M4).
 */
export function axisDims(model: CadModel): [number, number, number] {
  const { min, max } = model.bbox;
  return [max[0] - min[0], max[1] - min[1], max[2] - min[2]];
}

/**
 * Optimal (oriented) bounding-box extents — the box aligned to the part's
 * principal axes rather than the world axes, which is tighter for a rotated
 * part. This is the standard PCA approximation (principal axes of the vertex
 * covariance); it is not guaranteed to be the true minimum-volume box, hence
 * "optimal" is approximate — good enough for the readout, refined by
 * GeometryService in M4. Returns extents along the three principal axes.
 * Whole-model (union point cloud); like axisDims, per-active-body scoping is
 * M2.9/M4 — correct for the single-body parts M2.7 targets.
 */
export function optimalBoundingBox(model: CadModel): [number, number, number] {
  let n = 0;
  const mean: MutVec3 = [0, 0, 0];
  for (const body of model.bodies) {
    for (let i = 0; i < body.positions.length; i += 3) {
      mean[0] += body.positions[i];
      mean[1] += body.positions[i + 1];
      mean[2] += body.positions[i + 2];
      n += 1;
    }
  }
  if (n === 0) return [0, 0, 0];
  mean[0] /= n;
  mean[1] /= n;
  mean[2] /= n;

  const cov: Mat3 = [0, 0, 0, 0, 0, 0, 0, 0, 0];
  for (const body of model.bodies) {
    for (let i = 0; i < body.positions.length; i += 3) {
      const d: Vec3 = [
        body.positions[i] - mean[0],
        body.positions[i + 1] - mean[1],
        body.positions[i + 2] - mean[2],
      ];
      for (let a = 0; a < 3; a += 1) for (let b = 0; b < 3; b += 1) cov[3 * a + b] += d[a] * d[b];
    }
  }
  for (let k = 0; k < 9; k += 1) cov[k] /= n;

  const { vectors } = jacobiEigen(cov);
  const lo: MutVec3 = [Infinity, Infinity, Infinity];
  const hi: MutVec3 = [-Infinity, -Infinity, -Infinity];
  for (const body of model.bodies) {
    for (let i = 0; i < body.positions.length; i += 3) {
      const v: Vec3 = [body.positions[i], body.positions[i + 1], body.positions[i + 2]];
      for (let a = 0; a < 3; a += 1) {
        const p = dot(v, vectors[a]);
        if (p < lo[a]) lo[a] = p;
        if (p > hi[a]) hi[a] = p;
      }
    }
  }
  return [hi[0] - lo[0], hi[1] - lo[1], hi[2] - lo[2]];
}

export function findBody(model: CadModel, bodyId: string): CadBody | undefined {
  return model.bodies.find((b) => b.id === bodyId);
}

/**
 * Map a ray hit (body id + triangle index, as three.js reports it) to the
 * B-rep face that owns that triangle. Returns null for an unknown body or a
 * triangle outside every face range.
 */
export function faceRefForHit(
  model: CadModel,
  bodyId: string,
  triangleIndex: number,
): EntityRef | null {
  const body = findBody(model, bodyId);
  if (!body) return null;
  const index = body.faces.findIndex(
    (f) => triangleIndex >= f.first && triangleIndex <= f.last,
  );
  return index >= 0 ? { kind: 'face', bodyId, index } : null;
}

export function cumulativeArea(model: CadModel, refs: readonly EntityRef[]): number {
  let total = 0;
  for (const ref of refs) {
    if (ref.kind !== 'face') continue;
    const body = findBody(model, ref.bodyId);
    const face = body?.faces[ref.index];
    if (body && face) total += faceArea(body, face);
  }
  return total;
}

/** Unit area-weighted mean normal of a face, and how planar it is (0..1). */
function faceNormalSpread(body: CadBody, face: CadFace): { mean: Vec3; planarity: number } {
  let sx = 0;
  let sy = 0;
  let sz = 0;
  let area = 0;
  for (let t = face.first; t <= face.last; t += 1) {
    const a = triAreaVector(body, t);
    sx += a[0];
    sy += a[1];
    sz += a[2];
    area += len(a) / 2;
  }
  const meanLen = Math.sqrt(sx * sx + sy * sy + sz * sz);
  // planarity = |Σ areaᵢ n̂ᵢ| / Σ areaᵢ : 1 when all normals align, <1 when they fan out
  const planarity = area > 0 ? meanLen / (2 * area) : 0;
  const mean: Vec3 = meanLen > 0 ? [sx / meanLen, sy / meanLen, sz / meanLen] : [0, 0, 1];
  return { mean, planarity };
}

/** Distinct vertex positions touched by a face's triangles. */
function faceVertices(body: CadBody, face: CadFace): Vec3[] {
  const seen = new Set<number>();
  const out: Vec3[] = [];
  for (let t = face.first; t <= face.last; t += 1) {
    for (let k = 0; k < 3; k += 1) {
      const idx = body.indices[3 * t + k];
      if (seen.has(idx)) continue;
      seen.add(idx);
      out.push(vertex(body, idx));
    }
  }
  return out;
}

type Mat3 = [number, number, number, number, number, number, number, number, number];

/** Eigen-decomposition of a symmetric 3×3 via cyclic Jacobi rotations. */
function jacobiEigen(m: Mat3): { values: [number, number, number]; vectors: [Vec3, Vec3, Vec3] } {
  const a = [
    [m[0], m[1], m[2]],
    [m[3], m[4], m[5]],
    [m[6], m[7], m[8]],
  ];
  const v = [
    [1, 0, 0],
    [0, 1, 0],
    [0, 0, 1],
  ];
  for (let sweep = 0; sweep < 50; sweep += 1) {
    let off = 0;
    for (const [p, q] of [
      [0, 1],
      [0, 2],
      [1, 2],
    ]) {
      off += a[p][q] * a[p][q];
    }
    if (off < 1e-20) break;
    for (const [p, q] of [
      [0, 1],
      [0, 2],
      [1, 2],
    ] as const) {
      if (Math.abs(a[p][q]) < 1e-18) continue;
      const theta = (a[q][q] - a[p][p]) / (2 * a[p][q]);
      const t = Math.sign(theta || 1) / (Math.abs(theta) + Math.sqrt(theta * theta + 1));
      const c = 1 / Math.sqrt(t * t + 1);
      const s = t * c;
      for (let i = 0; i < 3; i += 1) {
        const aip = a[i][p];
        const aiq = a[i][q];
        a[i][p] = c * aip - s * aiq;
        a[i][q] = s * aip + c * aiq;
      }
      for (let i = 0; i < 3; i += 1) {
        const api = a[p][i];
        const aqi = a[q][i];
        a[p][i] = c * api - s * aqi;
        a[q][i] = s * api + c * aqi;
      }
      for (let i = 0; i < 3; i += 1) {
        const vip = v[i][p];
        const viq = v[i][q];
        v[i][p] = c * vip - s * viq;
        v[i][q] = s * vip + c * viq;
      }
    }
  }
  return {
    values: [a[0][0], a[1][1], a[2][2]],
    vectors: [
      [v[0][0], v[1][0], v[2][0]],
      [v[0][1], v[1][1], v[2][1]],
      [v[0][2], v[1][2], v[2][2]],
    ],
  };
}

/** Area-weighted covariance of the unit face normals: Σ areaᵢ n̂ᵢ n̂ᵢᵀ / Σ areaᵢ. */
function normalCovariance(body: CadBody, face: CadFace): Mat3 {
  const c = [0, 0, 0, 0, 0, 0, 0, 0, 0] as Mat3;
  let area = 0;
  for (let t = face.first; t <= face.last; t += 1) {
    const av = triAreaVector(body, t);
    const a = len(av) / 2;
    if (a === 0) continue;
    const n: Vec3 = [av[0] / (2 * a), av[1] / (2 * a), av[2] / (2 * a)];
    for (let i = 0; i < 3; i += 1) for (let j = 0; j < 3; j += 1) c[3 * i + j] += a * n[i] * n[j];
    area += a;
  }
  if (area > 0) for (let k = 0; k < 9; k += 1) c[k] /= area;
  return c;
}

function normalize(a: Vec3): Vec3 {
  const l = len(a);
  return l > 0 ? [a[0] / l, a[1] / l, a[2] / l] : [0, 0, 1];
}

/** Two orthonormal vectors spanning the plane ⊥ axis. */
function basisPerp(axis: Vec3): [Vec3, Vec3] {
  const seed: Vec3 = Math.abs(axis[0]) < 0.9 ? [1, 0, 0] : [0, 1, 0];
  const e1 = normalize(cross(axis, seed));
  const e2 = normalize(cross(axis, e1));
  return [e1, e2];
}

/** Kåsa algebraic circle fit over 2D points → { center, radius }. */
function fitCircle(pts: readonly [number, number][]): { cx: number; cy: number; r: number } {
  // Solve [2u 2v 1]·[a b c]ᵀ = u²+v² in least squares; center=(a,b), r=√(c+a²+b²).
  let Suu = 0;
  let Suv = 0;
  let Svv = 0;
  let Su = 0;
  let Sv = 0;
  let Suz = 0;
  let Svz = 0;
  let Sz = 0;
  const n = pts.length;
  for (const [u, v] of pts) {
    const z = u * u + v * v;
    Suu += u * u;
    Suv += u * v;
    Svv += v * v;
    Su += u;
    Sv += v;
    Suz += u * z;
    Svz += v * z;
    Sz += z;
  }
  // Normal equations for [A=2a, B=2b, C]:
  const m: Mat3 = [Suu, Suv, Su, Suv, Svv, Sv, Su, Sv, n];
  const rhs: Vec3 = [Suz, Svz, Sz];
  const sol = solve3(m, rhs);
  const cx = sol[0] / 2;
  const cy = sol[1] / 2;
  const r = Math.sqrt(Math.max(sol[2] + cx * cx + cy * cy, 0));
  return { cx, cy, r };
}

/** Solve a 3×3 linear system by Cramer's rule (small, well-conditioned fits). */
function solve3(m: Mat3, b: Vec3): Vec3 {
  const det = (a: Mat3): number =>
    a[0] * (a[4] * a[8] - a[5] * a[7]) -
    a[1] * (a[3] * a[8] - a[5] * a[6]) +
    a[2] * (a[3] * a[7] - a[4] * a[6]);
  const d = det(m);
  if (Math.abs(d) < 1e-12) return [0, 0, 0];
  const col = (i: number): Mat3 => {
    const c = [...m] as Mat3;
    c[i] = b[0];
    c[i + 3] = b[1];
    c[i + 6] = b[2];
    return c;
  };
  return [det(col(0)) / d, det(col(1)) / d, det(col(2)) / d];
}

/**
 * Angular sweep (deg) of points about a center: 360 − largest angular gap.
 * A closed loop (full revolution) has no gap larger than the tessellation
 * spacing, so we snap to 360 when the largest gap is within a few average
 * spacings — otherwise a full cylinder would read as 360 − one-segment.
 * (A real cylindrical face is either full 360° or a distinct partial arc;
 * near-full arcs are indistinguishable from a full loop on mesh alone.)
 */
function angularSweep(angles: number[]): number {
  const n = angles.length;
  if (n < 2) return 0;
  const sorted = [...angles].sort((a, b) => a - b);
  const gaps = [sorted[0] + 2 * Math.PI - sorted[n - 1]];
  for (let i = 1; i < n; i += 1) gaps.push(sorted[i] - sorted[i - 1]);
  gaps.sort((a, b) => b - a);
  const maxGap = gaps[0];
  const secondGap = gaps[1];
  // A full loop's largest gap is just tessellation spacing — no bigger than the
  // next gap. A real partial arc leaves one gap far larger than the rest.
  // (Robust to duplicate vertices, which only add zero-width gaps.)
  if (maxGap < secondGap * 2.5) return 360;
  return ((2 * Math.PI - maxGap) * 180) / Math.PI;
}

interface CurvedFit {
  axis: Vec3;
  /** parametric center: on the axis line, at the mid-point of the axial extent. */
  center: Vec3;
  diameter: number;
  height: number;
  sweepDeg: number;
  /** max |n̂·axis| over the face — ~0 for a cylinder, larger for a cone. */
  axisNormalAlignment: number;
}

/** Fit a surface of revolution (cylinder-shaped) to a face's mesh. */
function fitCurved(body: CadBody, face: CadFace): CurvedFit {
  const { values, vectors } = jacobiEigen(normalCovariance(body, face));
  // Axis = the normal direction with least variance (normals ⊥ axis on a cylinder).
  let axisIdx = 0;
  for (let i = 1; i < 3; i += 1) if (values[i] < values[axisIdx]) axisIdx = i;
  const axis = normalize(vectors[axisIdx]);

  const verts = faceVertices(body, face);
  const [e1, e2] = basisPerp(axis);
  const projected = verts.map((v): [number, number] => [dot(v, e1), dot(v, e2)]);
  const { cx, cy, r } = fitCircle(projected);

  const axials = verts.map((v) => dot(v, axis));
  const aMin = Math.min(...axials);
  const aMax = Math.max(...axials);
  const height = aMax - aMin;

  // parametric center = circle center (in the e1/e2 plane) lifted onto the axis
  // at the mid-point of the axial extent
  const aMid = (aMin + aMax) / 2;
  const center: Vec3 = [
    cx * e1[0] + cy * e2[0] + aMid * axis[0],
    cx * e1[1] + cy * e2[1] + aMid * axis[1],
    cx * e1[2] + cy * e2[2] + aMid * axis[2],
  ];

  const angles = projected.map(([u, v]) => Math.atan2(v - cy, u - cx));
  const sweepDeg = angularSweep(angles);

  // how much the face normals tilt toward the axis (cone vs cylinder discriminator)
  let axisNormalAlignment = 0;
  for (let t = face.first; t <= face.last; t += 1) {
    const av = triAreaVector(body, t);
    const l = len(av);
    if (l === 0) continue;
    axisNormalAlignment = Math.max(axisNormalAlignment, Math.abs(dot([av[0] / l, av[1] / l, av[2] / l], axis)));
  }

  return { axis, center, diameter: 2 * r, height, sweepDeg, axisNormalAlignment };
}

/** Area-weighted centroid of a face's triangles — a representative point that
 * lies on a planar face (and inside a curved one). */
function faceCentroid(body: CadBody, face: CadFace): Vec3 {
  let cx = 0;
  let cy = 0;
  let cz = 0;
  let area = 0;
  for (let t = face.first; t <= face.last; t += 1) {
    const av = triAreaVector(body, t);
    const a = len(av) / 2;
    if (a === 0) continue;
    const v0 = vertex(body, body.indices[3 * t]);
    const v1 = vertex(body, body.indices[3 * t + 1]);
    const v2 = vertex(body, body.indices[3 * t + 2]);
    cx += (a * (v0[0] + v1[0] + v2[0])) / 3;
    cy += (a * (v0[1] + v1[1] + v2[1])) / 3;
    cz += (a * (v0[2] + v1[2] + v2[2])) / 3;
    area += a;
  }
  return area > 0 ? [cx / area, cy / area, cz / area] : vertex(body, body.indices[3 * face.first]);
}

/** Triangle centroid and unit normal, for surface-of-revolution/sphere fits. */
function triCentroidNormal(body: CadBody, tri: number): { g: Vec3; n: Vec3 } | null {
  const av = triAreaVector(body, tri);
  const l = len(av);
  if (l === 0) return null;
  const v0 = vertex(body, body.indices[3 * tri]);
  const v1 = vertex(body, body.indices[3 * tri + 1]);
  const v2 = vertex(body, body.indices[3 * tri + 2]);
  const g: Vec3 = [(v0[0] + v1[0] + v2[0]) / 3, (v0[1] + v1[1] + v2[1]) / 3, (v0[2] + v1[2] + v2[2]) / 3];
  return { g, n: [av[0] / l, av[1] / l, av[2] / l] };
}

/**
 * Fit a sphere by intersecting the face's per-triangle normal lines: the
 * center c minimises Σ‖(gᵢ−c) − ((gᵢ−c)·n̂ᵢ)n̂ᵢ‖² (distance from each normal
 * line). Returns the center, radius, and relative residual (0 = perfect fit).
 */
function fitSphere(body: CadBody, face: CadFace): { center: Vec3; radius: number; residual: number } {
  // Normal equations Σ(I − n̂n̂ᵀ) c = Σ(I − n̂n̂ᵀ) gᵢ.
  const m: Mat3 = [0, 0, 0, 0, 0, 0, 0, 0, 0];
  const rhs: MutVec3 = [0, 0, 0];
  const tris: { g: Vec3; n: Vec3 }[] = [];
  for (let t = face.first; t <= face.last; t += 1) {
    const cn = triCentroidNormal(body, t);
    if (!cn) continue;
    tris.push(cn);
    const { g, n } = cn;
    const p: Mat3 = [
      1 - n[0] * n[0], -n[0] * n[1], -n[0] * n[2],
      -n[1] * n[0], 1 - n[1] * n[1], -n[1] * n[2],
      -n[2] * n[0], -n[2] * n[1], 1 - n[2] * n[2],
    ];
    for (let k = 0; k < 9; k += 1) m[k] += p[k];
    rhs[0] += p[0] * g[0] + p[1] * g[1] + p[2] * g[2];
    rhs[1] += p[3] * g[0] + p[4] * g[1] + p[5] * g[2];
    rhs[2] += p[6] * g[0] + p[7] * g[1] + p[8] * g[2];
  }
  const center = solve3(m, rhs);
  const dists = tris.map((c) => len(sub(c.g, center)));
  const radius = dists.reduce((s, d) => s + d, 0) / (dists.length || 1);
  const variance = dists.reduce((s, d) => s + (d - radius) ** 2, 0) / (dists.length || 1);
  const residual = radius > 0 ? Math.sqrt(variance) / radius : Infinity;
  return { center, radius, residual };
}

/** FaceProps for a face EntityRef, or null if it doesn't resolve. */
export function facePropsForRef(model: CadModel, ref: EntityRef | undefined): FaceProps | null {
  if (!ref || ref.kind !== 'face') return null;
  const body = findBody(model, ref.bodyId);
  if (!body || !body.faces[ref.index]) return null;
  return faceProps(body, ref.index);
}

/** FacePrimitive for a face EntityRef, or null if it doesn't resolve. */
export function facePrimitiveForRef(
  model: CadModel,
  ref: EntityRef | undefined,
): FacePrimitive | null {
  if (!ref || ref.kind !== 'face') return null;
  const body = findBody(model, ref.bodyId);
  if (!body || !body.faces[ref.index]) return null;
  return facePrimitive(body, ref.index);
}

export function faceProps(body: CadBody, faceIndex: number): FaceProps {
  const prim = facePrimitive(body, faceIndex);
  switch (prim.type) {
    case 'plane':
      return { type: 'plane', area: prim.area, height: null, diameter: null, angle: null };
    case 'cylinder':
      return {
        type: 'cylinder',
        area: prim.area,
        height: prim.height,
        diameter: 2 * prim.radius,
        angle: Math.round(prim.sweepDeg),
      };
    case 'sphere':
      return { type: 'sphere', area: prim.area, height: null, diameter: 2 * prim.radius, angle: null };
    case 'freeform':
      return { type: 'freeform', area: prim.area, height: null, diameter: null, angle: null };
  }
}

/**
 * The analytic {@link FacePrimitive} fitted to a face — the same mesh fits that
 * back {@link faceProps}, but carrying geometric placement (normal / axis /
 * center) for the M2.8 measure tool. Single classification path: `faceProps`
 * derives its scalars from this.
 */
export function facePrimitive(body: CadBody, faceIndex: number): FacePrimitive {
  const face = body.faces[faceIndex];
  const area = faceArea(body, face);
  const { mean, planarity } = faceNormalSpread(body, face);

  if (planarity > 0.999) {
    return { type: 'plane', area, point: faceCentroid(body, face), normal: mean };
  }

  const fit = fitCurved(body, face);
  // Cylinder: every normal is ⊥ the axis (alignment ≈ 0) and a circle fits well.
  if (fit.axisNormalAlignment < 0.2 && fit.diameter > 0) {
    return {
      type: 'cylinder',
      area,
      center: fit.center,
      axis: fit.axis,
      radius: fit.diameter / 2,
      height: fit.height,
      sweepDeg: fit.sweepDeg,
    };
  }

  // Sphere: all surface points equidistant from a single fitted center.
  const s = fitSphere(body, face);
  if (s.residual < 0.02 && s.radius > 0) {
    return { type: 'sphere', area, center: s.center, radius: s.radius };
  }

  // Cone and other surfaces of revolution: authoritative typing is
  // GeometryService's job (M4); mesh-only fits here stop at 'freeform'.
  return { type: 'freeform', area, centroid: faceCentroid(body, face) };
}
