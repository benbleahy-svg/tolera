/**
 * The WebGL seam: everything jsdom can't do — renderer, orbit controls,
 * animation loop — behind one factory the tests mock. Scene/camera state
 * itself lives in CadSceneController (tested directly).
 */
import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';

import type { EntityRef } from './model';
import type { CadSceneController } from './sceneController';

export interface ViewerGl {
  domElement: HTMLCanvasElement;
  start: () => void;
  resize: (width: number, height: number) => void;
  /** Re-point the controls at the controller's target (after snap/reset). */
  syncTarget: () => void;
  dispose: () => void;
}

export interface ViewerGlOptions {
  /**
   * Called when the user clicks (not drags) the canvas: `ref` is the picked
   * face or null (empty space); `additive` is true when a modifier key is held
   * (accumulate into the selection set rather than replace it).
   */
  onPick?: (ref: EntityRef | null, additive: boolean) => void;
}

/** A drag beyond this many pixels is an orbit, not a click-to-pick. */
const CLICK_SLOP_PX = 4;

export function createViewerGl(controller: CadSceneController, opts: ViewerGlOptions = {}): ViewerGl {
  const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
  renderer.setPixelRatio(window.devicePixelRatio);
  const controls = new OrbitControls(controller.camera, renderer.domElement);
  controls.enableDamping = true;
  controls.target.copy(controller.target);

  const canvas = renderer.domElement;
  let downX = 0;
  let downY = 0;
  const onPointerDown = (e: PointerEvent) => {
    downX = e.clientX;
    downY = e.clientY;
  };
  const onPointerUp = (e: PointerEvent) => {
    if (!opts.onPick) return;
    if (Math.hypot(e.clientX - downX, e.clientY - downY) > CLICK_SLOP_PX) return; // was an orbit
    const rect = canvas.getBoundingClientRect();
    if (rect.width === 0 || rect.height === 0) return;
    const ndcX = ((e.clientX - rect.left) / rect.width) * 2 - 1;
    const ndcY = -((e.clientY - rect.top) / rect.height) * 2 + 1;
    opts.onPick(controller.pickAt(ndcX, ndcY), e.shiftKey || e.metaKey || e.ctrlKey);
  };
  canvas.addEventListener('pointerdown', onPointerDown);
  canvas.addEventListener('pointerup', onPointerUp);

  return {
    domElement: renderer.domElement,
    start: () => {
      renderer.setAnimationLoop(() => {
        controls.update();
        renderer.render(controller.scene, controller.camera);
      });
    },
    resize: (width, height) => {
      controller.camera.aspect = width / Math.max(height, 1);
      controller.camera.updateProjectionMatrix();
      renderer.setSize(width, height, false);
    },
    syncTarget: () => {
      controls.target.copy(controller.target);
      controls.update();
    },
    dispose: () => {
      renderer.setAnimationLoop(null);
      canvas.removeEventListener('pointerdown', onPointerDown);
      canvas.removeEventListener('pointerup', onPointerUp);
      controls.dispose();
      renderer.dispose();
    },
  };
}
