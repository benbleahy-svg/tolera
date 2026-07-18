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
      inputs_hash: '',
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
    // let any in-flight poll land before sampling the count — on a slow
    // runner the request issued just before the stop can resolve late
    await new Promise((r) => setTimeout(r, 30));
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
    expect(screen.getByText(/Merkmalserkennung folgt/)).toBeInTheDocument();
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

  it('renders the sheet-metal results block with the flat-pattern thumbnail (M4.2)', async () => {
    // The bracket fixture's analytic values (goldens.json).
    const sheet = succeeded();
    sheet.run!.family = 'SHEET_METAL';
    sheet.run!.result = {
      ...sheet.run!.result!,
      family: 'SHEET_METAL',
      family_scalars: {
        thickness: 2,
        bend_count: 1,
        flat_area: 4814.16,
        total_cut_length: 292.57,
        pierce_count: 0,
        size_x: 95.87,
        size_y: 50,
        flat_pattern: {
          size_x: 95.87,
          size_y: 50,
          bend_lines: [{ position: 57.94, angle: 90 }],
        },
      },
      features: [
        {
          name: 'bend',
          properties: { radius: 3, angle: 90, length: 50, k_factor: 0.369 },
          geometry_refs: [],
        },
      ],
    };
    getInterrogation.mockResolvedValue(sheet);
    await renderWithProviders(<InterrogationPanel partId="part-1" displayOpts={OPTS} />);
    await waitFor(() => {
      expect(screen.getByText('Blechanalyse – Ergebnisse')).toBeInTheDocument();
    });
    // The four block attributes (DemoA/8), German-first, mm/mm² primary.
    expect(screen.getByText('Blechdicke')).toBeInTheDocument();
    expect(screen.getByText(/2,00\s*mm/)).toBeInTheDocument();
    expect(screen.getByText('Fläche (Abwicklung)')).toBeInTheDocument();
    expect(screen.getByText('Abwicklungsmaße')).toBeInTheDocument();
    expect(screen.getByText(/95,87\s*mm\s*×\s*50,00\s*mm/)).toBeInTheDocument();
    expect(screen.getByText('Anzahl Biegungen')).toBeInTheDocument();
    // The flat-pattern thumbnail renders (acceptance) with its bend line.
    const thumb = screen.getByRole('img', { name: /Abwicklung/ });
    expect(thumb.querySelector('rect')).not.toBeNull();
    expect(thumb.querySelectorAll('line')).toHaveLength(1);
    // The generic pending note is replaced by the family block.
    expect(screen.queryByText(/Merkmalserkennung folgt/)).not.toBeInTheDocument();
  });

  it('renders the milling results block with per-setup runtimes (M4.4)', async () => {
    // The block-3setups fixture's analytic values (goldens.json → milling).
    const mill = succeeded();
    mill.run!.family = 'MILLING';
    mill.run!.result = {
      ...mill.run!.result!,
      family: 'MILLING',
      confidence: 'High',
      family_scalars: {
        setup_count: 3,
        runtime: 0.021055,
        setup_time: 3,
        setups: [
          {
            direction: [0, 0, 1],
            setup_time: 1,
            runtime: 0.003166,
            confidence: 'High',
            features: [],
            feedback: [],
          },
          {
            direction: [1, 0, 0],
            setup_time: 1,
            runtime: 0.009,
            confidence: 'High',
            features: [],
            feedback: [],
          },
          {
            direction: [0, -1, 0],
            setup_time: 1,
            runtime: 0.008888,
            confidence: 'High',
            features: [],
            feedback: [],
          },
        ],
      },
      features: [],
    };
    getInterrogation.mockResolvedValue(mill);
    await renderWithProviders(<InterrogationPanel partId="part-1" displayOpts={OPTS} />);
    await waitFor(() => {
      expect(screen.getByText('Fräsanalyse – Ergebnisse')).toBeInTheDocument();
    });
    // setup count: the dd next to the label (the # also appears as a table
    // row index, so scope the query)
    expect(
      screen.getByText('Anzahl Aufspannungen').nextElementSibling,
    ).toHaveTextContent('3');
    // aggregate setup time (3 h) and runtime (~1,3 min), German decimal comma
    expect(screen.getByText(/3,00\s*h/)).toBeInTheDocument();
    expect(screen.getByText(/1,3\s*min/)).toBeInTheDocument();
    expect(screen.getByText('Verlässlichkeit')).toBeInTheDocument();
    expect(screen.getByText('Hoch')).toBeInTheDocument();
    // per-setup table with direction labels
    expect(screen.getByText('+Z')).toBeInTheDocument();
    expect(screen.getByText('+X')).toBeInTheDocument();
    expect(screen.getByText('−Y')).toBeInTheDocument();
    // High confidence → no manual-override note; family block replaces the
    // pending note.
    expect(screen.queryByRole('note')).not.toBeInTheDocument();
    expect(screen.queryByText(/Merkmalserkennung folgt/)).not.toBeInTheDocument();
  });

  it('surfaces the manual-override hint on low confidence (M4.4)', async () => {
    const mill = succeeded();
    mill.run!.family = 'MILLING';
    mill.run!.result = {
      ...mill.run!.result!,
      family: 'MILLING',
      confidence: 'Low',
      family_scalars: {
        setup_count: 1,
        runtime: 0.011253,
        setup_time: 1,
        setups: [
          {
            direction: [0, 0, 1],
            setup_time: 1,
            runtime: 0.011253,
            confidence: 'Low',
            features: [],
            feedback: [],
          },
        ],
      },
      features: [],
    };
    getInterrogation.mockResolvedValue(mill);
    await renderWithProviders(<InterrogationPanel partId="part-1" displayOpts={OPTS} />);
    await waitFor(() => {
      expect(screen.getByText('Fräsanalyse – Ergebnisse')).toBeInTheDocument();
    });
    expect(screen.getByText('Niedrig')).toBeInTheDocument();
    expect(screen.getByRole('note')).toHaveTextContent(/manuell prüfen und überschreiben/);
  });

  it('renders the lathe results block with stock + live-tooling callouts (M4.5)', async () => {
    // The flange fixture's analytic values (goldens.json → lathe): stock
    // ⌀40×15, 1 setup, 1 external / 1 internal cut, 4 off-axis bolt holes.
    const lathe = succeeded();
    lathe.run!.family = 'LATHE';
    lathe.run!.result = {
      ...lathe.run!.result!,
      family: 'LATHE',
      family_scalars: { setup_count: 1, stock_radius: 20, stock_length: 15 },
      features: [
        {
          name: 'lathe_stock',
          properties: { radius: 20, diameter: 40, length: 15 },
          geometry_refs: [],
        },
        { name: 'setup', properties: { direction: [0, 0, 1] }, geometry_refs: [] },
        {
          name: 'external_cut',
          properties: {
            axial_area: 1884.96,
            radial_area: 2199.11,
            area: 4084.07,
            max_radius: 20,
            length: 15,
          },
          geometry_refs: [],
        },
        {
          name: 'internal_cut',
          properties: {
            radius: 5,
            diameter: 10,
            depth: 15,
            thru: true,
            axial_area: 471.24,
            radial_area: 0,
            area: 471.24,
          },
          geometry_refs: [],
        },
        ...[1, 2, 3, 4].map(() => ({
          name: 'off_axis_hole',
          properties: { radius: 2.5, diameter: 5, depth: 15, area: 117.81 },
          geometry_refs: [],
        })),
      ],
    };
    getInterrogation.mockResolvedValue(lathe);
    await renderWithProviders(<InterrogationPanel partId="part-1" displayOpts={OPTS} />);
    await waitFor(() => {
      expect(screen.getByText('Drehanalyse – Ergebnisse')).toBeInTheDocument();
    });
    // recommended stock ⌀ 40 × 15 mm, German decimal comma, mm primary
    expect(screen.getByText('Empfohlenes Rohteil')).toBeInTheDocument();
    expect(screen.getByText(/⌀\s*40,00\s*mm\s*×\s*15,00\s*mm/)).toBeInTheDocument();
    expect(screen.getByText('Anzahl Aufspannungen').nextElementSibling).toHaveTextContent('1');
    expect(screen.getByText('Außenschnitte').nextElementSibling).toHaveTextContent('1');
    expect(screen.getByText('Innenschnitte').nextElementSibling).toHaveTextContent('1');
    // the live-tooling callouts are flagged, with the not-auto-costed note
    expect(screen.getByText('Außermittige Bohrungen').nextElementSibling).toHaveTextContent('4');
    expect(screen.getByRole('note')).toHaveTextContent(/Angetriebene Werkzeuge erforderlich/);
    // the family block replaces the generic pending note
    expect(screen.queryByText(/Merkmalserkennung folgt/)).not.toBeInTheDocument();
  });

  it('omits the live-tooling rows and note on a clean turned part (M4.5)', async () => {
    const lathe = succeeded();
    lathe.run!.family = 'LATHE';
    lathe.run!.result = {
      ...lathe.run!.result!,
      family: 'LATHE',
      family_scalars: { setup_count: 1, stock_radius: 15, stock_length: 80 },
      features: [
        {
          name: 'lathe_stock',
          properties: { radius: 15, diameter: 30, length: 80 },
          geometry_refs: [],
        },
        { name: 'setup', properties: { direction: [0, 0, 1] }, geometry_refs: [] },
        {
          name: 'external_cut',
          properties: {
            axial_area: 5466.37,
            radial_area: 1413.72,
            area: 6880.09,
            max_radius: 15,
            length: 80,
          },
          geometry_refs: [],
        },
      ],
    };
    getInterrogation.mockResolvedValue(lathe);
    await renderWithProviders(<InterrogationPanel partId="part-1" displayOpts={OPTS} />);
    await waitFor(() => {
      expect(screen.getByText('Drehanalyse – Ergebnisse')).toBeInTheDocument();
    });
    expect(screen.getByText(/⌀\s*30,00\s*mm\s*×\s*80,00\s*mm/)).toBeInTheDocument();
    expect(screen.queryByText('Außermittige Bohrungen')).not.toBeInTheDocument();
    expect(screen.queryByText('Asymmetrische Flächen')).not.toBeInTheDocument();
    expect(screen.queryByRole('note')).not.toBeInTheDocument();
  });

  it('says a LATHE body was rejected as not turnable, not "pending" (M4.5)', async () => {
    // The recognizer's designed honest path: a non-turned body yields {} —
    // the panel must not claim recognition is still unshipped.
    const lathe = succeeded();
    lathe.run!.family = 'LATHE';
    lathe.run!.result = {
      ...lathe.run!.result!,
      family: 'LATHE',
      family_scalars: {},
      features: [],
    };
    getInterrogation.mockResolvedValue(lathe);
    await renderWithProviders(<InterrogationPanel partId="part-1" displayOpts={OPTS} />);
    await waitFor(() => {
      expect(screen.getByText(/Kein Drehteil erkannt/)).toBeInTheDocument();
    });
    expect(screen.queryByText(/Merkmalserkennung folgt/)).not.toBeInTheDocument();
    expect(screen.queryByText('Drehanalyse – Ergebnisse')).not.toBeInTheDocument();
  });

  it('renders the tube-laser results block with profile + cut metrics (M4.6)', async () => {
    // The angled-60° fixture's analytic values (goldens.json → tube_laser):
    // rectangular 40×20 t2, machining_required (60° > 45° threshold).
    const tube = succeeded();
    tube.run!.family = 'TUBE_LASER';
    tube.run!.result = {
      ...tube.run!.result!,
      family: 'TUBE_LASER',
      family_scalars: {
        stock_type: 'rectangular',
        width: 40,
        height: 20,
        thickness: 2,
        length: 114.64,
        total_cut_length: 112,
        pierce_count: 0,
        machining_required: true,
        is_outside_corner_round: false,
      },
      features: [
        {
          name: 'angled_cut',
          properties: { angle: 60, cut_length: 129.3, machining_required: true },
          geometry_refs: [],
        },
        { name: 'cut', properties: { angle: 0, cut_length: 112 }, geometry_refs: [] },
      ],
    };
    getInterrogation.mockResolvedValue(tube);
    await renderWithProviders(<InterrogationPanel partId="part-1" displayOpts={OPTS} />);
    await waitFor(() => {
      expect(screen.getByText('Rohrlaser-Analyse – Ergebnisse')).toBeInTheDocument();
    });
    expect(screen.getByText('Rechteckrohr')).toBeInTheDocument();
    expect(screen.getByText(/40,00\s*mm\s*×\s*20,00\s*mm/)).toBeInTheDocument();
    expect(screen.getByText('Schnittlänge gesamt')).toBeInTheDocument();
    expect(screen.getByText('Schrägschnitte')).toBeInTheDocument();
    // machining_required → the flagged-not-costed note
    expect(screen.getByRole('note')).toHaveTextContent(/Zusätzliche Bearbeitung erforderlich/);
  });

  it('renders angle-profile leg angle and radiused-profile corner radii (M4.6)', async () => {
    // The radiused fixture's analytic values: 40×20 t2, outer corner r4 / inner r2.
    const tube = succeeded();
    tube.run!.family = 'TUBE_LASER';
    tube.run!.result = {
      ...tube.run!.result!,
      family: 'TUBE_LASER',
      family_scalars: {
        stock_type: 'rectangular_radiused',
        width: 40,
        height: 20,
        thickness: 2,
        length: 150,
        outside_corner_radius: 4,
        internal_radius: 2,
        is_outside_corner_round: true,
        leg_angle: 90,
        total_cut_length: 213.7,
        pierce_count: 0,
        machining_required: false,
      },
      features: [],
    };
    getInterrogation.mockResolvedValue(tube);
    await renderWithProviders(<InterrogationPanel partId="part-1" displayOpts={OPTS} />);
    await waitFor(() => {
      expect(screen.getByText('Rechteckrohr (gerundete Ecken)')).toBeInTheDocument();
    });
    expect(screen.getByText('Außeneckenradius').parentElement?.textContent).toContain('4,00');
    expect(screen.getByText('Inneneckenradius').parentElement?.textContent).toContain('2,00');
    expect(screen.getByText('Schenkelwinkel').parentElement?.textContent).toContain('90');
    expect(screen.queryByRole('note')).not.toBeInTheDocument();
  });

  it('says a TUBE_LASER body matched no profile, not "pending" (M4.6)', async () => {
    // The recognizer's honest path: incompatible — never a fabricated guess.
    const tube = succeeded();
    tube.run!.family = 'TUBE_LASER';
    tube.run!.result = {
      ...tube.run!.result!,
      family: 'TUBE_LASER',
      family_scalars: { stock_type: 'incompatible' },
      features: [],
    };
    getInterrogation.mockResolvedValue(tube);
    await renderWithProviders(<InterrogationPanel partId="part-1" displayOpts={OPTS} />);
    await waitFor(() => {
      expect(screen.getByText(/Kein Rohrprofil erkannt/)).toBeInTheDocument();
    });
    expect(screen.queryByText(/Merkmalserkennung folgt/)).not.toBeInTheDocument();
    expect(screen.queryByText('Rohrlaser-Analyse – Ergebnisse')).not.toBeInTheDocument();
  });

  it('omits unfolded dims and thumbnail when the recognizer could not unfold', async () => {
    const sheet = succeeded();
    sheet.run!.family = 'SHEET_METAL';
    sheet.run!.result = {
      ...sheet.run!.result!,
      family: 'SHEET_METAL',
      family_scalars: {
        thickness: 1.5,
        bend_count: 4,
        flat_area: 1000,
        total_cut_length: 140,
        pierce_count: 0,
      },
      features: [],
    };
    getInterrogation.mockResolvedValue(sheet);
    await renderWithProviders(<InterrogationPanel partId="part-1" displayOpts={OPTS} />);
    await waitFor(() => {
      expect(screen.getByText('Blechanalyse – Ergebnisse')).toBeInTheDocument();
    });
    expect(screen.getByText('Blechdicke')).toBeInTheDocument();
    expect(screen.queryByText('Abwicklungsmaße')).not.toBeInTheDocument();
    expect(screen.queryByRole('img', { name: /Abwicklung/ })).not.toBeInTheDocument();
  });
  it('renders the Manufacturability Warnings list with expandable instances (M4.7)', async () => {
    const userEvent = (await import('@testing-library/user-event')).default;
    const sheet = succeeded();
    sheet.run!.family = 'SHEET_METAL';
    sheet.run!.result = {
      ...sheet.run!.result!,
      family: 'SHEET_METAL',
      family_scalars: {
        thickness: 2,
        bend_count: 1,
        flat_area: 2062.4,
        total_cut_length: 184,
        pierce_count: 0,
      },
      features: [
        {
          name: 'bend',
          properties: { radius: 1, angle: 90, length: 40, k_factor: 0.25 },
          geometry_refs: [],
        },
      ],
      feedback: [
        {
          type: 'small_bend_radius',
          count: 1,
          threshold_used: { min_bend_radius: 0.75 },
          geometry_refs: [],
          can_disable: true,
          instances: [{ radius: 1, angle: 90, length: 40 }],
        },
      ],
    };
    getInterrogation.mockResolvedValue(sheet);
    await renderWithProviders(<InterrogationPanel partId="part-1" displayOpts={OPTS} />);
    await waitFor(() => {
      expect(screen.getByText('Fertigbarkeitswarnungen')).toBeInTheDocument();
    });
    // family label + localized warning name with count + the ⓘ threshold
    expect(screen.getByText('Blech')).toBeInTheDocument();
    expect(screen.getByText(/Zu kleiner Biegeradius \(1\)/)).toBeInTheDocument();
    expect(screen.getByTitle(/min_bend_radius = 0,75/)).toBeInTheDocument();
    // expanding shows the per-instance row with formatted metric values
    await userEvent.click(screen.getByRole('button', { expanded: false }));
    expect(screen.getByText(/Radius: 1,00\s*mm/)).toBeInTheDocument();
  });

  it('renders no warnings block when nothing fired (M4.7)', async () => {
    const sheet = succeeded();
    sheet.run!.family = 'SHEET_METAL';
    sheet.run!.result = {
      ...sheet.run!.result!,
      family: 'SHEET_METAL',
      family_scalars: {
        thickness: 2,
        bend_count: 1,
        flat_area: 4814.16,
        total_cut_length: 292.57,
        pierce_count: 0,
      },
      features: [],
      feedback: [],
    };
    getInterrogation.mockResolvedValue(sheet);
    await renderWithProviders(<InterrogationPanel partId="part-1" displayOpts={OPTS} />);
    await waitFor(() => {
      expect(screen.getByText('Blechanalyse – Ergebnisse')).toBeInTheDocument();
    });
    expect(screen.queryByText('Fertigbarkeitswarnungen')).not.toBeInTheDocument();
  });
});
