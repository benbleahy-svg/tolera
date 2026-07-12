/**
 * Per-page SVG markup overlay (M2.2). Renders the layer's annotations for
 * one page and turns pointer gestures into annotation objects according to
 * the active tool's kind (drag-rect / drag-line / freehand / click-point /
 * click-points). Stores scale-1 coordinates; the <g> scales by zoom.
 */

import { useRef, useState } from 'react';

import {
  TOOL_KIND,
  buildAnnotation,
  hitTest,
  type Annotation,
  type AnnotationStyle,
  type AnnotationType,
  type Point,
} from './annotations';

interface Props {
  page: number;
  zoom: number;
  annotations: Annotation[];
  tool: AnnotationType | 'eraser' | null;
  style: AnnotationStyle;
  onAdd: (annotation: Annotation) => void;
  onErase: (id: string) => void;
  promptText: (kind: 'free_text' | 'note') => string | null;
}

let counter = 0;
const nextId = () => `ann-${Date.now().toString(36)}-${(counter += 1)}`;

function Squiggle({ x, width, y, style }: { x: number; width: number; y: number; style: AnnotationStyle }) {
  const step = 6;
  let d = `M ${x} ${y}`;
  for (let dx = 0; dx < width; dx += step) {
    const mid = x + dx + step / 2;
    const end = Math.min(x + dx + step, x + width);
    const wave = (dx / step) % 2 === 0 ? y + 3 : y - 3;
    d += ` Q ${mid} ${wave} ${end} ${y}`;
  }
  return <path d={d} stroke={style.stroke} strokeWidth={style.strokeWidth} fill="none" />;
}

function AnnotationShape({ annotation }: { annotation: Annotation }) {
  const { type, rect, points, at, text, style } = annotation;
  const common = {
    stroke: style.stroke,
    strokeWidth: style.strokeWidth,
    fill: style.fill === 'none' ? 'none' : style.fill,
    opacity: style.opacity,
  };
  if (rect) {
    const bottom = rect.y + rect.height;
    const middle = rect.y + rect.height / 2;
    switch (type) {
      case 'highlight':
        return <rect {...rect} fill={style.fill === 'none' ? '#facc15' : style.fill} opacity={0.4} />;
      case 'underline':
        return <line x1={rect.x} y1={bottom} x2={rect.x + rect.width} y2={bottom} {...common} />;
      case 'strikeout':
        return <line x1={rect.x} y1={middle} x2={rect.x + rect.width} y2={middle} {...common} />;
      case 'squiggly':
        return <Squiggle x={rect.x} width={rect.width} y={bottom} style={style} />;
      case 'ellipse':
        return (
          <ellipse
            cx={rect.x + rect.width / 2}
            cy={rect.y + rect.height / 2}
            rx={rect.width / 2}
            ry={rect.height / 2}
            {...common}
          />
        );
      default:
        return <rect {...rect} {...common} />;
    }
  }
  if (points && points.length >= 2) {
    const path = points.map((p, i) => `${i === 0 ? 'M' : 'L'} ${p.x} ${p.y}`).join(' ');
    switch (type) {
      case 'freehand_highlight':
        return <path d={path} stroke="#facc15" strokeWidth={12} opacity={0.4} fill="none" strokeLinecap="round" />;
      case 'arrow': {
        const [from, to] = [points[0], points.at(-1) as Point];
        const angle = Math.atan2(to.y - from.y, to.x - from.x);
        const head = (offset: number) =>
          `${to.x - 10 * Math.cos(angle + offset)},${to.y - 10 * Math.sin(angle + offset)}`;
        return (
          <g {...common} fill="none">
            <line x1={from.x} y1={from.y} x2={to.x} y2={to.y} />
            <polyline points={`${head(0.5)} ${to.x},${to.y} ${head(-0.5)}`} />
          </g>
        );
      }
      case 'arc': {
        const [from, to] = [points[0], points.at(-1) as Point];
        const cx = (from.x + to.x) / 2 + (to.y - from.y) / 3;
        const cy = (from.y + to.y) / 2 - (to.x - from.x) / 3;
        return <path d={`M ${from.x} ${from.y} Q ${cx} ${cy} ${to.x} ${to.y}`} {...common} fill="none" />;
      }
      case 'polygon':
        return <polygon points={points.map((p) => `${p.x},${p.y}`).join(' ')} {...common} />;
      default:
        return <path d={path} {...common} fill="none" strokeLinecap="round" />;
    }
  }
  if (at) {
    if (type === 'note') {
      return (
        <g opacity={style.opacity}>
          <rect x={at.x - 8} y={at.y - 8} width={16} height={16} fill="#fde68a" stroke={style.stroke} />
          <title>{text}</title>
        </g>
      );
    }
    return (
      <text x={at.x} y={at.y} fill={style.stroke} fontSize={style.fontSize ?? 12} opacity={style.opacity}>
        {text}
      </text>
    );
  }
  return null;
}

export function AnnotationOverlay({
  page,
  zoom,
  annotations,
  tool,
  style,
  onAdd,
  onErase,
  promptText,
}: Props) {
  const svgRef = useRef<SVGSVGElement>(null);
  const [dragStart, setDragStart] = useState<Point | null>(null);
  const [freehand, setFreehand] = useState<Point[] | null>(null);
  const [clickPoints, setClickPoints] = useState<Point[]>([]);

  const toPoint = (e: React.PointerEvent): Point => {
    const bounds = svgRef.current?.getBoundingClientRect();
    if (!bounds) return { x: 0, y: 0 };
    return { x: (e.clientX - bounds.left) / zoom, y: (e.clientY - bounds.top) / zoom };
  };

  const finishDrag = (start: Point, end: Point) => {
    if (!tool || tool === 'eraser') return;
    const kind = TOOL_KIND[tool];
    if (kind === 'drag-rect') {
      const rect = {
        x: Math.min(start.x, end.x),
        y: Math.min(start.y, end.y),
        width: Math.abs(end.x - start.x),
        height: Math.abs(end.y - start.y),
      };
      if (rect.width < 2 && rect.height < 2) return;
      onAdd(buildAnnotation(nextId(), page, tool, style, { rect }));
    } else if (kind === 'drag-line') {
      onAdd(buildAnnotation(nextId(), page, tool, style, { points: [start, end] }));
    }
  };

  const onPointerDown = (e: React.PointerEvent) => {
    if (!tool) return;
    e.stopPropagation();
    const point = toPoint(e);
    if (tool === 'eraser') {
      const target = [...annotations].reverse().find((a) => a.page === page && hitTest(a, point));
      if (target) onErase(target.id);
      return;
    }
    const kind = TOOL_KIND[tool];
    if (kind === 'click-point') {
      const text = promptText(tool === 'note' ? 'note' : 'free_text');
      if (text) onAdd(buildAnnotation(nextId(), page, tool, style, { at: point, text }));
      return;
    }
    if (kind === 'click-points') {
      setClickPoints((points) => [...points, point]);
      return;
    }
    if (kind === 'freehand') {
      setFreehand([point]);
      return;
    }
    setDragStart(point);
  };

  const onPointerMove = (e: React.PointerEvent) => {
    if (freehand) setFreehand((points) => [...(points ?? []), toPoint(e)]);
  };

  const onPointerUp = (e: React.PointerEvent) => {
    if (freehand && tool && tool !== 'eraser') {
      if (freehand.length > 2) {
        onAdd(buildAnnotation(nextId(), page, tool, style, { points: freehand }));
      }
      setFreehand(null);
      return;
    }
    if (dragStart) {
      finishDrag(dragStart, toPoint(e));
      setDragStart(null);
    }
  };

  const onDoubleClick = () => {
    if (!tool || tool === 'eraser') return;
    if (TOOL_KIND[tool] === 'click-points' && clickPoints.length >= 2) {
      onAdd(buildAnnotation(nextId(), page, tool, style, { points: clickPoints }));
      setClickPoints([]);
    }
  };

  return (
    <svg
      ref={svgRef}
      className="pdf-annotation-overlay"
      data-active={tool ? '' : undefined}
      role="application"
      aria-label={`Anmerkungen Seite ${page}`}
      onPointerDown={onPointerDown}
      onPointerMove={onPointerMove}
      onPointerUp={onPointerUp}
      onDoubleClick={onDoubleClick}
    >
      <g transform={`scale(${zoom})`}>
        {annotations
          .filter((annotation) => annotation.page === page)
          .map((annotation) => (
            <AnnotationShape key={annotation.id} annotation={annotation} />
          ))}
        {clickPoints.length > 0 && (
          <polyline
            points={clickPoints.map((p) => `${p.x},${p.y}`).join(' ')}
            stroke={style.stroke}
            strokeWidth={style.strokeWidth}
            fill="none"
            strokeDasharray="4 3"
          />
        )}
      </g>
    </svg>
  );
}
