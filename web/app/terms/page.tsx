import type { Metadata } from "next";

import { LegalPage } from "@/components/LegalPage";
import { DEFAULT_LOCALE, dictionaries } from "@/lib/i18n";
import { pageMetadata } from "@/lib/page-metadata";

export const metadata: Metadata = pageMetadata({
  name: dictionaries[DEFAULT_LOCALE].meta.pages.terms,
  path: "/terms",
  description:
    "What BioPolicy offers, what it explicitly does not, and the limits that apply to the demo.",
});

export default function Page() {
  return <LegalPage slug="terms" />;
}
