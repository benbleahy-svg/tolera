/**
 * Annotation model + pure editing logic (M2.2, spec #pdf-capabilities
 * Annotate/Shapes). Coordinates live in pdf.js viewport space at scale 1
 * (top-left origin, y down); the overlay scales them by zoom, and
 * download-with-annotations converts to PDF bottom-left space. Undo/redo is
 * snapshot-based so "restores prior state exactly" is trivially true.
 */

export type AnnotationType =
  // annotate tools (spec keys)
  | 'underline' // U
  | 'highlight' // H
  | 'rectangle' // R
  | 'free_text' // T
  | 'freehand_highlight'
  | 'freehand' // F
  | 'note' // N
  | 'squiggly' // G
  | 'strikeout' // K
  // shapes
  | 'shape_rectangle'
  | 'line' // L
  | 'polyline'
  | 'arrow' // A
  | 'arc'
  | 'ellipse' // O
  | 'polygon';

export interface Point {
  x: number;
  y: number;
}

export interface Rect {
  x: number;
  y: number;
  width: number;
  height: number;
}

export interface AnnotationStyle {
  stroke: string;
  strokeWidth: number;
  fill: string;
  opacity: number;
  fontSize?: number;
}

export interface Annotation {
  id: string;
  page: number;
  type: AnnotationType;
  rect?: Rect;
  points?: Point[];
  at?: Point;
  text?: string;
  style: AnnotationStyle;
}

/** Styling presets (spec: "Presets for styling"). */
export const PRESETS: Record<string, AnnotationStyle> = {
  standard: { stroke: '#d6409f', strokeWidth: 2, fill: 'none', opacity: 1 },
  fein: { stroke: '#1d4ed8', strokeWidth: 1, fill: 'none', opacity: 1 },
  marker: { stroke: 'none', strokeWidth: 0, fill: '#facc15', opacity: 0.4 },
  warnung: { stroke: '#b91c1c', strokeWidth: 3, fill: 'none', opacity: 1 },
};

/** Which geometry a tool produces (drives the overlay's pointer handling). */
export const TOOL_KIND: Record<
  AnnotationType,
  'drag-rect' | 'drag-line' | 'freehand' | 'click-point' | 'click-points'
> = {
  underline: 'drag-rect',
  highlight: 'drag-rect',
  rectangle: 'drag-rect',
  free_text: 'click-point',
  freehand_highlight: 'freehand',
  freehand: 'freehand',
  note: 'click-point',
  squiggly: 'drag-rect',
  strikeout: 'drag-rect',
  shape_rectangle: 'drag-rect',
  line: 'drag-line',
  polyline: 'click-points',
  arrow: 'drag-line',
  arc: 'drag-line',
  ellipse: 'drag-rect',
  polygon: 'click-points',
};

/** Keyboard shortcuts per spec (§4 Annotate / Shapes). */
export const TOOL_SHORTCUTS: Record<string, AnnotationType | 'eraser'> = {
  u: 'underline',
  h: 'highlight',
  r: 'rectangle',
  t: 'free_text',
  f: 'freehand',
  n: 'note',
  g: 'squiggly',
  k: 'strikeout',
  e: 'eraser',
  l: 'line',
  a: 'arrow',
  o: 'ellipse',
};

export interface LayerState {
  objects: Annotation[];
  undoStack: Annotation[][];
  redoStack: Annotation[][];
  dirty: boolean;
}

export type LayerAction =
  | { kind: 'load'; objects: Annotation[] }
  | { kind: 'add'; annotation: Annotation }
  | { kind: 'remove'; id: string }
  | { kind: 'undo' }
  | { kind: 'redo' }
  | { kind: 'saved' };

export const emptyLayer: LayerState = {
  objects: [],
  undoStack: [],
  redoStack: [],
  dirty: false,
};

/** Snapshot-based reducer: undo/redo restore the exact prior object list. */
export function layerReducer(state: LayerState, action: LayerAction): LayerState {
  switch (action.kind) {
    case 'load':
      return { objects: action.objects, undoStack: [], redoStack: [], dirty: false };
    case 'add':
      return {
        objects: [...state.objects, action.annotation],
        undoStack: [...state.undoStack, state.objects],
        redoStack: [],
        dirty: true,
      };
    case 'remove': {
      if (!state.objects.some((a) => a.id === action.id)) return state;
      return {
        objects: state.objects.filter((a) => a.id !== action.id),
        undoStack: [...state.undoStack, state.objects],
        redoStack: [],
        dirty: true,
      };
    }
    case 'undo': {
      const previous = state.undoStack.at(-1);
      if (!previous) return state;
      return {
        objects: previous,
        undoStack: state.undoStack.slice(0, -1),
        redoStack: [...state.redoStack, state.objects],
        dirty: true,
      };
    }
    case 'redo': {
      const next = state.redoStack.at(-1);
      if (!next) return state;
      return {
        objects: next,
        undoStack: [...state.undoStack, state.objects],
        redoStack: state.redoStack.slice(0, -1),
        dirty: true,
      };
    }
    case 'saved':
      return { ...state, dirty: false };
  }
}

function rectOf(annotation: Annotation): Rect | null {
  if (annotation.rect) return annotation.rect;
  if (annotation.at) return { x: annotation.at.x - 8, y: annotation.at.y - 8, width: 16, height: 16 };
  if (annotation.points?.length) {
    const xs = annotation.points.map((p) => p.x);
    const ys = annotation.points.map((p) => p.y);
    return {
      x: Math.min(...xs),
      y: Math.min(...ys),
      width: Math.max(...xs) - Math.min(...xs),
      height: Math.max(...ys) - Math.min(...ys),
    };
  }
  return null;
}

/** Eraser hit test: within the annotation's bounding box (+ tolerance). */
export function hitTest(annotation: Annotation, point: Point, tolerance = 6): boolean {
  const rect = rectOf(annotation);
  if (!rect) return false;
  return (
    point.x >= rect.x - tolerance &&
    point.x <= rect.x + rect.width + tolerance &&
    point.y >= rect.y - tolerance &&
    point.y <= rect.y + rect.height + tolerance
  );
}

/** Build the annotation object a completed gesture produces. */
export function buildAnnotation(
  id: string,
  page: number,
  type: AnnotationType,
  style: AnnotationStyle,
  geometry: { rect?: Rect; points?: Point[]; at?: Point; text?: string },
): Annotation {
  return { id, page, type, style, ...geometry };
}
