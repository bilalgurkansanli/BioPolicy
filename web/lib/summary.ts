import type { Locale } from "./i18n";
import type {
  PolicyProfile,
  ProfileEntry,
  ProfileField,
} from "./types";

/**
 * "Summarise the cover" answered from the schema instead of from a model.
 *
 * ## Why this is not a model call, again
 *
 * `suggest.ts` makes this argument for suggested questions; it is stronger
 * here. Asked to summarise a policy, a model writes a paragraph — and a
 * paragraph is the wrong shape for the question. Someone asking what a policy
 * covers wants the coverage list with the amounts beside it, in an order they
 * can scan, with the page each figure came from. That is a table, and the
 * system already has one: typed extraction read the whole document into a fixed
 * schema and every row carries a citation that was checked against the chunk it
 * came from.
 *
 * So a summary here is a *view* over data that already exists. No prompt, no
 * call, no latency, no new way to be wrong — and, unlike a generated summary,
 * nothing in it can be true of insurance policies in general but false of this
 * one, because there is nowhere for such a sentence to enter.
 *
 * The measured difference on the AXA policy: the model's prose summary cost
 * $0.03, took 29 seconds, and cited 6 clauses. This costs nothing, renders
 * immediately, and every line it shows is cited.
 *
 * ## What it deliberately does not do
 *
 * It does not summarise in the sense of *condensing*. Nothing is paraphrased,
 * ranked by importance, or left out for brevity — the sections are fixed, and
 * within a section every extracted row is shown. A summary that decides which
 * of your exclusions matter is making a judgement this product does not make.
 */

export type SummaryKind = "cover" | "exclusions" | "terms";

export type SummarySection = {
  field: ProfileField;
  entries: ProfileEntry[];
};

export type Summary = {
  kind: SummaryKind;
  sections: SummarySection[];
  /**
   * Schema slots this summary covers that the document turned out to be silent
   * on. Carried separately from `sections` because an empty slot is a finding,
   * not a gap in the rendering — it is the half a chatbot cannot produce.
   *
   * Only ever populated when the whole document was read; see `summarise`.
   */
  absent: ProfileField[];
};

/**
 * Which slots each summary answers from.
 *
 * `cover` leads with the sub-limits rather than the perils: a reader asking
 * what a policy covers is nearly always asking for the amounts, and the perils
 * list without figures beside it is the part they can already guess.
 */
const SECTIONS: Record<SummaryKind, ProfileField[]> = {
  cover: ["sub_limit", "covered_peril"],
  exclusions: ["exclusion", "deductible"],
  terms: [
    "insured",
    "policy_period",
    "territorial_scope",
    "waiting_period",
    "notification_deadline",
  ],
};

export function summarise(
  profile: PolicyProfile | null,
  kind: SummaryKind,
): Summary | null {
  if (!profile) return null;

  const fields = SECTIONS[kind];
  const sections = fields
    .map((field) => ({
      field,
      entries: profile.entries.filter((entry) => entry.field === field),
    }))
    .filter((section) => section.entries.length > 0);

  if (sections.length === 0) return null;

  // The same rule `PolicyProfile` renders under: a slot nobody read looks
  // identical to a slot the document is silent on, so "not in this document" is
  // only claimed when the whole document was read.
  const complete =
    profile.chunks_seen >= profile.chunks_total && profile.batches_failed === 0;

  return {
    kind,
    sections,
    absent: complete ? profile.absent.filter((f) => fields.includes(f)) : [],
  };
}

/**
 * Does this look like a request for a summary, and of what?
 *
 * ## Why a word list and not a classifier
 *
 * Two reasons, and the second is the real one. A model call to route a question
 * adds latency and cost to *every* question in order to change the handling of
 * a few. And the cost of being wrong is asymmetric in a way that decides the
 * design: a missed summary request falls through to the ordinary answering
 * path, which answers it — the user gets prose instead of a table. A false
 * positive replaces a real question's answer with a table that does not address
 * it.
 *
 * So this is built to under-fire. It requires a summary word *and* refuses
 * anything carrying an interrogative that points at a specific fact ("ne kadar",
 * "kaç", "how much"), because "deprem teminatı ne kadar, özetle" is a question
 * about one figure, not a request for the schedule.
 */
export function summaryIntent(
  text: string,
  locale: Locale,
): SummaryKind | null {
  const lowered = text.toLocaleLowerCase(locale === "tr" ? "tr-TR" : "en-US");

  if (!SUMMARY_WORDS.some((word) => lowered.includes(word))) return null;
  if (SPECIFIC_WORDS.some((word) => lowered.includes(word))) return null;

  // Order matters: "istisnaları özetle" is about exclusions even though it also
  // matches nothing in the cover list. Cover is the fallback because it is what
  // an unqualified "summarise this policy" means to a reader.
  if (EXCLUSION_WORDS.some((word) => lowered.includes(word))) return "exclusions";
  if (TERM_WORDS.some((word) => lowered.includes(word))) return "terms";
  return "cover";
}

// Turkish is agglutinative, so these are stems rather than words: `özet`
// catches özeti, özetle, özetler, özetini. That is also why they are matched
// with `includes` rather than on word boundaries — `\bözet\b` would miss every
// inflected form, which is most of them.
const SUMMARY_WORDS = [
  "özet",
  "özetle",
  "summar", // summary, summarise, summarize
  "overview",
  "genel bakış",
  "listele",
  "list all",
  "hepsini",
  "tümünü",
  "neler var",
  "what does it cover",
  "what is covered",
  "nelerdir",
];

/**
 * A question about one figure, however it is phrased. Present, this is not a
 * summary request even if the word "özet" appears next to it.
 */
const SPECIFIC_WORDS = [
  "ne kadar",
  "kaç ",
  "kaçtır",
  "how much",
  "how many",
  "how long",
  "var mı",
  "is there",
  "does it cover ",
];

const EXCLUSION_WORDS = [
  "istisna",
  "kapsam dışı",
  "teminat dışı",
  "hariç",
  "muafiyet",
  "exclusion",
  "excluded",
  "not covered",
  "deductible",
];

const TERM_WORDS = [
  "süre",
  "tarih",
  "vade",
  "sigortalı kim",
  "taraflar",
  "coğrafi",
  "nerede geçerli",
  "period",
  "term",
  "dates",
  "who is insured",
  "where does",
];
