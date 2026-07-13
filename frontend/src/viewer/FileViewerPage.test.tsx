/**
 * M2.6 type dispatch — one viewer route, viewer chosen from the M1.2 file
 * record (server truth: file_type category + filename extension, never byte
 * sniffing). PDFs keep the M2.1 viewer, STEP gets the 3D viewer, everything
 * else on the allow-list gets a German-first no-preview state.
 */
import { screen, waitFor } from '@testing-library/react';
import { Route, Routes } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { renderWithProviders } from '../test/render';
import type { PartFile } from '../parts/api';

vi.mock('./PdfViewerPage', () => ({
  PdfViewerPage: () => <div data-testid="pdf-viewer" />,
}));
vi.mock('./cad/CadViewerPage', () => ({
  CadViewerPage: () => <div data-testid="cad-viewer" />,
}));

const listFiles = vi.fn();
vi.mock('../parts/api', () => ({
  usePartsApi: () => ({ listFiles }),
}));

import { FileViewerPage } from './FileViewerPage';

function record(filename: string, fileType: string): PartFile {
  return {
    id: 'f1',
    part_id: 'p1',
    filename,
    file_type: fileType,
    content_type: null,
    size_bytes: 1000,
    role: 'supporting' as PartFile['role'],
    is_redacted: false,
    source_file_id: null,
    created_at: '2026-07-14T00:00:00Z',
  };
}

async function renderViewer(file: PartFile) {
  listFiles.mockResolvedValue([file]);
  await renderWithProviders(
    <Routes>
      <Route path="/parts/:partId/files/:fileId/view" element={<FileViewerPage />} />
    </Routes>,
    { route: '/parts/p1/files/f1/view' },
  );
}

beforeEach(() => {
  listFiles.mockReset();
});

describe('FileViewerPage dispatch', () => {
  it('renders the PDF viewer for a PDF document', async () => {
    await renderViewer(record('zeichnung-4711.pdf', 'document'));
    expect(await screen.findByTestId('pdf-viewer')).toBeInTheDocument();
  });

  it.each(['halter.step', 'halter.STP'])('renders the 3D viewer for %s', async (name) => {
    await renderViewer(record(name, 'brep_cad'));
    expect(await screen.findByTestId('cad-viewer')).toBeInTheDocument();
  });

  it('shows the no-preview state for a non-STEP CAD file (M4 formats)', async () => {
    await renderViewer(record('halter.sldprt', 'brep_cad'));
    expect(
      await screen.findByText('Für diesen Dateityp ist keine Vorschau verfügbar.'),
    ).toBeInTheDocument();
    expect(screen.queryByTestId('cad-viewer')).not.toBeInTheDocument();
    expect(screen.queryByTestId('pdf-viewer')).not.toBeInTheDocument();
  });

  it('shows the no-preview state for a non-PDF document', async () => {
    await renderViewer(record('kalkulation.xlsx', 'document'));
    expect(
      await screen.findByText('Für diesen Dateityp ist keine Vorschau verfügbar.'),
    ).toBeInTheDocument();
  });

  it('shows a not-found state when the file id is not on the part', async () => {
    listFiles.mockResolvedValue([]);
    await renderWithProviders(
      <Routes>
        <Route path="/parts/:partId/files/:fileId/view" element={<FileViewerPage />} />
      </Routes>,
      { route: '/parts/p1/files/missing/view' },
    );
    expect(await screen.findByText('Datei nicht gefunden.')).toBeInTheDocument();
  });

  it('surfaces a load failure instead of spinning forever', async () => {
    listFiles.mockRejectedValue(new Error('boom'));
    await renderWithProviders(
      <Routes>
        <Route path="/parts/:partId/files/:fileId/view" element={<FileViewerPage />} />
      </Routes>,
      { route: '/parts/p1/files/f1/view' },
    );
    await waitFor(() =>
      expect(screen.getByText('Datei konnte nicht geladen werden.')).toBeInTheDocument(),
    );
  });
});
