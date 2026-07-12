/**
 * Pure viewer logic (M2.1, spec #pdf-capabilities) — kept free of pdf.js so
 * the behaviors the acceptance criteria name (page multi-select parsing,
 * case/whole-word search, the red/blue/black revision diff) are unit-testable
 * without a rendering stack.
 */

/** Parse the thumbnail panel's multi-select input: `1,3,5` and ranges `1-5`. */
export function parsePageSelection(input: string, pageCount: number): number[] {
  const pages = new Set<number>();
  for (const raw of input.split(',')) {
    const token = raw.trim();
    if (!token) continue;
    const range = token.match(/^(\d+)\s*-\s*(\d+)$/);
    if (range) {
      const from = Number(range[1]);
      const to = Number(range[2]);
      if (from < 1 || to < from) continue;
      for (let page = from; page <= Math.min(to, pageCount); page += 1) pages.add(page);
      continue;
    }
    const page = Number(token);
    if (Number.isInteger(page) && page >= 1 && page <= pageCount) pages.add(page);
  }
  return [...pages].sort((a, b) => a - b);
}

export interface SearchOptions {
  caseSensitive: boolean;
  wholeWord: boolean;
}

export interface SearchHit {
  page: number;
  index: number;
}

const escapeRegExp = (value: string) => value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');

/** In-document search over extracted page texts, honoring both toggles. */
export function searchPages(
  pageTexts: readonly string[],
  query: string,
  options: SearchOptions,
): SearchHit[] {
  if (!query.trim()) return [];
  const source = options.wholeWord
    ? `(?<![\\p{L}\\p{N}_])${escapeRegExp(query)}(?![\\p{L}\\p{N}_])`
    : escapeRegExp(query);
  const regex = new RegExp(source, options.caseSensitive ? 'gu' : 'giu');
  const hits: SearchHit[] = [];
  pageTexts.forEach((text, pageIndex) => {
    for (const match of text.matchAll(regex)) {
      hits.push({ page: pageIndex + 1, index: match.index ?? 0 });
    }
  });
  return hits;
}

/** Is this RGBA pixel "ink" (dark enough to count as drawing)? */
function isInk(data: Uint8ClampedArray, offset: number): boolean {
  const alpha = data[offset + 3];
  if (alpha < 32) return false;
  const luma = 0.299 * data[offset] + 0.587 * data[offset + 1] + 0.114 * data[offset + 2];
  return luma < 176;
}

/**
 * The revision-diff coloring (spec: **red = removed, blue = added,
 * black = identical**): pixels inked only in the base turn red, only in the
 * comparison blue, in both black; everything else stays transparent.
 * Both inputs must share dimensions (the caller renders at one scale).
 */
export function diffImageData(
  base: Uint8ClampedArray,
  comparison: Uint8ClampedArray,
): Uint8ClampedArray<ArrayBuffer> {
  const out = new Uint8ClampedArray(new ArrayBuffer(base.length));
  for (let offset = 0; offset < base.length; offset += 4) {
    const inBase = isInk(base, offset);
    const inComparison = isInk(comparison, offset);
    if (!inBase && !inComparison) continue; // transparent
    if (inBase && inComparison) {
      out[offset + 3] = 255; // black
    } else if (inBase) {
      out[offset] = 220; // red = removed
      out[offset + 3] = 255;
    } else {
      out[offset + 2] = 220; // blue = added
      out[offset + 3] = 255;
    }
  }
  return out;
}

/** The zoom presets the toolbar dropdown offers. */
export const ZOOM_STEPS = [0.5, 0.75, 1, 1.25, 1.5, 2, 3, 4, 6, 8] as const;

export function nextZoom(current: number, direction: 1 | -1): number {
  const sorted = [...ZOOM_STEPS];
  if (direction === 1) return sorted.find((step) => step > current + 1e-9) ?? current;
  return [...sorted].reverse().find((step) => step < current - 1e-9) ?? current;
}
