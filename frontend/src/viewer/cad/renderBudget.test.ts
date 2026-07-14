/**
 * Pure vertex-budget planning (M2.9 rendering limits). Given each body's
 * tessellation vertex count and a concurrent budget (default 25 M), decide
 * which bodies stay full-detail and which drop to a bounding-box simplified
 * rep — and in which colour:
 *
 *  - **blue**  = collection over budget: the smallest / least-significant
 *    bodies are boxed first, preserving the largest (most-significant) body's
 *    full detail. Restored by isolating a subassembly (fewer bodies visible →
 *    re-plan over the subset).
 *  - **orange** = a single body whose own mesh exceeds the whole budget; it can
 *    never render in full and additionally suppresses its (future M4)
 *    interrogation results.
 *
 * Provenance: VIEWER-AND-FILE-TYPES.md §3.
 */
import { describe, expect, it } from 'vitest';

import { DEFAULT_VERTEX_BUDGET, bodyVertexCounts, planRenderBudget } from './renderBudget';
import type { CadModel } from './model';

/** Look up the plan entry for a body id. */
function state(plan: ReturnType<typeof planRenderBudget>, id: string) {
  const s = plan.bodies.find((b) => b.bodyId === id);
  if (!s) throw new Error(`no plan entry for ${id}`);
  return s;
}

describe('planRenderBudget', () => {
  it('leaves every body full-detail when the total is within budget', () => {
    const plan = planRenderBudget(
      [
        { id: 'a', vertexCount: 10 },
        { id: 'b', vertexCount: 10 },
      ],
      100,
    );
    expect(plan.overBudget).toBe(false);
    for (const b of plan.bodies) {
      expect(b.boxed).toBe(false);
      expect(b.repColor).toBeNull();
      expect(b.interrogationSuppressed).toBe(false);
    }
  });

  it('treats the budget as inclusive (total == budget is not over)', () => {
    const plan = planRenderBudget(
      [
        { id: 'a', vertexCount: 60 },
        { id: 'b', vertexCount: 40 },
      ],
      100,
    );
    expect(plan.overBudget).toBe(false);
    expect(plan.bodies.every((b) => !b.boxed)).toBe(true);
  });

  it('boxes a single over-budget body ORANGE and suppresses its interrogation', () => {
    const plan = planRenderBudget([{ id: 'solo', vertexCount: 30 }], 25);
    expect(plan.overBudget).toBe(true);
    const s = state(plan, 'solo');
    expect(s.boxed).toBe(true);
    expect(s.repColor).toBe('orange');
    expect(s.interrogationSuppressed).toBe(true);
  });

  it('boxes the smallest bodies BLUE first, preserving the largest full-detail', () => {
    // total 25 > 20; none individually over budget.
    const plan = planRenderBudget(
      [
        { id: 'big', vertexCount: 10 },
        { id: 'mid', vertexCount: 10 },
        { id: 'small', vertexCount: 5 },
      ],
      20,
    );
    expect(plan.overBudget).toBe(true);
    // box smallest (5) → rendered 20 ≤ 20, stop.
    expect(state(plan, 'small')).toMatchObject({ boxed: true, repColor: 'blue' });
    expect(state(plan, 'big')).toMatchObject({ boxed: false, repColor: null });
    expect(state(plan, 'mid')).toMatchObject({ boxed: false, repColor: null });
    // blue reps never suppress interrogation (that is the orange, single-body case)
    expect(state(plan, 'small').interrogationSuppressed).toBe(false);
  });

  it('keeps boxing smallest-upward until the rendered load fits', () => {
    // total 25 > 15; box 5 then 8 (the two smallest) → rendered 12 ≤ 15.
    const plan = planRenderBudget(
      [
        { id: 'big', vertexCount: 12 },
        { id: 'mid', vertexCount: 8 },
        { id: 'small', vertexCount: 5 },
      ],
      15,
    );
    expect(state(plan, 'small').boxed).toBe(true);
    expect(state(plan, 'mid').boxed).toBe(true);
    expect(state(plan, 'big').boxed).toBe(false); // the largest survives full-detail
  });

  it('mixes ORANGE (own > budget) with BLUE (collective overflow)', () => {
    const plan = planRenderBudget(
      [
        { id: 'giant', vertexCount: 30 },
        { id: 'a', vertexCount: 20 },
        { id: 'b', vertexCount: 20 },
      ],
      25,
    );
    // giant alone exceeds budget → orange + suppressed, boxed regardless.
    expect(state(plan, 'giant')).toMatchObject({
      repColor: 'orange',
      boxed: true,
      interrogationSuppressed: true,
    });
    // remaining a+b = 40 > 25 → box the smaller one blue (tie → first ascending).
    const a = state(plan, 'a');
    const b = state(plan, 'b');
    const boxedBlue = [a, b].filter((s) => s.repColor === 'blue');
    expect(boxedBlue).toHaveLength(1);
    expect([a, b].filter((s) => !s.boxed)).toHaveLength(1);
  });

  it('reports the total vertices and the budget it planned against', () => {
    const plan = planRenderBudget([{ id: 'a', vertexCount: 12 }], 25);
    expect(plan.totalVertices).toBe(12);
    expect(plan.budget).toBe(25);
  });

  it('defaults to the 25 M-vertex platform budget', () => {
    expect(DEFAULT_VERTEX_BUDGET).toBe(25_000_000);
    const plan = planRenderBudget([{ id: 'a', vertexCount: 1000 }]);
    expect(plan.overBudget).toBe(false);
  });
});

describe('bodyVertexCounts', () => {
  it('counts positions/3 per body', () => {
    const model: CadModel = {
      bodies: [
        {
          id: 'b0',
          name: '',
          positions: new Float32Array(9), // 3 vertices
          normals: null,
          indices: new Uint32Array([0, 1, 2]),
          faces: [],
          color: null,
        },
        {
          id: 'b1',
          name: '',
          positions: new Float32Array(18), // 6 vertices
          normals: null,
          indices: new Uint32Array([0, 1, 2, 3, 4, 5]),
          faces: [],
          color: null,
        },
      ],
      bbox: { min: [0, 0, 0], max: [1, 1, 1] },
    };
    expect(bodyVertexCounts(model)).toEqual([
      { id: 'b0', vertexCount: 3 },
      { id: 'b1', vertexCount: 6 },
    ]);
  });
});
