/**
 * STEP → CadModel via occt-import-js (client-side OCCT WASM).
 *
 * Environment-neutral: runs in the Web Worker (production) and directly in
 * vitest's node environment (fixture test). The emscripten module finds its
 * .wasm from disk in node; the worker passes `locateWasm` so Vite's bundled
 * asset URL is used in the browser.
 */
import occtimportjs from 'occt-import-js';

import type { CadBody, CadModel } from './model';

let occtModule: ReturnType<typeof occtimportjs> | null = null;

export async function parseStep(
  bytes: Uint8Array,
  opts?: { locateWasm?: (path: string, scriptDirectory: string) => string },
): Promise<CadModel> {
  occtModule ??= occtimportjs(opts?.locateWasm ? { locateFile: opts.locateWasm } : undefined);
  const occt = await occtModule;

  const result = occt.ReadStepFile(bytes, null);
  if (!result.success || result.meshes.length === 0) {
    throw new Error('STEP parse failed');
  }

  const min: [number, number, number] = [Infinity, Infinity, Infinity];
  const max: [number, number, number] = [-Infinity, -Infinity, -Infinity];

  const bodies: CadBody[] = result.meshes.map((mesh, i) => {
    const positions = Float32Array.from(mesh.attributes.position.array);
    for (let p = 0; p < positions.length; p += 3) {
      for (const axis of [0, 1, 2] as const) {
        const v = positions[p + axis];
        if (v < min[axis]) min[axis] = v;
        if (v > max[axis]) max[axis] = v;
      }
    }
    return {
      id: `body-${i}`,
      name: mesh.name ?? '',
      positions,
      normals: mesh.attributes.normal ? Float32Array.from(mesh.attributes.normal.array) : null,
      indices: Uint32Array.from(mesh.index.array),
      color: mesh.color ?? null,
    };
  });

  return { bodies, bbox: { min, max } };
}
