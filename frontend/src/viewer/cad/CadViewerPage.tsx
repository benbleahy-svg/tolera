/**
 * 3D viewer core (M2.6) — SS 10/13 chrome, M2.6 subset: toolbar with the
 * three render modes + reset, left Struktur/Merkmale panel (features =
 * M4 empty state), orientation faces, whole-file readout shell (values are
 * M2.7). Select/measure/section tools are deliberately absent (M2.7/M2.8);
 * display-options gear + rendering limits are M2.9.
 */
import { useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router-dom';

import { usePartsApi, type PartFile } from '../../parts/api';
import { workerMeshProvider } from './meshProvider';
import type { BodySummary } from './model';
import { CadSceneController, type CubeFace, type RenderMode } from './sceneController';
import { createViewerGl, type ViewerGl } from './viewerGl';

const RENDER_MODES: { mode: RenderMode; labelKey: string }[] = [
  { mode: 'shaded', labelKey: 'viewer.cad_render_shaded' },
  { mode: 'xray', labelKey: 'viewer.cad_render_xray' },
  { mode: 'wireframe', labelKey: 'viewer.cad_render_wireframe' },
];

const CUBE_FACES: { face: CubeFace; labelKey: string }[] = [
  { face: 'top', labelKey: 'viewer.cad_face_top' },
  { face: 'front', labelKey: 'viewer.cad_face_front' },
  { face: 'back', labelKey: 'viewer.cad_face_back' },
  { face: 'left', labelKey: 'viewer.cad_face_left' },
  { face: 'right', labelKey: 'viewer.cad_face_right' },
  { face: 'bottom', labelKey: 'viewer.cad_face_bottom' },
];

type LoadState = 'loading' | 'ready' | 'failed';

export function CadViewerPage({ file }: { file: PartFile }) {
  const api = usePartsApi();
  const { t } = useTranslation();
  const canvasHostRef = useRef<HTMLDivElement>(null);
  const controllerRef = useRef<CadSceneController | null>(null);
  const glRef = useRef<ViewerGl | null>(null);

  const [state, setState] = useState<LoadState>('loading');
  const [renderMode, setRenderModeState] = useState<RenderMode>('shaded');
  const [bodies, setBodies] = useState<BodySummary[]>([]);
  const [panelTab, setPanelTab] = useState<'tree' | 'features'>('tree');

  useEffect(() => {
    const controller = new CadSceneController();
    controllerRef.current = controller;
    // aborting terminates a parse worker mid-flight — a navigation away must
    // not leave a WASM instance chewing on a 200 MB STEP
    const abort = new AbortController();

    api
      .fetchFileBytes(file.part_id, file.id)
      .then((bytes) => workerMeshProvider(bytes, abort.signal))
      .then((model) => {
        if (abort.signal.aborted) return;
        controller.loadModel(model);
        setBodies(controller.bodies);
        setState('ready');
      })
      .catch((err: unknown) => {
        if (abort.signal.aborted) return;
        console.error('CAD model load failed', err);
        setState('failed');
      });

    return () => {
      abort.abort();
      glRef.current?.dispose();
      glRef.current = null;
      controller.dispose();
      controllerRef.current = null;
    };
  }, [api, file.part_id, file.id]);

  // Mount the WebGL canvas once the model is ready (host div exists then).
  useEffect(() => {
    const host = canvasHostRef.current;
    const controller = controllerRef.current;
    if (state !== 'ready' || !host || !controller || glRef.current) return;

    const gl = createViewerGl(controller);
    glRef.current = gl;
    host.appendChild(gl.domElement);
    const resize = () => gl.resize(host.clientWidth, host.clientHeight);
    resize();
    // jsdom has no ResizeObserver; in browsers it keeps the canvas fitted
    const observer =
      typeof ResizeObserver === 'undefined' ? null : new ResizeObserver(resize);
    observer?.observe(host);
    gl.start();

    return () => {
      observer?.disconnect();
      gl.dispose();
      if (gl.domElement.parentNode === host) host.removeChild(gl.domElement);
      glRef.current = null;
    };
  }, [state]);

  const setRenderMode = (mode: RenderMode) => {
    controllerRef.current?.setRenderMode(mode);
    setRenderModeState(mode);
  };

  const snapTo = (face: CubeFace) => {
    controllerRef.current?.snapToFace(face);
    glRef.current?.syncTarget();
  };

  const resetView = () => {
    controllerRef.current?.resetView();
    glRef.current?.syncTarget();
  };

  return (
    <main className="viewer-page">
      <header className="viewer-toolbar">
        <Link to="/parts">{t('viewer.back_to_parts')}</Link>
        <strong>{file.filename}</strong>
        <div className="cad-render-modes" role="group" aria-label={t('viewer.cad_render_modes')}>
          {RENDER_MODES.map(({ mode, labelKey }) => (
            <button
              key={mode}
              type="button"
              aria-pressed={renderMode === mode}
              disabled={state !== 'ready'}
              onClick={() => setRenderMode(mode)}
            >
              {t(labelKey)}
            </button>
          ))}
        </div>
        <button type="button" disabled={state !== 'ready'} onClick={resetView}>
          {t('viewer.cad_reset_view')}
        </button>
      </header>

      <div className="cad-layout">
        <aside className="cad-panel">
          <div role="tablist" className="cad-panel-tabs">
            <button
              type="button"
              role="tab"
              aria-selected={panelTab === 'tree'}
              onClick={() => setPanelTab('tree')}
            >
              {t('viewer.cad_tree')}
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={panelTab === 'features'}
              onClick={() => setPanelTab('features')}
            >
              {t('viewer.cad_features')}
            </button>
          </div>
          {panelTab === 'tree' ? (
            <ul className="cad-tree">
              {bodies.map((body, i) => (
                <li key={body.id}>{body.name || t('viewer.cad_body_fallback', { n: i + 1 })}</li>
              ))}
            </ul>
          ) : (
            <p className="cad-features-pending">{t('viewer.cad_features_pending')}</p>
          )}
        </aside>

        <section className="cad-canvas-host" ref={canvasHostRef}>
          {state === 'loading' && <p role="status">{t('viewer.cad_loading')}</p>}
          {state === 'failed' && <p role="status">{t('viewer.cad_load_failed')}</p>}

          {state === 'ready' && (
            <>
              <div className="cad-orientation" role="group" aria-label={t('viewer.cad_orientation')}>
                {CUBE_FACES.map(({ face, labelKey }) => (
                  <button
                    key={face}
                    type="button"
                    className={`cad-face cad-face-${face}`}
                    onClick={() => snapTo(face)}
                  >
                    {t(labelKey)}
                  </button>
                ))}
              </div>
              <dl className="cad-readout">
                <div>
                  <dt>{t('viewer.cad_readout_volume')}</dt>
                  <dd>—</dd>
                </div>
                <div>
                  <dt>{t('viewer.cad_readout_surface')}</dt>
                  <dd>—</dd>
                </div>
                <div>
                  <dt>{t('viewer.cad_readout_weight')}</dt>
                  <dd>—</dd>
                </div>
              </dl>
            </>
          )}
        </section>
      </div>
    </main>
  );
}
