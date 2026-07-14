/**
 * The WebGL seam: everything jsdom can't do — renderer, orbit controls,
 * animation loop — behind one factory the tests mock. Scene/camera state
 * itself lives in CadSceneController (tested directly).
 */
import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';

import type { CadSceneController } from './sceneController';

export interface ViewerGl {
  domElement: HTMLCanvasElement;
  start: () => void;
  resize: (width: number, height: number) => void;
  /** Re-point the controls at the controller's target (after snap/reset). */
  syncTarget: () => void;
  dispose: () => void;
}

export function createViewerGl(controller: CadSceneController): ViewerGl {
  const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
  renderer.setPixelRatio(window.devicePixelRatio);
  const controls = new OrbitControls(controller.camera, renderer.domElement);
  controls.enableDamping = true;
  controls.target.copy(controller.target);

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
      controls.dispose();
      renderer.dispose();
    },
  };
}
