"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { PDFDocumentLoadingTask, PDFDocumentProxy } from "pdfjs-dist";

import { useLocale } from "@/components/LocaleProvider";
import type { BBox } from "@/lib/types";

export type Highlight = {
  /** 1-based, matching the citation and the database. */
  page: number;
  bbox: BBox;
  /** Changes on every click so re-clicking the same citation re-flashes it. */
  nonce: number;
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
  url,
  highlight,
}: {
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
}: {
  pdf: PDFDocumentProxy;
  pageNumber: number;
  width: number;
  highlight: Highlight | null;
}) {
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
      {highlight && scale > 0 && (
        <div
          key={highlight.nonce}
          className="citation-flash pointer-events-none absolute rounded-[2px] mix-blend-multiply"
          style={{
            left: highlight.bbox.x0 * scale,
            top: highlight.bbox.top * scale,
            width: Math.max(4, (highlight.bbox.x1 - highlight.bbox.x0) * scale),
            height: Math.max(
              4,
              (highlight.bbox.bottom - highlight.bbox.top) * scale,
            ),
            backgroundColor: "color-mix(in srgb, var(--highlight) 55%, transparent)",
            outline: "1px solid var(--highlight-ring)",
          }}
        />
      )}
      <span className="absolute -bottom-0.5 right-1 font-mono text-[10px] text-ink-faint">
        {pageNumber}
      </span>
    </div>
  );
}
