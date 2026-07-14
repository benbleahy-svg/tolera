/**
 * Owns the three.js scene graph, camera pose, and render-mode state for the
 * 3D viewer — deliberately renderer-free so it is testable in jsdom (the
 * agreed M2.6 strategy: assert scene state, not pixels). The React component
 * wires a WebGLRenderer + OrbitControls around this.
 *
 * World convention: Z-up, -Y = front („Vorne") — a low-stakes assumption
 * (CLAUDE.md §6.3); STEP carries no front semantics.
 */
import * as THREE from 'three';

import type { BodySummary, CadModel, EntityRef } from './model';
import { faceRefForHit, findBody } from './selection';

export type RenderMode = 'shaded' | 'xray' | 'wireframe';
export type CubeFace = 'front' | 'back' | 'left' | 'right' | 'top' | 'bottom';

const FACE_DIRECTIONS: Record<CubeFace, THREE.Vector3> = {
  front: new THREE.Vector3(0, -1, 0),
  back: new THREE.Vector3(0, 1, 0),
  left: new THREE.Vector3(-1, 0, 0),
  right: new THREE.Vector3(1, 0, 0),
  top: new THREE.Vector3(0, 0, 1),
  bottom: new THREE.Vector3(0, 0, -1),
};

const XRAY_OPACITY = 0.35;
const DEFAULT_BODY_COLOR = 0x8896a5;
/** Selection highlight — the PP viewer's green face tint. */
const SELECTION_COLOR = 0x7ac142;
/** Isometric-ish default view direction (from front-right-above). */
const DEFAULT_VIEW_DIR = new THREE.Vector3(1, -1, 0.75).normalize();

export class CadSceneController {
  readonly scene = new THREE.Scene();
  readonly camera = new THREE.PerspectiveCamera(50, 1, 0.1, 10_000);
  /** Orbit target (model center after load); OrbitControls syncs to this. */
  readonly target = new THREE.Vector3();

  private mode: RenderMode = 'shaded';
  private modelGroup: THREE.Group | null = null;
  private model: CadModel | null = null;
  private selectionGroup: THREE.Group | null = null;
  private bodyList: BodySummary[] = [];
  private defaultPose: { position: THREE.Vector3; target: THREE.Vector3 } | null = null;
  private fitDistance = 100;

  constructor() {
    this.camera.up.set(0, 0, 1);
    const ambient = new THREE.AmbientLight(0xffffff, 0.55);
    const key = new THREE.DirectionalLight(0xffffff, 1.4);
    key.position.set(150, -220, 300);
    const fill = new THREE.DirectionalLight(0xffffff, 0.5);
    fill.position.set(-180, 160, -120);
    this.scene.add(ambient, key, fill);
  }

  get renderMode(): RenderMode {
    return this.mode;
  }

  get bodies(): BodySummary[] {
    return this.bodyList;
  }

  loadModel(model: CadModel): void {
    if (this.modelGroup) {
      this.scene.remove(this.modelGroup);
      this.disposeGroup(this.modelGroup);
    }
    this.setSelection([]);
    this.model = model;
    const group = new THREE.Group();
    for (const body of model.bodies) {
      const geometry = new THREE.BufferGeometry();
      geometry.setAttribute('position', new THREE.BufferAttribute(body.positions, 3));
      if (body.normals) {
        geometry.setAttribute('normal', new THREE.BufferAttribute(body.normals, 3));
      } else {
        geometry.computeVertexNormals();
      }
      geometry.setIndex(new THREE.BufferAttribute(body.indices, 1));
      const material = new THREE.MeshStandardMaterial({
        color: body.color
          ? new THREE.Color(body.color[0], body.color[1], body.color[2])
          : DEFAULT_BODY_COLOR,
        roughness: 0.6,
        metalness: 0.15,
        side: THREE.DoubleSide,
      });
      const mesh = new THREE.Mesh(geometry, material);
      mesh.userData.bodyId = body.id;
      group.add(mesh);
    }
    this.scene.add(group);
    this.modelGroup = group;
    this.bodyList = model.bodies.map(({ id, name }) => ({ id, name }));

    const min = new THREE.Vector3(...model.bbox.min);
    const max = new THREE.Vector3(...model.bbox.max);
    const center = min.clone().add(max).multiplyScalar(0.5);
    const diagonal = Math.max(max.clone().sub(min).length(), 1e-3);
    this.fitDistance = (diagonal / 2 / Math.tan((this.camera.fov * Math.PI) / 360)) * 1.4;

    this.target.copy(center);
    // a prior top/bottom snap leaves Y-up; the default pose must be Z-up
    this.camera.up.set(0, 0, 1);
    this.camera.position
      .copy(center)
      .add(DEFAULT_VIEW_DIR.clone().multiplyScalar(this.fitDistance));
    this.camera.lookAt(this.target);
    this.defaultPose = { position: this.camera.position.clone(), target: center.clone() };
    this.applyRenderMode();
  }

  setRenderMode(mode: RenderMode): void {
    this.mode = mode;
    this.applyRenderMode();
  }

  snapToFace(face: CubeFace): void {
    this.camera.position
      .copy(this.target)
      .add(FACE_DIRECTIONS[face].clone().multiplyScalar(this.fitDistance));
    // looking along ±Z the world-up is degenerate; use +Y as screen-up there
    this.camera.up.set(0, 0, 1);
    if (face === 'top' || face === 'bottom') this.camera.up.set(0, 1, 0);
    this.camera.lookAt(this.target);
  }

  /** Return the EntityRef of the first face a pre-configured ray hits, else null. */
  pick(raycaster: THREE.Raycaster): EntityRef | null {
    if (!this.modelGroup || !this.model) return null;
    const hits = raycaster.intersectObjects(this.modelGroup.children, false);
    for (const hit of hits) {
      const bodyId = hit.object.userData.bodyId;
      if (typeof bodyId === 'string' && hit.faceIndex != null) {
        const ref = faceRefForHit(this.model, bodyId, hit.faceIndex);
        if (ref) return ref;
      }
    }
    return null;
  }

  /** Pick from a normalized device coordinate (−1..1) via the current camera. */
  pickAt(ndcX: number, ndcY: number): EntityRef | null {
    const raycaster = new THREE.Raycaster();
    raycaster.setFromCamera(new THREE.Vector2(ndcX, ndcY), this.camera);
    return this.pick(raycaster);
  }

  /**
   * Highlight the given faces with a translucent overlay mesh built from just
   * those triangles (drawn slightly in front to avoid z-fighting). Replaces any
   * previous selection; an empty list clears it.
   */
  setSelection(refs: readonly EntityRef[]): void {
    if (this.selectionGroup) {
      this.scene.remove(this.selectionGroup);
      this.disposeGroup(this.selectionGroup);
      this.selectionGroup = null;
    }
    if (refs.length === 0 || !this.model) return;

    const group = new THREE.Group();
    for (const ref of refs) {
      if (ref.kind !== 'face') continue;
      const body = findBody(this.model, ref.bodyId);
      const face = body?.faces[ref.index];
      if (!body || !face) continue;

      const triCount = face.last - face.first + 1;
      const positions = new Float32Array(triCount * 9);
      let w = 0;
      for (let t = face.first; t <= face.last; t += 1) {
        for (let k = 0; k < 3; k += 1) {
          const vi = body.indices[3 * t + k];
          positions[w++] = body.positions[3 * vi];
          positions[w++] = body.positions[3 * vi + 1];
          positions[w++] = body.positions[3 * vi + 2];
        }
      }
      const geometry = new THREE.BufferGeometry();
      geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3));
      geometry.computeVertexNormals();
      const material = new THREE.MeshBasicMaterial({
        color: SELECTION_COLOR,
        transparent: true,
        opacity: 0.55,
        side: THREE.DoubleSide,
        depthTest: true,
        polygonOffset: true,
        polygonOffsetFactor: -1,
        polygonOffsetUnits: -1,
      });
      const mesh = new THREE.Mesh(geometry, material);
      mesh.userData.selection = true;
      group.add(mesh);
    }
    this.scene.add(group);
    this.selectionGroup = group;
  }

  resetView(): void {
    if (!this.defaultPose) return;
    this.camera.up.set(0, 0, 1);
    this.camera.position.copy(this.defaultPose.position);
    this.target.copy(this.defaultPose.target);
    this.camera.lookAt(this.target);
  }

  dispose(): void {
    if (this.modelGroup) this.disposeGroup(this.modelGroup);
    if (this.selectionGroup) this.disposeGroup(this.selectionGroup);
  }

  private applyRenderMode(): void {
    if (!this.modelGroup) return;
    for (const obj of this.modelGroup.children) {
      if (!(obj instanceof THREE.Mesh)) continue;
      const mat = obj.material as THREE.MeshStandardMaterial;
      mat.wireframe = this.mode === 'wireframe';
      mat.transparent = this.mode === 'xray';
      mat.opacity = this.mode === 'xray' ? XRAY_OPACITY : 1;
      mat.depthWrite = this.mode !== 'xray';
      mat.needsUpdate = true;
    }
  }

  private disposeGroup(group: THREE.Group): void {
    for (const obj of group.children) {
      if (obj instanceof THREE.Mesh) {
        obj.geometry.dispose();
        (obj.material as THREE.Material).dispose();
      }
    }
  }
}
