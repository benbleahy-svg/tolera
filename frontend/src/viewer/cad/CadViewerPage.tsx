/**
 * 3D viewer (M2.6 core + M2.7 selection & readout + M2.9 display options &
 * rendering limits). Toolbar with the three render modes + reset + the
 * display-options gear, left Struktur/Merkmale panel (features = M4 empty
 * state), orientation faces. M2.7 adds the selection-data overlay and the
 * whole-file Volume / Surface / Weight readout.
 *
 * M2.9 adds:
 *  - the display-options gear popover: a metric↔imperial unit toggle
 *    (Tolera default = metric mm/kg, never imperial by default — DACH §6), a
 *    live decimal-precision, and a native-model-colours toggle;
 *  - vertex-budget rendering limits: bodies past the 25 M-vertex budget drop to
 *    blue (collection over budget) / orange (single body over budget)
 *    bounding-box simplified reps with matching tree icons, restored by
 *    isolating a body (which re-plans over the smaller visible set). An orange
 *    body also suppresses its (future-M4) interrogation results.
 *
 * Display state is ephemeral (per-viewer session), not persisted. Measure = M2.8.
 */
import { useEffect, useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router-dom';

import { usePartsApi, type PartFile } from '../../parts/api';
import { measure, type MeasurePick, type MeasureResult } from './measure';
import {
  formatAngle,
  formatArea,
  formatLength,
  formatMass,
  formatMeasureDistance,
  formatVolume,
  type DisplayOptions,
  type UnitSystem,
} from './measureFormat';
import { workerMeshProvider } from './meshProvider';
import type { CadModel, EntityRef } from './model';
import { entityKey } from './model';
import {
  DEFAULT_VERTEX_BUDGET,
  bodyVertexCounts,
  planRenderBudget,
  type RepColor,
} from './renderBudget';
import {
  axisDims,
  cumulativeArea,
  facePrimitiveForRef,
  facePropsForRef,
  optimalBoundingBox,
  wholeFileStats,
} from './selection';
import {
  CadSceneController,
  type CubeFace,
  type PickHit,
  type BodyDisplayState,
  type RenderMode,
} from './sceneController';
import { createViewerGl, type ViewerGl } from './viewerGl';

type ViewerTool = 'select' | 'measure';
/** A {@link MeasurePick} plus the face ref, so the scene can highlight it. */
interface MeasurePickUi extends MeasurePick {
  ref: EntityRef;
}

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

const MIN_PRECISION = 0;
const MAX_PRECISION = 6;

type LoadState = 'loading' | 'ready' | 'failed';

function clamp(n: number, lo: number, hi: number): number {
  return Math.min(Math.max(n, lo), hi);
}

/** "x × y × z" with each extent formatted as a length. */
function formatTriple(v: readonly [number, number, number] | null, opts: DisplayOptions): string {
  if (!v) return '—';
  return `${formatLength(v[0], opts)} × ${formatLength(v[1], opts)} × ${formatLength(v[2], opts)}`;
}

export function CadViewerPage({
  file,
  densityGCm3,
  vertexBudget = DEFAULT_VERTEX_BUDGET,
}: {
  file: PartFile;
  /** Material density in g/cm³ for the Weight readout; omitted → em-dash. */
  densityGCm3?: number | null;
  /** Concurrent vertex budget; overridable so tests can drive over-budget bodies. */
  vertexBudget?: number;
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
  const [tool, setTool] = useState<ViewerTool>('select');
  const [measurePicks, setMeasurePicks] = useState<MeasurePickUi[]>([]);
  const [panelTab, setPanelTab] = useState<'tree' | 'features'>('tree');

  // The pick callback is wired into the GL layer once (mount effect below), so
  // it must read the live tool + model through refs, not stale closure state.
  const toolRef = useRef<ViewerTool>(tool);
  toolRef.current = tool;
  const modelRef = useRef<CadModel | null>(null);
  useEffect(() => {
    modelRef.current = model;
  }, [model]);
  // Display options (ephemeral; DACH default = metric, precision 2, native colours on).
  const [gearOpen, setGearOpen] = useState(false);
  const [unitSystem, setUnitSystem] = useState<UnitSystem>('metric');
  const [precision, setPrecision] = useState(2);
  const [nativeColors, setNativeColors] = useState(true);
  // Isolate: when set, only this body renders (drops the vertex load → re-plan).
  const [isolatedBodyId, setIsolatedBodyId] = useState<string | null>(null);

  const displayOpts = useMemo<DisplayOptions>(
    () => ({ language: lang, system: unitSystem, precision }),
    [lang, unitSystem, precision],
  );

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
        modelRef.current = loaded;
        setModel(loaded);
        setSelection([]);
        setMeasurePicks([]);
        setIsolatedBodyId(null);
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
      onPick: (hit: PickHit | null, additive) => {
        if (toolRef.current === 'measure') {
          setMeasurePicks((prev) => {
            if (!hit) return []; // click empty space → clear the measurement
            const m = modelRef.current;
            const primitive = m ? facePrimitiveForRef(m, hit.ref) : null;
            if (!primitive) return prev;
            const next: MeasurePickUi = { ref: hit.ref, primitive, hitPoint: hit.point };
            // ignore re-picking the same face (would read a degenerate 0 mm)
            if (prev.some((p) => entityKey(p.ref) === entityKey(next.ref))) return prev;
            // two picks define a measurement; a third click starts a fresh one
            return prev.length >= 2 ? [next] : [...prev, next];
          });
          return;
        }
        setSelection((prev) => {
          if (!hit) return [];
          const ref = hit.ref;
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

  // The measurement: two picks → distance / exact flag / angle / leader points.
  const measureResult: MeasureResult | null = useMemo(
    () => (measurePicks.length === 2 ? measure(measurePicks[0], measurePicks[1]) : null),
    [measurePicks],
  );

  // Keep the scene face-highlight in sync with whichever tool is active: the
  // select set, or the faces being measured.
  useEffect(() => {
    const refs = tool === 'measure' ? measurePicks.map((p) => p.ref) : selection;
    controllerRef.current?.setSelection(refs);
  }, [selection, measurePicks, tool]);

  // Draw / clear the in-scene measure leader.
  useEffect(() => {
    controllerRef.current?.setMeasure(measureResult?.endpoints ?? null);
  }, [measureResult]);

  const changeTool = (next: ViewerTool) => {
    setTool(next);
    setSelection([]);
    setMeasurePicks([]);
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

  // Vertex-budget plan over the currently-visible bodies (isolate → subset).
  const budgetPlan = useMemo(() => {
    const counts = model ? bodyVertexCounts(model) : [];
    const visible = isolatedBodyId ? counts.filter((c) => c.id === isolatedBodyId) : counts;
    return planRenderBudget(visible, vertexBudget);
  }, [model, isolatedBodyId, vertexBudget]);

  const repByBody = useMemo(() => {
    const map = new Map<string, RepColor>();
    for (const b of budgetPlan.bodies) if (b.repColor) map.set(b.bodyId, b.repColor);
    return map;
  }, [budgetPlan]);

  // Push per-body display (hidden / boxed) to the scene whenever it changes.
  useEffect(() => {
    const controller = controllerRef.current;
    if (!controller || !model) return;
    const states = new Map<string, BodyDisplayState>();
    for (const body of model.bodies) {
      if (isolatedBodyId && body.id !== isolatedBodyId) {
        states.set(body.id, { hidden: true, repColor: null });
      } else {
        states.set(body.id, { hidden: false, repColor: repByBody.get(body.id) ?? null });
      }
    }
    controller.setBodyDisplayStates(states);
  }, [model, isolatedBodyId, repByBody]);

  // Apply the native-colour toggle to the scene.
  useEffect(() => {
    controllerRef.current?.setNativeColors(nativeColors);
  }, [nativeColors, model]);

  // Escape closes the display-options popover (standard popover affordance).
  useEffect(() => {
    if (!gearOpen) return;
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setGearOpen(false);
    };
    document.addEventListener('keydown', onKeyDown);
    return () => document.removeEventListener('keydown', onKeyDown);
  }, [gearOpen]);

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

  const toggleIsolate = (bodyId: string) =>
    setIsolatedBodyId((cur) => (cur === bodyId ? null : bodyId));

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
        <div className="cad-tools" role="group" aria-label={t('viewer.cad_tools')}>
          <button
            type="button"
            aria-pressed={tool === 'select'}
            disabled={state !== 'ready'}
            onClick={() => changeTool('select')}
          >
            {t('viewer.cad_tool_select')}
          </button>
          <button
            type="button"
            aria-pressed={tool === 'measure'}
            disabled={state !== 'ready'}
            onClick={() => changeTool('measure')}
          >
            {t('viewer.cad_tool_measure')}
          </button>
        </div>
        <button type="button" disabled={state !== 'ready'} onClick={resetView}>
          {t('viewer.cad_reset_view')}
        </button>

        <div className="cad-display-options">
          <button
            type="button"
            className="cad-gear"
            aria-label={t('viewer.cad_display_options')}
            aria-expanded={gearOpen}
            disabled={state !== 'ready'}
            onClick={() => setGearOpen((o) => !o)}
          >
            ⚙
          </button>
          {gearOpen && state === 'ready' && (
            <div
              className="cad-display-popover"
              role="group"
              aria-label={t('viewer.cad_display_options')}
            >
              <fieldset className="cad-units">
                <legend>{t('viewer.cad_units')}</legend>
                <button
                  type="button"
                  aria-pressed={unitSystem === 'metric'}
                  onClick={() => setUnitSystem('metric')}
                >
                  {t('viewer.cad_units_metric')}
                </button>
                <button
                  type="button"
                  aria-pressed={unitSystem === 'imperial'}
                  onClick={() => setUnitSystem('imperial')}
                >
                  {t('viewer.cad_units_imperial')}
                </button>
              </fieldset>
              <label className="cad-precision">
                {t('viewer.cad_precision')}
                <input
                  type="number"
                  min={MIN_PRECISION}
                  max={MAX_PRECISION}
                  value={precision}
                  onChange={(e) => {
                    const n = Number.parseInt(e.target.value, 10);
                    if (!Number.isNaN(n)) setPrecision(clamp(n, MIN_PRECISION, MAX_PRECISION));
                  }}
                />
              </label>
              <label className="cad-native-colors">
                <input
                  type="checkbox"
                  checked={nativeColors}
                  onChange={(e) => setNativeColors(e.target.checked)}
                />
                {t('viewer.cad_native_colors')}
              </label>
            </div>
          )}
        </div>
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
            <>
              {isolatedBodyId && (
                <button
                  type="button"
                  className="cad-tree-showall"
                  onClick={() => setIsolatedBodyId(null)}
                >
                  {t('viewer.cad_show_all')}
                </button>
              )}
              <ul className="cad-tree">
                {bodies.map((body, i) => {
                  const rep = repByBody.get(body.id);
                  const isolatedOut = isolatedBodyId != null && body.id !== isolatedBodyId;
                  const name = body.name || t('viewer.cad_body_fallback', { n: i + 1 });
                  const repLabel = rep
                    ? t(rep === 'orange' ? 'viewer.cad_simplified_orange' : 'viewer.cad_simplified_blue')
                    : null;
                  return (
                    <li key={body.id}>
                      <button
                        type="button"
                        className={`cad-tree-body${isolatedOut ? ' cad-tree-body-hidden' : ''}`}
                        aria-pressed={isolatedBodyId === body.id}
                        // the rep meaning lives in the aria-hidden cube's title; surface it
                        // to assistive tech via the button's accessible name when boxed
                        aria-label={repLabel ? `${name} — ${repLabel}` : undefined}
                        // tooltip mirrors the toggle: an isolated body's click un-isolates it
                        title={
                          isolatedBodyId === body.id
                            ? t('viewer.cad_show_all')
                            : t('viewer.cad_isolate')
                        }
                        onClick={() => toggleIsolate(body.id)}
                      >
                        {rep && (
                          <span
                            className={`cad-tree-icon cad-tree-icon-${rep}`}
                            aria-hidden="true"
                            title={t(
                              rep === 'orange'
                                ? 'viewer.cad_simplified_orange'
                                : 'viewer.cad_simplified_blue',
                            )}
                          >
                            {/* simplified-rep cube (blue/orange) — colour from currentColor */}
                            <svg viewBox="0 0 24 24" width="12" height="12" fill="currentColor">
                              <path d="M12 2 L21 7 L12 12 L3 7 Z" opacity="0.95" />
                              <path d="M3 7 L12 12 L12 22 L3 17 Z" opacity="0.6" />
                              <path d="M21 7 L12 12 L12 22 L21 17 Z" opacity="0.78" />
                            </svg>
                          </span>
                        )}
                        {name}
                      </button>
                    </li>
                  );
                })}
              </ul>
            </>
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
                {tool === 'measure' && (
                  <section className="cad-readout-block cad-measure-data">
                    <h3>{t('viewer.cad_measure')}</h3>
                    {measureResult ? (
                      <dl>
                        <div>
                          <dt>{t('viewer.cad_measure_distance')}</dt>
                          <dd>
                            {formatMeasureDistance(
                              measureResult.distanceMm,
                              measureResult.exact,
                              displayOpts,
                            )}
                          </dd>
                        </div>
                        {measureResult.angleDeg != null && (
                          <div>
                            <dt>{t('viewer.cad_measure_angle')}</dt>
                            <dd>{formatAngle(measureResult.angleDeg, displayOpts)}</dd>
                          </div>
                        )}
                      </dl>
                    ) : (
                      <p className="cad-measure-hint">{t('viewer.cad_measure_hint')}</p>
                    )}
                  </section>
                )}

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
                        <dd>{formatArea(active.area, displayOpts)}</dd>
                      </div>
                      <div>
                        <dt>{t('viewer.cad_selection_height')}</dt>
                        <dd>{formatLength(active.height, displayOpts)}</dd>
                      </div>
                      <div>
                        <dt>{t('viewer.cad_selection_diameter')}</dt>
                        <dd>{formatLength(active.diameter, displayOpts)}</dd>
                      </div>
                      <div>
                        <dt>{t('viewer.cad_selection_angle')}</dt>
                        <dd>{formatAngle(active.angle, displayOpts)}</dd>
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
                        <dd>{formatArea(cumulative, displayOpts)}</dd>
                      </div>
                    </dl>
                  </section>
                )}

                <section className="cad-readout-block cad-file-readout">
                  <h3>{t('viewer.cad_readout_file')}</h3>
                  <dl>
                    <div>
                      <dt>{t('viewer.cad_readout_volume')}</dt>
                      <dd>{formatVolume(stats?.volumeMm3 ?? null, displayOpts)}</dd>
                    </div>
                    <div>
                      <dt>{t('viewer.cad_readout_surface')}</dt>
                      <dd>{formatArea(stats?.surfaceAreaMm2 ?? null, displayOpts)}</dd>
                    </div>
                    <div>
                      <dt>{t('viewer.cad_readout_weight')}</dt>
                      <dd>
                        {stats?.massKg != null ? (
                          formatMass(stats.massKg, displayOpts)
                        ) : (
                          <span title={t('viewer.cad_weight_no_material')}>—</span>
                        )}
                      </dd>
                    </div>
                    <div>
                      <dt>{t('viewer.cad_axis_dims')}</dt>
                      <dd>{formatTriple(dims, displayOpts)}</dd>
                    </div>
                    <div>
                      <dt>{t('viewer.cad_bbox_optimal')}</dt>
                      <dd>{formatTriple(obb, displayOpts)}</dd>
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
