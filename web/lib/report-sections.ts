/**
 * A generated report, cut along its own headings.
 *
 * The reports are published whole and rendered as written, which on a page
 * meant a single disclosure holding twelve hundred words under nine headings —
 * and two of those disclosures, carrying the same nine. Opening either gave the
 * same wall, and nothing on screen said which report you were now inside.
 *
 * Splitting on `## ` turns the wall into a list of names. Nothing is dropped
 * and no sentence is rewritten; the reader simply gets to choose which part
 * they are reading, which is the difference between a document and a dump.
 *
 * The split is on the heading marker rather than on any particular heading, so
 * it works the same in both languages and survives a section being added,
 * renamed or reordered in `eval/copy.py`.
 */

export type ReportSection = {
  /** The heading text, without its `##`. */
  heading: string;
  /** Everything under it, up to the next `##`, including any `###` inside. */
  body: string;
};

export function splitSections(markdown: string): ReportSection[] {
  const sections: ReportSection[] = [];

  // Everything before the first `##` is the report's own title and the
  // blockquote under it. Both say what this page has already said above the
  // fold, so they are left out here rather than repeated twice per report.
  for (const part of markdown.split(/^## /m).slice(1)) {
    const newline = part.indexOf("\n");
    const heading = (newline === -1 ? part : part.slice(0, newline)).trim();
    const body = newline === -1 ? "" : part.slice(newline + 1).trim();
    if (heading) sections.push({ heading, body });
  }

  return sections;
}
