/**
 * M2.3 measure + scale calibration — the AC list: no scale → warn/block;
 * calibrate from a known dimension, then a second known distance computes
 * within tolerance; arc/area/count plausible; snapping locks to
 * vertices/edges. Math tested pure; the block/warn flow through the page.
 */

import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { renderWithProviders } from '../test/render';
import { partPanelStubs } from '../test/lensStubs';
import {
  MM_PER_PT,
  arcThroughPoints,
  circleAreaMm2,
  distanceMm,
  formatMeasurement,
  pathLengthMm,
  polygonAreaMm2,
  rectAreaMm2,
  scaleFromCalibration,
  scaleFromRatio,
  snapPoint,
} from './measure';
import { MeasureOverlay } from './MeasureOverlay';

describe('scale + distance (the calibration AC)', () => {
  it('calibrating from a known dimension makes a second distance read true', () => {
    // the fixture drawing's 80 mm edge spans 100 pts on the page
    const scale = scaleFromCalibration(100, 80);
    expect(scale).not.toBeNull();
    // a second, 50 pt feature must read 40 mm within tolerance
    const second = distanceMm({ x: 0, y: 0 }, { x: 50, y: 0 }, scale!);
    expect(second).toBeCloseTo(40, 6);
  });

  it('ratio scales derive from the printed physical size', () => {
    const oneToOne = scaleFromRatio(1, 1);
    expect(distanceMm({ x: 0, y: 0 }, { x: 72, y: 0 }, oneToOne)).toBeCloseTo(25.4, 6);
    const oneToTwo = scaleFromRatio(1, 2);
    expect(oneToTwo.mmPerPt).toBeCloseTo(MM_PER_PT * 2, 9);
  });

  it('rejects nonsense calibrations', () => {
    expect(scaleFromCalibration(0, 80)).toBeNull();
    expect(scaleFromCalibration(100, 0)).toBeNull();
    expect(scaleFromCalibration(100, Number.NaN)).toBeNull();
  });
});

describe('measure math', () => {
  const unit = scaleFromCalibration(1, 1)!; // 1 pt = 1 mm — readable numbers

  it('perimeter sums the path (closed adds the last edge)', () => {
    const square = [
      { x: 0, y: 0 },
      { x: 10, y: 0 },
      { x: 10, y: 10 },
      { x: 0, y: 10 },
    ];
    expect(pathLengthMm(square, unit)).toBeCloseTo(30, 6);
    expect(pathLengthMm(square, unit, true)).toBeCloseTo(40, 6);
  });

  it('areas: shoelace polygon, circle, rectangle', () => {
    const triangle = [
      { x: 0, y: 0 },
      { x: 10, y: 0 },
      { x: 0, y: 10 },
    ];
    expect(polygonAreaMm2(triangle, unit)).toBeCloseTo(50, 6);
    expect(circleAreaMm2({ x: 0, y: 0 }, { x: 10, y: 0 }, unit)).toBeCloseTo(Math.PI * 100, 4);
    expect(rectAreaMm2({ x: 0, y: 0 }, { x: 4, y: 5 }, unit)).toBeCloseTo(20, 6);
  });

  it('arc through three points: a known semicircle', () => {
    // half circle of radius 10 through (−10,0) → (0,10) → (10,0)
    const arc = arcThroughPoints({ x: -10, y: 0 }, { x: 0, y: 10 }, { x: 10, y: 0 }, unit)!;
    expect(arc.radiusMm).toBeCloseTo(10, 6);
    expect(arc.centerAngleDeg).toBeCloseTo(180, 4);
    expect(arc.lengthMm).toBeCloseTo(Math.PI * 10, 4);
  });

  it('collinear points yield no arc', () => {
    expect(
      arcThroughPoints({ x: 0, y: 0 }, { x: 5, y: 0 }, { x: 10, y: 0 }, unit),
    ).toBeNull();
  });
});

describe('snapping', () => {
  const vertices = [{ x: 100, y: 100 }];
  const segments: [{ x: number; y: number }, { x: number; y: number }][] = [
    [
      { x: 0, y: 0 },
      { x: 0, y: 50 },
    ],
  ];

  it('locks to a nearby vertex first', () => {
    expect(snapPoint({ x: 104, y: 97 }, vertices, segments)).toEqual({ x: 100, y: 100 });
  });

  it('projects onto a nearby edge when no vertex is close', () => {
    expect(snapPoint({ x: 5, y: 25 }, vertices, segments)).toEqual({ x: 0, y: 25 });
  });

  it('leaves far points alone', () => {
    expect(snapPoint({ x: 300, y: 300 }, vertices, segments)).toEqual({ x: 300, y: 300 });
  });
});

describe('formatMeasurement', () => {
  it('formats metric values with the precision preset (de locale)', () => {
    expect(
      formatMeasurement(
        { id: 'm', page: 1, kind: 'distance', points: [], valueMm: 1234.567 },
        1,
      ),
    ).toBe('1.234,6 mm');
    expect(
      formatMeasurement({ id: 'm', page: 1, kind: 'count', points: [{ x: 0, y: 0 }], count: 3 }, 1),
    ).toBe('3');
  });
});

describe('MeasureOverlay', () => {
  const scale = scaleFromCalibration(1, 1)!;

  it('creates a distance measurement from a drag', () => {
    const onAdd = vi.fn();
    render(
      <MeasureOverlay
        ariaLabel="Messungen Seite 1"
        page={1}
        zoom={1}
        scale={scale}
        measurements={[]}
        tool="distance"
        snapping={false}
        precision={1}
        onAdd={onAdd}
        onErase={() => {}}
        onCalibrated={() => {}}
      />,
    );
    const svg = screen.getByRole('application');
    fireEvent.pointerDown(svg, { clientX: 0, clientY: 0 });
    fireEvent.pointerUp(svg, { clientX: 30, clientY: 40 });
    expect(onAdd).toHaveBeenCalledTimes(1);
    expect(onAdd.mock.calls[0][0].valueMm).toBeCloseTo(50, 6);
  });

  it('reports the dragged length for calibration', () => {
    const onCalibrated = vi.fn();
    render(
      <MeasureOverlay
        ariaLabel="Messungen Seite 1"
        page={1}
        zoom={1}
        scale={null}
        measurements={[]}
        tool="calibrate"
        snapping
        precision={1}
        onAdd={() => {}}
        onErase={() => {}}
        onCalibrated={onCalibrated}
      />,
    );
    const svg = screen.getByRole('application');
    fireEvent.pointerDown(svg, { clientX: 0, clientY: 0 });
    fireEvent.pointerUp(svg, { clientX: 100, clientY: 0 });
    expect(onCalibrated).toHaveBeenCalledWith(100);
  });
});

// --- the page: no-scale warn/block --------------------------------------------
const loadedDoc = {
  pageCount: 1,
  getPageSize: vi.fn(() => Promise.resolve({ width: 595, height: 842 })),
  getPageText: vi.fn(() => Promise.resolve('Zeichnung')),
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
}));

const stableApi = {
  fetchFileBytes: vi.fn(() => Promise.resolve(new Uint8Array([37, 80, 68, 70]))),
  listFiles: vi.fn(() => Promise.resolve([])),
  getAnnotations: vi.fn(() => Promise.resolve({ objects: [] })),
  putAnnotations: vi.fn(),
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

import { PdfViewerPage } from './PdfViewerPage';

describe('PdfViewerPage measure gating', () => {
  it('blocks measuring until a scale is set (AC: warns/blocks)', async () => {
    await renderWithProviders(<PdfViewerPage />, { route: '/parts/p1/files/f1/view' });
    await waitFor(() =>
      expect(screen.getByRole('button', { name: 'Distanz' })).toBeInTheDocument(),
    );
    await userEvent.click(screen.getByRole('button', { name: 'Distanz' }));
    expect(screen.getByRole('alert')).toHaveTextContent('Zuerst Maßstab setzen');
    expect(screen.getByRole('button', { name: 'Distanz' })).toHaveAttribute(
      'aria-pressed',
      'false',
    );
    // picking a ratio clears the warning and arms the tool
    await userEvent.selectOptions(screen.getByLabelText('Maßstab'), '1:2');
    await userEvent.click(screen.getByRole('button', { name: 'Distanz' }));
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Distanz' })).toHaveAttribute(
      'aria-pressed',
      'true',
    );
  });
});
