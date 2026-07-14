/**
 * 3D viewer (M2.6 core + M2.7 selection & readout). Toolbar with the three
 * render modes + reset, left Struktur/Merkmale panel (features = M4 empty
 * state), orientation faces. M2.7 adds: click a face → selection-data overlay
 * (Type / Area / Height / Diameter / Angle), cumulative area across a
 * multi-pick, and the whole-file Volume / Surface / Weight readout filled from
 * the tessellation. Weight needs a material density (optional prop); without it
 * the row shows an em-dash + tooltip (the quote-item context that supplies it
 * arrives in M2.10). Measure = M2.8; display-options gear + limits = M2.9.
 */
import { useEffect, useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router-dom';

import { usePartsApi, type PartFile } from '../../parts/api';
import {
  formatAngle,
  formatArea,
  formatLength,
  formatMass,
  formatVolume,
} from './measureFormat';
import { workerMeshProvider } from './meshProvider';
import type { CadModel, EntityRef } from './model';
import { entityKey } from './model';
import {
  axisDims,
  cumulativeArea,
  facePropsForRef,
  optimalBoundingBox,
  wholeFileStats,
} from './selection';
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

/** "x × y × z" with each extent formatted as a length. */
function formatTriple(v: readonly [number, number, number] | null, lang: string): string {
  if (!v) return '—';
  return `${formatLength(v[0], lang)} × ${formatLength(v[1], lang)} × ${formatLength(v[2], lang)}`;
}

export function CadViewerPage({
  file,
  densityGCm3,
}: {
  file: PartFile;
  /** Material density in g/cm³ for the Weight readout; omitted → em-dash. */
  densityGCm3?: number | null;
}) {
  const api = usePartsApi();
  const { t, i18n } = useTranslation();
  const lang = i18n.language;
  const canvasHostRef = useRef<HTMLDivElement>(null);
  const controllerRef = useRef<CadSceneController | null>(null);
  const glRef = useRef<ViewerGl | null>(null);

  const [state, setState] = useState<LoadState>('loading');
  const [renderMode, setRenderModeState] = useState<RenderMode>('shaded');
  const [model, setModel] = useState<CadModel | null>(null);
  const [selection, setSelection] = useState<EntityRef[]>([]);
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
      .then((loaded) => {
        if (abort.signal.aborted) return;
        controller.loadModel(loaded);
        setModel(loaded);
        setSelection([]);
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

    const gl = createViewerGl(controller, {
      onPick: (ref, additive) => {
        setSelection((prev) => {
          if (!ref) return [];
          if (!additive) return [ref];
          const key = entityKey(ref);
          return prev.some((r) => entityKey(r) === key)
            ? prev.filter((r) => entityKey(r) !== key)
            : [...prev, ref];
        });
      },
    });
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

  // Keep the scene highlight in sync with the selection set.
  useEffect(() => {
    controllerRef.current?.setSelection(selection);
  }, [selection]);

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

  const stats = useMemo(
    () => (model ? wholeFileStats(model, densityGCm3 ?? null) : null),
    [model, densityGCm3],
  );
  const dims = useMemo(() => (model ? axisDims(model) : null), [model]);
  const obb = useMemo(() => (model ? optimalBoundingBox(model) : null), [model]);
  const active = useMemo(
    () => (model ? facePropsForRef(model, selection[selection.length - 1]) : null),
    [model, selection],
  );
  const cumulative = useMemo(
    () => (model && selection.length > 0 ? cumulativeArea(model, selection) : null),
    [model, selection],
  );

  const bodies = model?.bodies ?? [];

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

              <div className="cad-readout">
                {active && (
                  <section className="cad-readout-block cad-selection-data">
                    <h3>{t('viewer.cad_selection_data')}</h3>
                    <dl>
                      <div>
                        <dt>{t('viewer.cad_selection_type')}</dt>
                        <dd>{t(`viewer.cad_facetype_${active.type}`)}</dd>
                      </div>
                      <div>
                        <dt>{t('viewer.cad_selection_area')}</dt>
                        <dd>{formatArea(active.area, lang)}</dd>
                      </div>
                      <div>
                        <dt>{t('viewer.cad_selection_height')}</dt>
                        <dd>{formatLength(active.height, lang)}</dd>
                      </div>
                      <div>
                        <dt>{t('viewer.cad_selection_diameter')}</dt>
                        <dd>{formatLength(active.diameter, lang)}</dd>
                      </div>
                      <div>
                        <dt>{t('viewer.cad_selection_angle')}</dt>
                        <dd>{formatAngle(active.angle, lang)}</dd>
                      </div>
                    </dl>
                  </section>
                )}

                {cumulative != null && (
                  <section className="cad-readout-block cad-cumulative">
                    <h3>{t('viewer.cad_cumulative')}</h3>
                    <dl>
                      <div>
                        <dt>{t('viewer.cad_cumulative_area')}</dt>
                        <dd>{formatArea(cumulative, lang)}</dd>
                      </div>
                    </dl>
                  </section>
                )}

                <section className="cad-readout-block cad-file-readout">
                  <h3>{t('viewer.cad_readout_file')}</h3>
                  <dl>
                    <div>
                      <dt>{t('viewer.cad_readout_volume')}</dt>
                      <dd>{formatVolume(stats?.volumeMm3 ?? null, lang)}</dd>
                    </div>
                    <div>
                      <dt>{t('viewer.cad_readout_surface')}</dt>
                      <dd>{formatArea(stats?.surfaceAreaMm2 ?? null, lang)}</dd>
                    </div>
                    <div>
                      <dt>{t('viewer.cad_readout_weight')}</dt>
                      <dd>
                        {stats?.massKg != null ? (
                          formatMass(stats.massKg, lang)
                        ) : (
                          <span title={t('viewer.cad_weight_no_material')}>—</span>
                        )}
                      </dd>
                    </div>
                    <div>
                      <dt>{t('viewer.cad_axis_dims')}</dt>
                      <dd>{formatTriple(dims, lang)}</dd>
                    </div>
                    <div>
                      <dt>{t('viewer.cad_bbox_optimal')}</dt>
                      <dd>{formatTriple(obb, lang)}</dd>
                    </div>
                  </dl>
                </section>
              </div>
            </>
          )}
        </section>
      </div>
    </main>
  );
}
