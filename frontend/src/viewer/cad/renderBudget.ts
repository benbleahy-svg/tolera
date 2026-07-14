/**
 * Vertex-budget planning for the 3D viewer (M2.9 rendering limits).
 *
 * The GPU can only hold so many tessellation vertices concurrently; beyond the
 * budget the viewer substitutes bounding-box "simplified representations" for
 * the least-significant bodies rather than choking. This module is the pure
 * decision layer — it takes each body's vertex count and the budget, and
 * returns which bodies box and in which colour. The three.js side (materials,
 * box geometry) lives in the scene controller; keeping the policy pure means it
 * is exhaustively testable without WebGL.
 *
 * Policy (VIEWER-AND-FILE-TYPES.md §3):
 *  - **orange** — a *single body* whose own mesh alone exceeds the whole budget.
 *    It can never render in full, so it is always boxed, and (per the spec's tie
 *    to the interrogation honest-ceiling) it also suppresses its future-M4
 *    interrogation results.
 *  - **blue** — the *collection* exceeds the budget though each remaining body
 *    fits. We box the smallest / least-significant bodies first, preserving the
 *    largest (most-significant) body's full detail, until the rendered load
 *    fits. Isolating a subassembly re-plans over fewer bodies and restores them.
 *
 * A boxed body contributes negligible geometry (8 corners), so for accounting
 * it is treated as removed from the rendered load.
 */
import type { CadModel } from './model';

/** Concurrent tessellation-vertex budget (PP: 25 million). Overridable for tests. */
export const DEFAULT_VERTEX_BUDGET = 25_000_000;

export type RepColor = 'blue' | 'orange';

/** A body's identity + its tessellation vertex count (positions/3). */
export interface BodyBudgetInput {
  id: string;
  vertexCount: number;
}

/** The render decision for one body. */
export interface BodyRenderState {
  bodyId: string;
  /** True when the full mesh is replaced by a bounding-box rep. */
  boxed: boolean;
  /** The rep colour when boxed, else null (full-detail). */
  repColor: RepColor | null;
  /**
   * True only for an orange single-body-over-budget rep: its future-M4
   * interrogation results are suppressed (it also exceeds interrogation limits).
   */
  interrogationSuppressed: boolean;
}

export interface BudgetPlan {
  totalVertices: number;
  budget: number;
  overBudget: boolean;
  bodies: BodyRenderState[];
}

/** Per-body tessellation vertex counts for a loaded model. */
export function bodyVertexCounts(model: CadModel): BodyBudgetInput[] {
  return model.bodies.map((b) => ({ id: b.id, vertexCount: b.positions.length / 3 }));
}

/**
 * Decide the simplified-rep substitution for a set of (visible) bodies against
 * a vertex budget. Pass the visible subset to model "restore on isolate".
 */
export function planRenderBudget(
  bodies: readonly BodyBudgetInput[],
  budget: number = DEFAULT_VERTEX_BUDGET,
): BudgetPlan {
  const totalVertices = bodies.reduce((sum, b) => sum + b.vertexCount, 0);
  const states = new Map<string, BodyRenderState>(
    bodies.map((b) => [
      b.id,
      { bodyId: b.id, boxed: false, repColor: null, interrogationSuppressed: false },
    ]),
  );

  if (totalVertices <= budget) {
    return { totalVertices, budget, overBudget: false, bodies: [...states.values()] };
  }

  // 1. Any body that alone blows the budget → orange, boxed, interrogation off.
  //    These bodies are hopeless to render in full regardless of what else is hidden.
  for (const b of bodies) {
    if (b.vertexCount > budget) {
      states.set(b.id, {
        bodyId: b.id,
        boxed: true,
        repColor: 'orange',
        interrogationSuppressed: true,
      });
    }
  }

  // 2. Among the bodies that individually fit, if their collective load still
  //    overflows, box the smallest first (preserving the largest full-detail)
  //    until the rendered load fits. A boxed body drops out of the load.
  const fitting = bodies
    .filter((b) => b.vertexCount <= budget)
    .sort((a, b) => a.vertexCount - b.vertexCount);
  let renderedLoad = fitting.reduce((sum, b) => sum + b.vertexCount, 0);
  for (const b of fitting) {
    if (renderedLoad <= budget) break;
    states.set(b.id, {
      bodyId: b.id,
      boxed: true,
      repColor: 'blue',
      interrogationSuppressed: false,
    });
    renderedLoad -= b.vertexCount;
  }

  // Preserve the caller's body order in the output.
  return {
    totalVertices,
    budget,
    overBudget: true,
    bodies: bodies.map((b) => states.get(b.id) as BodyRenderState),
  };
}
