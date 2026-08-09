import type { Metadata } from "next";

import { LegalPage } from "@/components/LegalPage";

export const metadata: Metadata = {
  // The root layout appends " — BioPolicy"; repeating it here produced
  // "Cookies — BioPolicy — BioPolicy" in the tab.
  title: "Cookies",
  description:
    "One storage key keeps you signed in; measurement is optional and never loads unless accepted.",
};

export default function Page() {
  return <LegalPage slug="cookies" />;
}
