/**
 * M4.1 InterrogationPanel — the "interrogating…" state and the analyzed
 * dims readout. The API is mocked at the module boundary (viewer precedent);
 * polling is exercised by resolving queued → succeeded across two calls.
 */

import { beforeEach, describe, expect, it, vi } from 'vitest';
import { screen, waitFor } from '@testing-library/react';

import { renderWithProviders } from '../../test/render';
import { InterrogationPanel } from './InterrogationPanel';
import type { InterrogationStatus } from '../../parts/api';

const getInterrogation = vi.fn();

vi.mock('../../parts/api', () => ({
  usePartsApi: () => ({ getInterrogation }),
}));

function succeeded(): InterrogationStatus {
  return {
    part_id: 'part-1',
    status: 'succeeded',
    run: {
      id: 'run-1',
      part_id: 'part-1',
      file_id: 'file-1',
      family: null,
      material_id: null,
      geom_hash: 'gs1:abc',
      status: 'succeeded',
      error_code: null,
      error_detail: null,
      result: {
        dimensions: {
          size_x: 20,
          size_y: 20,
          size_z: 20,
          max_dim: 20,
          med_dim: 20,
          min_dim: 20,
          area: 2400,
          volume: 8000,
          weight: 63.2,
          bbox_source: 'obb',
        },
      },
      created_at: '2026-07-16T00:00:00Z',
      started_at: '2026-07-16T00:00:01Z',
      finished_at: '2026-07-16T00:00:02Z',
    },
  };
}

const OPTS = { language: 'de', system: 'metric', precision: 2 } as const;

beforeEach(() => {
  getInterrogation.mockReset();
});

describe('InterrogationPanel', () => {
  it('shows the interrogating state while queued, then the analyzed dims', async () => {
    // Stateful mock: the server reports queued until the "worker" finishes.
    let current: InterrogationStatus = { part_id: 'part-1', status: 'queued', run: null };
    getInterrogation.mockImplementation(() => Promise.resolve(current));
    await renderWithProviders(
      <InterrogationPanel partId="part-1" displayOpts={OPTS} pollIntervalMs={5} />,
    );
    // First poll: queued → the spec's "interrogating…" state.
    await waitFor(() => {
      expect(screen.getByRole('status')).toHaveTextContent(/analysiert/i);
    });
    // The run finishes server-side; the next poll renders the dims and stops.
    current = succeeded();
    await waitFor(() => {
      expect(screen.getByText('Abmessungen (Analyse)')).toBeInTheDocument();
    });
    const settled = getInterrogation.mock.calls.length;
    await new Promise((r) => setTimeout(r, 30));
    expect(getInterrogation.mock.calls.length).toBe(settled); // polling stopped
  });

  it('renders volume/area/weight metric-first (German locale)', async () => {
    getInterrogation.mockResolvedValue(succeeded());
    await renderWithProviders(<InterrogationPanel partId="part-1" displayOpts={OPTS} />);
    await waitFor(() => {
      expect(screen.getByText('Abmessungen (Analyse)')).toBeInTheDocument();
    });
    expect(screen.getByText('Volumen')).toBeInTheDocument();
    expect(screen.getByText('Oberfläche')).toBeInTheDocument();
    // Weight arrives in grams (63.2 g) and renders as mass via the shared
    // formatter (kg) — German decimal comma.
    expect(screen.getByText(/0,063\s*kg/)).toBeInTheDocument();
    // The per-family feature list stays a pending note (M4.2+).
    expect(screen.getByText(/Geometrische Analyse steht noch aus/)).toBeInTheDocument();
  });

  it('explains a multi-body failure', async () => {
    const failed = succeeded();
    failed.status = 'failed';
    failed.run = { ...failed.run!, status: 'failed', error_code: 'multi_body', result: null };
    getInterrogation.mockResolvedValue(failed);
    await renderWithProviders(<InterrogationPanel partId="part-1" displayOpts={OPTS} />);
    await waitFor(() => {
      expect(screen.getByRole('status')).toHaveTextContent(/Baugruppe erkannt/);
    });
  });

  it('shows the none state when no run exists', async () => {
    getInterrogation.mockResolvedValue({ part_id: 'part-1', status: 'none', run: null });
    await renderWithProviders(<InterrogationPanel partId="part-1" displayOpts={OPTS} />);
    await waitFor(() => {
      expect(screen.getByText(/Noch keine Geometrieanalyse/)).toBeInTheDocument();
    });
  });
});
