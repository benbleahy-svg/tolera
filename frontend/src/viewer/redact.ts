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

/** `halter-4711.pdf` → `halter-4711-redacted.pdf` (server derives the same). */
export function redactedFilename(filename: string): string {
  return filename.replace(/\.pdf$/i, '') + '-redacted.pdf';
}

/** White-on-white hides that a redaction happened (spec-named preset). */
export const REDACTION_PRESETS: Record<string, { fill: string; stroke: string }> = {
  schwarz: { fill: '#000000', stroke: '#000000' },
  weiss: { fill: '#ffffff', stroke: '#ffffff' },
};
