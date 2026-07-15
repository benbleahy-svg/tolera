/**
 * M2.5 Split PDF — the viewer side: the Split-PDF action posts the split,
 * polls the task status, and narrates progress → success (or failure) via
 * the aria-live status region. The server work is mocked at the parts-api
 * module boundary (as in viewer.test.tsx).
 */

import { describe, expect, it, vi } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { renderWithProviders } from '../test/render';
import { partPanelStubs } from '../test/lensStubs';

const loadedDoc = {
  pageCount: 3,
  getPageSize: vi.fn(() => Promise.resolve({ width: 595, height: 842 })),
  getPageText: vi.fn(() => Promise.resolve('')),
  renderPage: vi.fn(() => Promise.resolve()),
  renderPagePixels: vi.fn(() =>
    Promise.resolve({ data: new Uint8ClampedArray(4), width: 1, height: 1 }),
  ),
};

vi.mock('./pdf', () => ({
  loadPdf: vi.fn(() => Promise.resolve(loadedDoc)),
  extractPages: vi.fn(() => Promise.resolve(new Uint8Array([1]))),
  rotatePages: vi.fn(),
  drawAnnotations: vi.fn(() => Promise.resolve(new Uint8Array([2]))),
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
      filename: 'halter-4711-blaetter.pdf',
      file_type: 'pdf',
      content_type: 'application/pdf',
      size_bytes: 100,
      role: 'primary',
      is_redacted: false,
      source_file_id: null,
      created_at: '2026-07-13T00:00:00Z',
    },
  ]),
);

const splitFile = vi.fn(() => Promise.resolve({ task_id: 't1' }));
const splitStatus = vi
  .fn()
  .mockResolvedValueOnce({
    state: 'in_progress',
    progress: { done: 1, total: 3 },
    file_ids: null,
    error: null,
  })
  .mockResolvedValueOnce({
    state: 'succeeded',
    progress: { done: 3, total: 3 },
    file_ids: ['n1', 'n2', 'n3'],
    error: null,
  });

const stableApi = {
  fetchFileBytes,
  listFiles,
  getAnnotations,
  putAnnotations,
  splitFile,
  splitStatus,
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


// the page reads params via useParams — provide a route wrapper
vi.mock('react-router-dom', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react-router-dom')>();
  return { ...actual, useParams: () => ({ partId: 'p1', fileId: 'f1' }) };
});

import { PdfViewerPage } from './PdfViewerPage';

describe('Split PDF (M2.5)', () => {
  it('posts the split, polls, and reports progress then success', async () => {
    window.history.pushState({}, '', '/parts/p1/files/f1/view');
    renderWithProviders(<PdfViewerPage />, { route: '/parts/p1/files/f1/view' });
    const user = userEvent.setup();

    const button = await screen.findByRole('button', { name: 'PDF aufteilen' });
    await user.click(button);

    expect(splitFile).toHaveBeenCalledWith('p1', 'f1');
    await waitFor(
      () => {
        // Success names the count — "3 Seiten als neue Dateien gespeichert".
        expect(screen.getByRole('status')).toHaveTextContent(
          '3 Seiten als neue Dateien gespeichert',
        );
      },
      { timeout: 4000 },
    );
    expect(splitStatus).toHaveBeenCalledWith('p1', 'f1', 't1');
    expect(splitStatus).toHaveBeenCalledTimes(2);
  });

  it('reports failure when the task fails', async () => {
    splitFile.mockResolvedValueOnce({ task_id: 't2' });
    splitStatus.mockReset();
    splitStatus.mockResolvedValueOnce({
      state: 'failed',
      progress: null,
      file_ids: null,
      error: { code: 'split_failed', message: 'Split failed.' },
    });

    window.history.pushState({}, '', '/parts/p1/files/f1/view');
    renderWithProviders(<PdfViewerPage />, { route: '/parts/p1/files/f1/view' });
    const user = userEvent.setup();

    await user.click(await screen.findByRole('button', { name: 'PDF aufteilen' }));
    await waitFor(
      () => {
        expect(screen.getByRole('status')).toHaveTextContent('Aufteilen fehlgeschlagen');
      },
      { timeout: 4000 },
    );
  });

  it('stops polling once the viewer unmounts', async () => {
    splitFile.mockResolvedValueOnce({ task_id: 't3' });
    splitStatus.mockReset();
    // Never resolves to a terminal state — the loop would poll forever if the
    // component kept running after unmount.
    splitStatus.mockResolvedValue({
      state: 'in_progress',
      progress: { done: 1, total: 3 },
      file_ids: null,
      error: null,
    });

    window.history.pushState({}, '', '/parts/p1/files/f1/view');
    const { unmount } = await renderWithProviders(<PdfViewerPage />, {
      route: '/parts/p1/files/f1/view',
    });
    const user = userEvent.setup();

    await user.click(await screen.findByRole('button', { name: 'PDF aufteilen' }));
    await waitFor(() => expect(splitStatus).toHaveBeenCalled());

    unmount();
    const callsAtUnmount = splitStatus.mock.calls.length;

    // Well past two poll intervals — without the mounted-ref guard the loop
    // would fire several more requests; with it, at most one in-flight call
    // can land before the loop bails.
    await new Promise((resolve) => setTimeout(resolve, 1500));
    expect(splitStatus.mock.calls.length).toBeLessThanOrEqual(callsAtUnmount + 1);
  });
});
