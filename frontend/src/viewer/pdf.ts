/**
 * Thin pdf.js / pdf-lib facade (M2.1). Everything the viewer needs from the
 * rendering stack goes through this module so tests can mock it wholesale
 * (the repo's api.ts pattern) — jsdom has no canvas.
 */

import * as pdfjs from 'pdfjs-dist';
import workerUrl from 'pdfjs-dist/build/pdf.worker.min.mjs?url';
import { PDFDocument, degrees, rgb, type PDFPage } from 'pdf-lib';

import { arrowHeads, highlightFill, sampleArc, squigglePoints, type Annotation } from './annotations';
import {
  REDACTION_RENDER_SCALE,
  buildRedactionPlan,
  fillRedactionsInPixels,
  type Redaction,
} from './redact';

pdfjs.GlobalWorkerOptions.workerSrc = workerUrl;

export interface LoadedPdf {
  pageCount: number;
  /** Unscaled page dimensions (pdf units ≈ CSS px at scale 1). */
  getPageSize: (page: number) => Promise<{ width: number; height: number }>;
  /** Extracted text per page (1-based), for search. */
  getPageText: (page: number) => Promise<string>;
  /** Render one page into a canvas at the given scale/rotation (degrees). */
  renderPage: (
    page: number,
    canvas: HTMLCanvasElement,
    scale: number,
    rotation: number,
  ) => Promise<void>;
  /** Render one page offscreen and return its pixels (revision compare). */
  renderPagePixels: (
    page: number,
    scale: number,
  ) => Promise<{ data: Uint8ClampedArray; width: number; height: number }>;
}

export async function loadPdf(bytes: Uint8Array): Promise<LoadedPdf> {
  const doc = await pdfjs.getDocument({ data: bytes }).promise;
  return {
    pageCount: doc.numPages,
    getPageSize: async (page) => {
      const pdfPage = await doc.getPage(page);
      const viewport = pdfPage.getViewport({ scale: 1 });
      return { width: viewport.width, height: viewport.height };
    },
    getPageText: async (page) => {
      const pdfPage = await doc.getPage(page);
      const content = await pdfPage.getTextContent();
      return content.items
        .map((item) => ('str' in item ? item.str : ''))
        .join(' ');
    },
    renderPage: async (page, canvas, scale, rotation) => {
      const pdfPage = await doc.getPage(page);
      const viewport = pdfPage.getViewport({ scale, rotation });
      canvas.width = viewport.width;
      canvas.height = viewport.height;
      const context = canvas.getContext('2d');
      if (!context) return;
      await pdfPage.render({ canvasContext: context, viewport, canvas }).promise;
    },
    renderPagePixels: async (page, scale) => {
      const pdfPage = await doc.getPage(page);
      const viewport = pdfPage.getViewport({ scale });
      const canvas = document.createElement('canvas');
      canvas.width = viewport.width;
      canvas.height = viewport.height;
      const context = canvas.getContext('2d');
      if (!context) return { data: new Uint8ClampedArray(0), width: 0, height: 0 };
      await pdfPage.render({ canvasContext: context, viewport, canvas }).promise;
      const image = context.getImageData(0, 0, canvas.width, canvas.height);
      return { data: image.data, width: image.width, height: image.height };
    },
  };
}

/** Build a new PDF from selected 1-based pages (thumbnail Extract → local download). */
export async function extractPages(bytes: Uint8Array, pages: number[]): Promise<Uint8Array> {
  const source = await PDFDocument.load(bytes);
  const target = await PDFDocument.create();
  const copied = await target.copyPages(
    source,
    pages.map((page) => page - 1),
  );
  for (const page of copied) target.addPage(page);
  return target.save();
}

/** Apply the viewer's per-page rotations (degrees) so Extract matches the view. */
export async function rotatePages(
  bytes: Uint8Array,
  rotations: Record<number, number>,
): Promise<Uint8Array> {
  const doc = await PDFDocument.load(bytes);
  for (const [pageNumber, rotation] of Object.entries(rotations)) {
    if (!rotation) continue;
    const page = doc.getPage(Number(pageNumber) - 1);
    page.setRotation(degrees((page.getRotation().angle + rotation) % 360));
  }
  return doc.save();
}

/**
 * Render the redacted copy (M2.4, spec #pdf-capabilities Redact / #collab
 * "exact redacted copy"). Untouched pages are copied vector-identical;
 * fully-redacted pages become a fresh page under a solid fill; pages with
 * region redactions are RASTERIZED — rendered to pixels, regions filled in
 * the buffer, re-embedded as a full-page image — so the content underneath
 * is irrecoverable in the copy (a rect overlay would leave it extractable;
 * the M2 exit check greps the copy's extracted text). The source bytes are
 * never mutated.
 */
export async function renderRedactedCopy(
  bytes: Uint8Array,
  doc: Pick<LoadedPdf, 'renderPagePixels'>,
  redactions: Redaction[],
): Promise<Uint8Array> {
  const source = await PDFDocument.load(bytes);
  const target = await PDFDocument.create();
  const plan = buildRedactionPlan(source.getPageCount(), redactions);
  const solid = new Set(plan.solidPages);
  const raster = new Set(plan.rasterPages);
  for (let page = 1; page <= source.getPageCount(); page += 1) {
    if (solid.has(page)) {
      const { width, height } = source.getPage(page - 1).getSize();
      const fill = redactions.find((r) => r.page === page && !r.rect)?.fill ?? '#000000';
      target
        .addPage([width, height])
        .drawRectangle({ x: 0, y: 0, width, height, color: hexToRgb(fill) });
    } else if (raster.has(page)) {
      const pixels = await doc.renderPagePixels(page, REDACTION_RENDER_SCALE);
      fillRedactionsInPixels(
        pixels,
        redactions.filter((r) => r.page === page && r.rect),
        REDACTION_RENDER_SCALE,
      );
      const canvas = document.createElement('canvas');
      canvas.width = pixels.width;
      canvas.height = pixels.height;
      const context = canvas.getContext('2d');
      if (!context) throw new Error('Canvas 2D ist für geschwärzte Seiten erforderlich.');
      context.putImageData(
        new ImageData(pixels.data as Uint8ClampedArray<ArrayBuffer>, pixels.width, pixels.height),
        0,
        0,
      );
      const png = await target.embedPng(canvas.toDataURL('image/png'));
      // page size = what was rendered, ÷ scale — follows any inherent rotation
      const width = pixels.width / REDACTION_RENDER_SCALE;
      const height = pixels.height / REDACTION_RENDER_SCALE;
      target.addPage([width, height]).drawImage(png, { x: 0, y: 0, width, height });
    } else {
      const [copied] = await target.copyPages(source, [page - 1]);
      target.addPage(copied);
    }
  }
  return target.save();
}

function hexToRgb(hex: string) {
  const value = /^#?([\da-f]{6})$/i.exec(hex)?.[1];
  if (!value) return rgb(0, 0, 0);
  return rgb(
    parseInt(value.slice(0, 2), 16) / 255,
    parseInt(value.slice(2, 4), 16) / 255,
    parseInt(value.slice(4, 6), 16) / 255,
  );
}

function drawPolyline(pdfPage: PDFPage, points: { x: number; y: number }[], height: number, color: ReturnType<typeof rgb>, thickness: number, opacity: number) {
  for (let i = 1; i < points.length; i += 1) {
    pdfPage.drawLine({
      start: { x: points[i - 1].x, y: height - points[i - 1].y },
      end: { x: points[i].x, y: height - points[i].y },
      color,
      thickness,
      opacity,
    });
  }
}

/** Burn the annotation layer into a copy (download-with-annotations). */
export async function drawAnnotations(
  bytes: Uint8Array,
  objects: Annotation[],
): Promise<Uint8Array> {
  const doc = await PDFDocument.load(bytes);
  for (const annotation of objects) {
    if (annotation.page < 1 || annotation.page > doc.getPageCount()) continue;
    const pdfPage = doc.getPage(annotation.page - 1);
    const { height } = pdfPage.getSize();
    const stroke = hexToRgb(annotation.style.stroke === 'none' ? '#000000' : annotation.style.stroke);
    const thickness = annotation.style.strokeWidth || 1;
    const opacity = annotation.style.opacity;
    const { rect, points, at } = annotation;
    if (rect) {
      const yTop = height - rect.y;
      switch (annotation.type) {
        case 'highlight': {
          const marker = highlightFill(annotation.style);
          pdfPage.drawRectangle({
            x: rect.x,
            y: yTop - rect.height,
            width: rect.width,
            height: rect.height,
            color: hexToRgb(marker.fill),
            opacity: marker.opacity,
          });
          break;
        }
        case 'underline':
          pdfPage.drawLine({
            start: { x: rect.x, y: yTop - rect.height },
            end: { x: rect.x + rect.width, y: yTop - rect.height },
            color: stroke,
            thickness,
            opacity,
          });
          break;
        case 'squiggly':
          // the same wave the overlay renders, not a straight line
          drawPolyline(
            pdfPage,
            squigglePoints(rect.x, rect.width, rect.y + rect.height),
            height,
            stroke,
            thickness,
            opacity,
          );
          break;
        case 'strikeout':
          pdfPage.drawLine({
            start: { x: rect.x, y: yTop - rect.height / 2 },
            end: { x: rect.x + rect.width, y: yTop - rect.height / 2 },
            color: stroke,
            thickness,
            opacity,
          });
          break;
        case 'ellipse':
          pdfPage.drawEllipse({
            x: rect.x + rect.width / 2,
            y: yTop - rect.height / 2,
            xScale: rect.width / 2,
            yScale: rect.height / 2,
            borderColor: stroke,
            borderWidth: thickness,
            opacity: annotation.style.fill === 'none' ? 0 : opacity,
            borderOpacity: opacity,
          });
          break;
        default:
          pdfPage.drawRectangle({
            x: rect.x,
            y: yTop - rect.height,
            width: rect.width,
            height: rect.height,
            borderColor: stroke,
            borderWidth: thickness,
            opacity: annotation.style.fill === 'none' ? 0 : opacity,
            borderOpacity: opacity,
          });
      }
    } else if (points && points.length >= 2) {
      if (annotation.type === 'arc') {
        // the same quadratic the overlay renders (shared sampler)
        drawPolyline(
          pdfPage,
          sampleArc(points[0], points.at(-1)!),
          height,
          stroke,
          thickness || 2,
          opacity,
        );
      } else if (annotation.type === 'freehand_highlight') {
        const marker = highlightFill(annotation.style);
        drawPolyline(pdfPage, points, height, hexToRgb(marker.fill), 12, marker.opacity);
      } else {
        drawPolyline(pdfPage, points, height, stroke, thickness || 2, opacity);
      }
      if (annotation.type === 'polygon') {
        drawPolyline(pdfPage, [points.at(-1)!, points[0]], height, stroke, thickness || 2, opacity);
      }
      if (annotation.type === 'arrow') {
        // the overlay's arrowhead, mirrored into the export (shared helper)
        for (const head of arrowHeads(points[0], points.at(-1)!)) {
          drawPolyline(pdfPage, head, height, stroke, thickness || 2, opacity);
        }
      }
    } else if (at && annotation.text) {
      if (annotation.type === 'note') {
        // keep the sticky-note marker visible in the export
        pdfPage.drawRectangle({
          x: at.x - 8,
          y: height - at.y - 8,
          width: 16,
          height: 16,
          color: hexToRgb('#fde68a'),
          borderColor: stroke,
          borderWidth: 1,
          opacity,
        });
        pdfPage.drawText(annotation.text, {
          x: at.x + 12,
          y: height - at.y - 4,
          size: annotation.style.fontSize ?? 10,
          color: stroke,
          opacity,
        });
      } else {
        pdfPage.drawText(annotation.text, {
          x: at.x,
          y: height - at.y,
          size: annotation.style.fontSize ?? 12,
          color: stroke,
          opacity,
        });
      }
    }
  }
  return doc.save();
}
