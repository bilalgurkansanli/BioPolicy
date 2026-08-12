import type { Metadata } from "next";

import { LegalPage } from "@/components/LegalPage";
import { DEFAULT_LOCALE, dictionaries } from "@/lib/i18n";
import { pageMetadata } from "@/lib/page-metadata";

export const metadata: Metadata = pageMetadata({
  name: dictionaries[DEFAULT_LOCALE].meta.pages.cookies,
  path: "/cookies",
  description:
    "One storage key keeps you signed in; measurement is optional and never loads unless accepted.",
});

export default function Page() {
  return <LegalPage slug="cookies" />;
}
