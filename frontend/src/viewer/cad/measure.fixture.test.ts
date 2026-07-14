// @vitest-environment node
/// <reference types="node" />
//
// The M2.8 acceptance oracle: run the REAL occt-import-js tessellation against
// the plate-with-hole fixture and assert the exact-vs-approximate measure
// behaviour on genuine mesh fits (not synthetic primitives) — the block's test
// plan: "parallel-plane distance is unprefixed and within tight tolerance, and
// a skew measurement carries the ~ prefix." The plate also witnesses the
// perpendicular cylinder+plane exact case (hole axis ⟂ the 20×20 faces). The
// concentric-cylinder exact case is covered by synthetic primitives in
// measure.test.ts (no concentric pair exists in this single-hole fixture; per
// DECISIONS.md [2026-07-14] the classification is fit-based, so a synthetic
// witness exercises the same code path).
import { readFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';

import { measure, type MeasurePick } from './measure';
import { parseStep } from './parseStep';
import { facePrimitive, type FacePrimitive } from './selection';
import type { CadBody } from './model';

const FIXTURE = fileURLToPath(
  new URL('../../../../fixtures/cad/plate-hole-20x20x10-d8.step', import.meta.url),
);

/** A measure pick from a face primitive; a representative point stands in for
 * the ray hit (unused by the special-orientation branches). */
function pickOf(prim: FacePrimitive): MeasurePick {
  const hitPoint =
    prim.type === 'plane' ? prim.point : prim.type === 'cylinder' || prim.type === 'sphere' ? prim.center : prim.centroid;
  return { primitive: prim, hitPoint };
}

async function loadPlate(): Promise<{ body: CadBody; prims: FacePrimitive[] }> {
  const model = await parseStep(new Uint8Array(await readFile(FIXTURE)));
  const body = model.bodies[0];
  return { body, prims: body.faces.map((_, i) => facePrimitive(body, i)) };
}

describe('measure on the real tessellated fixture (M2.8)', () => {
  it('parallel plate faces → EXACT thickness (no ~), within tight tolerance', async () => {
    const { prims } = await loadPlate();
    // the two 20×20 faces (largest planes) are the parallel top/bottom, 10 mm apart
    const bigPlanes = prims
      .filter((p): p is Extract<FacePrimitive, { type: 'plane' }> => p.type === 'plane')
      .sort((a, b) => b.area - a.area)
      .slice(0, 2);
    expect(bigPlanes).toHaveLength(2);

    const r = measure(pickOf(bigPlanes[0]), pickOf(bigPlanes[1]));
    expect(r.relationship).toBe('parallel-planes');
    expect(r.exact).toBe(true); // unprefixed — the estimator-trust signal
    expect(r.distanceMm).toBeCloseTo(10, 2); // plate thickness, tight tolerance
  });

  it('skew (perpendicular) plate faces → APPROXIMATE (~) + ~90° angle', async () => {
    const { prims } = await loadPlate();
    const planes = prims.filter(
      (p): p is Extract<FacePrimitive, { type: 'plane' }> => p.type === 'plane',
    );
    const bigPlane = [...planes].sort((a, b) => b.area - a.area)[0]; // a 20×20 face (normal ≈ ±z)
    const sidePlane = planes.find((p) => Math.abs(p.normal[2]) < 0.1); // a 20×10 side (normal ⟂ z)
    expect(sidePlane).toBeDefined();

    const r = measure(pickOf(bigPlane), pickOf(sidePlane!));
    expect(r.exact).toBe(false); // not a special pair → carries ~
    expect(r.angleDeg).toBeCloseTo(90, 0);
  });

  it('hole cylinder ⟂ plate face → EXACT center-to-plane distance', async () => {
    const { prims } = await loadPlate();
    const cyl = prims.find(
      (p): p is Extract<FacePrimitive, { type: 'cylinder' }> => p.type === 'cylinder',
    );
    const bigPlane = prims
      .filter((p): p is Extract<FacePrimitive, { type: 'plane' }> => p.type === 'plane')
      .sort((a, b) => b.area - a.area)[0];
    expect(cyl).toBeDefined();

    const r = measure(pickOf(cyl!), pickOf(bigPlane));
    expect(r.relationship).toBe('perpendicular-cyl-plane');
    expect(r.exact).toBe(true);
    // hole is centred through the 10 mm thickness → center sits 5 mm from each face
    expect(r.distanceMm).toBeCloseTo(5, 1);
  });
});
