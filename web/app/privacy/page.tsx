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
};

export default function Page() {
  return <LegalPage slug="privacy" />;
}
