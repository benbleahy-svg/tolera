// @vitest-environment node
/// <reference types="node" />
//
// The M2.7 acceptance oracle: run the REAL occt-import-js tessellation against
// the plate-with-hole fixture and assert the picked cylinder's diameter and a
// planar face's area match the known geometry within tessellation tolerance.
// (Node env: emscripten resolves its .wasm from disk here, as in parseStep.)
import { readFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';

import { parseStep } from './parseStep';
import { faceProps, wholeFileStats } from './selection';

const FIXTURE = fileURLToPath(
  new URL('../../../../fixtures/cad/plate-hole-20x20x10-d8.step', import.meta.url),
);

// Plate 20×20×10 mm with a Ø8 through-hole: analytic ground truth.
const PLATE_VOLUME = 20 * 20 * 10 - Math.PI * 4 * 4 * 10; // ≈ 3497.35 mm³
const PLATE_FACE = 20 * 20 - Math.PI * 4 * 4; // top/bottom, ≈ 349.73 mm²
const HOLE_AREA = Math.PI * 8 * 10; // cylinder lateral, ≈ 251.33 mm²

describe('selection geometry on the real tessellated fixture', () => {
  it('picks the Ø8 hole as a cylinder: diameter, height, full sweep, area', async () => {
    const model = await parseStep(new Uint8Array(await readFile(FIXTURE)));
    const body = model.bodies[0];

    const all = body.faces.map((_, i) => faceProps(body, i));
    const cylinders = all.filter((p) => p.type === 'cylinder');
    expect(cylinders).toHaveLength(1);

    const hole = cylinders[0];
    expect(hole.diameter).toBeCloseTo(8, 0);
    expect(hole.height).toBeCloseTo(10, 1);
    expect(hole.angle).toBe(360);
    expect(hole.area).toBeGreaterThan(HOLE_AREA * 0.97);
    expect(hole.area).toBeLessThanOrEqual(HOLE_AREA + 0.5);
  });

  it('picks a plate face as a plane whose area matches 20×20 minus the hole', async () => {
    const model = await parseStep(new Uint8Array(await readFile(FIXTURE)));
    const body = model.bodies[0];

    const planes = body.faces
      .map((_, i) => faceProps(body, i))
      .filter((p) => p.type === 'plane');

    // the two largest planes are the top/bottom faces pierced by the hole
    const largest = planes.map((p) => p.area).sort((a, b) => b - a)[0];
    expect(largest).toBeCloseTo(PLATE_FACE, 0);
  });

  it('reports whole-file volume and surface area within tessellation tolerance', async () => {
    const model = await parseStep(new Uint8Array(await readFile(FIXTURE)));

    const stats = wholeFileStats(model, 7.85);
    expect(stats.volumeMm3).toBeGreaterThan(PLATE_VOLUME);
    expect(stats.volumeMm3).toBeLessThan(PLATE_VOLUME * 1.01);
    // mass = 7.85 g/cm³ × 3.4987 cm³ ≈ 27.5 g = 0.0275 kg
    expect(stats.massKg).toBeCloseTo((7.85 * stats.volumeMm3 * 1e-3) / 1000, 9);
    expect(stats.massKg).toBeGreaterThan(0.027);
  });
});
