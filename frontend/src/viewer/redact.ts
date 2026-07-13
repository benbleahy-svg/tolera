/**
 * Redaction + whiteout model (M2.4, spec #pdf-capabilities Redact;
 * VIEWER-AND-FILE-TYPES §4/§6). Redactions are page-space regions or whole
 * pages; saving renders a NEW file in which affected pages are rasterized —
 * content under a region is irrecoverable in the copy (an overlay box would
 * leave the text extractable). Whiteout sections are session view-state
 * that clear callout clutter; spotlight lifts exactly one.
 */

import type { Rect } from './annotations';

export interface Redaction {
  id: string;
  page: number;
  /** absent rect = the whole page is redacted */
  rect?: Rect;
  fill: string;
  stroke: string;
}

export interface WhiteoutSection {
  id: string;
  page: number;
  rect: Rect;
}

export interface RedactionPlan {
  /** pages whose regions force rasterization */
  rasterPages: number[];
  /** fully-redacted pages → solid fill, no content at all */
  solidPages: number[];
  /** pages copied vector-identical */
  untouchedPages: number[];
}

/** Which page gets which treatment in the rendered copy. */
export function buildRedactionPlan(pageCount: number, redactions: Redaction[]): RedactionPlan {
  const solid = new Set(redactions.filter((r) => !r.rect).map((r) => r.page));
  const raster = new Set(
    redactions.filter((r) => r.rect && !solid.has(r.page)).map((r) => r.page),
  );
  const untouched: number[] = [];
  for (let page = 1; page <= pageCount; page += 1) {
    if (!solid.has(page) && !raster.has(page)) untouched.push(page);
  }
  return {
    rasterPages: [...raster].sort((a, b) => a - b),
    solidPages: [...solid].sort((a, b) => a - b),
    untouchedPages: untouched,
  };
}

/**
 * Fidelity of rasterized pages in the saved copy (pdf.js render scale,
 * ≈ 72·scale DPI). Grill 2026-07-13: 3, trading file size for legibility of
 * vendor-bound prints.
 */
export const REDACTION_RENDER_SCALE = 3;

export interface PagePixels {
  data: Uint8ClampedArray;
  width: number;
  height: number;
}

/** `#rrggbb` → 0–255 channels (shared with pdf.ts's pdf-lib colours). */
export function hexChannels(hex: string): [number, number, number] {
  const value = /^#?([\da-f]{6})$/i.exec(hex)?.[1];
  if (!value) return [0, 0, 0];
  return [
    parseInt(value.slice(0, 2), 16),
    parseInt(value.slice(2, 4), 16),
    parseInt(value.slice(4, 6), 16),
  ];
}

/**
 * Paint each region's fill straight into the rendered page's RGBA buffer —
 * the pixels under a region are gone before the page is re-encoded, which is
 * what makes the copy irrecoverable. Region coords are scale-1 viewport
 * space; the buffer was rendered at `renderScale`.
 */
export function fillRedactionsInPixels(
  pixels: PagePixels,
  redactions: Redaction[],
  renderScale: number,
): void {
  for (const redaction of redactions) {
    if (!redaction.rect) continue;
    const [r, g, b] = hexChannels(redaction.fill);
    const x0 = Math.max(0, Math.floor(redaction.rect.x * renderScale));
    const y0 = Math.max(0, Math.floor(redaction.rect.y * renderScale));
    const x1 = Math.min(
      pixels.width,
      Math.ceil((redaction.rect.x + redaction.rect.width) * renderScale),
    );
    const y1 = Math.min(
      pixels.height,
      Math.ceil((redaction.rect.y + redaction.rect.height) * renderScale),
    );
    for (let y = y0; y < y1; y += 1) {
      for (let x = x0; x < x1; x += 1) {
        const i = (y * pixels.width + x) * 4;
        pixels.data[i] = r;
        pixels.data[i + 1] = g;
        pixels.data[i + 2] = b;
        pixels.data[i + 3] = 255;
      }
    }
  }
}

/** `halter-4711.pdf` → `halter-4711-redacted.pdf` (server derives the same). */
export function redactedFilename(filename: string): string {
  return filename.replace(/\.pdf$/i, '') + '-redacted.pdf';
}

/** White-on-white hides that a redaction happened (spec-named preset). */
export const REDACTION_PRESETS: Record<string, { fill: string; stroke: string }> = {
  schwarz: { fill: '#000000', stroke: '#000000' },
  weiss: { fill: '#ffffff', stroke: '#ffffff' },
};
