/**
 * Finding a cited quote's actual position on a rendered page.
 *
 * Citations carry the bounding box of the *chunk* they came from, because that
 * is what ingestion stored. For a chunk that happens to be a coverage table,
 * that box is the whole table: the chip says "Sigorta Süresi | 01.03.2026 –
 * 01.03.2027" and the highlight covers forty lines around it. The citation is
 * correct and the highlight is useless, which is the worst combination — it
 * looks like the system found the clause and cannot point at it.
 *
 * So the quote is located in the page's own text layer at click time. Nothing
 * is re-ingested and nothing is stored; the geometry comes from the PDF the
 * user is looking at.
 *
 * ## Why the quote is searched in pieces
 *
 * A table row reaches the model as Markdown — `| Sigorta Süresi | 01.03.2026 –
 * 01.03.2027 |` — and the model quotes it that way. Those pipes exist nowhere
 * in the PDF: the row is two independent text runs with a gap between them.
 * Searching for the quote as one string finds nothing on exactly the documents
 * where precise highlighting matters most, so the quote is split on its
 * separators and each piece located on its own.
 *
 * ## What this does not handle
 *
 * Rotated pages, and pages with no text layer at all — a scan, where the
 * characters are pixels and `getTextContent` returns nothing. Both fall back to
 * the chunk box, which is the behaviour that existed before this file.
 */

export type Rect = { x0: number; top: number; x1: number; bottom: number };

/** The shape of a `getTextContent()` item, narrowed to what is used here. */
export type TextItem = {
  str: string;
  /** `[a, b, c, d, e, f]` — text space to PDF space, at scale 1. */
  transform: number[];
  width: number;
  height: number;
};

/** Below this, a fragment matches too much to be worth highlighting. */
const MIN_SEGMENT_CHARS = 3;

/** Glyphs sit slightly outside their reported box; a little air avoids clipping. */
const PADDING = 1.5;

/** Two runs whose baselines differ by less than this are on the same line. */
const LINE_TOLERANCE = 3;

function isSpace(character: string): boolean {
  return /[\s ]/.test(character);
}

function isIgnorable(character: string): boolean {
  // Quotation marks are added by the interface and by the model, and are not in
  // the document. Matching them would fail on every quoted span.
  return "“”\"'«»".includes(character);
}

/**
 * Case folding that survives Turkish.
 *
 * `"İ".toLowerCase()` is `"i"` followed by a combining dot above — two code
 * points, not one — so `"SİGORTA"` folds to something that never equals
 * `"sigorta"`. The dotless `"ı"` fails the same comparison from the other side:
 * `"SIGORTALI"` and `"Sigortalı"` are the same word and disagree on their last
 * letter once lowercased.
 *
 * Both are collapsed onto plain `i`. Every other letter is left alone, so `ü`,
 * `ş`, `ğ`, `ç` and `ö` still have to match exactly — folding those away would
 * buy nothing and start matching words the document does not contain.
 *
 * One character in, one character out, because the index map back to the page
 * depends on it.
 */
const FOLDED: Record<string, string> = { "İ": "i", I: "i", "ı": "i" };

function fold(character: string): string {
  const mapped = FOLDED[character];
  if (mapped) return mapped;
  const lowered = character.toLowerCase();
  return lowered.length === 1 ? lowered : character;
}

/**
 * A searchable form of the page text, plus the map back to where it came from.
 *
 * Normalisation has to happen without losing position, so every kept character
 * records the index it occupied in the concatenated original.
 */
type Haystack = {
  text: string;
  /** `origin[i]` is the index in `raw` of normalised character `i`. */
  origin: number[];
  /** `[start, end)` in `raw` for each item, in order. */
  spans: { start: number; end: number; item: TextItem }[];
};

export function buildHaystack(items: TextItem[]): Haystack {
  let raw = "";
  const spans: Haystack["spans"] = [];

  for (const item of items) {
    if (!item.str) continue;
    const start = raw.length;
    raw += item.str;
    spans.push({ start, end: raw.length, item });
    // A separator between runs, so two adjacent cells cannot accidentally join
    // into a word that appears in neither.
    raw += " ";
  }

  let text = "";
  const origin: number[] = [];
  for (let index = 0; index < raw.length; index += 1) {
    const character = raw[index];
    if (isIgnorable(character)) continue;
    if (isSpace(character)) {
      if (text.length > 0 && !text.endsWith(" ")) {
        text += " ";
        origin.push(index);
      }
      continue;
    }
    text += fold(character);
    origin.push(index);
  }

  return { text, origin, spans };
}

function normalizeNeedle(value: string): string {
  let out = "";
  for (const character of value) {
    if (isIgnorable(character)) continue;
    if (isSpace(character)) {
      if (out.length > 0 && !out.endsWith(" ")) out += " ";
      continue;
    }
    out += fold(character);
  }
  return out.trim();
}

/**
 * Split a quote into the fragments worth searching for separately.
 *
 * Pipes and newlines are Markdown table structure, not document text. Anything
 * that survives as its own fragment is a run the PDF really contains.
 */
export function segments(quote: string): string[] {
  return quote
    .split(/[|\n]+/)
    .map(normalizeNeedle)
    .filter((piece) => piece.length >= MIN_SEGMENT_CHARS);
}

function itemsInRange(
  haystack: Haystack,
  from: number,
  to: number,
): TextItem[] {
  return haystack.spans
    .filter((span) => span.start < to && span.end > from)
    .map((span) => span.item);
}

function rectFor(item: TextItem, pageHeight: number): Rect {
  const [, b, , d, x, baseline] = item.transform;
  // `d` is the vertical scale for upright text; `b` covers the skewed case.
  const height = item.height || Math.hypot(b, d) || 0;
  // PDF space has its origin bottom-left and measures y upward; every stored
  // box in this project is top-left, matching pdfplumber and the viewer.
  return {
    x0: x - PADDING,
    x1: x + item.width + PADDING,
    top: pageHeight - baseline - height - PADDING,
    bottom: pageHeight - baseline + height * 0.25 + PADDING,
  };
}

/**
 * Merge runs that sit on the same line into one rectangle each.
 *
 * A quote spanning three lines should read as three highlighted lines, not as
 * one box swallowing the margin between them.
 */
function mergeByLine(rects: Rect[]): Rect[] {
  const lines: Rect[] = [];
  for (const rect of [...rects].sort((a, b) => a.top - b.top || a.x0 - b.x0)) {
    const line = lines.find(
      (candidate) => Math.abs(candidate.top - rect.top) <= LINE_TOLERANCE,
    );
    if (line) {
      line.x0 = Math.min(line.x0, rect.x0);
      line.x1 = Math.max(line.x1, rect.x1);
      line.top = Math.min(line.top, rect.top);
      line.bottom = Math.max(line.bottom, rect.bottom);
    } else {
      lines.push({ ...rect });
    }
  }
  return lines;
}

/**
 * Where `quote` sits on the page, or `null` if it could not be found.
 *
 * `null` is a real answer and the caller is expected to fall back to the chunk
 * box rather than showing nothing: a coarse highlight is worth more than none.
 */
export function locateQuote(
  items: TextItem[],
  pageHeight: number,
  quote: string,
): Rect[] | null {
  if (!quote.trim() || items.length === 0) return null;

  const haystack = buildHaystack(items);
  if (!haystack.text) return null;

  const matched: TextItem[] = [];

  // The whole quote first. When it is prose it appears verbatim, and matching
  // it in one piece keeps the highlight to exactly the sentence cited.
  const whole = normalizeNeedle(quote);
  const wholeAt = whole ? haystack.text.indexOf(whole) : -1;
  if (wholeAt !== -1) {
    matched.push(
      ...itemsInRange(
        haystack,
        haystack.origin[wholeAt],
        haystack.origin[wholeAt + whole.length - 1] + 1,
      ),
    );
  } else {
    for (const segment of segments(quote)) {
      const at = haystack.text.indexOf(segment);
      if (at === -1) continue;
      matched.push(
        ...itemsInRange(
          haystack,
          haystack.origin[at],
          haystack.origin[at + segment.length - 1] + 1,
        ),
      );
    }
  }

  if (matched.length === 0) return null;
  return mergeByLine(matched.map((item) => rectFor(item, pageHeight)));
}
