/**
 * Pure selection geometry (M2.7). Tested against synthetic meshes whose
 * dimensions are known independently of the code under test (a unit cube, an
 * axis cylinder built from first principles), plus the real occt-tessellated
 * fixture in selection.fixture.test.ts.
 */
import { describe, expect, it } from 'vitest';

import type { CadBody, CadModel } from './model';
import {
  axisDims,
  cumulativeArea,
  faceArea,
  faceProps,
  faceRefForHit,
  optimalBoundingBox,
  wholeFileStats,
} from './selection';

/** Unit cube [0,1]³ as 12 triangles, one CadFace per side (2 tris each). */
function unitCube(): CadBody {
  // 8 corners
  const p = [
    [0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0], // bottom z=0
    [0, 0, 1], [1, 0, 1], [1, 1, 1], [0, 1, 1], // top z=1
  ];
  // 6 faces, outward winding, 2 tris each
  const quads: [number, number, number, number][] = [
    [0, 3, 2, 1], // bottom (-z)
    [4, 5, 6, 7], // top (+z)
    [0, 1, 5, 4], // -y
    [2, 3, 7, 6], // +y
    [1, 2, 6, 5], // +x
    [3, 0, 4, 7], // -x
  ];
  const positions: number[] = [];
  const indices: number[] = [];
  const faces = [];
  let tri = 0;
  for (const [a, b, c, d] of quads) {
    const base = positions.length / 3;
    positions.push(...p[a], ...p[b], ...p[c], ...p[d]);
    indices.push(base, base + 1, base + 2, base, base + 2, base + 3);
    faces.push({ first: tri, last: tri + 1 });
    tri += 2;
  }
  return {
    id: 'body-0',
    name: 'cube',
    positions: Float32Array.from(positions),
    normals: null,
    indices: Uint32Array.from(indices),
    faces,
    color: null,
  };
}

function model(bodies: CadBody[], bbox: CadModel['bbox']): CadModel {
  return { bodies, bbox };
}

/**
 * A cylindrical side surface about the Z axis: radius R, from z=0 to z=H,
 * swept over `sweepDeg` degrees in `segments` steps, as a single CadFace.
 * Ground truth is the constructor args, independent of the fit under test.
 */
function cylinderSide(R: number, H: number, segments: number, sweepDeg = 360): CadBody {
  const positions: number[] = [];
  const indices: number[] = [];
  const sweep = (sweepDeg * Math.PI) / 180;
  const ring = (z: number, k: number): number => {
    const a = (k / segments) * sweep;
    const base = positions.length / 3;
    positions.push(R * Math.cos(a), R * Math.sin(a), z);
    return base;
  };
  for (let k = 0; k < segments; k += 1) {
    const b0 = ring(0, k);
    const t0 = ring(H, k);
    const b1 = ring(0, k + 1);
    const t1 = ring(H, k + 1);
    indices.push(b0, b1, t1, b0, t1, t0);
  }
  const triangles = indices.length / 3;
  return {
    id: 'body-0',
    name: 'cyl',
    positions: Float32Array.from(positions),
    normals: null,
    indices: Uint32Array.from(indices),
    faces: [{ first: 0, last: triangles - 1 }],
    color: null,
  };
}

describe('faceArea', () => {
  it('sums the triangle areas of a face (unit-cube side = 1 mm²)', () => {
    const cube = unitCube();
    expect(faceArea(cube, cube.faces[0])).toBeCloseTo(1, 6);
  });
});

describe('wholeFileStats', () => {
  const cube = unitCube();
  const m = model([cube], { min: [0, 0, 0], max: [1, 1, 1] });

  it('computes signed volume (unit cube = 1 mm³) and surface area (= 6 mm²)', () => {
    const stats = wholeFileStats(m, null);
    expect(stats.volumeMm3).toBeCloseTo(1, 6);
    expect(stats.surfaceAreaMm2).toBeCloseTo(6, 6);
  });

  it('is sign-robust: volume is positive regardless of winding', () => {
    expect(wholeFileStats(m, null).volumeMm3).toBeGreaterThan(0);
  });

  it('derives mass in kg from density (g/cm³) × volume', () => {
    // 1 mm³ = 1e-3 cm³; steel 7.85 g/cm³ → 7.85e-3 g = 7.85e-6 kg
    const stats = wholeFileStats(m, 7.85);
    expect(stats.massKg).toBeCloseTo(7.85e-6, 12);
  });

  it('leaves mass null when no density is known', () => {
    expect(wholeFileStats(m, null).massKg).toBeNull();
    expect(wholeFileStats(m, 0).massKg).toBeNull();
  });
});

describe('axisDims', () => {
  it('reports X/Y/Z extents from the model bbox', () => {
    const m = model([unitCube()], { min: [-1, 2, 0], max: [4, 5, 10] });
    expect(axisDims(m)).toEqual([5, 3, 10]);
  });
});

describe('optimalBoundingBox', () => {
  it('finds a tighter box than the axis-aligned one for a rotated part', () => {
    // a 20×10×4 box rotated 45° about Z: axis-aligned bbox bulges in X/Y,
    // but the optimal (oriented) box recovers the true 20×10×4 extents.
    const hx = 10;
    const hy = 5;
    const hz = 2;
    const corners: number[] = [];
    for (const sx of [-1, 1])
      for (const sy of [-1, 1])
        for (const sz of [-1, 1]) {
          const x = sx * hx;
          const y = sy * hy;
          const c = Math.SQRT1_2;
          corners.push(x * c - y * c, x * c + y * c, sz * hz);
        }
    const body: CadBody = {
      id: 'body-0',
      name: 'box',
      positions: Float32Array.from(corners),
      normals: null,
      indices: new Uint32Array([0, 1, 2]),
      faces: [{ first: 0, last: 0 }],
      color: null,
    };
    const m = model([body], { min: [0, 0, 0], max: [1, 1, 1] });

    const obb = optimalBoundingBox(m).slice().sort((a, b) => a - b);
    expect(obb[0]).toBeCloseTo(4, 4);
    expect(obb[1]).toBeCloseTo(10, 4);
    expect(obb[2]).toBeCloseTo(20, 4);
  });
});

describe('cumulativeArea', () => {
  it('sums face areas across a multi-pick set', () => {
    const cube = unitCube();
    const m = model([cube], { min: [0, 0, 0], max: [1, 1, 1] });
    const refs = [
      { kind: 'face' as const, bodyId: 'body-0', index: 0 },
      { kind: 'face' as const, bodyId: 'body-0', index: 1 },
    ];
    expect(cumulativeArea(m, refs)).toBeCloseTo(2, 6);
  });
});

describe('faceRefForHit', () => {
  const cube = unitCube(); // 6 faces, 2 triangles each: face i covers tris 2i..2i+1
  const m = model([cube], { min: [0, 0, 0], max: [1, 1, 1] });

  it('maps a hit triangle index to the face whose range contains it', () => {
    expect(faceRefForHit(m, 'body-0', 0)).toEqual({ kind: 'face', bodyId: 'body-0', index: 0 });
    expect(faceRefForHit(m, 'body-0', 3)).toEqual({ kind: 'face', bodyId: 'body-0', index: 1 });
    expect(faceRefForHit(m, 'body-0', 11)).toEqual({ kind: 'face', bodyId: 'body-0', index: 5 });
  });

  it('returns null for an unknown body or an out-of-range triangle', () => {
    expect(faceRefForHit(m, 'nope', 0)).toBeNull();
    expect(faceRefForHit(m, 'body-0', 999)).toBeNull();
  });
});

describe('faceProps — plane', () => {
  it('classifies a flat cube side as a plane with its area, no diameter/height', () => {
    const cube = unitCube();
    const props = faceProps(cube, 0);
    expect(props.type).toBe('plane');
    expect(props.area).toBeCloseTo(1, 6);
    expect(props.diameter).toBeNull();
    expect(props.height).toBeNull();
    expect(props.angle).toBeNull();
  });
});

describe('faceProps — cylinder', () => {
  it('classifies a full cylinder: diameter, height, 360° sweep, lateral area', () => {
    const cyl = cylinderSide(4, 10, 64); // R=4 → D=8, H=10, full
    const props = faceProps(cyl, 0);
    expect(props.type).toBe('cylinder');
    expect(props.diameter).toBeCloseTo(8, 1);
    expect(props.height).toBeCloseTo(10, 3);
    expect(props.angle).toBeCloseTo(360, 0);
    // lateral area 2πRH = 251.3, minus a little from chordal tessellation
    expect(props.area).toBeGreaterThan(240);
    expect(props.area).toBeLessThan(252);
  });

  it('reports the arc sweep of a partial cylinder (quarter → ~90°)', () => {
    const quarter = cylinderSide(5, 6, 32, 90);
    const props = faceProps(quarter, 0);
    expect(props.type).toBe('cylinder');
    expect(props.diameter).toBeCloseTo(10, 1);
    expect(props.angle).toBeCloseTo(90, 0);
  });

  it('does not misclassify a plane or a flat quad as a cylinder', () => {
    const cube = unitCube();
    for (let i = 0; i < 6; i += 1) expect(faceProps(cube, i).type).toBe('plane');
  });

  it('detects a cylinder off the Z axis (axis along X)', () => {
    const cyl = cylinderSide(3, 8, 48);
    // rotate 90° about Y so the axis lands on X: (x,y,z) → (z,y,-x)
    const rotated = { ...cyl, positions: new Float32Array(cyl.positions.length) };
    for (let i = 0; i < cyl.positions.length; i += 3) {
      rotated.positions[i] = cyl.positions[i + 2];
      rotated.positions[i + 1] = cyl.positions[i + 1];
      rotated.positions[i + 2] = -cyl.positions[i];
    }
    const props = faceProps(rotated, 0);
    expect(props.type).toBe('cylinder');
    expect(props.diameter).toBeCloseTo(6, 1);
    expect(props.height).toBeCloseTo(8, 3);
  });
});

/** A UV sphere of radius R centered at c, as a single CadFace. */
function sphere(R: number, c: Vec3, uSeg = 24, vSeg = 16): CadBody {
  const positions: number[] = [];
  const indices: number[] = [];
  const at = (iu: number, iv: number): number => {
    const theta = (iu / uSeg) * 2 * Math.PI;
    const phi = (iv / vSeg) * Math.PI;
    const base = positions.length / 3;
    positions.push(
      c[0] + R * Math.sin(phi) * Math.cos(theta),
      c[1] + R * Math.sin(phi) * Math.sin(theta),
      c[2] + R * Math.cos(phi),
    );
    return base;
  };
  for (let iu = 0; iu < uSeg; iu += 1) {
    for (let iv = 0; iv < vSeg; iv += 1) {
      const a = at(iu, iv);
      const b = at(iu + 1, iv);
      const d = at(iu, iv + 1);
      const e = at(iu + 1, iv + 1);
      indices.push(a, b, e, a, e, d);
    }
  }
  const triangles = indices.length / 3;
  return {
    id: 'body-0',
    name: 'sphere',
    positions: Float32Array.from(positions),
    normals: null,
    indices: Uint32Array.from(indices),
    faces: [{ first: 0, last: triangles - 1 }],
    color: null,
  };
}

type Vec3 = [number, number, number];

describe('faceProps — sphere', () => {
  it('classifies a sphere with its diameter, no height/angle', () => {
    const props = faceProps(sphere(5, [1, 2, 3]), 0);
    expect(props.type).toBe('sphere');
    expect(props.diameter).toBeCloseTo(10, 0);
    expect(props.height).toBeNull();
    expect(props.angle).toBeNull();
  });
});
