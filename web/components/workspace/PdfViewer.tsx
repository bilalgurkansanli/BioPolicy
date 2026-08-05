"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { PDFDocumentLoadingTask, PDFDocumentProxy } from "pdfjs-dist";

import { useLocale } from "@/components/LocaleProvider";
import { fetchPageLines } from "@/lib/api";
import {
  locateQuote,
  locateQuoteInLines,
  type Rect,
  type TextItem,
} from "@/lib/locate-quote";
import type { BBox } from "@/lib/types";

export type Highlight = {
  /** 1-based, matching the citation and the database. */
  page: number;
  /** The chunk's box. Used only when the quote cannot be located precisely. */
  bbox: BBox;
  /** What was actually cited. Located in the page's text layer on click. */
  quote: string;
  /** Changes on every click so re-clicking the same citation re-flashes it. */
  nonce: number;
};

/** Where the highlight came from, because the two mean different things. */
type Located = {
  nonce: number;
  rects: Rect[];
  /** False when the quote was not found and this is the surrounding block. */
  precise: boolean;
};

/**
 * pdf.js is loaded lazily and only in the browser. It is the largest dependency
 * in the app and the landing page has no use for it.
 */
async function loadPdfjs() {
  const pdfjs = await import("pdfjs-dist");
  // The worker is copied into `public/` by `scripts/copy-pdf-worker.mjs`, which
  // keeps it version-locked to the package without asking either bundler to do
  // anything clever with `new URL(..., import.meta.url)`.
  pdfjs.GlobalWorkerOptions.workerSrc = "/pdf.worker.min.mjs";
  return pdfjs;
}

export function PdfViewer({
  documentId,
  url,
  highlight,
}: {
  /** Needed to ask for OCR geometry; the signed URL says nothing about which
      document it is. */
  documentId: string | null;
  url: string | null;
  highlight: Highlight | null;
}) {
  const { t } = useLocale();
  // Both the loaded document and the failure carry the URL they belong to, so
  // the effect never has to reset state synchronously when the URL changes —
  // a stale document is simply one whose URL no longer matches.
  const [loaded, setLoaded] = useState<{
    url: string;
    pdf: PDFDocumentProxy;
  } | null>(null);
  const [failedUrl, setFailedUrl] = useState<string | null>(null);
  const [width, setWidth] = useState(0);
  const [located, setLocated] = useState<Located | null>(null);

  const pdf = loaded && loaded.url === url ? loaded.pdf : null;
  const failed = failedUrl === url;

  // Measured in a ref callback rather than an effect so the first measurement
  // is synchronous. ResizeObserver's initial notification is delivered on the
  // rendering lifecycle, which a background or non-compositing tab never runs —
  // observing alone leaves the viewer permanently at zero width in that case.
  // 32px throughout is the container's horizontal padding.
  const measure = useCallback((element: HTMLDivElement | null) => {
    if (!element) return;
    setWidth(Math.max(0, element.clientWidth - 32));
    const observer = new ResizeObserver(([entry]) => {
      setWidth(Math.max(0, entry.contentRect.width - 32));
    });
    observer.observe(element);
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    if (!url) return;
    let cancelled = false;
    // `destroy` lives on the loading task, not on the document proxy: it is
    // what aborts the network request as well as tearing down the worker.
    let task: PDFDocumentLoadingTask | null = null;

    void (async () => {
      try {
        const pdfjs = await loadPdfjs();
        task = pdfjs.getDocument({ url });
        const opened = await task.promise;
        if (cancelled) return;
        setLoaded({ url, pdf: opened });
      } catch {
        if (!cancelled) setFailedUrl(url);
      }
    })();

    return () => {
      cancelled = true;
      void task?.destroy();
    };
  }, [url]);

  useEffect(() => {
    if (!pdf || !highlight) return;
    let cancelled = false;

    void (async () => {
      const fallback: Located = {
        nonce: highlight.nonce,
        rects: [highlight.bbox],
        precise: false,
      };
      try {
        const page = await pdf.getPage(highlight.page);
        const content = await page.getTextContent();
        const height = page.getViewport({ scale: 1 }).height;
        let rects = locateQuote(
          content.items as TextItem[],
          height,
          highlight.quote,
        );

        // No text layer, or a quote that is not in it: the page was scanned.
        // Its geometry exists, but it was produced by the OCR pass and lives on
        // the server rather than in the file the browser is holding.
        if (!rects && documentId) {
          const { lines } = await fetchPageLines(documentId, highlight.page);
          rects = locateQuoteInLines(lines, highlight.quote);
        }

        if (!cancelled) {
          setLocated(
            rects ? { nonce: highlight.nonce, rects, precise: true } : fallback,
          );
        }
      } catch {
        // Nothing found and nothing to ask. The block box is still the right
        // region, just a coarser one.
        if (!cancelled) setLocated(fallback);
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [pdf, highlight, documentId]);

  const resolved =
    highlight && located && located.nonce === highlight.nonce ? located : null;

  return (
    <div
      ref={measure}
      className="h-full overflow-y-auto overscroll-contain bg-surface-sunken px-4 py-4"
    >
      {!url && (
        <p className="pt-12 text-center text-sm text-ink-faint">
          {t.workspace.noDocument}
        </p>
      )}
      {url && failed && (
        <p className="pt-12 text-center text-sm text-danger">
          {t.workspace.viewerFailed}
        </p>
      )}
      {url && !failed && !pdf && (
        <p className="pt-12 text-center text-sm text-ink-faint">
          {t.workspace.viewerLoading}
        </p>
      )}
      {pdf && width > 0 && (
        <div className="flex flex-col items-center gap-4">
          {Array.from({ length: pdf.numPages }, (_, index) => (
            <PdfPage
              key={`${url}:${index + 1}`}
              pdf={pdf}
              pageNumber={index + 1}
              width={Math.min(width, 900)}
              highlight={
                highlight && highlight.page === index + 1 ? highlight : null
              }
              located={
                highlight && highlight.page === index + 1 ? resolved : null
              }
            />
          ))}
        </div>
      )}
    </div>
  );
}

function PdfPage({
  pdf,
  pageNumber,
  width,
  highlight,
  located,
}: {
  pdf: PDFDocumentProxy;
  pageNumber: number;
  width: number;
  highlight: Highlight | null;
  located: Located | null;
}) {
  const { t } = useLocale();
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const wrapperRef = useRef<HTMLDivElement>(null);
  const [scale, setScale] = useState(0);
  const [height, setHeight] = useState(0);

  useEffect(() => {
    let cancelled = false;
    let renderTask: { cancel: () => void } | null = null;

    void (async () => {
      const page = await pdf.getPage(pageNumber);
      if (cancelled) return;

      const unscaled = page.getViewport({ scale: 1 });
      const pageScale = width / unscaled.width;
      const viewport = page.getViewport({ scale: pageScale });

      const canvas = canvasRef.current;
      if (!canvas) return;
      // Render at device resolution and scale down with CSS. A policy is read
      // at small type; a blurry canvas makes the highlighted clause unreadable,
      // which defeats the point of highlighting it.
      const ratio = window.devicePixelRatio || 1;
      canvas.width = Math.floor(viewport.width * ratio);
      canvas.height = Math.floor(viewport.height * ratio);
      canvas.style.width = `${viewport.width}px`;
      canvas.style.height = `${viewport.height}px`;

      setScale(pageScale);
      setHeight(viewport.height);

      const task = page.render({
        canvas,
        viewport,
        transform: ratio === 1 ? undefined : [ratio, 0, 0, ratio, 0, 0],
      });
      renderTask = task;
      try {
        await task.promise;
      } catch {
        // A cancelled render is the normal path on resize, not a failure.
      }
    })();

    return () => {
      cancelled = true;
      renderTask?.cancel();
    };
  }, [pdf, pageNumber, width]);

  useEffect(() => {
    if (!highlight) return;
    wrapperRef.current?.scrollIntoView({ behavior: "smooth", block: "center" });
  }, [highlight]);

  return (
    <div
      ref={wrapperRef}
      className="relative shadow-sm ring-1 ring-line"
      style={{ width, height: height || undefined }}
      data-page={pageNumber}
    >
      <canvas ref={canvasRef} className="block bg-white" />
      {located && scale > 0 &&
        located.rects.map((rect, index) => (
          <div
            key={`${located.nonce}:${index}`}
            className="citation-flash pointer-events-none absolute rounded-[2px] mix-blend-multiply"
            style={{
              left: rect.x0 * scale,
              top: rect.top * scale,
              width: Math.max(4, (rect.x1 - rect.x0) * scale),
              height: Math.max(4, (rect.bottom - rect.top) * scale),
              backgroundColor:
                "color-mix(in srgb, var(--highlight) 55%, transparent)",
              // Dashed when this is the surrounding block rather than the quote
              // itself, so a coarse highlight is not passed off as a precise
              // one. The caption below says which.
              outline: located.precise
                ? "1px solid var(--highlight-ring)"
                : "1px dashed var(--highlight-ring)",
            }}
          />
        ))}

      {located && !located.precise && scale > 0 && (
        <span
          className="pointer-events-none absolute rounded bg-refuse-soft px-1.5 py-0.5 text-[10px] font-medium text-refuse ring-1 ring-highlight-ring"
          style={{
            left: located.rects[0].x0 * scale,
            top: Math.max(0, located.rects[0].top * scale - 18),
          }}
        >
          {t.workspace.approximateRegion}
        </span>
      )}
      <span className="absolute -bottom-0.5 right-1 font-mono text-[10px] text-ink-faint">
        {pageNumber}
      </span>
    </div>
  );
}
