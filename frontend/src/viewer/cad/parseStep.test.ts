// @vitest-environment node
/// <reference types="node" />
//
// Runs the real occt-import-js WASM (no mocks) against the repo CAD fixture —
// the machine-checkable half of the M2.6 exit check. Node environment: the
// emscripten module resolves its .wasm from disk here; jsdom would make it
// try (and fail) a browser-style fetch.
import { readFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';

import { parseStep } from './parseStep';

const FIXTURE = fileURLToPath(new URL('../../../../fixtures/cad/cube-20mm.step', import.meta.url));
const HOLE_FIXTURE = fileURLToPath(
  new URL('../../../../fixtures/cad/plate-hole-20x20x10-d8.step', import.meta.url),
);

describe('parseStep (real occt-import-js WASM)', () => {
  it('tessellates the 20 mm cube fixture: bodies, triangles, 20×20×20 mm bbox', async () => {
    const bytes = new Uint8Array(await readFile(FIXTURE));

    const model = await parseStep(bytes);

    expect(model.bodies.length).toBeGreaterThan(0);
    const triangles = model.bodies.reduce((n, body) => n + body.indices.length / 3, 0);
    expect(triangles).toBeGreaterThan(0);

    for (const axis of [0, 1, 2] as const) {
      expect(model.bbox.max[axis] - model.bbox.min[axis]).toBeCloseTo(20, 3);
    }
  });

  it('carries B-rep face ranges that partition the body index buffer', async () => {
    const bytes = new Uint8Array(await readFile(HOLE_FIXTURE));

    const model = await parseStep(bytes);
    const body = model.bodies[0];

    // 6 planar walls + 1 cylindrical hole face = 7 topological faces
    expect(body.faces.length).toBe(7);
    // ranges are contiguous, ordered, inclusive, and cover every triangle
    const triangleCount = body.indices.length / 3;
    expect(body.faces[0].first).toBe(0);
    expect(body.faces[body.faces.length - 1].last).toBe(triangleCount - 1);
    for (let i = 1; i < body.faces.length; i += 1) {
      expect(body.faces[i].first).toBe(body.faces[i - 1].last + 1);
    }
  });

  it('rejects bytes that are not a STEP file', async () => {
    await expect(parseStep(new TextEncoder().encode('not a step file'))).rejects.toThrow();
  });
});
