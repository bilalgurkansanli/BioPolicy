import type { Metadata } from "next";

import { DEFAULT_LOCALE, dictionaries } from "@/lib/i18n";
import { pageMetadata } from "@/lib/page-metadata";

/**
 * The evaluation page's metadata. Its description names the numbers rather
 * than the page, because a search result for "does this thing work" should
 * answer the question in the snippet.
 */
export const metadata: Metadata = pageMetadata({
  name: dictionaries[DEFAULT_LOCALE].meta.pages.eval,
  path: "/eval",
  description:
    "Results over a 70-question set, exactly as the harness wrote them: refusal accuracy, false-refusal rate, citation validity and cost — including the numbers that do not flatter the system.",
  card: "Measured over a 70-question set, none of it hand-written, including the unflattering results.",
});

// `LayoutProps` is generated per route by Next; the plain `children` type
// fails the route validator it also generates.
export default function EvaluationLayout({ children }: LayoutProps<"/eval">) {
  return children;
}
