/**
 * Thin pdf.js / pdf-lib facade (M2.1). Everything the viewer needs from the
 * rendering stack goes through this module so tests can mock it wholesale
 * (the repo's api.ts pattern) — jsdom has no canvas.
 */

import * as pdfjs from 'pdfjs-dist';
import workerUrl from 'pdfjs-dist/build/pdf.worker.min.mjs?url';
import { PDFDocument, degrees } from 'pdf-lib';

pdfjs.GlobalWorkerOptions.workerSrc = workerUrl;

export interface LoadedPdf {
  pageCount: number;
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

/** Rotate selected 1-based pages by +90° and return the new bytes. */
export async function rotatePages(bytes: Uint8Array, pages: number[]): Promise<Uint8Array> {
  const doc = await PDFDocument.load(bytes);
  for (const pageNumber of pages) {
    const page = doc.getPage(pageNumber - 1);
    page.setRotation(degrees((page.getRotation().angle + 90) % 360));
  }
  return doc.save();
}
