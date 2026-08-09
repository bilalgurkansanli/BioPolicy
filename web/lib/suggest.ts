import type { Locale } from "./i18n";
import type { PolicyProfile, ProfileEntry, ProfileField } from "./types";

/**
 * Questions this document can actually answer, derived from what was read out
 * of it.
 *
 * ## Why this is not a model call
 *
 * The obvious implementation is to ask a model for five questions about the
 * document. It would cost a call per upload, it would need its own prompt and
 * its own evaluation, and — the part that decides it — the questions would be
 * *plausible* rather than *answerable*. A model asked for questions about an
 * insurance policy will produce questions about insurance policies, several of
 * which this one is silent on. Suggesting a question the document cannot answer
 * teaches a visitor that the product does not know its own contents.
 *
 * Typed extraction has already read the whole document into a schema, and every
 * entry in it carries a citation that was checked against the chunk it came
 * from. A question built from `deductible → "Deprem"` is a question this
 * document demonstrably answers, and the clause proving it is attached. So this
 * is a pure function over data the system already had: no call, no prompt, no
 * new failure mode.
 *
 * ## The tradeoff, stated plainly
 *
 * These read as templates, because they are. A model would write more natural
 * ones. The judgement is that a slightly stiff question that is guaranteed
 * answerable beats a fluent one that might not be — this is a product about not
 * asserting things the document does not support, and inventing questions it
 * cannot answer is the same failure wearing a friendlier face.
 */

export type Suggestion = {
  question: string;
  /** Which slot it came from. Used for ordering and for the key. */
  field: ProfileField;
  /** The item it is about — "Deprem", "Theft". Empty for singular fields. */
  label: string;
};

/**
 * Ordered by how much a reader is likely to care, not by how the extractor
 * happens to return them. Money and deadlines first; scope and definitions
 * after. `insured` is absent on purpose: "who is the insured" is answerable and
 * nobody wants to know.
 */
const FIELD_ORDER: ProfileField[] = [
  "sub_limit",
  "deductible",
  "waiting_period",
  "exclusion",
  "notification_deadline",
  "covered_peril",
  "territorial_scope",
  "policy_period",
];

type Template = (label: string) => string;

const TEMPLATES: Record<Locale, Partial<Record<ProfileField, Template>>> = {
  tr: {
    sub_limit: (label) => `${label} teminatının limiti ne kadar?`,
    deductible: (label) =>
      label ? `${label} hasarında muafiyet ne kadar?` : "Muafiyet ne kadar?",
    waiting_period: (label) =>
      label
        ? `${label} için bekleme süresi ne kadar?`
        : "Bekleme süresi ne kadar?",
    // Phrased as a question rather than a statement on purpose. The answer is
    // "no, and here is the clause" — which is the behaviour worth showing.
    exclusion: (label) => `${label} teminat kapsamında mı?`,
    notification_deadline: (label) =>
      label
        ? `${label} durumunda hasarı kaç gün içinde bildirmeliyim?`
        : "Hasarı kaç gün içinde bildirmem gerekiyor?",
    covered_peril: (label) => `${label} teminat altında mı?`,
    territorial_scope: () => "Poliçe hangi coğrafi alanda geçerli?",
    policy_period: () => "Poliçe hangi tarihler arasında geçerli?",
  },
  en: {
    sub_limit: (label) => `What is the limit for ${label}?`,
    deductible: (label) =>
      label ? `What is the deductible for ${label}?` : "What is the deductible?",
    waiting_period: (label) =>
      label
        ? `What is the waiting period for ${label}?`
        : "What is the waiting period?",
    exclusion: (label) => `Is ${label} covered?`,
    notification_deadline: (label) =>
      label
        ? `How long do I have to report a ${label} claim?`
        : "How long do I have to report a claim?",
    covered_peril: (label) => `Is ${label} covered?`,
    territorial_scope: () => "Where does this policy apply?",
    policy_period: () => "What dates does this policy run between?",
  },
};

/** A label long enough to be a clause rather than a name makes a bad question. */
const MAX_LABEL_CHARS = 60;

export const MAX_SUGGESTIONS = 4;

export function suggestQuestions(
  profile: PolicyProfile | null,
  locale: Locale,
  limit: number = MAX_SUGGESTIONS,
): Suggestion[] {
  if (!profile) return [];

  const templates = TEMPLATES[locale];
  const byField = new Map<ProfileField, ProfileEntry[]>();
  for (const entry of profile.entries) {
    const list = byField.get(entry.field);
    if (list) list.push(entry);
    else byField.set(entry.field, [entry]);
  }

  const suggestions: Suggestion[] = [];
  const seen = new Set<string>();
  const usedLabels = new Set<string>();
  const tag = (value: string) =>
    value.toLocaleLowerCase(locale === "tr" ? "tr" : "en");

  // One pass per rank, taking a single entry from each field before coming back
  // for a second. Four questions about four sub-limits is a worse list than one
  // about a limit, one about a deductible and one about an exclusion — it looks
  // like the document is only about one thing.
  //
  // Subjects are spread the same way. On the real profile the first pass
  // produced "Yangın, Yıldırım, İnfilak teminatının limiti" followed by
  // "Yangın, Yıldırım, İnfilak hasarında muafiyet" — two different slots and
  // the same subject twice, which reads as a document about fire. Skipping a
  // label already used moves the second question onto the next peril, and a
  // whole pass is retried without the constraint if it leaves the list short.
  for (const uniqueSubjects of [true, false]) {
    for (let rank = 0; suggestions.length < limit && rank < 6; rank += 1) {
      for (const field of FIELD_ORDER) {
        if (suggestions.length >= limit) break;

        const entries = byField.get(field);
        if (!entries) continue;

        // Under the constraint, walk past entries whose subject is taken
        // rather than giving up on the field for this rank.
        const entry = uniqueSubjects
          ? entries.filter((e) => !usedLabels.has(tag(e.label.trim())))[rank]
          : entries[rank];
        if (!entry) continue;

        const template = templates[field];
        if (!template) continue;

        const label = entry.label.trim();
        if (label.length > MAX_LABEL_CHARS) continue;
        // A singular field's template ignores the label; a per-item one without
        // a label would produce "What is the limit for ?".
        if (!label && !isSingular(field)) continue;

        const question = template(label);
        const key = tag(question);
        if (seen.has(key)) continue;

        seen.add(key);
        if (label) usedLabels.add(tag(label));
        suggestions.push({ question, field, label });
      }
    }
    if (suggestions.length >= limit) break;
  }

  return suggestions;
}

/** Fields the document has exactly one of, whose templates take no label. */
function isSingular(field: ProfileField): boolean {
  return (
    field === "territorial_scope" ||
    field === "policy_period" ||
    field === "notification_deadline" ||
    field === "deductible" ||
    field === "waiting_period"
  );
}
