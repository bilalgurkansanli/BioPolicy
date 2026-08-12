import type { Metadata } from "next";

import { DEFAULT_LOCALE, dictionaries } from "@/lib/i18n";
import { pageMetadata } from "@/lib/page-metadata";

/**
 * The workspace's own metadata. The page itself is a client component and
 * cannot export any, so it lives beside it.
 *
 * Written in the default locale like the rest: the interface language is a
 * stored preference, and a crawler has no preference to read (ADR 011). The
 * name comes from the dictionary rather than a literal, because
 * `LocaleProvider` rewrites this same tab title from the same key — two copies
 * would drift the day one of them is reworded.
 */
export const metadata: Metadata = pageMetadata({
  name: dictionaries[DEFAULT_LOCALE].meta.pages.app,
  path: "/app",
  description:
    "Pick a document and ask it a question. The answer arrives with the clause it came from, marked on the page — and when the document does not say, neither does the system.",
  card: "Pick a document and ask it a question. The answer arrives with the clause it came from, marked on the page.",
});

// `LayoutProps` is generated per route by Next; the plain `children` type
// fails the route validator it also generates.
export default function WorkspaceLayout({ children }: LayoutProps<"/app">) {
  return children;
}
