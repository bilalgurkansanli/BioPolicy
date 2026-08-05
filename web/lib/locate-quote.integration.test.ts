/**
 * The locator against a real PDF, with pdf.js producing the text runs.
 *
 * The unit tests model what `getTextContent()` returns. This one stops
 * modelling it. A real page splits text into runs on its own schedule — a whole
 * row, a single word, sometimes a stray space — and the first version of this
 * code passed every unit test while highlighting an extra row on the actual
 * document.
 *
 * Skips rather than fails when the sample is absent: the fixtures are generated
 * by `python -m eval.generate_samples`, and a Node-only checkout may not have
 * run it.
 */

import { readFileSync } from "node:fs";
import path from "node:path";

import { describe, expect, it } from "vitest";

import { locateQuote, type Rect, type TextItem } from "./locate-quote";

const SAMPLE = path.join(
  __dirname,
  "..",
  "..",
  "eval",
  "golden",
  "samples",
  "konut-sigortasi-tr.pdf",
);

async function pageText(
  pageNumber: number,
): Promise<{ items: TextItem[]; height: number } | null> {
  let data: Buffer;
  try {
    data = readFileSync(SAMPLE);
  } catch {
    return null;
  }

  // The legacy build is the one that runs outside a browser.
  const pdfjs = await import("pdfjs-dist/legacy/build/pdf.mjs");
  const pdf = await pdfjs.getDocument({
    data: new Uint8Array(data),
    // No worker in a test process; the main thread is fine for four pages.
    disableWorker: true,
  } as Parameters<typeof pdfjs.getDocument>[0]).promise;

  const page = await pdf.getPage(pageNumber);
  const content = await page.getTextContent();
  return {
    items: content.items as TextItem[],
    height: page.getViewport({ scale: 1 }).height,
  };
}

function covers(rects: Rect[], point: { x: number; y: number }): boolean {
  return rects.some(
    (rect) =>
      point.x >= rect.x0 &&
      point.x <= rect.x1 &&
      point.y >= rect.top &&
      point.y <= rect.bottom,
  );
}

describe("locateQuote on the sample policy", () => {
  it("highlights the insurance-period row and nothing else", async () => {
    const page = await pageText(1);
    if (!page) return; // fixtures not generated

    const rects = locateQuote(
      page.items,
      page.height,
      "Sigorta Süresi | 01.03.2026 – 01.03.2027",
    );

    expect(rects).not.toBeNull();

    // The row sits at top≈158 in the parsed document; the rows on either side
    // are 17pt away. Covering either of them is the failure this test exists
    // for — the answer looked right while the highlight pointed at the wrong
    // clause.
    expect(covers(rects!, { x: 100, y: 162 })).toBe(true); // "Sigorta Süresi"
    expect(covers(rects!, { x: 260, y: 162 })).toBe(true); // the dates
    expect(covers(rects!, { x: 100, y: 128 })).toBe(false); // "Poliçe No" above
    expect(covers(rects!, { x: 100, y: 179 })).toBe(false); // "Risk Adresi" below

    // One line cited, one rectangle drawn.
    expect(rects).toHaveLength(1);
  });

  it("finds a prose clause on a later page", async () => {
    const page = await pageText(4);
    if (!page) return;

    const rects = locateQuote(
      page.items,
      page.height,
      "poliçede belirtilen sürenin son günü saat 12.00'de sona erer",
    );

    expect(rects).not.toBeNull();
    // Prose wraps, so more than one line is expected; what must not happen is
    // the highlight spreading across the whole article.
    expect(rects!.length).toBeLessThanOrEqual(3);
  });
});
