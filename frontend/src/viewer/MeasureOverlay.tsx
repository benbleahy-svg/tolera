/**
 * Per-page measurement overlay (M2.3, spec #pdf-capabilities Measure).
 * Gestures per kind: distance/area-rect/area-circle drag; arc = three
 * clicks; perimeter/area-custom collect clicks, double-click finishes;
 * count accumulates numbered markers, double-click finishes. Captured
 * points snap to existing measurement vertices/edges when snapping is on.
 * Values are computed at finish (measure.ts) and rendered as labels.
 */

import { useRef, useState } from 'react';

import type { Point } from './annotations';
import {
  arcThroughPoints,
  circleAreaMm2,
  distanceMm,
  formatMeasurement,
  pathLengthMm,
  polygonAreaMm2,
  rectAreaMm2,
  snapPoint,
  type Measurement,
  type MeasurementKind,
  type Scale,
} from './measure';

export type MeasureTool = MeasurementKind | 'calibrate' | 'erase';

interface Props {
  ariaLabel: string;
  page: number;
  zoom: number;
  scale: Scale | null;
  measurements: Measurement[];
  tool: MeasureTool | null;
  snapping: boolean;
  precision: number;
  onAdd: (measurement: Measurement) => void;
  onErase: (id: string) => void;
  onCalibrated: (measuredPts: number) => void;
}

let counter = 0;
const nextId = () => `mes-${Date.now().toString(36)}-${(counter += 1)}`;

function midpoint(points: readonly Point[]): Point {
  const sum = points.reduce((acc, p) => ({ x: acc.x + p.x, y: acc.y + p.y }), { x: 0, y: 0 });
  return { x: sum.x / points.length, y: sum.y / points.length };
}

function MeasurementShape({
  measurement,
  precision,
}: {
  measurement: Measurement;
  precision: number;
}) {
  const { kind, points } = measurement;
  const label = formatMeasurement(measurement, precision);
  const anchor = midpoint(points);
  const stroke = '#0e7490';
  const path = points.map((p, i) => `${i === 0 ? 'M' : 'L'} ${p.x} ${p.y}`).join(' ');
  return (
    <g className="pdf-measurement" data-kind={kind}>
      {kind === 'count' ? (
        points.map((p, i) => (
          <g key={i}>
            <circle cx={p.x} cy={p.y} r={7} fill={stroke} opacity={0.85} />
            <text x={p.x} y={p.y + 3} textAnchor="middle" fill="#fff" fontSize={9}>
              {i + 1}
            </text>
          </g>
        ))
      ) : kind === 'area_circle' && points.length === 2 ? (
        <circle
          cx={points[0].x}
          cy={points[0].y}
          r={Math.hypot(points[1].x - points[0].x, points[1].y - points[0].y)}
          stroke={stroke}
          strokeWidth={1.5}
          fill={stroke}
          fillOpacity={0.08}
        />
      ) : kind === 'area_rectangle' && points.length === 2 ? (
        <rect
          x={Math.min(points[0].x, points[1].x)}
          y={Math.min(points[0].y, points[1].y)}
          width={Math.abs(points[1].x - points[0].x)}
          height={Math.abs(points[1].y - points[0].y)}
          stroke={stroke}
          strokeWidth={1.5}
          fill={stroke}
          fillOpacity={0.08}
        />
      ) : kind === 'area_custom' ? (
        <polygon
          points={points.map((p) => `${p.x},${p.y}`).join(' ')}
          stroke={stroke}
          strokeWidth={1.5}
          fill={stroke}
          fillOpacity={0.08}
        />
      ) : (
        <path d={path} stroke={stroke} strokeWidth={1.5} fill="none" />
      )}
      <text x={anchor.x} y={anchor.y - 6} fill={stroke} fontSize={11} className="pdf-measure-label">
        {label}
      </text>
    </g>
  );
}

export function MeasureOverlay({
  ariaLabel,
  page,
  zoom,
  scale,
  measurements,
  tool,
  snapping,
  precision,
  onAdd,
  onErase,
  onCalibrated,
}: Props) {
  const svgRef = useRef<SVGSVGElement>(null);
  const [dragStart, setDragStart] = useState<Point | null>(null);
  const [clicks, setClicks] = useState<Point[]>([]);

  const pageMeasurements = measurements.filter((m) => m.page === page);
  const vertices = pageMeasurements.flatMap((m) => m.points);
  const segments = pageMeasurements.flatMap((m) => {
    const pairs: [Point, Point][] = [];
    for (let i = 1; i < m.points.length; i += 1) pairs.push([m.points[i - 1], m.points[i]]);
    return pairs;
  });

  const toPoint = (e: React.PointerEvent): Point => {
    const bounds = svgRef.current?.getBoundingClientRect();
    const raw = bounds
      ? { x: (e.clientX - bounds.left) / zoom, y: (e.clientY - bounds.top) / zoom }
      : { x: 0, y: 0 };
    return snapping && tool !== 'calibrate' ? snapPoint(raw, vertices, segments) : raw;
  };

  const finish = (kind: MeasurementKind, points: Point[]) => {
    if (!scale) return;
    const base: Measurement = { id: nextId(), page, kind, points };
    switch (kind) {
      case 'distance':
        base.valueMm = distanceMm(points[0], points[1], scale);
        break;
      case 'perimeter':
        base.valueMm = pathLengthMm(points, scale);
        break;
      case 'arc': {
        const arc = arcThroughPoints(points[0], points[1], points[2], scale);
        if (!arc) return;
        base.arc = {
          radiusMm: arc.radiusMm,
          lengthMm: arc.lengthMm,
          centerAngleDeg: arc.centerAngleDeg,
        };
        break;
      }
      case 'area_custom':
        base.valueMm2 = polygonAreaMm2(points, scale);
        break;
      case 'area_circle':
        base.valueMm2 = circleAreaMm2(points[0], points[1], scale);
        break;
      case 'area_rectangle':
        base.valueMm2 = rectAreaMm2(points[0], points[1], scale);
        break;
      case 'count':
        base.count = points.length;
        break;
    }
    onAdd(base);
  };

  const onPointerDown = (e: React.PointerEvent) => {
    if (!tool) return;
    e.stopPropagation();
    const point = toPoint(e);
    if (tool === 'erase') {
      const target = [...pageMeasurements]
        .reverse()
        .find((m) =>
          m.points.some((p) => Math.hypot(p.x - point.x, p.y - point.y) < 10 / zoom + 8),
        );
      if (target) onErase(target.id);
      return;
    }
    if (tool === 'calibrate' || tool === 'distance' || tool === 'area_circle' || tool === 'area_rectangle') {
      setDragStart(point);
      return;
    }
    // arc / perimeter / area_custom / count collect clicks
    const next = [...clicks, point];
    if (tool === 'arc' && next.length === 3) {
      finish('arc', next);
      setClicks([]);
    } else {
      setClicks(next);
    }
  };

  const onPointerUp = (e: React.PointerEvent) => {
    if (!dragStart || !tool) return;
    const end = toPoint(e);
    const start = dragStart;
    setDragStart(null);
    if (Math.hypot(end.x - start.x, end.y - start.y) < 2) return;
    if (tool === 'calibrate') {
      onCalibrated(Math.hypot(end.x - start.x, end.y - start.y));
      return;
    }
    if (tool === 'distance' || tool === 'area_circle' || tool === 'area_rectangle') {
      finish(tool, [start, end]);
    }
  };

  const onDoubleClick = () => {
    if (!tool) return;
    // a double-click fires two pointer-downs at the same spot — collapse the
    // duplicate so the finish location counts exactly once
    const deduped = clicks.filter(
      (p, i) => i === 0 || Math.hypot(p.x - clicks[i - 1].x, p.y - clicks[i - 1].y) > 1,
    );
    if ((tool === 'perimeter' || tool === 'area_custom') && deduped.length >= 2) {
      finish(tool, deduped);
      setClicks([]);
    } else if (tool === 'count' && deduped.length >= 1) {
      finish('count', deduped);
      setClicks([]);
    }
  };

  return (
    <svg
      ref={svgRef}
      className="pdf-annotation-overlay"
      data-active={tool ? '' : undefined}
      role="application"
      aria-label={ariaLabel}
      onPointerDown={onPointerDown}
      onPointerUp={onPointerUp}
      onDoubleClick={onDoubleClick}
    >
      <g transform={`scale(${zoom})`}>
        {pageMeasurements.map((measurement) => (
          <MeasurementShape key={measurement.id} measurement={measurement} precision={precision} />
        ))}
        {clicks.length > 0 && (
          <polyline
            points={clicks.map((p) => `${p.x},${p.y}`).join(' ')}
            stroke="#0e7490"
            strokeWidth={1.5}
            fill="none"
            strokeDasharray="4 3"
          />
        )}
      </g>
    </svg>
  );
}
