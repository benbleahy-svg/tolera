/**
 * M2.4 redaction + whiteout — the AC list: redacting a region/page renders a
 * NEW file with the content irrecoverable in the copy (rasterized/solid, no
 * text ops left), fill recolour applies, whiteout hides drawn sections and
 * spotlight re-reveals exactly one, save posts the copy as a supporting file
 * (with a confirm when one already exists). pdf.js stays mocked at the module
 * boundary in page tests; renderRedactedCopy is tested for real against
 * pdf-lib with a stubbed canvas encoder (jsdom has no canvas).
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import {
  PDFArray,
  PDFDocument,
  PDFRawStream,
  StandardFonts,
  decodePDFRawStream,
} from 'pdf-lib';

import {
  REDACTION_PRESETS,
  REDACTION_RENDER_SCALE,
  buildRedactionPlan,
  fillRedactionsInPixels,
  redactedFilename,
  type Redaction,
} from './redact';

// --- plan + naming (pure) ------------------------------------------------------

describe('buildRedactionPlan', () => {
  const region = (page: number): Redaction => ({
    id: `r${page}`,
    page,
    rect: { x: 10, y: 10, width: 50, height: 20 },
    ...REDACTION_PRESETS.schwarz,
  });
  const wholePage = (page: number): Redaction => ({
    id: `p${page}`,
    page,
    ...REDACTION_PRESETS.schwarz,
  });

  it('buckets pages into solid / raster / untouched', () => {
    const plan = buildRedactionPlan(4, [region(2), wholePage(3)]);
    expect(plan).toEqual({ rasterPages: [2], solidPages: [3], untouchedPages: [1, 4] });
  });

  it('a whole-page redaction wins over regions on the same page', () => {
    const plan = buildRedactionPlan(2, [region(1), wholePage(1)]);
    expect(plan).toEqual({ rasterPages: [], solidPages: [1], untouchedPages: [2] });
  });

  it('no redactions → every page untouched', () => {
    expect(buildRedactionPlan(2, [])).toEqual({
      rasterPages: [],
      solidPages: [],
      untouchedPages: [1, 2],
    });
  });
});

describe('redactedFilename', () => {
  it('derives the -redacted sibling the backend also derives', () => {
    expect(redactedFilename('halter-4711.pdf')).toBe('halter-4711-redacted.pdf');
    expect(redactedFilename('HALTER.PDF')).toBe('HALTER-redacted.pdf');
  });
});

// --- pixel fill (pure — what makes region redaction irrecoverable) -------------

describe('fillRedactionsInPixels', () => {
  it('paints the region (× renderScale) with the redaction fill, alpha opaque', () => {
    // 6×4 buffer at renderScale 2 ← a 3×2 page; redact the 1×1 rect at (1,0)
    const pixels = {
      data: new Uint8ClampedArray(6 * 4 * 4).fill(7),
      width: 6,
      height: 4,
    };
    const redaction: Redaction = {
      id: 'r1',
      page: 1,
      rect: { x: 1, y: 0, width: 1, height: 1 },
      fill: '#102030',
      stroke: '#102030',
    };
    fillRedactionsInPixels(pixels, [redaction], 2);
    const px = (x: number, y: number) => {
      const i = (y * pixels.width + x) * 4;
      return [pixels.data[i], pixels.data[i + 1], pixels.data[i + 2], pixels.data[i + 3]];
    };
    // inside: columns 2–3, rows 0–1
    expect(px(2, 0)).toEqual([0x10, 0x20, 0x30, 255]);
    expect(px(3, 1)).toEqual([0x10, 0x20, 0x30, 255]);
    // outside stays untouched
    expect(px(1, 0)).toEqual([7, 7, 7, 7]);
    expect(px(2, 2)).toEqual([7, 7, 7, 7]);
    expect(px(4, 0)).toEqual([7, 7, 7, 7]);
  });

  it('clamps regions that overhang the page', () => {
    const pixels = { data: new Uint8ClampedArray(2 * 2 * 4), width: 2, height: 2 };
    const redaction: Redaction = {
      id: 'r1',
      page: 1,
      rect: { x: -5, y: -5, width: 100, height: 100 },
      ...REDACTION_PRESETS.weiss,
    };
    expect(() => fillRedactionsInPixels(pixels, [redaction], 1)).not.toThrow();
    expect(pixels.data[0]).toBe(255);
    expect(pixels.data[15]).toBe(255);
  });
});

// --- renderRedactedCopy (pdf-lib for real; canvas encoder stubbed) --------------

// verified 1×1 PNG — the stubbed toDataURL result pdf-lib embeds
const PNG_1X1 =
  'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==';

async function makeSourcePdf(): Promise<Uint8Array> {
  const doc = await PDFDocument.create();
  const font = await doc.embedFont(StandardFonts.Helvetica);
  const first = doc.addPage([600, 400]);
  first.drawText('GEHEIM', { x: 50, y: 350, size: 24, font });
  const second = doc.addPage([600, 400]);
  second.drawText('OFFEN', { x: 50, y: 350, size: 24, font });
  return doc.save();
}

/** Concatenated decoded content-stream ops of one page (0-based). */
function pageOps(doc: PDFDocument, index: number): string {
  const contents = doc.getPage(index).node.Contents();
  const streams: PDFRawStream[] = [];
  if (contents instanceof PDFRawStream) streams.push(contents);
  else if (contents instanceof PDFArray) {
    for (let i = 0; i < contents.size(); i += 1) {
      const stream = doc.context.lookup(contents.get(i));
      if (stream instanceof PDFRawStream) streams.push(stream);
    }
  }
  return streams
    .map((stream) => new TextDecoder('latin1').decode(decodePDFRawStream(stream).decode()))
    .join('\n');
}

const fakeDoc = {
  renderPagePixels: vi.fn((_page: number, scale: number) =>
    Promise.resolve({
      data: new Uint8ClampedArray(Math.round(600 * scale) * Math.round(400 * scale) * 4).fill(
        255,
      ),
      width: Math.round(600 * scale),
      height: Math.round(400 * scale),
    }),
  ),
};

describe('renderRedactedCopy', () => {
  beforeEach(() => {
    vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue({
      putImageData: vi.fn(),
    } as unknown as CanvasRenderingContext2D);
    vi.spyOn(HTMLCanvasElement.prototype, 'toDataURL').mockReturnValue(PNG_1X1);
  });
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('whole-page redaction → solid page with no text ops (irrecoverable)', async () => {
    const { renderRedactedCopy } = await import('./pdf');
    const bytes = await makeSourcePdf();
    const out = await renderRedactedCopy(bytes, fakeDoc, [
      { id: 'p1', page: 1, ...REDACTION_PRESETS.schwarz },
    ]);
    const copy = await PDFDocument.load(out);
    expect(copy.getPageCount()).toBe(2);
    const solid = pageOps(copy, 0);
    expect(solid).not.toMatch(/Tj|TJ/); // no text-show operators survive
    expect(solid).toContain('600 400 l'); // the full-page fill path…
    expect(solid).toMatch(/\bf\b/); // …painted
    expect(pageOps(copy, 1)).toMatch(/Tj|TJ/); // untouched page keeps its text
  });

  it('region redaction → the page is rasterized (image, no text ops)', async () => {
    const { renderRedactedCopy } = await import('./pdf');
    const bytes = await makeSourcePdf();
    const out = await renderRedactedCopy(bytes, fakeDoc, [
      {
        id: 'r1',
        page: 1,
        rect: { x: 40, y: 30, width: 200, height: 40 },
        ...REDACTION_PRESETS.schwarz,
      },
    ]);
    // rendered at the fidelity knob agreed in the grill
    expect(fakeDoc.renderPagePixels).toHaveBeenCalledWith(1, REDACTION_RENDER_SCALE);
    const copy = await PDFDocument.load(out);
    expect(copy.getPageCount()).toBe(2);
    const raster = pageOps(copy, 0);
    expect(raster).not.toMatch(/Tj|TJ/);
    expect(raster).toContain('Do'); // the full-page image draw
    // the raster page keeps the source page's size (pixels ÷ renderScale)
    expect(copy.getPage(0).getSize()).toEqual({ width: 600, height: 400 });
    expect(pageOps(copy, 1)).toMatch(/Tj|TJ/);
  });

  it('solid pages keep the source page’s inherent rotation (exact copy)', async () => {
    const { renderRedactedCopy } = await import('./pdf');
    const { degrees } = await import('pdf-lib');
    const doc = await PDFDocument.create();
    const rotated = doc.addPage([600, 400]);
    rotated.setRotation(degrees(90));
    const bytes = await doc.save();
    const out = await renderRedactedCopy(bytes, fakeDoc, [
      { id: 'p1', page: 1, ...REDACTION_PRESETS.schwarz },
    ]);
    const copy = await PDFDocument.load(out);
    expect(copy.getPage(0).getRotation().angle).toBe(90);
    expect(copy.getPage(0).getSize()).toEqual({ width: 600, height: 400 });
  });

  it('untouched pages are copied and the original bytes are never mutated', async () => {
    const { renderRedactedCopy } = await import('./pdf');
    const bytes = await makeSourcePdf();
    const before = bytes.slice();
    const out = await renderRedactedCopy(bytes, fakeDoc, [
      { id: 'p2', page: 2, ...REDACTION_PRESETS.weiss },
    ]);
    expect(bytes).toEqual(before);
    const copy = await PDFDocument.load(out);
    expect(pageOps(copy, 0)).toMatch(/Tj|TJ/); // page 1 untouched
    expect(pageOps(copy, 1)).not.toMatch(/Tj|TJ/); // page 2 solid (weiss)
  });
});
