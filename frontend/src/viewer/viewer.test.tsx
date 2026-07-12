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
    expect(nextZoom(4, 1)).toBe(4);
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
  getPageText: vi.fn((page: number) => Promise.resolve(PAGE_TEXTS[page - 1] ?? '')),
  renderPage: vi.fn(() => Promise.resolve()),
  renderPagePixels: vi.fn(() =>
    Promise.resolve({ data: new Uint8ClampedArray(4), width: 1, height: 1 }),
  ),
};
const extractPages = vi.fn((_bytes: Uint8Array, _pages: number[]) =>
  Promise.resolve(new Uint8Array([1])),
);

vi.mock('./pdf', () => ({
  loadPdf: vi.fn(() => Promise.resolve(loadedDoc)),
  extractPages: (bytes: Uint8Array, pages: number[]) => extractPages(bytes, pages),
  rotatePages: vi.fn(),
}));

const fetchFileBytes = vi.fn(() => Promise.resolve(new Uint8Array([37, 80, 68, 70])));
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

vi.mock('../parts/api', () => ({
  usePartsApi: () => ({ fetchFileBytes, listFiles }),
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
