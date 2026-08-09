import type { Metadata } from "next";

import { LegalPage } from "@/components/LegalPage";

export const metadata: Metadata = {
  // The root layout appends " — BioPolicy"; repeating it here produced
  // "Terms of Use — BioPolicy — BioPolicy" in the tab.
  title: "Terms of Use",
  description:
    "What BioPolicy offers, what it explicitly does not, and the limits that apply to the demo.",
};

export default function Page() {
  return <LegalPage slug="terms" />;
}
