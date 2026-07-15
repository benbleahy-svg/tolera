/**
 * M2.4 redact UI flow — overlay gestures (region / whole page / whiteout /
 * spotlight / erase), one-tool-at-a-time across annotate/measure/redact, and
 * the save flow: render → POST as supporting file → refresh, with a confirm
 * when a redacted copy already exists. pdf.js is mocked at the module
 * boundary (jsdom has no canvas), per viewer.test.tsx.
 */

import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { renderWithProviders } from '../test/render';
import { partPanelStubs } from '../test/lensStubs';
import { REDACTION_PRESETS, type Redaction, type WhiteoutSection } from './redact';
import { RedactOverlay } from './RedactOverlay';

// --- the overlay ---------------------------------------------------------------

const overlayProps = {
  ariaLabel: 'Schwärzungen Seite 1',
  page: 1,
  zoom: 1,
  redactions: [] as Redaction[],
  whiteouts: [] as WhiteoutSection[],
  tool: null as React.ComponentProps<typeof RedactOverlay>['tool'],
  style: REDACTION_PRESETS.schwarz,
  whiteoutActive: false,
  spotlightId: null as string | null,
  onAddRedaction: () => {},
  onAddWhiteout: () => {},
  onEraseRedaction: () => {},
  onEraseWhiteout: () => {},
  onSpotlight: () => {},
};

describe('RedactOverlay', () => {
  it('drag with the region tool adds a redaction in the active preset', () => {
    const onAddRedaction = vi.fn();
    render(
      <RedactOverlay
        {...overlayProps}
        tool="region"
        style={REDACTION_PRESETS.weiss}
        onAddRedaction={onAddRedaction}
      />,
    );
    const svg = screen.getByRole('application');
    fireEvent.pointerDown(svg, { clientX: 10, clientY: 20 });
    fireEvent.pointerUp(svg, { clientX: 60, clientY: 50 });
    expect(onAddRedaction).toHaveBeenCalledTimes(1);
    const added = onAddRedaction.mock.calls[0][0] as Redaction;
    expect(added.page).toBe(1);
    expect(added.rect).toEqual({ x: 10, y: 20, width: 50, height: 30 });
    expect(added.fill).toBe(REDACTION_PRESETS.weiss.fill); // recolour applies
  });

  it('click with the page tool adds a whole-page redaction (no rect)', () => {
    const onAddRedaction = vi.fn();
    render(<RedactOverlay {...overlayProps} tool="page" onAddRedaction={onAddRedaction} />);
    fireEvent.pointerDown(screen.getByRole('application'), { clientX: 5, clientY: 5 });
    expect(onAddRedaction).toHaveBeenCalledTimes(1);
    expect(onAddRedaction.mock.calls[0][0].rect).toBeUndefined();
  });

  it('repeat page-tool clicks do not stack duplicate whole-page redactions', () => {
    const onAddRedaction = vi.fn();
    render(
      <RedactOverlay
        {...overlayProps}
        tool="page"
        redactions={[{ id: 'whole', page: 1, ...REDACTION_PRESETS.schwarz }]}
        onAddRedaction={onAddRedaction}
      />,
    );
    fireEvent.pointerDown(screen.getByRole('application'), { clientX: 5, clientY: 5 });
    expect(onAddRedaction).not.toHaveBeenCalled();
  });

  it('drag with the whiteout tool adds a section', () => {
    const onAddWhiteout = vi.fn();
    render(<RedactOverlay {...overlayProps} tool="whiteout" onAddWhiteout={onAddWhiteout} />);
    const svg = screen.getByRole('application');
    fireEvent.pointerDown(svg, { clientX: 0, clientY: 0 });
    fireEvent.pointerUp(svg, { clientX: 40, clientY: 40 });
    expect(onAddWhiteout).toHaveBeenCalledTimes(1);
    expect(onAddWhiteout.mock.calls[0][0].rect).toEqual({ x: 0, y: 0, width: 40, height: 40 });
  });

  it('erase removes the region under the click (regions before whole-page)', () => {
    const onEraseRedaction = vi.fn();
    const redactions: Redaction[] = [
      { id: 'whole', page: 1, ...REDACTION_PRESETS.schwarz },
      {
        id: 'region',
        page: 1,
        rect: { x: 10, y: 10, width: 20, height: 20 },
        ...REDACTION_PRESETS.schwarz,
      },
    ];
    render(
      <RedactOverlay
        {...overlayProps}
        tool="erase"
        redactions={redactions}
        onEraseRedaction={onEraseRedaction}
      />,
    );
    const svg = screen.getByRole('application');
    fireEvent.pointerDown(svg, { clientX: 15, clientY: 15 });
    expect(onEraseRedaction).toHaveBeenCalledWith('region');
    fireEvent.pointerDown(svg, { clientX: 200, clientY: 200 });
    expect(onEraseRedaction).toHaveBeenCalledWith('whole');
  });

  it('whiteout mode paints sections opaque white; spotlight lifts exactly one', () => {
    const whiteouts: WhiteoutSection[] = [
      { id: 'w1', page: 1, rect: { x: 0, y: 0, width: 10, height: 10 } },
      { id: 'w2', page: 1, rect: { x: 20, y: 0, width: 10, height: 10 } },
    ];
    const { container, rerender } = render(
      <RedactOverlay {...overlayProps} whiteouts={whiteouts} whiteoutActive spotlightId="w2" />,
    );
    const rects = container.querySelectorAll('rect.pdf-whiteout');
    expect(rects).toHaveLength(2);
    expect(rects[0]).toHaveAttribute('fill', '#ffffff');
    expect(rects[1]).toHaveAttribute('fill', 'none'); // the spotlighted one
    // whiteout off → sections are outlines only, nothing covered
    rerender(
      <RedactOverlay {...overlayProps} whiteouts={whiteouts} whiteoutActive={false} />,
    );
    for (const rect of container.querySelectorAll('rect.pdf-whiteout')) {
      expect(rect).toHaveAttribute('fill', 'none');
    }
  });

  it('spotlight tool toggles the section under the click', () => {
    const onSpotlight = vi.fn();
    const whiteouts: WhiteoutSection[] = [
      { id: 'w1', page: 1, rect: { x: 0, y: 0, width: 10, height: 10 } },
    ];
    render(
      <RedactOverlay
        {...overlayProps}
        tool="spotlight"
        whiteouts={whiteouts}
        whiteoutActive
        onSpotlight={onSpotlight}
      />,
    );
    fireEvent.pointerDown(screen.getByRole('application'), { clientX: 5, clientY: 5 });
    expect(onSpotlight).toHaveBeenCalledWith('w1');
  });

  it('honors the active-only hit-testing contract (data-active)', () => {
    const { rerender } = render(<RedactOverlay {...overlayProps} tool={null} />);
    expect(screen.getByRole('application')).not.toHaveAttribute('data-active');
    rerender(<RedactOverlay {...overlayProps} tool="region" />);
    expect(screen.getByRole('application')).toHaveAttribute('data-active');
  });
});

// --- the page flow ---------------------------------------------------------------

const loadedDoc = {
  pageCount: 1,
  getPageSize: vi.fn(() => Promise.resolve({ width: 595, height: 842 })),
  getPageText: vi.fn(() => Promise.resolve('Zeichnung GEHEIM')),
  renderPage: vi.fn(() => Promise.resolve()),
  renderPagePixels: vi.fn(() =>
    Promise.resolve({ data: new Uint8ClampedArray(4), width: 1, height: 1 }),
  ),
};

vi.mock('./pdf', () => ({
  loadPdf: vi.fn(() => Promise.resolve(loadedDoc)),
  extractPages: vi.fn(),
  rotatePages: vi.fn(),
  drawAnnotations: vi.fn(),
  renderRedactedCopy: vi.fn(() => Promise.resolve(new Uint8Array([9, 9, 9]))),
}));

const sourceFile = {
  id: 'f1',
  part_id: 'p1',
  filename: 'halter.pdf',
  file_type: 'pdf',
  content_type: 'application/pdf',
  size_bytes: 4,
  role: 'primary',
  is_redacted: false,
  created_at: '2026-07-13T00:00:00Z',
};

const stableApi = {
  fetchFileBytes: vi.fn(() => Promise.resolve(new Uint8Array([37, 80, 68, 70]))),
  listFiles: vi.fn(() => Promise.resolve([sourceFile])),
  getAnnotations: vi.fn(() => Promise.resolve({ objects: [] })),
  putAnnotations: vi.fn(),
  saveRedactedCopy: vi.fn(() =>
    Promise.resolve({ ...sourceFile, id: 'f2', filename: 'halter-redacted.pdf' }),
  ),
  ...partPanelStubs,
};

vi.mock('../collab/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../collab/api')>()),
  useCollabApi: () => new Proxy({}, { get: () => () => Promise.resolve([]) }),
}));

vi.mock('../parts/api', () => ({
  usePartsApi: () => stableApi,
}));

// M3.2: the page now mounts the Found-in-Files panel — quiet shared stubs
// (the panel's own behaviour is covered in found-in-files.test.tsx).

vi.mock('./lens-api', async () => {
  // Hoist-safe: the factory imports the stub itself instead of closing over
  // this file's static import (vitest hoists mock factories above it).
  const { stableLensApi } = await import('../test/lensStubs');
  return { useLensApi: () => stableLensApi };
});


vi.mock('react-router-dom', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react-router-dom')>();
  return { ...actual, useParams: () => ({ partId: 'p1', fileId: 'f1' }) };
});

import { renderRedactedCopy } from './pdf';
import { PdfViewerPage } from './PdfViewerPage';

async function renderViewer(files: (typeof sourceFile)[] = [sourceFile]) {
  vi.clearAllMocks();
  stableApi.listFiles.mockResolvedValue(files);
  await renderWithProviders(<PdfViewerPage />, { route: '/parts/p1/files/f1/view' });
  await waitFor(() =>
    expect(screen.getByRole('button', { name: 'Bereich schwärzen' })).toBeInTheDocument(),
  );
}

async function dragRegion() {
  await userEvent.click(screen.getByRole('button', { name: 'Bereich schwärzen' }));
  const overlay = await screen.findByRole('application', { name: 'Schwärzungen Seite 1' });
  fireEvent.pointerDown(overlay, { clientX: 10, clientY: 10 });
  fireEvent.pointerUp(overlay, { clientX: 80, clientY: 40 });
}

describe('PdfViewerPage redact flow', () => {
  it('arming a redact tool clears annotate + measure (one tool at a time)', async () => {
    await renderViewer();
    await userEvent.click(screen.getByRole('button', { name: 'Markieren' }));
    expect(screen.getByRole('button', { name: 'Markieren' })).toHaveAttribute(
      'aria-pressed',
      'true',
    );
    await userEvent.click(screen.getByRole('button', { name: 'Bereich schwärzen' }));
    expect(screen.getByRole('button', { name: 'Markieren' })).toHaveAttribute(
      'aria-pressed',
      'false',
    );
    expect(screen.getByRole('button', { name: 'Bereich schwärzen' })).toHaveAttribute(
      'aria-pressed',
      'true',
    );
    // and the other way round
    await userEvent.click(screen.getByRole('button', { name: 'Markieren' }));
    expect(screen.getByRole('button', { name: 'Bereich schwärzen' })).toHaveAttribute(
      'aria-pressed',
      'false',
    );
  });

  it('drag → save posts the rendered copy and refreshes the file list', async () => {
    await renderViewer();
    const save = screen.getByRole('button', { name: 'Geschwärzte Kopie speichern' });
    expect(save).toBeDisabled(); // nothing to save yet
    await dragRegion();
    expect(save).toBeEnabled();
    await userEvent.click(save);
    await waitFor(() => expect(stableApi.saveRedactedCopy).toHaveBeenCalledTimes(1));
    // rendered from the fetched bytes + loaded doc with the drawn region
    const [renderedBytes, renderedDoc, redactions] = vi.mocked(renderRedactedCopy).mock
      .calls[0];
    expect(renderedBytes).toEqual(new Uint8Array([37, 80, 68, 70]));
    expect(renderedDoc).toBe(loadedDoc);
    expect(redactions).toHaveLength(1);
    expect(redactions[0].rect).toEqual({ x: 10, y: 10, width: 70, height: 30 });
    expect(stableApi.saveRedactedCopy).toHaveBeenCalledWith(
      'p1',
      'f1',
      new Uint8Array([9, 9, 9]),
      'halter-redacted.pdf',
    );
    expect(stableApi.listFiles).toHaveBeenCalledTimes(2); // initial + refresh
    expect(await screen.findByRole('status')).toHaveTextContent('halter-redacted.pdf');
  });

  it('asks before saving when a redacted copy already exists', async () => {
    await renderViewer([
      sourceFile,
      { ...sourceFile, id: 'f2', filename: 'halter-redacted.pdf', role: 'supporting' },
    ]);
    await dragRegion();
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(false);
    await userEvent.click(screen.getByRole('button', { name: 'Geschwärzte Kopie speichern' }));
    expect(confirm).toHaveBeenCalled();
    expect(stableApi.saveRedactedCopy).not.toHaveBeenCalled();
    confirm.mockReturnValue(true);
    await userEvent.click(screen.getByRole('button', { name: 'Geschwärzte Kopie speichern' }));
    await waitFor(() => expect(stableApi.saveRedactedCopy).toHaveBeenCalledTimes(1));
    confirm.mockRestore();
  });

  it('blocks saving while a view rotation is applied (coords are unrotated)', async () => {
    await renderViewer();
    await dragRegion();
    const save = screen.getByRole('button', { name: 'Geschwärzte Kopie speichern' });
    expect(save).toBeEnabled();
    // rotate page 1 via the sidebar → redactions hide, save must lock
    await userEvent.type(screen.getByLabelText('Seitenauswahl'), '1');
    await userEvent.click(screen.getByRole('button', { name: 'Drehen' }));
    expect(save).toBeDisabled();
  });

  it('whiteout toggle + spotlight drive the overlay view state', async () => {
    await renderViewer();
    // draw a whiteout section
    await userEvent.click(screen.getByRole('button', { name: 'Whiteout-Bereich' }));
    const overlay = await screen.findByRole('application', { name: 'Schwärzungen Seite 1' });
    fireEvent.pointerDown(overlay, { clientX: 0, clientY: 0 });
    fireEvent.pointerUp(overlay, { clientX: 30, clientY: 30 });
    // toggle whiteout on → the section covers (opaque white)
    await userEvent.click(screen.getByLabelText('Whiteout'));
    const section = overlay.querySelector('rect.pdf-whiteout');
    expect(section).toHaveAttribute('fill', '#ffffff');
    // spotlight it → lifted
    await userEvent.click(screen.getByRole('button', { name: 'Spotlight' }));
    fireEvent.pointerDown(overlay, { clientX: 15, clientY: 15 });
    expect(overlay.querySelector('rect.pdf-whiteout')).toHaveAttribute('fill', 'none');
    // spotlight again → back to covered
    fireEvent.pointerDown(overlay, { clientX: 15, clientY: 15 });
    expect(overlay.querySelector('rect.pdf-whiteout')).toHaveAttribute('fill', '#ffffff');
  });
});
