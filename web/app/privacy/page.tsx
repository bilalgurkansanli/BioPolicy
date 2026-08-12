import type { Metadata } from "next";

import { LegalPage } from "@/components/LegalPage";
import { DEFAULT_LOCALE, dictionaries } from "@/lib/i18n";
import { pageMetadata } from "@/lib/page-metadata";

/**
 * Served in the default locale, like all metadata: the locale is a client
 * preference and this is generated on the server, so the crawler gets the
 * default and `LocaleProvider` corrects the tab after hydration.
 *
 * The name is read from the dictionary — the same entry `LegalPage` renders as
 * the `<h1>` and `LocaleProvider` writes into the tab. One string, three
 * readers.
 *
 * The canonical matters more here than anywhere else on the site. Inherited, it
 * would name the home page, and the one document a reader may need to find and
 * a regulator may need to cite would quietly leave the index.
 */
export const metadata: Metadata = pageMetadata({
  name: dictionaries[DEFAULT_LOCALE].meta.pages.privacy,
  path: "/privacy",
  description:
    "What BioPolicy processes, why, for how long, and which providers see an uploaded document.",
});

export default function Page() {
  return <LegalPage slug="privacy" />;
}
