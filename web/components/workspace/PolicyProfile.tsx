"use client";

import { useCallback, useEffect, useState } from "react";

import { useLocale } from "@/components/LocaleProvider";
import { buildPolicyProfile, fetchPolicyProfile } from "@/lib/api";
import type { Citation, PolicyProfile as Profile, ProfileField } from "@/lib/types";

/**
 * The document read into a fixed schema, above the conversation.
 *
 * This is the part of the product that does not require the reader to know what
 * to ask. A chat box is a good interface for a question you already have and a
 * bad one for a policy you have never read — you cannot ask about the waiting
 * period you do not know exists.
 *
 * Two rules shape what is on screen, and both are inherited from the answering
 * path rather than invented here:
 *
 * **Nothing is shown that is not bound.** Every row came back from the API with
 * a citation whose quote was checked against the chunk it names. Rows that
 * failed are gone before this component sees them, and their count is reported
 * rather than quietly dropped.
 *
 * **An empty slot is only called empty when the whole document was read.** The
 * "not in this document" list is the most valuable thing here and the easiest
 * to get wrong: a slot nobody looked at renders identically to a slot the
 * document is silent on, unless the interface refuses to conflate them. When
 * coverage is partial the list is withheld and the reason is stated.
 */

const FIELD_ORDER: ProfileField[] = [
  "insured",
  "policy_period",
  "territorial_scope",
  "covered_peril",
  "sub_limit",
  "deductible",
  "waiting_period",
  "notification_deadline",
  "exclusion",
];

/** Fields with exactly one value, rendered without a label column. */
const SINGULAR: ReadonlySet<ProfileField> = new Set([
  "insured",
  "policy_period",
  "territorial_scope",
]);

export function PolicyProfile({
  documentId,
  signedIn,
  onCite,
  activeCitation,
  onProfile,
}: {
  documentId: string;
  signedIn: boolean;
  onCite: (citation: Citation, key: string) => void;
  activeCitation: string | null;
  /**
   * Handed up so the workspace can suggest questions from it.
   *
   * The profile is fetched here and needed there, and the alternative — a
   * second fetch in the parent — would ask the API for the same thing twice
   * and let the two copies disagree about whether extraction had run.
   */
  onProfile?: (profile: Profile | null) => void;
}) {
  const { t } = useLocale();
  const copy = t.workspace.profile;

  const [profile, setProfile] = useState<Profile | null>(null);
  const [loading, setLoading] = useState(true);
  const [building, setBuilding] = useState(false);
  const [failed, setFailed] = useState(false);
  const [open, setOpen] = useState(true);

  // No state is reset here on a document change, and that is deliberate: the
  // parent mounts this with `key={document.id}`, so switching documents builds
  // a fresh component with fresh initial state. Clearing it by hand inside the
  // effect would be a synchronous setState in an effect body — a cascading
  // render, and the thing `react-hooks/set-state-in-effect` exists to catch.
  useEffect(() => {
    const controller = new AbortController();

    fetchPolicyProfile(documentId, controller.signal)
      .then((result) => {
        setProfile(result);
        onProfile?.(result);
      })
      .catch(() => {
        // A profile that cannot be read is not an error worth interrupting the
        // workspace for — the document and the chat still work. It renders as
        // "not built yet", which is recoverable by the button.
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });

    return () => controller.abort();
  }, [documentId, onProfile]);

  const build = useCallback(async () => {
    setBuilding(true);
    setFailed(false);
    try {
      const built = await buildPolicyProfile(documentId);
      setProfile(built);
      onProfile?.(built);
    } catch {
      setFailed(true);
    } finally {
      setBuilding(false);
    }
  }, [documentId, onProfile]);

  // Nothing at all until the first read settles, so the card does not flash a
  // call-to-action at somebody whose profile is already cached.
  if (loading) return null;

  if (!profile) {
    return (
      <section className="rounded-xl border border-line bg-surface-sunken p-3.5">
        <Header title={copy.title} lede={copy.lede} />
        <div className="mt-3 flex flex-wrap items-center gap-x-3 gap-y-2">
          <button
            type="button"
            onClick={() => void build()}
            disabled={!signedIn || building}
            className="cursor-pointer rounded-full border border-accent/25 bg-accent-soft px-3.5 py-1.5 text-sm font-medium text-accent transition-colors hover:border-accent/45 disabled:cursor-default disabled:opacity-50"
          >
            {building ? copy.building : copy.build}
          </button>
          <p className="text-xs text-ink-faint">
            {signedIn ? copy.buildNote : copy.signInToBuild}
          </p>
        </div>
        {failed && <p className="mt-2 text-xs text-refuse">{copy.buildFailed}</p>}
      </section>
    );
  }

  const complete =
    profile.chunks_seen >= profile.chunks_total && profile.batches_failed === 0;
  const groups = FIELD_ORDER.map((field) => ({
    field,
    entries: profile.entries.filter((entry) => entry.field === field),
  })).filter((group) => group.entries.length > 0);

  return (
    <section className="rounded-xl border border-line bg-surface-sunken p-3.5">
      <div className="flex items-start justify-between gap-3">
        <Header title={copy.title} lede={copy.lede} />
        <button
          type="button"
          onClick={() => setOpen((current) => !current)}
          aria-expanded={open}
          className="shrink-0 cursor-pointer rounded-full border border-line px-2.5 py-1 text-[11px] text-ink-muted transition-colors hover:border-line-strong hover:text-ink"
        >
          {open ? copy.hide : copy.show}
        </button>
      </div>

      {open && (
        <div className="mt-3 space-y-3">
          {profile.chunks_seen < profile.chunks_total && (
            <Notice
              title={copy.partialTitle}
              body={copy.partialBody
                .replace("{seen}", String(profile.chunks_seen))
                .replace("{total}", String(profile.chunks_total))}
            />
          )}
          {profile.batches_failed > 0 && (
            <Notice
              title={copy.failedTitle}
              body={copy.failedBody.replace(
                "{count}",
                String(profile.batches_failed),
              )}
            />
          )}

          {groups.length === 0 ? (
            <div>
              <h4 className="text-sm font-medium text-ink">{copy.emptyTitle}</h4>
              <p className="mt-1 text-xs leading-5 text-ink-muted">
                {copy.emptyBody}
              </p>
            </div>
          ) : (
            groups.map((group) => (
              <div key={group.field}>
                <h4 className="text-xs font-medium uppercase tracking-wide text-ink-faint">
                  {copy.fields[group.field]}
                </h4>
                <ul className="mt-1.5 space-y-1">
                  {/* The index is in the key because field + chunk + value is
                      not unique and a policy makes that obvious: seven cover
                      rows on the sample all read "Teminat kapsamında" and all
                      cite C3, differing only in their label. React logged a
                      duplicate-key error for each, and — the visible half —
                      `activeCitation` is this same string, so clicking one of
                      the seven lit up all seven at once.

                      Position is stable here: `entries` is filtered from a
                      profile that is fetched once and never reordered. */}
                  {group.entries.map((entry, index) => {
                    const key = `profile:${entry.field}:${entry.citation.context_id}:${index}`;
                    return (
                      <li key={key}>
                        <Row
                          label={SINGULAR.has(entry.field) ? "" : entry.label}
                          value={entry.value}
                          citation={entry.citation}
                          active={activeCitation === key}
                          onSelect={() => onCite(entry.citation, key)}
                        />
                      </li>
                    );
                  })}
                </ul>
              </div>
            ))
          )}

          {/* Withheld unless the whole document was read. An "absent" list built
              from a partial sweep is a confident statement about pages nobody
              opened, which is the failure this feature is supposed to prevent. */}
          {complete && profile.absent.length > 0 && (
            <div className="border-t border-line pt-3">
              <h4 className="text-xs font-medium uppercase tracking-wide text-refuse">
                {copy.absentTitle}
              </h4>
              <p className="mt-1 flex flex-wrap gap-1.5">
                {profile.absent.map((field) => (
                  <span
                    key={field}
                    className="rounded-full border border-refuse/25 bg-refuse-soft px-2 py-0.5 text-[11px] text-refuse"
                  >
                    {copy.fields[field]}
                  </span>
                ))}
              </p>
              <p className="mt-1.5 text-xs leading-5 text-ink-muted">
                {copy.absentNote}
              </p>
            </div>
          )}

          {profile.dropped > 0 && (
            <p className="text-xs text-refuse">
              {copy.dropped.replace("{count}", String(profile.dropped))}
            </p>
          )}
        </div>
      )}
    </section>
  );
}

function Header({ title, lede }: { title: string; lede: string }) {
  return (
    <div>
      <h3 className="text-sm font-semibold text-ink">{title}</h3>
      <p className="mt-1 max-w-lg text-xs leading-5 text-ink-muted">{lede}</p>
    </div>
  );
}

function Notice({ title, body }: { title: string; body: string }) {
  return (
    <div className="rounded-lg border border-refuse/25 bg-refuse-soft px-2.5 py-2">
      <p className="text-xs font-medium text-refuse">{title}</p>
      <p className="mt-0.5 text-xs leading-5 text-ink-muted">{body}</p>
    </div>
  );
}

function Row({
  label,
  value,
  citation,
  active,
  onSelect,
}: {
  label: string;
  value: string;
  citation: Citation;
  active: boolean;
  onSelect: () => void;
}) {
  const { t } = useLocale();
  const locatable = citation.bbox !== null;

  return (
    <button
      type="button"
      onClick={onSelect}
      disabled={!locatable}
      className={`w-full rounded-lg border px-2.5 py-1.5 text-left transition-colors ${
        active
          ? "border-highlight-ring bg-accent-soft"
          : "border-line bg-surface hover:border-line-strong"
      } ${locatable ? "cursor-pointer" : "cursor-default"}`}
    >
      <span className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5">
        {label && (
          <span className="text-xs font-medium text-ink-muted">{label}</span>
        )}
        <span className="text-sm text-ink">{value}</span>
        <span className="ml-auto shrink-0 font-mono text-[11px] text-ink-faint">
          {t.workspace.page}
          {citation.page_end > citation.page
            ? `${citation.page}–${citation.page_end}`
            : citation.page}
        </span>
      </span>
      {/* The quote is the whole claim. Clamped rather than hidden behind a
          tooltip: evidence you have to hover to find is evidence most readers
          never see. */}
      <span className="mt-0.5 line-clamp-2 block text-[11px] leading-4 text-ink-faint">
        “{citation.quote}”
      </span>
    </button>
  );
}
