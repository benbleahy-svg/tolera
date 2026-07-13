/**
 * PDF viewer core (M2.1, spec #pdf / #pdf-capabilities; KB pdf-viewer-guide):
 * the estimator's print cockpit — layouts (continuous / page-by-page,
 * single / double / cover-facing), pan + zoom (% / steps / fit width / fit
 * page / marquee), whole-document + per-page rotate, thumbnail panel with
 * `1,3,5` / `1-5` multi-select and rotate / extract / delete, in-document
 * search with case + whole-word toggles, and revision compare (red =
 * removed / blue = added / black = identical, eye toggle). The collapsed
 * sidebar persists (localStorage). Annotate/measure/redact/split arrive in
 * M2.2-M2.5; the Lens overlay in M3.
 */

import { useCallback, useEffect, useMemo, useReducer, useRef, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';

import { ApiError } from '../api/client';
import { usePartsApi, type PartFile } from '../parts/api';
import { AnnotationOverlay } from './AnnotationOverlay';
import { MeasureOverlay, type MeasureTool } from './MeasureOverlay';
import { scaleFromCalibration, scaleFromRatio, type Measurement, type Scale } from './measure';
import {
  PRESETS,
  TOOL_SHORTCUTS,
  emptyLayer,
  layerReducer,
  type Annotation,
  type AnnotationType,
} from './annotations';
import { RedactOverlay, type RedactTool } from './RedactOverlay';
import {
  REDACTION_PRESETS,
  redactedFilename,
  type Redaction,
  type WhiteoutSection,
} from './redact';
import {
  drawAnnotations,
  extractPages,
  loadPdf,
  renderRedactedCopy,
  rotatePages,
  type LoadedPdf,
} from './pdf';
import { diffImageData, nextZoom, parsePageSelection, searchPages, type SearchHit } from './utils';

const SIDEBAR_KEY = 'tolera.viewer.sidebar-collapsed';
// Split-status polling: cadence + cap (the task also hard-times-out server-side)
const SPLIT_POLL_MS = 500;
const SPLIT_POLL_LIMIT = 240;
// 422 codes from the split POST, mapped to user-actionable German-first copy
const SPLIT_ERROR_KEYS: Record<string, string> = {
  nothing_to_split: 'viewer.split_error_nothing_to_split',
  invalid_pdf: 'viewer.split_error_invalid_pdf',
  encrypted_pdf: 'viewer.split_error_encrypted_pdf',
  too_many_pages: 'viewer.split_error_too_many_pages',
};

type PageLayout = 'continuous' | 'paged';
type SpreadMode = 'single' | 'double' | 'cover';

function saveBlob(bytes: Uint8Array, filename: string) {
  const url = URL.createObjectURL(new Blob([bytes as BlobPart], { type: 'application/pdf' }));
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = filename;
  document.body.append(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}

function PageCanvas({
  doc,
  page,
  scale,
  rotation,
  overlay,
  children,
}: {
  doc: LoadedPdf;
  page: number;
  scale: number;
  rotation: number;
  overlay: ImageData | null;
  children?: React.ReactNode;
}) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const overlayRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (canvas) void doc.renderPage(page, canvas, scale, rotation);
  }, [doc, page, scale, rotation]);

  useEffect(() => {
    const canvas = overlayRef.current;
    if (!canvas || !overlay) return;
    canvas.width = overlay.width;
    canvas.height = overlay.height;
    canvas.getContext('2d')?.putImageData(overlay, 0, 0);
  }, [overlay]);

  return (
    <div className="pdf-page" data-page={page}>
      <canvas ref={canvasRef} aria-label={`Seite ${page}`} />
      {overlay && <canvas ref={overlayRef} className="pdf-compare-overlay" />}
      {children}
    </div>
  );
}

export function PdfViewerPage() {
  const { partId, fileId } = useParams<{ partId: string; fileId: string }>();
  const [splitting, setSplitting] = useState(false);
  const [splitMessage, setSplitMessage] = useState<string | null>(null);
  // Guards the split poll loop: once the viewer unmounts, stop scheduling
  // timers, firing status requests, or setting state on a dead component.
  const mountedRef = useRef(true);
  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
    };
  }, []);
  const { t } = useTranslation();
  const api = usePartsApi();

  const [bytes, setBytes] = useState<Uint8Array | null>(null);
  const [doc, setDoc] = useState<LoadedPdf | null>(null);
  const [file, setFile] = useState<PartFile | null>(null);
  const [siblings, setSiblings] = useState<PartFile[]>([]);
  const [pageTexts, setPageTexts] = useState<string[]>([]);
  const [pageSize, setPageSize] = useState<{ width: number; height: number } | null>(null);
  const [error, setError] = useState<string | null>(null);

  const [layout, setLayout] = useState<PageLayout>('continuous');
  const [spread, setSpread] = useState<SpreadMode>('single');
  const [currentPage, setCurrentPage] = useState(1);
  const [zoom, setZoom] = useState(1);
  const [docRotation, setDocRotation] = useState(0);
  const [pageRotations, setPageRotations] = useState<Record<number, number>>({});
  const [hiddenPages, setHiddenPages] = useState<Set<number>>(new Set());
  const [panMode, setPanMode] = useState(false);
  const [marqueeMode, setMarqueeMode] = useState(false);

  const [sidebarCollapsed, setSidebarCollapsed] = useState(
    () => localStorage.getItem(SIDEBAR_KEY) === '1',
  );
  const [selectionInput, setSelectionInput] = useState('');

  const [query, setQuery] = useState('');
  const [caseSensitive, setCaseSensitive] = useState(false);
  const [wholeWord, setWholeWord] = useState(false);
  const [hitIndex, setHitIndex] = useState(0);

  const [layer, dispatchLayer] = useReducer(layerReducer<Annotation>, emptyLayer<Annotation>());
  const [measures, dispatchMeasures] = useReducer(
    layerReducer<Measurement>,
    emptyLayer<Measurement>(),
  );
  const [measureTool, setMeasureTool] = useState<MeasureTool | null>(null);
  const [drawingScale, setDrawingScale] = useState<Scale | null>(null);
  const [snapping, setSnapping] = useState(true);
  const [precision, setPrecision] = useState(1);
  const [scaleWarning, setScaleWarning] = useState(false);
  const [tool, setTool] = useState<AnnotationType | 'eraser' | null>(null);
  const [presetName, setPresetName] = useState<keyof typeof PRESETS>('standard');

  const [redactions, setRedactions] = useState<Redaction[]>([]);
  const [whiteouts, setWhiteouts] = useState<WhiteoutSection[]>([]);
  const [redactTool, setRedactTool] = useState<RedactTool | null>(null);
  const [redactPreset, setRedactPreset] = useState<keyof typeof REDACTION_PRESETS>('schwarz');
  const [whiteoutActive, setWhiteoutActive] = useState(false);
  const [spotlightId, setSpotlightId] = useState<string | null>(null);
  const [redactNotice, setRedactNotice] = useState<string | null>(null);

  const [compareDoc, setCompareDoc] = useState<LoadedPdf | null>(null);
  const [compareVisible, setCompareVisible] = useState(true);
  const [overlays, setOverlays] = useState<Record<number, ImageData>>({});

  const pagesRef = useRef<HTMLElement>(null);
  const dragState = useRef<{ x: number; y: number; left: number; top: number } | null>(null);
  const marqueeStart = useRef<{ x: number; y: number } | null>(null);

  const onPagesMouseDown = (e: React.MouseEvent<HTMLElement>) => {
    const container = pagesRef.current;
    if (!container) return;
    if (marqueeMode) {
      marqueeStart.current = { x: e.clientX, y: e.clientY };
    } else if (panMode) {
      dragState.current = {
        x: e.clientX,
        y: e.clientY,
        left: container.scrollLeft,
        top: container.scrollTop,
      };
    }
  };

  const onPagesMouseMove = (e: React.MouseEvent<HTMLElement>) => {
    const container = pagesRef.current;
    if (!container || !dragState.current) return;
    container.scrollLeft = dragState.current.left - (e.clientX - dragState.current.x);
    container.scrollTop = dragState.current.top - (e.clientY - dragState.current.y);
  };

  const onPagesMouseUp = (e: React.MouseEvent<HTMLElement>) => {
    dragState.current = null;
    const container = pagesRef.current;
    if (marqueeMode && marqueeStart.current && container) {
      // marquee zoom: scale so the dragged region fills the container width
      const width = Math.abs(e.clientX - marqueeStart.current.x);
      if (width > 24) {
        setZoom((z) => Math.min(8, z * (container.clientWidth / width)));
      }
      marqueeStart.current = null;
      setMarqueeMode(false);
    }
  };

  const fail = useCallback((e: unknown) => {
    setError(e instanceof ApiError ? e.message : String(e));
  }, []);

  // real fits, computed from the container and the page's unscaled size
  const fitWidth = useCallback(() => {
    const container = pagesRef.current;
    if (!container || !pageSize) return;
    setZoom(Math.max(0.1, (container.clientWidth - 48) / pageSize.width));
  }, [pageSize]);

  const fitPage = useCallback(() => {
    const container = pagesRef.current;
    if (!container || !pageSize) return;
    setZoom(
      Math.max(
        0.1,
        Math.min(
          (container.clientWidth - 48) / pageSize.width,
          (container.clientHeight - 48) / pageSize.height,
        ),
      ),
    );
  }, [pageSize]);

  // keyboard shortcuts (spec: P pan, Z marquee, Cmd± zoom)
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement | null;
      if (target && ['INPUT', 'TEXTAREA', 'SELECT'].includes(target.tagName)) return;
      if ((e.metaKey || e.ctrlKey) && (e.key === '+' || e.key === '=')) {
        e.preventDefault();
        setZoom((z) => nextZoom(z, 1));
      } else if ((e.metaKey || e.ctrlKey) && e.key === '-') {
        e.preventDefault();
        setZoom((z) => nextZoom(z, -1));
      } else if (e.key === 'p' || e.key === 'P') {
        setPanMode((p) => !p);
      } else if (e.key === 'z' || e.key === 'Z') {
        setMarqueeMode((m) => !m);
      } else if (!e.metaKey && !e.ctrlKey && TOOL_SHORTCUTS[e.key.toLowerCase()]) {
        const next = TOOL_SHORTCUTS[e.key.toLowerCase()];
        setMeasureTool(null);
        setRedactTool(null);
        setTool((current) => (current === next ? null : next));
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);


  useEffect(() => {
    if (!partId || !fileId) return;
    api
      .fetchFileBytes(partId, fileId)
      .then(async (data) => {
        setBytes(data);
        const loaded = await loadPdf(data);
        // the persisted layer must land BEFORE the overlays render — a later
        // 'load' dispatch would wipe markup placed in the gap
        const persisted = await api.getAnnotations(partId, fileId);
        dispatchLayer({ kind: 'load', objects: persisted.objects as Annotation[] });
        setDoc(loaded);
        const texts = await Promise.all(
          Array.from({ length: loaded.pageCount }, (_, i) => loaded.getPageText(i + 1)),
        );
        setPageTexts(texts);
        setPageSize(await loaded.getPageSize(1));
      })
      .catch(fail);
    api
      .listFiles(partId)
      .then((files) => {
        setFile(files.find((f) => f.id === fileId) ?? null);
        setSiblings(files.filter((f) => f.id !== fileId && f.filename.endsWith('.pdf')));
      })
      .catch(fail);
  }, [api, partId, fileId, fail]);

  const hits: SearchHit[] = useMemo(
    () => searchPages(pageTexts, query, { caseSensitive, wholeWord }),
    [pageTexts, query, caseSensitive, wholeWord],
  );
  useEffect(() => setHitIndex(0), [query, caseSensitive, wholeWord]);

  // hit navigation scrolls the hit's page into view (paged: jumps to it)
  useEffect(() => {
    const hit = hits[hitIndex];
    if (!hit) return;
    setCurrentPage(hit.page);
    const target = pagesRef.current?.querySelector(`[data-page="${hit.page}"]`);
    // jsdom has no scrollIntoView — guard so tests and odd embeds stay safe
    if (target instanceof HTMLElement && typeof target.scrollIntoView === 'function') {
      target.scrollIntoView({ block: 'start' });
    }
  }, [hits, hitIndex]);

  const visiblePages = useMemo(() => {
    if (!doc) return [];
    const all = Array.from({ length: doc.pageCount }, (_, i) => i + 1).filter(
      (page) => !hiddenPages.has(page),
    );
    if (layout === 'continuous') return all;
    if (spread === 'single') return all.slice(currentPage - 1, currentPage);
    if (spread === 'cover' && currentPage === 1) return all.slice(0, 1);
    if (spread === 'cover') {
      // booklet pairs after the lone cover: (2,3), (4,5), …
      const pairFirst = currentPage % 2 === 0 ? currentPage : currentPage - 1;
      return all.slice(pairFirst - 1, pairFirst + 1);
    }
    return all.slice(currentPage - 1, currentPage + 1);
  }, [doc, layout, spread, currentPage, hiddenPages]);

  const runCompare = useCallback(
    async (target: LoadedPdf) => {
      if (!doc) return;
      const scale = 1.5;
      const built: Record<number, ImageData> = {};
      const pages = Math.max(doc.pageCount, target.pageCount);
      for (let page = 1; page <= pages; page += 1) {
        const empty = { data: new Uint8ClampedArray(0), width: 0, height: 0 };
        const base = page <= doc.pageCount ? await doc.renderPagePixels(page, scale) : empty;
        const cmp = page <= target.pageCount ? await target.renderPagePixels(page, scale) : empty;
        const width = Math.max(base.width, cmp.width);
        const height = Math.max(base.height, cmp.height);
        if (!width || !height) continue;
        const pad = (src: { data: Uint8ClampedArray; width: number; height: number }) => {
          const out = new Uint8ClampedArray(width * height * 4);
          for (let y = 0; y < src.height; y += 1) {
            out.set(
              src.data.subarray(y * src.width * 4, (y + 1) * src.width * 4),
              y * width * 4,
            );
          }
          return out;
        };
        const diff = diffImageData(pad(base), pad(cmp));
        built[page] = new ImageData(diff, width, height);
      }
      setOverlays(built);
    },
    [doc],
  );

  if (!partId || !fileId) return null;

  const extractSelection = async () => {
    if (!bytes) return;
    const pages = parsePageSelection(selectionInput, doc?.pageCount ?? 0);
    if (!pages.length) return;
    // Extract matches the view: apply any per-page rotations first
    const rotated = Object.fromEntries(
      pages.filter((page) => pageRotations[page]).map((page) => [page, pageRotations[page]]),
    );
    const source = Object.keys(rotated).length ? await rotatePages(bytes, rotated) : bytes;
    saveBlob(
      await extractPages(source, pages),
      `${file?.filename?.replace(/\.pdf$/i, '') ?? 'seiten'}-${pages.join('-')}.pdf`,
    );
  };

  // markup coords live in unrotated page space, so redactions are hidden and
  // blocked while any view rotation is applied — saving then would write marks
  // the user can't see; gate the save on the same condition
  const rotationApplied =
    docRotation % 360 !== 0 || Object.values(pageRotations).some((r) => r % 360 !== 0);

  // Redact → NEW supporting file (spec #collab "exact redacted copy"): the
  // affected pages are re-rendered client-side (renderRedactedCopy) so the
  // redacted content is irrecoverable in the copy; the original is untouched.
  const saveRedactedCopy = async () => {
    if (!bytes || !doc || !file || !redactions.length) return;
    const name = redactedFilename(file.filename);
    if (
      siblings.some((sibling) => sibling.filename === name) &&
      !window.confirm(t('viewer.redact_exists_confirm'))
    ) {
      return;
    }
    try {
      const rendered = await renderRedactedCopy(bytes, doc, redactions);
      await api.saveRedactedCopy(partId, fileId, rendered, name);
      const files = await api.listFiles(partId);
      setSiblings(files.filter((f) => f.id !== fileId && f.filename.endsWith('.pdf')));
      setRedactNotice(t('viewer.redact_saved', { filename: name }));
    } catch (e) {
      fail(e);
  const splitPdf = async () => {
    // Server-side split (M2.5): unlike Extract's local download, this persists
    // one supporting file per page on the part; poll the task for progress.
    if (splitting) return;
    setSplitting(true);
    setSplitMessage(t('viewer.split_running'));
    try {
      const { task_id: taskId } = await api.splitFile(partId, fileId);
      if (!mountedRef.current) return;
      for (let i = 0; i < SPLIT_POLL_LIMIT; i += 1) {
        if (!mountedRef.current) return;
        const status = await api.splitStatus(partId, fileId, taskId);
        if (!mountedRef.current) return;
        if (status.state === 'succeeded') {
          setSplitMessage(t('viewer.split_success', { n: status.file_ids?.length ?? 0 }));
          return;
        }
        if (status.state === 'failed') {
          setSplitMessage(t('viewer.split_failed'));
          return;
        }
        if (status.progress) {
          setSplitMessage(
            t('viewer.split_progress', {
              done: status.progress.done,
              total: status.progress.total,
            }),
          );
        }
        await new Promise((resolve) => setTimeout(resolve, SPLIT_POLL_MS));
      }
      if (!mountedRef.current) return;
      // Poll cap reached — the task may still finish server-side; say so
      // honestly instead of a false "failed".
      setSplitMessage(t('viewer.split_still_running'));
    } catch (err) {
      if (!mountedRef.current) return;
      // Map known 422 codes to localized copy; never surface the raw (English)
      // server message inside a German toast.
      const key = err instanceof ApiError ? SPLIT_ERROR_KEYS[err.code] : undefined;
      setSplitMessage(t(key ?? 'viewer.split_failed'));
    } finally {
      if (mountedRef.current) setSplitting(false);
    }
  };

  const toggleSidebar = () => {
    setSidebarCollapsed((collapsed) => {
      localStorage.setItem(SIDEBAR_KEY, collapsed ? '0' : '1');
      return !collapsed;
    });
  };

  return (
    <main className="viewer-page" data-pan={panMode || undefined}>
      <header className="viewer-toolbar">
        <Link to="/parts">{t('viewer.back_to_parts')}</Link>
        <strong>{file?.filename ?? '…'}</strong>

        <label>
          {t('viewer.layout')}
          <select
            value={layout}
            onChange={(e) => setLayout(e.target.value as PageLayout)}
            aria-label={t('viewer.layout')}
          >
            <option value="continuous">{t('viewer.layout_continuous')}</option>
            <option value="paged">{t('viewer.layout_paged')}</option>
          </select>
        </label>
        <label>
          {t('viewer.spread')}
          <select
            value={spread}
            onChange={(e) => setSpread(e.target.value as SpreadMode)}
            aria-label={t('viewer.spread')}
          >
            <option value="single">{t('viewer.spread_single')}</option>
            <option value="double">{t('viewer.spread_double')}</option>
            <option value="cover">{t('viewer.spread_cover')}</option>
          </select>
        </label>

        <div className="viewer-zoom">
          <button type="button" onClick={() => setZoom((z) => nextZoom(z, -1))} aria-label="Zoom −">
            −
          </button>
          <input
            value={Math.round(zoom * 100)}
            size={4}
            aria-label={t('viewer.zoom_pct')}
            onChange={(e) => {
              const pct = Number(e.target.value);
              if (Number.isFinite(pct) && pct >= 10 && pct <= 800) setZoom(pct / 100);
            }}
          />
          %
          <button type="button" onClick={() => setZoom((z) => nextZoom(z, 1))} aria-label="Zoom +">
            +
          </button>
          <button type="button" onClick={fitPage}>
            {t('viewer.fit_page')}
          </button>
          <button type="button" onClick={fitWidth}>
            {t('viewer.fit_width')}
          </button>
          <button
            type="button"
            aria-pressed={marqueeMode}
            onClick={() => setMarqueeMode((m) => !m)}
          >
            {t('viewer.marquee')}
          </button>
          <button type="button" aria-pressed={panMode} onClick={() => setPanMode((p) => !p)}>
            {t('viewer.pan')}
          </button>
          <button type="button" onClick={() => setDocRotation((r) => (r + 90) % 360)}>
            {t('viewer.rotate_doc')}
          </button>
        </div>

        <div className="viewer-search" role="search">
          <input
            value={query}
            placeholder={t('viewer.search')}
            aria-label={t('viewer.search')}
            onChange={(e) => setQuery(e.target.value)}
          />
          <label>
            <input
              type="checkbox"
              checked={caseSensitive}
              onChange={(e) => setCaseSensitive(e.target.checked)}
            />
            {t('viewer.case_sensitive')}
          </label>
          <label>
            <input
              type="checkbox"
              checked={wholeWord}
              onChange={(e) => setWholeWord(e.target.checked)}
            />
            {t('viewer.whole_word')}
          </label>
          <span aria-live="polite">
            {query ? t('viewer.hits', { current: hits.length ? hitIndex + 1 : 0, total: hits.length }) : ''}
          </span>
          <button
            type="button"
            disabled={!hits.length}
            aria-label={t('viewer.prev_hit')}
            onClick={() => setHitIndex((i) => (i - 1 + hits.length) % hits.length)}
          >
            ↑
          </button>
          <button
            type="button"
            disabled={!hits.length}
            aria-label={t('viewer.next_hit')}
            onClick={() => setHitIndex((i) => (i + 1) % hits.length)}
          >
            ↓
          </button>
        </div>

        <div className="viewer-compare">
          <select
            defaultValue=""
            aria-label={t('viewer.compare_pick')}
            onChange={async (e) => {
              if (!e.target.value) return;
              try {
                const data = await api.fetchFileBytes(partId, e.target.value);
                const loaded = await loadPdf(data);
                setCompareDoc(loaded);
                setCompareVisible(true);
                await runCompare(loaded);
              } catch (err) {
                fail(err);
              }
            }}
          >
            <option value="">{t('viewer.compare_pick')}</option>
            {siblings.map((sibling) => (
              <option key={sibling.id} value={sibling.id}>
                {sibling.filename}
              </option>
            ))}
          </select>
          {compareDoc && (
            <button
              type="button"
              aria-pressed={compareVisible}
              aria-label={t('viewer.compare_toggle')}
              onClick={() => setCompareVisible((v) => !v)}
            >
              👁
            </button>
          )}
        </div>
        <div className="viewer-annotate" role="toolbar" aria-label={t('viewer.annotate_tools')}>
          {(
            [
              ['underline', 'U'],
              ['highlight', 'H'],
              ['rectangle', 'R'],
              ['free_text', 'T'],
              ['freehand', 'F'],
              ['freehand_highlight', ''],
              ['note', 'N'],
              ['squiggly', 'G'],
              ['strikeout', 'K'],
              ['shape_rectangle', ''],
              ['line', 'L'],
              ['polyline', ''],
              ['arrow', 'A'],
              ['arc', ''],
              ['ellipse', 'O'],
              ['polygon', ''],
            ] as [AnnotationType, string][]
          ).map(([type, key]) => (
            <button
              key={type}
              type="button"
              aria-pressed={tool === type}
              title={key ? `${t(`viewer.tool_${type}`)} (${key})` : t(`viewer.tool_${type}`)}
              onClick={() => {
                setMeasureTool(null);
                setRedactTool(null);
                setTool((current) => (current === type ? null : type));
              }}
            >
              {t(`viewer.tool_${type}`)}
            </button>
          ))}
          <button
            type="button"
            aria-pressed={tool === 'eraser'}
            onClick={() => {
              setMeasureTool(null);
              setRedactTool(null);
              setTool((current) => (current === 'eraser' ? null : 'eraser'));
            }}
          >
            {t('viewer.tool_eraser')}
          </button>
          <select
            value={presetName}
            aria-label={t('viewer.preset')}
            onChange={(e) => setPresetName(e.target.value as keyof typeof PRESETS)}
          >
            {Object.keys(PRESETS).map((name) => (
              <option key={name} value={name}>
                {t(`viewer.preset_${name}`)}
              </option>
            ))}
          </select>
          <button
            type="button"
            disabled={!layer.undoStack.length}
            onClick={() => dispatchLayer({ kind: 'undo' })}
          >
            {t('viewer.undo')}
          </button>
          <button
            type="button"
            disabled={!layer.redoStack.length}
            onClick={() => dispatchLayer({ kind: 'redo' })}
          >
            {t('viewer.redo')}
          </button>
          <button
            type="button"
            disabled={!layer.dirty}
            onClick={() => {
              api
                .putAnnotations(partId, fileId, layer.objects)
                .then(() => dispatchLayer({ kind: 'saved' }))
                .catch(fail);
            }}
          >
            {t('viewer.save_annotations')}
          </button>
          <button
            type="button"
            onClick={async () => {
              if (!bytes) return;
              saveBlob(
                await drawAnnotations(bytes, layer.objects),
                `${file?.filename?.replace(/\.pdf$/i, '') ?? 'dokument'}-annotiert.pdf`,
              );
            }}
          >
            {t('viewer.download_with_annotations')}
          </button>
          <button type="button" disabled title={t('viewer.collab_stub_hint')}>
            {t('viewer.save_to_collaboration')}
          </button>
        </div>
        <div className="viewer-annotate" role="toolbar" aria-label={t('viewer.measure_tools')}>
          <label>
            {t('viewer.scale')}
            <select
              value={drawingScale?.source === 'ratio' ? drawingScale.label : ''}
              aria-label={t('viewer.scale')}
              onChange={(e) => {
                if (!e.target.value) return;
                const [drawn, real] = e.target.value.split(':').map(Number);
                setDrawingScale(scaleFromRatio(drawn, real));
                setScaleWarning(false);
              }}
            >
              <option value="">
                {drawingScale?.source === 'calibrated'
                  ? t('viewer.scale_calibrated', { label: drawingScale.label })
                  : t('viewer.scale_unset')}
              </option>
              {['1:1', '1:2', '1:5', '1:10', '2:1'].map((ratio) => (
                <option key={ratio} value={ratio}>
                  {ratio}
                </option>
              ))}
            </select>
          </label>
          <button
            type="button"
            aria-pressed={measureTool === 'calibrate'}
            onClick={() => {
              setTool(null);
              setRedactTool(null);
              setMeasureTool((current) => (current === 'calibrate' ? null : 'calibrate'));
              setScaleWarning(false);
            }}
          >
            {t('viewer.calibrate')}
          </button>
          {(
            [
              'distance',
              'arc',
              'perimeter',
              'area_custom',
              'area_circle',
              'area_rectangle',
              'count',
            ] as MeasureTool[]
          ).map((kind) => (
            <button
              key={kind}
              type="button"
              aria-pressed={measureTool === kind}
              onClick={() => {
                // spec: "Set scale first" — measuring without one warns/blocks
                if (!drawingScale) {
                  setScaleWarning(true);
                  return;
                }
                setScaleWarning(false);
                setTool(null);
                setRedactTool(null);
                setMeasureTool((current) => (current === kind ? null : kind));
              }}
            >
              {t(`viewer.measure_${kind}`)}
            </button>
          ))}
          <button
            type="button"
            aria-pressed={measureTool === 'erase'}
            onClick={() => {
              setTool(null);
              setRedactTool(null);
              setMeasureTool((current) => (current === 'erase' ? null : 'erase'));
            }}
          >
            {t('viewer.measure_erase')}
          </button>
          <label>
            <input
              type="checkbox"
              checked={snapping}
              onChange={(e) => setSnapping(e.target.checked)}
            />
            {t('viewer.snapping')}
          </label>
          <label>
            {t('viewer.precision')}
            <select
              value={precision}
              aria-label={t('viewer.precision')}
              onChange={(e) => setPrecision(Number(e.target.value))}
            >
              {[0, 1, 2].map((digits) => (
                <option key={digits} value={digits}>
                  {digits}
                </option>
              ))}
            </select>
          </label>
          <button
            type="button"
            disabled={!measures.undoStack.length}
            onClick={() => dispatchMeasures({ kind: 'undo' })}
          >
            {t('viewer.measure_undo')}
          </button>
          <button
            type="button"
            disabled={!measures.redoStack.length}
            onClick={() => dispatchMeasures({ kind: 'redo' })}
          >
            {t('viewer.measure_redo')}
          </button>
          {scaleWarning && (
            <span role="alert" className="est-warning-banner">
              {t('viewer.scale_required')}
            </span>
          )}
        </div>
        <div className="viewer-annotate" role="toolbar" aria-label={t('viewer.redact_tools')}>
          {(
            [
              ['region', 'redact_region'],
              ['page', 'redact_page'],
              ['whiteout', 'whiteout_draw'],
              ['spotlight', 'spotlight'],
              ['erase', 'redact_erase'],
            ] as [RedactTool, string][]
          ).map(([kind, label]) => (
            <button
              key={kind}
              type="button"
              aria-pressed={redactTool === kind}
              onClick={() => {
                setTool(null);
                setMeasureTool(null);
                setRedactTool((current) => (current === kind ? null : kind));
              }}
            >
              {t(`viewer.${label}`)}
            </button>
          ))}
          <span>{t('viewer.redact_fill')}</span>
          {(Object.keys(REDACTION_PRESETS) as (keyof typeof REDACTION_PRESETS)[]).map((name) => (
            <button
              key={name}
              type="button"
              aria-pressed={redactPreset === name}
              onClick={() => setRedactPreset(name)}
            >
              {t(`viewer.redact_fill_${name}`)}
            </button>
          ))}
          <label>
            <input
              type="checkbox"
              checked={whiteoutActive}
              onChange={(e) => setWhiteoutActive(e.target.checked)}
            />
            {t('viewer.whiteout_toggle')}
          </label>
          <button
            type="button"
            disabled={!redactions.length || rotationApplied}
            title={rotationApplied ? t('viewer.redact_rotation_hint') : undefined}
            onClick={() => void saveRedactedCopy()}
          >
            {t('viewer.save_redacted_copy')}
          </button>
          {redactNotice && <span role="status">{redactNotice}</span>}
        </div>
      </header>

      {error && (
        <p role="alert" className="est-error">
          {error}
        </p>
      )}

      <div className="viewer-body">
        <aside className={sidebarCollapsed ? 'viewer-sidebar collapsed' : 'viewer-sidebar'}>
          <button type="button" onClick={toggleSidebar} aria-expanded={!sidebarCollapsed}>
            {sidebarCollapsed ? '⟩' : '⟨'} {t('viewer.pages')}
          </button>
          {!sidebarCollapsed && doc && (
            <>
              <input
                value={selectionInput}
                placeholder="1,3 / 1-5"
                aria-label={t('viewer.page_selection')}
                onChange={(e) => setSelectionInput(e.target.value)}
              />
              <div className="viewer-thumb-actions">
                <button
                  type="button"
                  onClick={() => {
                    for (const page of parsePageSelection(selectionInput, doc.pageCount)) {
                      setPageRotations((prev) => ({
                        ...prev,
                        [page]: ((prev[page] ?? 0) + 90) % 360,
                      }));
                    }
                  }}
                >
                  {t('viewer.rotate_pages')}
                </button>
                <button type="button" onClick={() => void extractSelection()}>
                  {t('viewer.extract_pages')}
                </button>
                <button type="button" disabled={splitting} onClick={() => void splitPdf()}>
                  {t('viewer.split_pdf')}
                </button>
                <button
                  type="button"
                  // view-session removal only — the stored file is untouched;
                  // persisted page splits are M2.5's Split PDF
                  onClick={() =>
                    setHiddenPages(
                      (prev) =>
                        new Set([...prev, ...parsePageSelection(selectionInput, doc.pageCount)]),
                    )
                  }
                >
                  {t('viewer.delete_pages')}
                </button>
                {hiddenPages.size > 0 && (
                  <button type="button" onClick={() => setHiddenPages(new Set())}>
                    {t('viewer.restore_pages')}
                  </button>
                )}
              </div>
              {splitMessage && (
                <p role="status" className="viewer-split-status">
                  {splitMessage}
                </p>
              )}
              <ol className="viewer-thumbs">
                {Array.from({ length: doc.pageCount }, (_, i) => i + 1)
                  .filter((page) => !hiddenPages.has(page))
                  .map((page) => (
                    <li key={page}>
                      <button
                        type="button"
                        aria-current={layout === 'paged' && page === currentPage}
                        onClick={() => setCurrentPage(page)}
                      >
                        {page}
                      </button>
                    </li>
                  ))}
              </ol>
            </>
          )}
        </aside>

        <section
          ref={pagesRef}
          className={`viewer-pages layout-${layout} spread-${spread}`}
          data-marquee={marqueeMode || undefined}
          onMouseDown={onPagesMouseDown}
          onMouseMove={onPagesMouseMove}
          onMouseUp={onPagesMouseUp}
        >
          {doc &&
            visiblePages.map((page) => (
              <PageCanvas
                key={page}
                doc={doc}
                page={page}
                scale={zoom}
                rotation={(docRotation + (pageRotations[page] ?? 0)) % 360}
                overlay={compareDoc && compareVisible ? (overlays[page] ?? null) : null}
              >
                <AnnotationOverlay
                  ariaLabel={t('viewer.annotations_page', { page })}
                  page={page}
                  zoom={zoom}
                  annotations={
                    // coordinates live in unrotated page space — hide + block
                    // markup while a rotation is applied (export stays honest)
                    (docRotation + (pageRotations[page] ?? 0)) % 360 === 0 ? layer.objects : []
                  }
                  tool={(docRotation + (pageRotations[page] ?? 0)) % 360 === 0 ? tool : null}
                  style={PRESETS[presetName]}
                  onAdd={(annotation) => dispatchLayer({ kind: 'add', annotation })}
                  onErase={(id) => dispatchLayer({ kind: 'remove', id })}
                  promptText={(kind) =>
                    window.prompt(
                      kind === 'note' ? t('viewer.note_prompt') : t('viewer.text_prompt'),
                    )
                  }
                />
                <MeasureOverlay
                  ariaLabel={t('viewer.measurements_page', { page })}
                  page={page}
                  zoom={zoom}
                  scale={drawingScale}
                  measurements={
                    (docRotation + (pageRotations[page] ?? 0)) % 360 === 0 ? measures.objects : []
                  }
                  tool={
                    (docRotation + (pageRotations[page] ?? 0)) % 360 === 0 ? measureTool : null
                  }
                  snapping={snapping}
                  precision={precision}
                  onAdd={(measurement) => dispatchMeasures({ kind: 'add', annotation: measurement })}
                  onErase={(id) => dispatchMeasures({ kind: 'remove', id })}
                  onCalibrated={(measuredPts) => {
                    const known = window.prompt(t('viewer.calibrate_prompt'));
                    const parsed = known ? Number(known.replace(',', '.')) : NaN;
                    const next = scaleFromCalibration(measuredPts, parsed);
                    if (next) {
                      setDrawingScale(next);
                      setMeasureTool(null);
                    }
                  }}
                />
                <RedactOverlay
                  ariaLabel={t('viewer.redactions_page', { page })}
                  page={page}
                  zoom={zoom}
                  redactions={
                    (docRotation + (pageRotations[page] ?? 0)) % 360 === 0
                      ? redactions
                      : []
                  }
                  whiteouts={
                    (docRotation + (pageRotations[page] ?? 0)) % 360 === 0 ? whiteouts : []
                  }
                  tool={
                    (docRotation + (pageRotations[page] ?? 0)) % 360 === 0 ? redactTool : null
                  }
                  style={REDACTION_PRESETS[redactPreset]}
                  whiteoutActive={whiteoutActive}
                  spotlightId={spotlightId}
                  onAddRedaction={(redaction) => setRedactions((prev) => [...prev, redaction])}
                  onAddWhiteout={(section) => setWhiteouts((prev) => [...prev, section])}
                  onEraseRedaction={(id) =>
                    setRedactions((prev) => prev.filter((r) => r.id !== id))
                  }
                  onEraseWhiteout={(id) => {
                    setWhiteouts((prev) => prev.filter((w) => w.id !== id));
                    setSpotlightId((current) => (current === id ? null : current));
                  }}
                  onSpotlight={(id) =>
                    setSpotlightId((current) => (current === id ? null : id))
                  }
                />
              </PageCanvas>
            ))}
        </section>
      </div>

      {layout === 'paged' && doc && (
        <footer className="viewer-pager">
          <button
            type="button"
            disabled={currentPage <= 1}
            onClick={() => setCurrentPage((p) => Math.max(1, p - 1))}
          >
            ‹
          </button>
          <span>
            {currentPage} / {doc.pageCount}
          </span>
          <button
            type="button"
            disabled={currentPage >= doc.pageCount}
            onClick={() => setCurrentPage((p) => Math.min(doc.pageCount, p + 1))}
          >
            ›
          </button>
        </footer>
      )}
    </main>
  );
}
