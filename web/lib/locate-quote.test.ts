/**
 * Locating a cited quote on a page.
 *
 * These exist because the first working version looked right and was not: it
 * highlighted the correct table row *and* a second, unrelated row underneath
 * it. Index arithmetic that maps a normalised string back onto the runs it came
 * from is not something to verify by looking at a screenshot.
 *
 * Coordinates below are PDF points with a bottom-left origin, because that is
 * what `getTextContent` reports; the function returns top-left, which is what
 * every stored box in this project uses.
 */

import { describe, expect, it } from "vitest";

import {
  locateQuote,
  locateQuoteInLines,
  segments,
  type Rect,
  type TextItem,
} from "./locate-quote";

const PAGE_HEIGHT = 842;

/** One text run, positioned by its baseline like pdf.js reports it. */
function run(text: string, x: number, baseline: number, width: number): TextItem {
  return {
    str: text,
    transform: [11, 0, 0, 11, x, baseline],
    width,
    height: 11,
  };
}

/** The row from the sample policy that started this: label, then value. */
const TABLE_ROW: TextItem[] = [
  run("Poliçe No", 72, 700, 45),
  run("KNT-2026-004417", 200, 700, 77),
  run("Sigorta Süresi", 72, 683, 68),
  run("01.03.2026 – 01.03.2027", 200, 683, 107),
  run("Risk Adresi", 72, 666, 54),
  run("Örnek Mahallesi, Deneme Sokak", 200, 666, 155),
];

describe("segments", () => {
  it("splits a Markdown table row on its pipes", () => {
    // The pipes are how the row reached the model. They are nowhere in the PDF,
    // which is why the quote cannot be searched for as one string.
    expect(segments("Sigorta Süresi | 01.03.2026 – 01.03.2027")).toEqual([
      "sigorta süresi",
      "01.03.2026 – 01.03.2027",
    ]);
  });

  it("drops fragments too short to identify anything", () => {
    expect(segments("Deprem | %2 | x")).toEqual(["deprem"]);
  });
});

describe("locateQuote", () => {
  it("highlights only the row that was cited", () => {
    const rects = locateQuote(
      TABLE_ROW,
      PAGE_HEIGHT,
      "Sigorta Süresi | 01.03.2026 – 01.03.2027",
    );

    expect(rects).not.toBeNull();
    // One line, not two: the label and the value share a baseline and are
    // merged. A second rectangle here means a neighbouring row was matched,
    // which is the bug these tests were written for.
    expect(rects).toHaveLength(1);

    // Tolerances cover the padding the rectangles carry so glyphs are not
    // clipped at their edges; the geometry underneath is exact.
    const [rect] = rects!;
    expect(rect.x0).toBeCloseTo(72, -1);
    expect(rect.x1).toBeCloseTo(307, -1);
    // Baseline 683 on a page 842 tall, minus the glyph height.
    expect(rect.top).toBeCloseTo(842 - 683 - 11, -1);
  });

  it("does not reach into the rows above or below", () => {
    const rects = locateQuote(
      TABLE_ROW,
      PAGE_HEIGHT,
      "Sigorta Süresi | 01.03.2026 – 01.03.2027",
    )!;
    const covered = rects.map((r) => ({ top: r.top, bottom: r.bottom }));

    const rowAbove = 842 - 700; // "Poliçe No"
    const rowBelow = 842 - 666; // "Risk Adresi"
    for (const { top, bottom } of covered) {
      expect(top).toBeGreaterThan(rowAbove);
      expect(bottom).toBeLessThan(rowBelow);
    }
  });

  it("matches prose in one piece", () => {
    const items = [
      run("poliçede belirtilen sürenin son günü", 72, 500, 180),
      run("saat 12.00'de sona erer", 72, 483, 110),
    ];

    const rects = locateQuote(
      items,
      PAGE_HEIGHT,
      "poliçede belirtilen sürenin son günü saat 12.00'de sona erer",
    );

    // Two lines of one sentence: two rectangles, so the highlight follows the
    // text rather than boxing the whitespace between them.
    expect(rects).toHaveLength(2);
  });

  it("ignores the quotation marks the interface adds", () => {
    expect(locateQuote(TABLE_ROW, PAGE_HEIGHT, "“Risk Adresi”")).toHaveLength(1);
  });

  it("is insensitive to case, including Turkish", () => {
    expect(locateQuote(TABLE_ROW, PAGE_HEIGHT, "SIGORTA SÜRESİ")).not.toBeNull();
  });

  it("returns null when the quote is not on the page", () => {
    // The caller falls back to the chunk box. Returning an empty array instead
    // would render a highlight of nothing.
    expect(locateQuote(TABLE_ROW, PAGE_HEIGHT, "deprem muafiyeti")).toBeNull();
  });

  it("returns null for a page with no text layer", () => {
    // A scan. Every character is a pixel and there is nothing to search.
    expect(locateQuote([], PAGE_HEIGHT, "Sigorta Süresi")).toBeNull();
  });

  it("does not join two runs into a word that is in neither", () => {
    // Adjacent table cells must not read as "sigortasüresi" — a quote could
    // otherwise match across a cell boundary and highlight half of each.
    const cells = [run("Sigorta", 72, 683, 35), run("Süresi", 200, 683, 30)];
    expect(locateQuote(cells, PAGE_HEIGHT, "sigortasüresi")).toBeNull();
  });
});


/**
 * The OCR path.
 *
 * A scanned page has no text layer, so its geometry comes from the vision model
 * at ingestion: one box per visual line, each table cell its own line. The
 * numbers below are the real ones read off page 1 of the scanned sample.
 */
describe("locateQuoteInLines", () => {
  const line = (text: string, top: number, x0: number, x1: number) => ({
    text,
    bbox: { x0, top, x1, bottom: top + 9 } as Rect,
  });

  const COVERAGE_TABLE = [
    line("Ameliyat", 381.4, 75.1, 111.4),
    line("Limitsiz", 381.4, 268.0, 310.0),
    line("Yok", 381.4, 428.9, 446.8),
    line("Ayakta Tedavi (muayene)", 399.9, 75.1, 182.9),
    line("Yılda 8 kez", 399.9, 268.0, 320.0),
    line("%20", 399.9, 428.9, 446.8),
    line("Fizik Tedavi", 437.0, 75.1, 122.7),
    line("Yılda 20 seans", 437.0, 268.0, 335.0),
    line("%20", 437.0, 428.9, 446.8),
  ];

  it("merges the cells of one row and stops there", () => {
    const rects = locateQuoteInLines(
      COVERAGE_TABLE,
      "Ayakta Tedavi (muayene) | Yılda 8 kez | %20",
    );

    expect(rects).toHaveLength(1);
    const [rect] = rects!;
    expect(rect.x0).toBeCloseTo(75.1, 1);
    expect(rect.x1).toBeCloseTo(446.8, 1);

    // The rows above and below sit 18.5pt and 37pt away. Reaching either of
    // them is the whole failure mode: on a scan the alternative to a precise
    // box is the entire page, so a highlight that drifts one row is worse than
    // it looks — there is nothing else on screen to correct it against.
    expect(rect.top).toBeGreaterThan(381.4 + 9);
    expect(rect.bottom).toBeLessThan(437.0);
  });

  it("matches a cell on its own", () => {
    const rects = locateQuoteInLines(COVERAGE_TABLE, "Fizik Tedavi");
    expect(rects).toHaveLength(1);
    expect(rects![0].top).toBeCloseTo(437.0, 0);
  });

  it("returns null when a page has no stored geometry", () => {
    // Every document ingested before the OCR pass reported boxes. The caller
    // falls back to the chunk box, which is what those pages had all along.
    expect(locateQuoteInLines([], "Ayakta Tedavi")).toBeNull();
  });

  it("returns null when the quote is on another page", () => {
    expect(locateQuoteInLines(COVERAGE_TABLE, "Doğum teminatı")).toBeNull();
  });
});


/**
 * Pieces of one quote resolved against each other.
 *
 * This is the failure the anchoring exists for, and it was reported from the
 * running app: the label and limit of one coverage row highlighted correctly,
 * with the participation rate taken from the row above. `%20` occurs in every
 * row, so looked up on its own it lands on whichever comes first.
 *
 * Positions are the real ones from page 1 of the scanned sample.
 */
describe("resolving repeated fragments", () => {
  const cell = (text: string, top: number, x0: number, x1: number) => ({
    text,
    bbox: { x0, top, x1, bottom: top + 9 } as Rect,
  });

  const ROWS = [
    cell("Ameliyat", 381.4, 75.1, 111.4),
    cell("Limitsiz", 381.4, 315.1, 357.0),
    cell("Yok", 381.4, 428.9, 446.8),
    cell("Ayakta Tedavi (muayene)", 399.9, 75.1, 182.9),
    cell("Yılda 8 kez", 399.9, 314.5, 366.0),
    cell("%20", 399.9, 428.9, 446.8),
    cell("Ayakta Tedavi (tahlil ve görüntüleme)", 418.4, 75.1, 262.0),
    cell("12.000 TL", 418.4, 315.1, 366.0),
    cell("%20", 418.4, 428.9, 446.8),
    cell("Fizik Tedavi", 437.0, 75.1, 122.7),
    cell("Yılda 20 seans", 437.0, 315.1, 380.0),
    cell("%20", 437.0, 428.9, 446.8),
  ];

  it("takes the repeated fragment from the cited row, not the first row", () => {
    const rects = locateQuoteInLines(
      ROWS,
      "Ayakta Tedavi (tahlil ve görüntüleme) | 12.000 TL | %20",
    )!;

    expect(rects).toHaveLength(1);
    expect(rects[0].top).toBeCloseTo(418.4, 0);
    // The row above owns a %20 too. Reaching it is the reported bug.
    expect(rects[0].top).toBeGreaterThan(399.9 + 9);
  });

  it("still resolves when the cited row is the first one", () => {
    const rects = locateQuoteInLines(
      ROWS,
      "Ayakta Tedavi (muayene) | Yılda 8 kez | %20",
    )!;

    expect(rects).toHaveLength(1);
    expect(rects[0].top).toBeCloseTo(399.9, 0);
  });

  it("drops a fragment that only matches on someone else's line", () => {
    // OCR missed the rate on the cited row. Its nearest %20 belongs to a
    // neighbour, and no other fragment agrees with that line — so nothing is
    // drawn there. A highlight missing a cell beats one on the wrong clause.
    const missing = ROWS.filter(
      (line) => !(line.text === "%20" && line.bbox.top === 418.4),
    );

    const rects = locateQuoteInLines(
      missing,
      "Ayakta Tedavi (tahlil ve görüntüleme) | 12.000 TL | %20",
    )!;

    expect(rects).toHaveLength(1);
    expect(rects[0].top).toBeCloseTo(418.4, 0);
    expect(rects[0].x1).toBeLessThan(428.9); // the rate column is not touched
  });

  it("keeps a quote that genuinely spans two rows", () => {
    // Two fragments agreeing on the second line corroborate each other, so it
    // is kept even though it is not the anchor's line.
    const rects = locateQuoteInLines(
      ROWS,
      "Ayakta Tedavi (muayene) | Yılda 8 kez | Ayakta Tedavi (tahlil ve görüntüleme) | 12.000 TL",
    )!;

    expect(rects).toHaveLength(2);
    expect(rects.map((r) => Math.round(r.top))).toEqual([400, 418]);
  });

  it("refuses to place a lone fragment that occurs many times", () => {
    // "%20" alone identifies three rows equally well. There is nothing to
    // resolve it against, so the caller gets the coarse box instead of a
    // one-in-three guess.
    expect(locateQuoteInLines(ROWS, "%20")).toBeNull();
  });

  it("places a lone fragment that occurs once", () => {
    expect(locateQuoteInLines(ROWS, "Fizik Tedavi")).toHaveLength(1);
  });
});
