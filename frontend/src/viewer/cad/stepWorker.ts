/**
 * Web Worker shell around parseStep — a thin message wrapper (untested in
 * unit scope per the agreed M2.6 strategy; parseStep itself runs against the
 * real fixture in parseStep.test.ts). Keeps the 200 MB-class WASM parse off
 * the main thread.
 */
import wasmUrl from 'occt-import-js/dist/occt-import-js.wasm?url';

import { parseStep } from './parseStep';

self.onmessage = async (event: MessageEvent<Uint8Array>) => {
  try {
    const model = await parseStep(event.data, { locateWasm: () => wasmUrl });
    const buffers = model.bodies.flatMap((b) => [
      b.positions.buffer,
      ...(b.normals ? [b.normals.buffer] : []),
      b.indices.buffer,
    ]);
    self.postMessage({ ok: true, model }, { transfer: buffers });
  } catch (error) {
    self.postMessage({ ok: false, error: error instanceof Error ? error.message : String(error) });
  }
};
