import type { Metadata } from "next";

import { LegalPage } from "@/components/LegalPage";

/**
 * Titled in English in the metadata while the page renders in the reader's
 * language. The locale is a client preference and metadata is generated on the
 * server, so a translated title here would be a coin flip; the visible heading
 * is the one that follows the reader.
 */
export const metadata: Metadata = {
  // The root layout appends " — BioPolicy"; repeating it here produced
  // "Privacy Notice — BioPolicy — BioPolicy" in the tab.
  title: "Privacy Notice",
  description:
    "What BioPolicy processes, why, for how long, and which providers see an uploaded document.",
  // Both of these are inherited from the root layout when a page omits them,
  // and the root's value is `/`. This page therefore told crawlers it was a
  // duplicate of the home page and asked them to index that instead — which
  // for a privacy notice means the one page a reader may need to find, and a
  // regulator may need to cite, quietly leaves the index.
  alternates: { canonical: "/privacy" },
  openGraph: { url: "/privacy" },
};

export default function Page() {
  return <LegalPage slug="privacy" />;
}
