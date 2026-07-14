/**
 * Pure 3D measure math (M2.8) — the exact-vs-approximate trust signal.
 *
 * Tested against synthetic {@link FacePrimitive}s whose relationships are known
 * by construction, independent of the mesh fits that produce them in the real
 * viewer. The exact/`~` distinction is fit-based (DECISIONS.md [2026-07-14]
 * "M2.8 exact-vs-approximate is fit-derived until M4 B-rep"): a distance is
 * EXACT (no `~`) only on the three special relationships — parallel planes,
 * concentric cylinders, perpendicular cylinder+plane — and `~` otherwise.
 */
import { describe, expect, it } from 'vitest';

import { classifyRelationship, measure, type MeasurePick } from './measure';
import type { CadBody } from './model';
import { facePrimitive, type FacePrimitive, type Vec3 } from './selection';

const plane = (point: Vec3, normal: Vec3): FacePrimitive => ({
  type: 'plane',
  area: 1,
  point,
  normal,
});
const cylinder = (center: Vec3, axis: Vec3, radius = 4, height = 10): FacePrimitive => ({
  type: 'cylinder',
  area: 1,
  center,
  axis,
  radius,
  height,
  sweepDeg: 360,
});
const freeform = (centroid: Vec3): FacePrimitive => ({ type: 'freeform', area: 1, centroid });
const sphere = (center: Vec3, radius = 5): FacePrimitive => ({ type: 'sphere', area: 1, center, radius });
const pick = (primitive: FacePrimitive, hitPoint: Vec3): MeasurePick => ({ primitive, hitPoint });

describe('classifyRelationship', () => {
  it('parallel planes (incl. anti-parallel normals)', () => {
    expect(classifyRelationship(plane([0, 0, 0], [0, 0, 1]), plane([0, 0, 10], [0, 0, 1]))).toBe(
      'parallel-planes',
    );
    // outward normals of a slab point opposite ways — still parallel faces
    expect(classifyRelationship(plane([0, 0, 0], [0, 0, -1]), plane([0, 0, 10], [0, 0, 1]))).toBe(
      'parallel-planes',
    );
  });

  it('non-parallel planes are not special', () => {
    expect(classifyRelationship(plane([0, 0, 0], [0, 0, 1]), plane([0, 0, 0], [1, 0, 0]))).toBe(
      'none',
    );
  });

  it('concentric (coaxial) cylinders', () => {
    expect(
      classifyRelationship(
        cylinder([0, 0, 2], [0, 0, 1], 4),
        cylinder([0, 0, 8], [0, 0, 1], 8),
      ),
    ).toBe('concentric-cylinders');
  });

  it('parallel-but-offset cylinders are not concentric (hole pitch is approximate)', () => {
    expect(
      classifyRelationship(cylinder([0, 0, 5], [0, 0, 1]), cylinder([10, 0, 5], [0, 0, 1])),
    ).toBe('none');
  });

  it('perpendicular cylinder + plane, in either pick order', () => {
    const cyl = cylinder([0, 0, 5], [0, 0, 1]);
    const pl = plane([0, 0, 0], [0, 0, 1]);
    expect(classifyRelationship(cyl, pl)).toBe('perpendicular-cyl-plane');
    expect(classifyRelationship(pl, cyl)).toBe('perpendicular-cyl-plane');
  });

  it('non-perpendicular cylinder + plane is not special', () => {
    expect(
      classifyRelationship(cylinder([0, 0, 5], [0, 0, 1]), plane([0, 0, 0], [1, 0, 0])),
    ).toBe('none');
  });
});

describe('measure — exact special orientations (no ~)', () => {
  it('parallel planes → caliper (perpendicular gap), exact', () => {
    const r = measure(pick(plane([5, 5, 0], [0, 0, 1]), [5, 5, 0]), pick(plane([5, 5, 10], [0, 0, 1]), [1, 2, 10]));
    expect(r.relationship).toBe('parallel-planes');
    expect(r.exact).toBe(true);
    expect(r.distanceMm).toBeCloseTo(10, 6);
    expect(r.angleDeg).toBeCloseTo(0, 6);
  });

  it('concentric cylinders → center-to-center, exact', () => {
    const r = measure(
      pick(cylinder([0, 0, 2], [0, 0, 1], 4), [4, 0, 2]),
      pick(cylinder([0, 0, 8], [0, 0, 1], 8), [8, 0, 8]),
    );
    expect(r.relationship).toBe('concentric-cylinders');
    expect(r.exact).toBe(true);
    expect(r.distanceMm).toBeCloseTo(6, 6); // axial offset between the two centers
  });

  it('coincident concentric cylinders read exactly 0', () => {
    const r = measure(
      pick(cylinder([0, 0, 5], [0, 0, 1], 4), [4, 0, 5]),
      pick(cylinder([0, 0, 5], [0, 0, 1], 8), [8, 0, 5]),
    );
    expect(r.exact).toBe(true);
    expect(r.distanceMm).toBeCloseTo(0, 6);
  });

  it('perpendicular cylinder + plane → center-to-plane distance, exact', () => {
    const r = measure(
      pick(cylinder([0, 0, 5], [0, 0, 1]), [4, 0, 5]),
      pick(plane([0, 0, 0], [0, 0, 1]), [3, 3, 0]),
    );
    expect(r.relationship).toBe('perpendicular-cyl-plane');
    expect(r.exact).toBe(true);
    expect(r.distanceMm).toBeCloseTo(5, 6);
  });
});

describe('measure — approximate (~) everything else', () => {
  it('two arbitrary surface points → point-to-point, approximate', () => {
    const r = measure(pick(freeform([0, 0, 0]), [0, 0, 0]), pick(freeform([0, 0, 0]), [3, 4, 0]));
    expect(r.relationship).toBe('none');
    expect(r.exact).toBe(false);
    expect(r.distanceMm).toBeCloseTo(5, 6); // uses the actual clicked points
  });

  it('parallel-but-offset holes → center-to-center pitch, approximate', () => {
    const r = measure(
      pick(cylinder([0, 0, 5], [0, 0, 1]), [4, 0, 5]),
      pick(cylinder([10, 0, 5], [0, 0, 1]), [14, 0, 5]),
    );
    expect(r.exact).toBe(false);
    // circular entities measure from the parametric center, not the hit point
    expect(r.distanceMm).toBeCloseTo(10, 6);
  });

  it('a sphere is a circular entity → measured from its center, not the hit point', () => {
    // sphere R=5 centred at origin; the click lands on the surface at (5,0,0),
    // but the measurement must run from the parametric center (the spec rule)
    const r = measure(pick(sphere([0, 0, 0], 5), [5, 0, 0]), pick(freeform([0, 3, 4]), [0, 3, 4]));
    expect(r.exact).toBe(false);
    expect(r.distanceMm).toBeCloseTo(5, 6); // |center(0,0,0) → point(0,3,4)| = 5
  });

  it('skew (non-parallel) planes → approximate distance between clicked points', () => {
    const r = measure(
      pick(plane([0, 0, 0], [0, 0, 1]), [1, 0, 0]),
      pick(plane([0, 0, 0], [1, 0, 0]), [0, 0, 4]),
    );
    expect(r.exact).toBe(false);
    expect(r.angleDeg).toBeCloseTo(90, 6);
  });
});

/**
 * A Z-axis cylindrical side surface (R, z∈[z0,z0+H]) as a single-face body —
 * real tessellated triangle soup, so facePrimitive must recover axis/center by
 * fitting (not read them off a synthetic primitive). Mirrors the builder in
 * selection.test.ts.
 */
function cylinderBody(R: number, z0: number, H: number, segments = 64): CadBody {
  const positions: number[] = [];
  const indices: number[] = [];
  const ring = (z: number, k: number): number => {
    const a = (k / segments) * 2 * Math.PI;
    const base = positions.length / 3;
    positions.push(R * Math.cos(a), R * Math.sin(a), z);
    return base;
  };
  for (let k = 0; k < segments; k += 1) {
    const b0 = ring(z0, k);
    const t0 = ring(z0 + H, k);
    const b1 = ring(z0, k + 1);
    const t1 = ring(z0 + H, k + 1);
    indices.push(b0, b1, t1, b0, t1, t0);
  }
  return {
    id: 'body',
    name: 'cyl',
    positions: Float32Array.from(positions),
    normals: null,
    indices: Uint32Array.from(indices),
    faces: [{ first: 0, last: indices.length / 3 - 1 }],
    color: null,
  };
}

describe('measure — concentric cylinders on real tessellated meshes', () => {
  const pickFace = (body: CadBody): MeasurePick => {
    const primitive = facePrimitive(body, 0);
    const hitPoint: Vec3 = primitive.type === 'cylinder' ? primitive.center : [0, 0, 0];
    return { primitive, hitPoint };
  };

  it('classifies two coaxial fitted cylinders as concentric (exact), coincident → 0', () => {
    // outer R=8 and inner R=4 tube walls, same axis + extent → centers coincide
    const r = measure(pickFace(cylinderBody(8, 0, 10)), pickFace(cylinderBody(4, 0, 10)));
    expect(r.relationship).toBe('concentric-cylinders');
    expect(r.exact).toBe(true);
    expect(r.distanceMm).toBeCloseTo(0, 1);
  });

  it('coaxial cylinders with offset extents → exact center-to-center along the axis', () => {
    // outer z∈[0,10] (center z=5); inner counterbore z∈[0,4] (center z=2) → 3 mm apart
    const r = measure(pickFace(cylinderBody(8, 0, 10)), pickFace(cylinderBody(4, 0, 4)));
    expect(r.relationship).toBe('concentric-cylinders');
    expect(r.exact).toBe(true);
    expect(r.distanceMm).toBeCloseTo(3, 1);
  });
});

describe('measure — angle between two planar faces', () => {
  it('reports 90° for perpendicular faces and 0° for parallel', () => {
    expect(
      measure(pick(plane([0, 0, 0], [0, 0, 1]), [0, 0, 0]), pick(plane([0, 0, 0], [1, 0, 0]), [0, 0, 0]))
        .angleDeg,
    ).toBeCloseTo(90, 6);
    expect(
      measure(pick(plane([0, 0, 0], [0, 0, 1]), [0, 0, 0]), pick(plane([0, 0, 10], [0, 0, 1]), [0, 0, 10]))
        .angleDeg,
    ).toBeCloseTo(0, 6);
  });

  it('is null when a non-planar face is involved', () => {
    expect(
      measure(pick(cylinder([0, 0, 5], [0, 0, 1]), [4, 0, 5]), pick(plane([0, 0, 0], [0, 0, 1]), [0, 0, 0]))
        .angleDeg,
    ).toBeNull();
  });
});
