"use client";

import { useState } from "react";

import { useLocale } from "@/components/LocaleProvider";
import type { InjectionFinding } from "@/lib/types";

/**
 * Tell the reader their document is talking to the machine.
 *
 * Someone who uploads a policy prepared by a broker, an employer or a landlord
 * has no way to know it contains text aimed at an AI system — the sentences are
 * often buried mid-clause, and a PDF reader shows them as ordinary body text.
 * Until this existed, the only symptom was that answers about their document
 * read a little strangely.
 *
 * Three decisions worth stating, because each one could plausibly have gone the
 * other way:
 *
 * - **It does not block anything.** The document is still answerable and the
 *   answering path is measured against exactly this material
 *   (`eval/report_injection.md`). Refusing the file would fail the user harder
 *   than the planted text does.
 * - **It shows the evidence.** The excerpt is quoted so the reader can find the
 *   sentence in their own PDF and judge it. A warning that cannot be checked is
 *   a warning that has to be taken on faith, which is the opposite of what this
 *   product is for.
 * - **It does not accuse anyone.** The wording says what was found, not what
 *   somebody intended. A regex does not know whether a broker pasted something
 *   careless or an attacker planted it.
 */
export function InjectionNotice({ findings }: { findings: InjectionFinding[] }) {
  const { t } = useLocale();
  const [open, setOpen] = useState(false);

  if (findings.length === 0) return null;

  return (
    <div className="mb-3 rounded-xl border border-refuse/40 bg-refuse-soft p-3">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h4 className="text-sm font-medium text-refuse">
            {t.workspace.injection.title}
          </h4>
          <p className="mt-1 text-xs leading-5 text-ink-muted">
            {t.workspace.injection.body.replace("{count}", String(findings.length))}
          </p>
        </div>
        <button
          type="button"
          onClick={() => setOpen((value) => !value)}
          className="shrink-0 rounded border border-line-strong bg-surface px-2 py-1 text-[11px] text-ink transition-colors hover:bg-surface-sunken"
        >
          {open ? t.workspace.injection.hide : t.workspace.injection.show}
        </button>
      </div>

      {open && (
        <ul className="mt-3 space-y-2">
          {findings.map((finding, index) => (
            <li
              key={`${finding.rule}-${index}`}
              className="rounded-lg border border-line bg-surface p-2.5"
            >
              <span className="text-[11px] font-medium uppercase tracking-wide text-ink-faint">
                {t.workspace.injection.rules[
                  finding.rule as keyof typeof t.workspace.injection.rules
                ] ?? finding.rule}
              </span>
              {/* The document's own words, marked as a quotation rather than
                  rendered as prose — this text was written to be obeyed, and it
                  should not read as though the interface is saying it. */}
              <p className="mt-1 border-l-2 border-line-strong pl-2 font-mono text-[11px] leading-5 text-ink-muted">
                {finding.excerpt}
              </p>
            </li>
          ))}
        </ul>
      )}

      <p className="mt-2.5 text-[11px] leading-5 text-ink-faint">
        {t.workspace.injection.footer}
      </p>
    </div>
  );
}
