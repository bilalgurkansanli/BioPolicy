import type { Metadata } from "next";

import { DEFAULT_LOCALE, dictionaries } from "@/lib/i18n";
import { pageMetadata } from "@/lib/page-metadata";

/**
 * A door, not a destination. Nothing here ranks for anything, and a searcher
 * who lands on it has arrived at a page whose only content is a button — so it
 * asks not to be indexed, and `robots.ts` says the same thing from the other
 * side.
 *
 * It still gets the full treatment from `pageMetadata`. `noindex` keeps it out
 * of results; it does nothing about the preview when somebody pastes the link
 * into a chat to ask a friend to sign in, which is the one way this URL
 * actually travels.
 *
 * The canonical is set for a reason that outlives the `noindex`: inherited, it
 * would name the home page, and "do not index me, and by the way I am that
 * page" becomes a live bug the day the `noindex` is reconsidered.
 */
export const metadata: Metadata = {
  ...pageMetadata({
    name: dictionaries[DEFAULT_LOCALE].meta.pages.signin,
    path: "/signin",
    description:
      "Sign in with your Google account. The sample documents are readable without one.",
  }),
  robots: { index: false, follow: true },
};

// `LayoutProps` is generated per route by Next; the plain `children` type
// fails the route validator it also generates.
export default function SignInLayout({ children }: LayoutProps<"/signin">) {
  return children;
}
