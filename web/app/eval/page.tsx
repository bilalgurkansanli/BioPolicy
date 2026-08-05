import { readFile } from "node:fs/promises";
import path from "node:path";

import { EvaluationReport } from "@/components/EvaluationReport";

/**
 * The evaluation report is read from the repository at build time and rendered
 * verbatim.
 *
 * Not re-summarised here on purpose: a summary of your own results, written by
 * hand, is where selective quotation creeps in. The file this page renders is
 * the same file `python -m eval.run_eval` writes, including the parts that do
 * not flatter the system.
 */
async function readReport(): Promise<string | null> {
  try {
    return await readFile(
      path.join(process.cwd(), "..", "eval", "report.md"),
      "utf8",
    );
  } catch {
    // The Next.js project can be built without the Python side present. A
    // missing report is a build-context fact, not an error worth failing on.
    return null;
  }
}

export default async function EvaluationPage() {
  const markdown = await readReport();
  return <EvaluationReport markdown={markdown} />;
}
