import type { Metadata } from "next";

import { LegalPage } from "@/components/LegalPage";

export const metadata: Metadata = {
  // The root layout appends " — BioPolicy"; repeating it here produced
  // "Terms of Use — BioPolicy — BioPolicy" in the tab.
  title: "Terms of Use",
  description:
    "What BioPolicy offers, what it explicitly does not, and the limits that apply to the demo.",
  // See the note in `privacy/page.tsx`: omitting these inherits the root's `/`
  // and declares this page a duplicate of the home page.
  alternates: { canonical: "/terms" },
  openGraph: { url: "/terms" },
};

export default function Page() {
  return <LegalPage slug="terms" />;
}
