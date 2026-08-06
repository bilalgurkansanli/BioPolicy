import { readFile } from "node:fs/promises";
import path from "node:path";

import { EvaluationReport } from "@/components/EvaluationReport";
import type { HistoryRow } from "@/components/MetricHistory";

/**
 * The evaluation report is read from the repository at build time and rendered
 * verbatim.
 *
 * Not re-summarised here on purpose: a summary of your own results, written by
 * hand, is where selective quotation creeps in. The files this page renders are
 * the same ones `python -m eval.run_eval` writes, including the parts that do
 * not flatter the system.
 */
async function readText(...segments: string[]): Promise<string | null> {
  try {
    return await readFile(path.join(process.cwd(), "..", ...segments), "utf8");
  } catch {
    // The Next.js project can be built without the Python side present. A
    // missing file is a build-context fact, not an error worth failing on.
    return null;
  }
}

async function readHistory(): Promise<HistoryRow[]> {
  const raw = await readText("eval", "results", "history.jsonl");
  if (!raw) return [];
  return raw
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean)
    .flatMap((line) => {
      try {
        return [JSON.parse(line) as HistoryRow];
      } catch {
        // Append-only files can end mid-write. One bad line must not blank the
        // whole chart.
        return [];
      }
    });
}

export default async function EvaluationPage() {
  // Both languages are read here rather than fetched on a locale change: they
  // are two files in the repository, the locale is a client-side preference,
  // and a report that arrives after the page has rendered is a report the
  // reader watches appear.
  const [markdown, markdownTr, hard, hardTr, history] = await Promise.all([
    readText("eval", "report.md"),
    readText("eval", "report.tr.md"),
    readText("eval", "report_hard.md"),
    readText("eval", "report_hard.tr.md"),
    readHistory(),
  ]);

  return (
    <EvaluationReport
      markdown={{ en: markdown, tr: markdownTr }}
      hard={{ en: hard, tr: hardTr }}
      history={history}
    />
  );
}
