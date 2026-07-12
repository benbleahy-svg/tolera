/**
 * Measure + scale calibration math (M2.3, spec #pdf-capabilities Measure;
 * VIEWER-AND-FILE-TYPES §4: "Set scale first — pick a ratio or calibrate
 * from one known dimension"). All pure: page-space pdf points in, real
 * metric values out (mm/mm² — CLAUDE.md §5 metric-native), so the AC's
 * "after calibrating, a second known distance computes within tolerance"
 * is unit-testable without a canvas.
 */

import type { Point } from './annotations';

/** 1 pdf point = 1/72 inch — the physical size of the printed page. */
export const MM_PER_PT = 25.4 / 72;

export interface Scale {
  /** Real-world millimetres represented by one pdf point. */
  mmPerPt: number;
  /** How the scale was set (display only). */
  source: 'ratio' | 'calibrated';
  label: string;
}

/**
 * A drawing ratio `drawn:real` (e.g. 1:2 — the part is twice the drawn
 * size). At 1:1 a pdf point is exactly its printed physical size.
 */
export function scaleFromRatio(drawn: number, real: number): Scale {
  return {
    mmPerPt: (MM_PER_PT * real) / drawn,
    source: 'ratio',
    label: `${drawn}:${real}`,
  };
}

/** Calibrate: the user clicked both ends of a known dimension. */
export function scaleFromCalibration(measuredPts: number, knownMm: number): Scale | null {
  if (measuredPts <= 0 || knownMm <= 0 || !Number.isFinite(knownMm)) return null;
  return {
    mmPerPt: knownMm / measuredPts,
    source: 'calibrated',
    label: `${knownMm} mm`,
  };
}

const dist = (a: Point, b: Point) => Math.hypot(b.x - a.x, b.y - a.y);

export function distanceMm(a: Point, b: Point, scale: Scale): number {
  return dist(a, b) * scale.mmPerPt;
}

export function pathLengthMm(points: readonly Point[], scale: Scale, closed = false): number {
  let total = 0;
  for (let i = 1; i < points.length; i += 1) total += dist(points[i - 1], points[i]);
  if (closed && points.length > 2) total += dist(points.at(-1) as Point, points[0]);
  return total * scale.mmPerPt;
}

/** Shoelace area of a polygon (pdf pt² → mm²). */
export function polygonAreaMm2(points: readonly Point[], scale: Scale): number {
  if (points.length < 3) return 0;
  let doubled = 0;
  for (let i = 0; i < points.length; i += 1) {
    const a = points[i];
    const b = points[(i + 1) % points.length];
    doubled += a.x * b.y - b.x * a.y;
  }
  return Math.abs(doubled / 2) * scale.mmPerPt ** 2;
}

export function circleAreaMm2(center: Point, edge: Point, scale: Scale): number {
  const radius = dist(center, edge) * scale.mmPerPt;
  return Math.PI * radius ** 2;
}

export function rectAreaMm2(a: Point, b: Point, scale: Scale): number {
  return Math.abs(b.x - a.x) * Math.abs(b.y - a.y) * scale.mmPerPt ** 2;
}

export interface ArcMetrics {
  radiusMm: number;
  lengthMm: number;
  centerAngleDeg: number;
  center: Point;
}

/**
 * The circle through three points (start / on-arc / end) — the spec's arc
 * measure: length, radius, center angle. Returns null for collinear input.
 */
export function arcThroughPoints(a: Point, b: Point, c: Point, scale: Scale): ArcMetrics | null {
  const d = 2 * (a.x * (b.y - c.y) + b.x * (c.y - a.y) + c.x * (a.y - b.y));
  if (Math.abs(d) < 1e-9) return null;
  const aa = a.x ** 2 + a.y ** 2;
  const bb = b.x ** 2 + b.y ** 2;
  const cc = c.x ** 2 + c.y ** 2;
  const center = {
    x: (aa * (b.y - c.y) + bb * (c.y - a.y) + cc * (a.y - b.y)) / d,
    y: (aa * (c.x - b.x) + bb * (a.x - c.x) + cc * (b.x - a.x)) / d,
  };
  const radiusPts = dist(center, a);
  const angleOf = (p: Point) => Math.atan2(p.y - center.y, p.x - center.x);
  const start = angleOf(a);
  const mid = angleOf(b);
  const end = angleOf(c);
  const norm = (angle: number) => (angle + Math.PI * 2) % (Math.PI * 2);
  // sweep from start to end passing through mid
  let sweep = norm(end - start);
  if (norm(mid - start) > sweep) sweep = sweep - Math.PI * 2;
  const centerAngle = Math.abs(sweep);
  return {
    radiusMm: radiusPts * scale.mmPerPt,
    lengthMm: radiusPts * centerAngle * scale.mmPerPt,
    centerAngleDeg: (centerAngle * 180) / Math.PI,
    center,
  };
}

/** Snap to the nearest candidate vertex, else project onto candidate edges. */
export function snapPoint(
  point: Point,
  vertices: readonly Point[],
  segments: readonly [Point, Point][],
  tolerance = 8,
): Point {
  let best: Point | null = null;
  let bestDist = tolerance;
  for (const vertex of vertices) {
    const d = dist(point, vertex);
    if (d <= bestDist) {
      best = vertex;
      bestDist = d;
    }
  }
  if (best) return best;
  for (const [a, b] of segments) {
    const abx = b.x - a.x;
    const aby = b.y - a.y;
    const lengthSq = abx ** 2 + aby ** 2;
    if (lengthSq === 0) continue;
    const u = Math.max(0, Math.min(1, ((point.x - a.x) * abx + (point.y - a.y) * aby) / lengthSq));
    const projected = { x: a.x + u * abx, y: a.y + u * aby };
    const d = dist(point, projected);
    if (d <= bestDist) {
      best = projected;
      bestDist = d;
    }
  }
  return best ?? point;
}

export type MeasurementKind =
  | 'distance'
  | 'arc'
  | 'perimeter'
  | 'area_custom'
  | 'area_circle'
  | 'area_rectangle'
  | 'count';

export interface Measurement {
  id: string;
  page: number;
  kind: MeasurementKind;
  points: Point[];
  /** Formatted per kind at creation time (label rendering). */
  valueMm?: number;
  valueMm2?: number;
  arc?: Omit<ArcMetrics, 'center'>;
  count?: number;
}

/** Format a value with the precision preset (metric-native, de locale). */
export function formatMeasurement(measurement: Measurement, precision: number): string {
  const fmt = (value: number, unit: string) =>
    `${value.toLocaleString('de-DE', {
      minimumFractionDigits: precision,
      maximumFractionDigits: precision,
    })} ${unit}`;
  switch (measurement.kind) {
    case 'distance':
      return fmt(measurement.valueMm ?? 0, 'mm');
    case 'perimeter':
      return fmt(measurement.valueMm ?? 0, 'mm');
    case 'arc':
      return `${fmt(measurement.arc?.lengthMm ?? 0, 'mm')} · R ${fmt(
        measurement.arc?.radiusMm ?? 0,
        'mm',
      )} · ${(measurement.arc?.centerAngleDeg ?? 0).toLocaleString('de-DE', {
        maximumFractionDigits: 1,
      })}°`;
    case 'count':
      return String(measurement.count ?? measurement.points.length);
    default:
      return fmt(measurement.valueMm2 ?? 0, 'mm²');
  }
}
