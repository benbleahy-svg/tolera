/**
 * M2.1 PDF viewer core — the AC list: page multi-select parsing, search with
 * case + whole-word honored (title-block string), the red/blue/black revision
 * diff on a known rev B→C change, extract downloads the selection, and the
 * collapsed-sidebar state surviving reload. pdf.js is mocked at the module
 * boundary (jsdom has no canvas); the pure logic is tested directly.
 */

import { beforeEach, describe, expect, it, vi } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { renderWithProviders } from '../test/render';
import { diffImageData, nextZoom, parsePageSelection, searchPages } from './utils';

// --- pure logic --------------------------------------------------------------
describe('parsePageSelection', () => {
  it('parses lists, ranges, and mixtures, clamped to the page count', () => {
    expect(parsePageSelection('1,3,5', 6)).toEqual([1, 3, 5]);
    expect(parsePageSelection('1-5', 6)).toEqual([1, 2, 3, 4, 5]);
    expect(parsePageSelection('2, 4-6, 4', 5)).toEqual([2, 4, 5]);
    expect(parsePageSelection('0, 9, quatsch', 5)).toEqual([]);
  });
});

describe('searchPages', () => {
  const pages = [
    'Zeichnung: Halter 4711 Werkstoff: 1.4301 Allgemeintoleranzen ISO 2768-m',
    'Rev C Hinweis: Einzeln verpacken (VCI-Folie) iso norm',
  ];

  it('finds the title-block string and honors case sensitivity', () => {
    expect(searchPages(pages, 'ISO', { caseSensitive: false, wholeWord: false })).toHaveLength(2);
    expect(searchPages(pages, 'ISO', { caseSensitive: true, wholeWord: false })).toHaveLength(1);
  });

  it('honors whole-word matching', () => {
    // "verpacken" is a whole word; "packen" only a substring of it
    expect(searchPages(pages, 'packen', { caseSensitive: false, wholeWord: false })).toHaveLength(
      1,
    );
    expect(searchPages(pages, 'packen', { caseSensitive: false, wholeWord: true })).toHaveLength(0);
    expect(
      searchPages(pages, 'verpacken', { caseSensitive: false, wholeWord: true }),
    ).toHaveLength(1);
  });
});

describe('diffImageData', () => {
  const ink = [0, 0, 0, 255];
  const blank = [255, 255, 255, 255];
  const rgba = (...pixels: number[][]) => new Uint8ClampedArray(pixels.flat());

  it('colors removed red, added blue, identical black (spec-exact)', () => {
    const base = rgba(ink, blank, ink);
    const comparison = rgba(blank, ink, ink);
    const out = diffImageData(base, comparison);
    expect([out[0], out[1], out[2], out[3]]).toEqual([220, 0, 0, 255]); // removed → red
    expect([out[4], out[5], out[6], out[7]]).toEqual([0, 0, 220, 255]); // added → blue
    expect([out[8], out[9], out[10], out[11]]).toEqual([0, 0, 0, 255]); // identical → black
  });
});

describe('nextZoom', () => {
  it('steps through the preset ladder and clamps at the ends', () => {
    expect(nextZoom(1, 1)).toBe(1.25);
    expect(nextZoom(1, -1)).toBe(0.75);
    expect(nextZoom(4, 1)).toBe(6);
    expect(nextZoom(8, 1)).toBe(8);
    expect(nextZoom(0.5, -1)).toBe(0.5);
  });
});

// --- the page, with pdf.js mocked ---------------------------------------------
const PAGE_TEXTS = [
  'Zeichnung: Halter 4711 Allgemeintoleranzen ISO 2768-m Rev B',
  'Stueckliste Position 1',
];

const loadedDoc = {
  pageCount: 2,
  getPageSize: vi.fn(() => Promise.resolve({ width: 595, height: 842 })),
  getPageText: vi.fn((page: number) => Promise.resolve(PAGE_TEXTS[page - 1] ?? '')),
  renderPage: vi.fn(() => Promise.resolve()),
  renderPagePixels: vi.fn(() =>
    Promise.resolve({ data: new Uint8ClampedArray(4), width: 1, height: 1 }),
  ),
};
const extractPages = vi.fn((_bytes: Uint8Array, _pages: number[]) =>
  Promise.resolve(new Uint8Array([1])),
);

const drawAnnotations = vi.fn((_bytes: Uint8Array, _objects: unknown[]) =>
  Promise.resolve(new Uint8Array([2])),
);

vi.mock('./pdf', () => ({
  loadPdf: vi.fn(() => Promise.resolve(loadedDoc)),
  extractPages: (bytes: Uint8Array, pages: number[]) => extractPages(bytes, pages),
  rotatePages: vi.fn(),
  drawAnnotations: (bytes: Uint8Array, objects: unknown[]) => drawAnnotations(bytes, objects),
}));

const fetchFileBytes = vi.fn(() => Promise.resolve(new Uint8Array([37, 80, 68, 70])));
const getAnnotations = vi.fn(() => Promise.resolve({ objects: [] }));
const putAnnotations = vi.fn((_p: string, _f: string, objects: unknown[]) =>
  Promise.resolve({ objects }),
);
const listFiles = vi.fn(() =>
  Promise.resolve([
    {
      id: 'f1',
      part_id: 'p1',
      filename: 'halter-4711-rev-b.pdf',
      file_type: 'pdf',
      content_type: 'application/pdf',
      size_bytes: 100,
      role: 'drawing',
      is_redacted: false,
      created_at: '2026-07-12T00:00:00Z',
    },
    {
      id: 'f2',
      part_id: 'p1',
      filename: 'halter-4711-rev-c.pdf',
      file_type: 'pdf',
      content_type: 'application/pdf',
      size_bytes: 100,
      role: 'drawing',
      is_redacted: false,
      created_at: '2026-07-12T00:00:00Z',
    },
  ]),
);

const stableApi = {
  fetchFileBytes,
  listFiles,
  getAnnotations,
  putAnnotations,
  // Found-in-Files panel reads (M3.2) — plain stable functions, never reset.
  getPart: () =>
    Promise.resolve({
      id: 'p1',
      primary_file_id: null,
      name: null,
      part_number: null,
      revision: null,
      description: null,
      archived: false,
      created_at: '',
      updated_at: '',
    }),
  getGeometry: () =>
    Promise.resolve({
      part_id: 'p1',
      size_x: null,
      size_y: null,
      size_z: null,
      max_dim: null,
      med_dim: null,
      min_dim: null,
      area: null,
      volume: null,
      weight: null,
      overrides: {},
    }),
};

vi.mock('../collab/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../collab/api')>()),
  useCollabApi: () => new Proxy({}, { get: () => () => Promise.resolve([]) }),
}));

vi.mock('../parts/api', () => ({
  // the real hook is useMemo-stable; an unstable mock would retrigger the
  // page's load effect on every render
  usePartsApi: () => stableApi,
}));

// M3.2: the page now mounts the Found-in-Files panel — quiet, stable stubs
// (the panel's own behaviour is covered in found-in-files.test.tsx).
const stableLensApi = {
  listFindings: () => Promise.resolve([]),
  extract: () => Promise.resolve({ task_id: 't' }),
  extractStatus: () =>
    Promise.resolve({ state: 'succeeded', finding_count: 0, dropped_count: 0, error: null }),
  acceptFinding: () => Promise.resolve({ finding: null, applied_field: null }),
  rejectFinding: () => Promise.resolve({ finding: null, applied_field: null }),
  replaceFinding: () => Promise.resolve({ finding: null, applied_field: null }),
  addMissing: () => Promise.resolve(null),
};

vi.mock('./lens-api', () => ({
  useLensApi: () => stableLensApi,
}));


import { PdfViewerPage } from './PdfViewerPage';

async function renderViewer() {
  window.history.pushState({}, '', '/parts/p1/files/f1/view');
  return renderWithProviders(<PdfViewerPage />, { route: '/parts/p1/files/f1/view' });
}

// the page reads params via useParams — provide a route wrapper
vi.mock('react-router-dom', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react-router-dom')>();
  return { ...actual, useParams: () => ({ partId: 'p1', fileId: 'f1' }) };
});

beforeEach(() => {
  localStorage.clear();
  extractPages.mockClear();
});

describe('PdfViewerPage', () => {
  it('loads the document, searches with toggles, and reports hit counts', async () => {
    await renderViewer();
    await waitFor(() => expect(screen.getByText('halter-4711-rev-b.pdf')).toBeInTheDocument());
    await userEvent.type(screen.getByLabelText('Im Dokument suchen…'), 'iso');
    expect(await screen.findByText('1 / 1')).toBeInTheDocument();
    await userEvent.click(screen.getByLabelText('Groß-/Kleinschreibung'));
    expect(await screen.findByText('0 / 0')).toBeInTheDocument();
  });

  it('extracts the thumbnail multi-selection as a local download', async () => {
    await renderViewer();
    await waitFor(() => expect(screen.getByLabelText('Seitenauswahl')).toBeInTheDocument());
    await userEvent.type(screen.getByLabelText('Seitenauswahl'), '1-2');
    await userEvent.click(screen.getByRole('button', { name: 'Extrahieren' }));
    await waitFor(() => expect(extractPages).toHaveBeenCalled());
    expect(extractPages.mock.calls[0][1]).toEqual([1, 2]);
  });

  it('persists the collapsed sidebar across reloads', async () => {
    const first = await renderViewer();
    await waitFor(() => expect(screen.getByText('halter-4711-rev-b.pdf')).toBeInTheDocument());
    await userEvent.click(screen.getByRole('button', { name: /Seiten/ }));
    expect(localStorage.getItem('tolera.viewer.sidebar-collapsed')).toBe('1');
    first.unmount();
    await renderViewer();
    await waitFor(() => expect(screen.getByText('halter-4711-rev-b.pdf')).toBeInTheDocument());
    expect(screen.getByRole('button', { name: /Seiten/ })).toHaveAttribute(
      'aria-expanded',
      'false',
    );
  });
});

// --- M2.2: annotation layer -----------------------------------------------
import { emptyLayer, hitTest, layerReducer, type Annotation } from './annotations';

const RECT_ANN: Annotation = {
  id: 'a1',
  page: 1,
  type: 'rectangle',
  rect: { x: 10, y: 10, width: 40, height: 20 },
  style: { stroke: '#d6409f', strokeWidth: 2, fill: 'none', opacity: 1 },
};
const NOTE_ANN: Annotation = {
  id: 'a2',
  page: 1,
  type: 'note',
  at: { x: 100, y: 100 },
  text: 'Kante entgraten',
  style: { stroke: '#1d4ed8', strokeWidth: 1, fill: '#fde68a', opacity: 1 },
};

describe('layerReducer', () => {
  it('undo then redo restores the identical layer (AC-exact)', () => {
    let state = layerReducer(emptyLayer<Annotation>(), { kind: 'load', objects: [] });
    state = layerReducer(state, { kind: 'add', annotation: RECT_ANN });
    state = layerReducer(state, { kind: 'add', annotation: NOTE_ANN });
    const full = state.objects;
    state = layerReducer(state, { kind: 'undo' });
    expect(state.objects).toEqual([RECT_ANN]);
    state = layerReducer(state, { kind: 'redo' });
    expect(state.objects).toEqual(full);
  });

  it('remove + undo restores; redo stack clears on a new edit', () => {
    let state = layerReducer(emptyLayer<Annotation>(), { kind: 'load', objects: [RECT_ANN, NOTE_ANN] });
    state = layerReducer(state, { kind: 'remove', id: 'a1' });
    expect(state.objects).toEqual([NOTE_ANN]);
    state = layerReducer(state, { kind: 'undo' });
    expect(state.objects).toEqual([RECT_ANN, NOTE_ANN]);
    state = layerReducer(state, { kind: 'add', annotation: { ...RECT_ANN, id: 'a3' } });
    expect(state.redoStack).toEqual([]);
    expect(state.dirty).toBe(true);
  });
});

describe('hitTest (eraser)', () => {
  it('hits inside the bounding box with tolerance, misses outside', () => {
    expect(hitTest(RECT_ANN, { x: 30, y: 20 })).toBe(true);
    expect(hitTest(RECT_ANN, { x: 54, y: 32 })).toBe(true); // within tolerance
    expect(hitTest(RECT_ANN, { x: 200, y: 200 })).toBe(false);
    expect(hitTest(NOTE_ANN, { x: 101, y: 99 })).toBe(true);
  });
});

describe('PdfViewerPage annotations', () => {
  it('saves the layer through the API and marks it clean', async () => {
    await renderViewer();
    await waitFor(() => expect(screen.getByText('halter-4711-rev-b.pdf')).toBeInTheDocument());
    // place a rectangle: select the tool, drag on the overlay
    await userEvent.click(screen.getByRole('button', { name: 'Rechteck' }));
    const overlay = screen.getAllByRole('application')[0];
    const { fireEvent } = await import('@testing-library/react');
    fireEvent.pointerDown(overlay, { clientX: 10, clientY: 10 });
    fireEvent.pointerUp(overlay, { clientX: 80, clientY: 50 });
    const save = screen.getByRole('button', { name: 'Anmerkungen speichern' });
    await waitFor(() => expect(save).toBeEnabled());
    await userEvent.click(save);
    await waitFor(() => expect(putAnnotations).toHaveBeenCalled());
    const objects = putAnnotations.mock.calls[0][2] as Annotation[];
    expect(objects).toHaveLength(1);
    expect(objects[0].type).toBe('rectangle');
    await waitFor(() => expect(save).toBeDisabled()); // marked clean
  });

  it('downloads with annotations via the pdf facade', async () => {
    await renderViewer();
    await waitFor(() => expect(screen.getByText('halter-4711-rev-b.pdf')).toBeInTheDocument());
    await userEvent.click(
      screen.getByRole('button', { name: 'Mit Anmerkungen herunterladen' }),
    );
    await waitFor(() => expect(drawAnnotations).toHaveBeenCalled());
  });
});
