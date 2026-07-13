/**
 * Per-page redaction + whiteout overlay (M2.4, spec #pdf-capabilities
 * Redact). Region/whiteout drags capture a rect; the page tool marks the
 * whole page; spotlight/erase pick the shape under the click. Drawn
 * redactions display as red-stroked boxes (the KB's "red box") — the chosen
 * fill only applies in the saved copy. Whiteout sections are view-state:
 * opaque white while whiteout is on (spotlighted one lifted), outlines
 * otherwise. Same active-only hit-testing contract as the sibling overlays
 * (`.pdf-annotation-overlay:not([data-active]) { pointer-events: none }`).
 */

import { useRef } from 'react';

import type { Point, Rect } from './annotations';
import type { Redaction, WhiteoutSection } from './redact';

export type RedactTool = 'region' | 'page' | 'whiteout' | 'spotlight' | 'erase';

interface Props {
  ariaLabel: string;
  page: number;
  zoom: number;
  redactions: Redaction[];
  whiteouts: WhiteoutSection[];
  tool: RedactTool | null;
  fill: { fill: string; stroke: string };
  whiteoutActive: boolean;
  spotlightId: string | null;
  onAddRedaction: (redaction: Redaction) => void;
  onAddWhiteout: (section: WhiteoutSection) => void;
  onEraseRedaction: (id: string) => void;
  onEraseWhiteout: (id: string) => void;
  onSpotlight: (id: string) => void;
}

let counter = 0;
const nextId = (prefix: string) => `${prefix}-${Date.now().toString(36)}-${(counter += 1)}`;

const within = (point: Point, rect: Rect, slack = 0) =>
  point.x >= rect.x - slack &&
  point.x <= rect.x + rect.width + slack &&
  point.y >= rect.y - slack &&
  point.y <= rect.y + rect.height + slack;

export function RedactOverlay({
  ariaLabel,
  page,
  zoom,
  redactions,
  whiteouts,
  tool,
  fill,
  whiteoutActive,
  spotlightId,
  onAddRedaction,
  onAddWhiteout,
  onEraseRedaction,
  onEraseWhiteout,
  onSpotlight,
}: Props) {
  const svgRef = useRef<SVGSVGElement>(null);
  const dragStart = useRef<Point | null>(null);

  const pageRedactions = redactions.filter((r) => r.page === page);
  const pageWhiteouts = whiteouts.filter((w) => w.page === page);

  const toPoint = (e: React.PointerEvent): Point => {
    const bounds = svgRef.current?.getBoundingClientRect();
    return bounds
      ? { x: (e.clientX - bounds.left) / zoom, y: (e.clientY - bounds.top) / zoom }
      : { x: 0, y: 0 };
  };

  const onPointerDown = (e: React.PointerEvent) => {
    if (!tool) return;
    e.stopPropagation();
    const point = toPoint(e);
    if (tool === 'page') {
      onAddRedaction({ id: nextId('red'), page, ...fill });
      return;
    }
    if (tool === 'spotlight') {
      const hit = [...pageWhiteouts].reverse().find((w) => within(point, w.rect));
      if (hit) onSpotlight(hit.id);
      return;
    }
    if (tool === 'erase') {
      const region = [...pageRedactions]
        .reverse()
        .find((r) => r.rect && within(point, r.rect, 4 / zoom));
      const wholePage = pageRedactions.find((r) => !r.rect);
      const whiteout = [...pageWhiteouts]
        .reverse()
        .find((w) => within(point, w.rect, 4 / zoom));
      if (region) onEraseRedaction(region.id);
      else if (whiteout) onEraseWhiteout(whiteout.id);
      else if (wholePage) onEraseRedaction(wholePage.id);
      return;
    }
    dragStart.current = point; // region / whiteout drags
  };

  const onPointerUp = (e: React.PointerEvent) => {
    const start = dragStart.current;
    if (!start || !tool) return;
    dragStart.current = null;
    const end = toPoint(e);
    const rect: Rect = {
      x: Math.min(start.x, end.x),
      y: Math.min(start.y, end.y),
      width: Math.abs(end.x - start.x),
      height: Math.abs(end.y - start.y),
    };
    if (rect.width < 2 || rect.height < 2) return;
    if (tool === 'region') onAddRedaction({ id: nextId('red'), page, rect, ...fill });
    else if (tool === 'whiteout') onAddWhiteout({ id: nextId('wht'), page, rect });
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
    >
      {pageRedactions
        .filter((r) => !r.rect)
        .map((redaction) => (
          <rect
            key={redaction.id}
            className="pdf-redaction"
            data-kind="page"
            x={0}
            y={0}
            width="100%"
            height="100%"
            fill={redaction.fill}
            fillOpacity={0.3}
            stroke="#dc2626"
            strokeWidth={2}
          />
        ))}
      <g transform={`scale(${zoom})`}>
        {pageRedactions
          .filter((r) => r.rect)
          .map((redaction) => (
            <rect
              key={redaction.id}
              className="pdf-redaction"
              data-kind="region"
              x={redaction.rect!.x}
              y={redaction.rect!.y}
              width={redaction.rect!.width}
              height={redaction.rect!.height}
              fill={redaction.fill}
              fillOpacity={0.3}
              stroke="#dc2626"
              strokeWidth={1.5}
            />
          ))}
        {pageWhiteouts.map((section) => {
          const covered = whiteoutActive && section.id !== spotlightId;
          return (
            <rect
              key={section.id}
              className="pdf-whiteout"
              data-covered={covered || undefined}
              x={section.rect.x}
              y={section.rect.y}
              width={section.rect.width}
              height={section.rect.height}
              fill={covered ? '#ffffff' : 'none'}
              stroke={covered ? '#cbd5e1' : '#94a3b8'}
              strokeWidth={1}
              strokeDasharray={covered ? undefined : '4 3'}
            />
          );
        })}
      </g>
    </svg>
  );
}
