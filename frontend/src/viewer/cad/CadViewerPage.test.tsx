/**
 * M2.6 CadViewerPage — component states + chrome, with the two non-jsdom-able
 * seams mocked: the worker MeshProvider (WASM parse is covered by
 * parseStep.test.ts against the real fixture) and the WebGL layer
 * (scene-state correctness is covered by sceneController.test.ts).
 */
import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { renderWithProviders } from '../../test/render';
import type { PartFile } from '../../parts/api';
import type { CadModel } from './model';

const fetchFileBytes = vi.fn();
vi.mock('../../parts/api', () => ({
  usePartsApi: () => ({ fetchFileBytes }),
}));

const loadMesh = vi.fn();
vi.mock('./meshProvider', () => ({
  workerMeshProvider: (bytes: Uint8Array) => loadMesh(bytes),
}));

vi.mock('./viewerGl', () => ({
  createViewerGl: () => ({
    domElement: document.createElement('canvas'),
    start: () => {},
    resize: () => {},
    dispose: () => {},
    syncTarget: () => {},
  }),
}));

import { CadViewerPage } from './CadViewerPage';

const file: PartFile = {
  id: 'f1',
  part_id: 'p1',
  filename: 'halter.step',
  file_type: 'brep_cad',
  content_type: null,
  size_bytes: 1234,
  role: 'primary' as PartFile['role'],
  is_redacted: false,
  source_file_id: null,
  created_at: '2026-07-14T00:00:00Z',
};

function model(names: string[]): CadModel {
  return {
    bodies: names.map((name, i) => ({
      id: `body-${i}`,
      name,
      positions: new Float32Array([0, 0, 0, 10, 0, 0, 0, 10, 0]),
      normals: null,
      indices: new Uint32Array([0, 1, 2]),
      color: null,
    })),
    bbox: { min: [0, 0, 0], max: [10, 10, 0] },
  };
}

beforeEach(() => {
  fetchFileBytes.mockReset();
  loadMesh.mockReset();
  fetchFileBytes.mockResolvedValue(new Uint8Array([1, 2, 3]));
});

describe('CadViewerPage', () => {
  it('shows the loading state while downloading + parsing', async () => {
    loadMesh.mockReturnValue(new Promise(() => {}));
    await renderWithProviders(<CadViewerPage file={file} />);
    expect(await screen.findByText('Modell wird geladen …')).toBeInTheDocument();
  });

  it('shows a non-crashing failure state when the parse fails', async () => {
    loadMesh.mockRejectedValue(new Error('STEP parse failed'));
    await renderWithProviders(<CadViewerPage file={file} />);
    expect(await screen.findByText('Modell konnte nicht geladen werden.')).toBeInTheDocument();
  });

  it('lists bodies in the tree, with the German fallback for unnamed bodies', async () => {
    loadMesh.mockResolvedValue(model(['Deckel', '']));
    await renderWithProviders(<CadViewerPage file={file} />);
    expect(await screen.findByText('Deckel')).toBeInTheDocument();
    expect(screen.getByText('Körper 2')).toBeInTheDocument();
  });

  it('has a Geometric Features tab with the M4 empty state', async () => {
    loadMesh.mockResolvedValue(model(['Deckel']));
    await renderWithProviders(<CadViewerPage file={file} />);
    await screen.findByText('Deckel');
    await userEvent.click(screen.getByRole('tab', { name: 'Geometrische Merkmale' }));
    expect(
      screen.getByText('Geometrische Analyse folgt (Interrogation, M4).'),
    ).toBeInTheDocument();
  });

  it('renders the readout shell with placeholder dashes', async () => {
    loadMesh.mockResolvedValue(model(['Deckel']));
    await renderWithProviders(<CadViewerPage file={file} />);
    await screen.findByText('Deckel');
    for (const label of ['Volumen', 'Oberfläche', 'Gewicht']) {
      const term = screen.getByText(label);
      expect(term.parentElement?.textContent).toContain('—');
    }
  });

  it('switches render modes via the toolbar (pressed state follows)', async () => {
    loadMesh.mockResolvedValue(model(['Deckel']));
    await renderWithProviders(<CadViewerPage file={file} />);
    await screen.findByText('Deckel');
    const shaded = screen.getByRole('button', { name: 'Schattiert' });
    const wireframe = screen.getByRole('button', { name: 'Drahtgitter' });
    expect(shaded).toHaveAttribute('aria-pressed', 'true');
    await userEvent.click(wireframe);
    expect(wireframe).toHaveAttribute('aria-pressed', 'true');
    expect(shaded).toHaveAttribute('aria-pressed', 'false');
  });

  it('offers the six orientation-cube faces and reset view', async () => {
    loadMesh.mockResolvedValue(model(['Deckel']));
    await renderWithProviders(<CadViewerPage file={file} />);
    await screen.findByText('Deckel');
    for (const face of ['Vorne', 'Hinten', 'Links', 'Rechts', 'Oben', 'Unten']) {
      expect(screen.getByRole('button', { name: face })).toBeInTheDocument();
    }
    // snap then reset — smoke: no crash, buttons stay operable
    await userEvent.click(screen.getByRole('button', { name: 'Oben' }));
    await userEvent.click(screen.getByRole('button', { name: 'Ansicht zurücksetzen' }));
    expect(screen.getByRole('button', { name: 'Oben' })).toBeEnabled();
  });

  it('passes the downloaded bytes to the mesh provider', async () => {
    loadMesh.mockResolvedValue(model(['Deckel']));
    await renderWithProviders(<CadViewerPage file={file} />);
    await screen.findByText('Deckel');
    expect(fetchFileBytes).toHaveBeenCalledWith('p1', 'f1');
    expect(loadMesh).toHaveBeenCalledWith(new Uint8Array([1, 2, 3]));
  });
});
