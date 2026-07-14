/**
 * Production MeshProvider: one worker per parse, terminated on completion or
 * abort, so a navigation away mid-parse never leaks a WASM instance. The
 * per-parse worker is deliberate — terminating reclaims the WASM heap that a
 * kept-warm module would hold onto between file opens.
 */
import type { CadModel, MeshProvider } from './model';

type WorkerReply = { ok: true; model: CadModel } | { ok: false; error: string };

export const workerMeshProvider: MeshProvider = (bytes, signal) =>
  new Promise((resolve, reject) => {
    const worker = new Worker(new URL('./stepWorker.ts', import.meta.url), { type: 'module' });
    // terminate exactly once, then settle the promise
    let settled = false;
    const settle = (fn: () => void) => {
      if (settled) return;
      settled = true;
      worker.terminate();
      fn();
    };
    signal?.addEventListener('abort', () =>
      settle(() => reject(signal.reason instanceof Error ? signal.reason : new Error('aborted'))),
    );
    worker.onmessage = (event: MessageEvent<WorkerReply>) => {
      const reply = event.data;
      if (reply.ok) settle(() => resolve(reply.model));
      else settle(() => reject(new Error(reply.error)));
    };
    worker.onerror = () => settle(() => reject(new Error('STEP worker failed')));
    // transfer, don't clone — a 200 MB-class STEP must not exist twice
    worker.postMessage(bytes, { transfer: [bytes.buffer] });
  });
