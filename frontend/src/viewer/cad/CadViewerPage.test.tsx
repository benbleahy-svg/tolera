/**
 * M2.6 CadViewerPage — component states + chrome, with the two non-jsdom-able
 * seams mocked: the worker MeshProvider (WASM parse is covered by
 * parseStep.test.ts against the real fixture) and the WebGL layer
 * (scene-state correctness is covered by sceneController.test.ts).
 */
import { act, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { renderWithProviders } from '../../test/render';
import type { PartFile } from '../../parts/api';
import type { CadModel, EntityRef } from './model';

const fetchFileBytes = vi.fn();
vi.mock('../../parts/api', () => ({
  usePartsApi: () => ({ fetchFileBytes }),
}));

const loadMesh = vi.fn();
vi.mock('./meshProvider', () => ({
  workerMeshProvider: (bytes: Uint8Array) => loadMesh(bytes),
}));

type PickHit = { ref: EntityRef; point: [number, number, number] };

// Capture the pick callback the page hands the (mocked) GL layer so tests can
// simulate a canvas click without a real WebGL raycast.
const gl = vi.hoisted(() => ({
  onPick: undefined as ((hit: PickHit | null, additive: boolean) => void) | undefined,
}));
vi.mock('./viewerGl', () => ({
  createViewerGl: (_controller: unknown, opts?: { onPick?: typeof gl.onPick }) => {
    gl.onPick = opts?.onPick;
    return {
      domElement: document.createElement('canvas'),
      start: () => {},
      resize: () => {},
      dispose: () => {},
      syncTarget: () => {},
    };
  },
}));

/** Simulate a canvas click on a face (or empty space when ref is null). */
function pick(
  ref: EntityRef | null,
  additive = false,
  point: [number, number, number] = [0, 0, 0],
): void {
  act(() => gl.onPick?.(ref ? { ref, point } : null, additive));
}

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
      faces: [{ first: 0, last: 0 }],
      color: null,
    })),
    bbox: { min: [0, 0, 0], max: [10, 10, 0] },
  };
}

/** A closed 10 mm cube (volume 1000 mm³ = 1 cm³, each side 100 mm²). */
function cube10(): CadModel {
  const p = [
    [0, 0, 0], [10, 0, 0], [10, 10, 0], [0, 10, 0],
    [0, 0, 10], [10, 0, 10], [10, 10, 10], [0, 10, 10],
  ];
  const quads = [
    [0, 3, 2, 1], [4, 5, 6, 7], [0, 1, 5, 4], [2, 3, 7, 6], [1, 2, 6, 5], [3, 0, 4, 7],
  ];
  const positions: number[] = [];
  const indices: number[] = [];
  const faces: { first: number; last: number }[] = [];
  let tri = 0;
  for (const [a, b, c, d] of quads) {
    const base = positions.length / 3;
    positions.push(...p[a], ...p[b], ...p[c], ...p[d]);
    indices.push(base, base + 1, base + 2, base, base + 2, base + 3);
    faces.push({ first: tri, last: tri + 1 });
    tri += 2;
  }
  return {
    bodies: [
      {
        id: 'body-0',
        name: 'Würfel',
        positions: Float32Array.from(positions),
        normals: null,
        indices: Uint32Array.from(indices),
        faces,
        color: null,
      },
    ],
    bbox: { min: [0, 0, 0], max: [10, 10, 10] },
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

  it('shows the loading state while the download itself is pending', async () => {
    fetchFileBytes.mockReturnValue(new Promise(() => {}));
    await renderWithProviders(<CadViewerPage file={file} />);
    expect(await screen.findByText('Modell wird geladen …')).toBeInTheDocument();
  });

  it('shows the failure state when the download fails', async () => {
    fetchFileBytes.mockRejectedValue(new Error('download failed'));
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
    expect(screen.getByText('Geometrische Analyse steht noch aus (M4).')).toBeInTheDocument();
  });

  it('fills the whole-file readout from the loaded model', async () => {
    loadMesh.mockResolvedValue(cube10());
    await renderWithProviders(<CadViewerPage file={file} />);
    await screen.findByText('Würfel');
    // 1000 mm³ = 1,00 cm³ ; surface 600 mm²
    expect(screen.getByText('Volumen').parentElement?.textContent).toContain('1,00 cm³');
    expect(screen.getByText('Oberfläche').parentElement?.textContent).toContain('600,00 mm²');
  });

  it('shows an em-dash weight with a tooltip when no material density is known', async () => {
    loadMesh.mockResolvedValue(cube10());
    await renderWithProviders(<CadViewerPage file={file} />);
    await screen.findByText('Würfel');
    const weight = screen.getByText('Gewicht').parentElement;
    expect(weight?.textContent).toContain('—');
    expect(weight?.querySelector('[title]')?.getAttribute('title')).toMatch(/Material/);
  });

  it('computes weight when a material density is supplied', async () => {
    loadMesh.mockResolvedValue(cube10());
    await renderWithProviders(<CadViewerPage file={file} densityGCm3={7.85} />);
    await screen.findByText('Würfel');
    // 7.85 g/cm³ × 1 cm³ = 7.85 g = 0,008 kg
    expect(screen.getByText('Gewicht').parentElement?.textContent).toContain('0,008 kg');
  });

  it('shows selection data when a face is picked, then clears on empty-space click', async () => {
    loadMesh.mockResolvedValue(cube10());
    await renderWithProviders(<CadViewerPage file={file} />);
    await screen.findByText('Würfel');

    expect(screen.queryByText('Auswahldaten')).not.toBeInTheDocument();
    pick({ kind: 'face', bodyId: 'body-0', index: 0 });
    expect(screen.getByText('Auswahldaten')).toBeInTheDocument();
    // a cube side is a plane of 100 mm²
    expect(screen.getByText('Typ').parentElement?.textContent).toContain('Ebene');
    expect(screen.getByText('Fläche').parentElement?.textContent).toContain('100,00 mm²');

    pick(null);
    expect(screen.queryByText('Auswahldaten')).not.toBeInTheDocument();
  });

  it('sums face area across an additive multi-pick', async () => {
    loadMesh.mockResolvedValue(cube10());
    await renderWithProviders(<CadViewerPage file={file} />);
    await screen.findByText('Würfel');

    pick({ kind: 'face', bodyId: 'body-0', index: 0 });
    pick({ kind: 'face', bodyId: 'body-0', index: 1 }, true);
    // two 100 mm² sides → 200 mm²
    expect(screen.getByText('Kumulierte Auswahl').parentElement?.textContent).toContain(
      '200,00 mm²',
    );
  });

  it('measure tool: shows the hint until two faces are picked', async () => {
    loadMesh.mockResolvedValue(cube10());
    await renderWithProviders(<CadViewerPage file={file} />);
    await screen.findByText('Würfel');

    await userEvent.click(screen.getByRole('button', { name: 'Messen' }));
    expect(screen.getByText('Messung')).toBeInTheDocument();
    expect(screen.getByText(/Zwei Flächen wählen/)).toBeInTheDocument();
    // measure mode does not show the M2.7 selection-data block
    expect(screen.queryByText('Auswahldaten')).not.toBeInTheDocument();
  });

  it('measure tool: parallel faces read an EXACT distance (no ~) + 0° angle', async () => {
    loadMesh.mockResolvedValue(cube10());
    await renderWithProviders(<CadViewerPage file={file} />);
    await screen.findByText('Würfel');

    await userEvent.click(screen.getByRole('button', { name: 'Messen' }));
    // face 0 = bottom (z=0), face 1 = top (z=10) → parallel planes, 10 mm apart
    pick({ kind: 'face', bodyId: 'body-0', index: 0 });
    pick({ kind: 'face', bodyId: 'body-0', index: 1 });

    const distance = screen.getByText('Abstand').parentElement?.textContent ?? '';
    expect(distance).toContain('10,00 mm');
    expect(distance).not.toContain('~'); // exact — the estimator-trust signal
    expect(screen.getByText('Winkel zwischen Flächen').parentElement?.textContent).toContain('0°');
  });

  it('measure tool: skew faces read an APPROXIMATE (~) distance + 90° angle', async () => {
    loadMesh.mockResolvedValue(cube10());
    await renderWithProviders(<CadViewerPage file={file} />);
    await screen.findByText('Würfel');

    await userEvent.click(screen.getByRole('button', { name: 'Messen' }));
    // face 0 = bottom (−z), face 2 = −y side → perpendicular, not a special pair
    pick({ kind: 'face', bodyId: 'body-0', index: 0 }, false, [5, 5, 0]);
    pick({ kind: 'face', bodyId: 'body-0', index: 2 }, false, [5, 0, 5]);

    expect(screen.getByText('Abstand').parentElement?.textContent).toContain('~');
    expect(screen.getByText('Winkel zwischen Flächen').parentElement?.textContent).toContain('90°');
  });

  it('measure tool: re-picking the same face is ignored (no degenerate 0 mm)', async () => {
    loadMesh.mockResolvedValue(cube10());
    await renderWithProviders(<CadViewerPage file={file} />);
    await screen.findByText('Würfel');

    await userEvent.click(screen.getByRole('button', { name: 'Messen' }));
    pick({ kind: 'face', bodyId: 'body-0', index: 0 });
    pick({ kind: 'face', bodyId: 'body-0', index: 0 }); // same face again → ignored
    // still only one pick → no measurement, the hint remains
    expect(screen.queryByText('Abstand')).not.toBeInTheDocument();
    expect(screen.getByText(/Zwei Flächen wählen/)).toBeInTheDocument();
  });

  it('measure tool: clicking empty space clears the measurement', async () => {
    loadMesh.mockResolvedValue(cube10());
    await renderWithProviders(<CadViewerPage file={file} />);
    await screen.findByText('Würfel');

    await userEvent.click(screen.getByRole('button', { name: 'Messen' }));
    pick({ kind: 'face', bodyId: 'body-0', index: 0 });
    pick({ kind: 'face', bodyId: 'body-0', index: 1 });
    expect(screen.getByText('Abstand')).toBeInTheDocument();

    pick(null);
    expect(screen.queryByText('Abstand')).not.toBeInTheDocument();
    expect(screen.getByText(/Zwei Flächen wählen/)).toBeInTheDocument();
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
