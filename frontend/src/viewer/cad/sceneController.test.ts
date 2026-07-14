// Scene-controller state tests — the agreed M2.6 strategy: jsdom has no
// WebGL, so render modes / cube snaps / reset are asserted as three.js scene
// state, never pixels. No WebGLRenderer is instantiated here.
import * as THREE from 'three';
import { beforeEach, describe, expect, it } from 'vitest';

import type { CadModel } from './model';
import { CadSceneController, type CubeFace } from './sceneController';

/** Minimal synthetic single-triangle body — enough for scene-graph assertions. */
function syntheticModel(bodyCount = 1): CadModel {
  const bodies = Array.from({ length: bodyCount }, (_, i) => ({
    id: `body-${i}`,
    name: i === 0 ? 'Deckel' : '',
    positions: new Float32Array([0, 0, 0, 10, 0, 0, 0, 10, 0]),
    normals: null,
    indices: new Uint32Array([0, 1, 2]),
    faces: [{ first: 0, last: 0 }],
    color: i === 0 ? ([0.5, 0.5, 0.5] as [number, number, number]) : null,
  }));
  return { bodies, bbox: { min: [0, 0, 0], max: [10, 10, 0] } };
}

function bodyMaterials(controller: CadSceneController): THREE.MeshStandardMaterial[] {
  const materials: THREE.MeshStandardMaterial[] = [];
  controller.scene.traverse((obj) => {
    if (obj instanceof THREE.Mesh && obj.userData.bodyId) {
      materials.push(obj.material as THREE.MeshStandardMaterial);
    }
  });
  return materials;
}

describe('CadSceneController', () => {
  let controller: CadSceneController;

  beforeEach(() => {
    controller = new CadSceneController();
    controller.loadModel(syntheticModel(2));
  });

  it('loads bodies into the scene and lists them', () => {
    expect(controller.bodies).toEqual([
      { id: 'body-0', name: 'Deckel' },
      { id: 'body-1', name: '' },
    ]);
    expect(bodyMaterials(controller)).toHaveLength(2);
  });

  it('starts shaded: opaque, no wireframe', () => {
    expect(controller.renderMode).toBe('shaded');
    for (const mat of bodyMaterials(controller)) {
      expect(mat.wireframe).toBe(false);
      expect(mat.transparent).toBe(false);
      expect(mat.opacity).toBe(1);
    }
  });

  it('xray mode makes every body transparent; shaded restores it', () => {
    controller.setRenderMode('xray');
    for (const mat of bodyMaterials(controller)) {
      expect(mat.transparent).toBe(true);
      expect(mat.opacity).toBeLessThan(1);
      expect(mat.depthWrite).toBe(false);
    }
    controller.setRenderMode('shaded');
    for (const mat of bodyMaterials(controller)) {
      expect(mat.transparent).toBe(false);
      expect(mat.opacity).toBe(1);
      expect(mat.depthWrite).toBe(true);
    }
  });

  it('wireframe mode flips material wireframe on and off', () => {
    controller.setRenderMode('wireframe');
    for (const mat of bodyMaterials(controller)) expect(mat.wireframe).toBe(true);
    controller.setRenderMode('shaded');
    for (const mat of bodyMaterials(controller)) expect(mat.wireframe).toBe(false);
  });

  it.each([
    ['front', [0, -1, 0]],
    ['back', [0, 1, 0]],
    ['left', [-1, 0, 0]],
    ['right', [1, 0, 0]],
    ['top', [0, 0, 1]],
    ['bottom', [0, 0, -1]],
  ] as [CubeFace, number[]][])(
    'snapToFace(%s) puts the camera on that axis through the model center',
    (face, axis) => {
      controller.snapToFace(face);
      const dir = controller.camera.position.clone().sub(controller.target).normalize();
      expect(dir.x).toBeCloseTo(axis[0], 5);
      expect(dir.y).toBeCloseTo(axis[1], 5);
      expect(dir.z).toBeCloseTo(axis[2], 5);
      // still centered on the model
      expect(controller.target.x).toBeCloseTo(5, 5);
      expect(controller.target.y).toBeCloseTo(5, 5);
    },
  );

  it('resetView restores the exact default pose after moving the camera', () => {
    const defaultPos = controller.camera.position.clone();
    const defaultTarget = controller.target.clone();
    controller.camera.position.set(999, -50, 3);
    controller.target.set(1, 2, 3);
    controller.snapToFace('top');
    controller.resetView();
    expect(controller.camera.position.distanceTo(defaultPos)).toBeCloseTo(0, 5);
    expect(controller.target.distanceTo(defaultTarget)).toBeCloseTo(0, 5);
  });

  it('uses Z-up world orientation', () => {
    expect(controller.camera.up.z).toBe(1);
  });

  it('restores Z-up when a new model loads after a top/bottom snap', () => {
    controller.snapToFace('top'); // leaves Y-up (degenerate up on the Z axis)
    controller.loadModel(syntheticModel(1));
    expect(controller.camera.up.z).toBe(1);
  });

  it('applies the native body color to the material when present', () => {
    const [first] = bodyMaterials(controller);
    expect(first.color.r).toBeCloseTo(0.5, 5);
    expect(first.color.g).toBeCloseTo(0.5, 5);
    expect(first.color.b).toBeCloseTo(0.5, 5);
  });
});

function highlightTriangleCount(controller: CadSceneController): number {
  let triangles = 0;
  controller.scene.traverse((obj) => {
    if (obj instanceof THREE.Mesh && obj.userData.selection === true) {
      const geom = obj.geometry as THREE.BufferGeometry;
      triangles += geom.getAttribute('position').count / 3;
    }
  });
  return triangles;
}

describe('CadSceneController — picking & selection highlight', () => {
  let controller: CadSceneController;

  beforeEach(() => {
    controller = new CadSceneController();
    controller.loadModel(syntheticModel(1));
  });

  it('maps a ray hit to the face EntityRef', () => {
    const rc = new THREE.Raycaster();
    // the body's single triangle lies in z=0; shoot straight down at (2,2)
    rc.set(new THREE.Vector3(2, 2, 10), new THREE.Vector3(0, 0, -1));
    expect(controller.pick(rc)).toEqual({ kind: 'face', bodyId: 'body-0', index: 0 });
  });

  it('returns null when the ray misses all geometry', () => {
    const rc = new THREE.Raycaster();
    rc.set(new THREE.Vector3(500, 500, 10), new THREE.Vector3(0, 0, -1));
    expect(controller.pick(rc)).toBeNull();
  });

  it('renders a highlight mesh for the selected faces and clears it', () => {
    expect(highlightTriangleCount(controller)).toBe(0);
    controller.setSelection([{ kind: 'face', bodyId: 'body-0', index: 0 }]);
    expect(highlightTriangleCount(controller)).toBe(1); // the face's one triangle
    controller.setSelection([]);
    expect(highlightTriangleCount(controller)).toBe(0);
  });

  it('clears any selection highlight when a new model loads', () => {
    controller.setSelection([{ kind: 'face', bodyId: 'body-0', index: 0 }]);
    controller.loadModel(syntheticModel(1));
    expect(highlightTriangleCount(controller)).toBe(0);
  });
});
