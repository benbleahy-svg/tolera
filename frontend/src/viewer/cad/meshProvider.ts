/**
 * Production MeshProvider: one worker per parse (terminated after), so a
 * navigation away mid-parse never leaks a WASM instance on the main thread.
 */
import type { CadModel, MeshProvider } from './model';

type WorkerReply = { ok: true; model: CadModel } | { ok: false; error: string };

export const workerMeshProvider: MeshProvider = (bytes) =>
  new Promise((resolve, reject) => {
    const worker = new Worker(new URL('./stepWorker.ts', import.meta.url), { type: 'module' });
    const done = (fn: () => void) => {
      worker.terminate();
      fn();
    };
    worker.onmessage = (event: MessageEvent<WorkerReply>) => {
      const reply = event.data;
      if (reply.ok) done(() => resolve(reply.model));
      else done(() => reject(new Error(reply.error)));
    };
    worker.onerror = () => done(() => reject(new Error('STEP worker failed')));
    worker.postMessage(bytes);
  });
