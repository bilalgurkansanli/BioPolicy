"use client";

import { useLocale } from "@/components/LocaleProvider";
import type { RetrievalComplete } from "@/lib/types";

export type Stage = "retrieval" | "answering" | "verifying";

const ORDER: Stage[] = ["retrieval", "answering", "verifying"];

/**
 * What the user looks at during the wait.
 *
 * There is no token stream — citation binding and self-verification run after
 * generation and can withhold the answer, so nothing can be shown until they
 * have (ADR 010). These lines are the mitigation, and they are only worth
 * anything because each one is a real pipeline stage that really has completed.
 */
export function StageProgress({
  stage,
  retrieval,
}: {
  stage: Stage;
  retrieval: RetrievalComplete | null;
}) {
  const { t } = useLocale();
  const current = ORDER.indexOf(stage);

  return (
    <div className="rounded-xl border border-line bg-surface p-4">
      <ol className="space-y-2">
        {ORDER.map((name, index) => {
          const done = index < current;
          const active = index === current;
          return (
            <li
              key={name}
              className={`flex items-center gap-2.5 text-sm ${
                done
                  ? "text-ink-muted"
                  : active
                    ? "stage-active text-ink"
                    : "text-ink-faint/60"
              }`}
            >
              <span
                aria-hidden
                className={`size-1.5 shrink-0 rounded-full ${
                  done ? "bg-good" : active ? "bg-accent" : "bg-line-strong"
                }`}
              />
              {t.workspace.stages[name]}
              {name === "retrieval" && done && retrieval && (
                <span className="font-mono text-xs text-ink-faint">
                  {retrieval.count} {t.workspace.chunksFound}
                  {retrieval.rewritten ? ` · ${t.workspace.rewritten}` : ""}
                </span>
              )}
            </li>
          );
        })}
      </ol>
      <p className="mt-3 text-xs text-ink-faint">{t.workspace.stageNote}</p>
    </div>
  );
}
