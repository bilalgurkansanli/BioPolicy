import type { Metadata } from "next";

/**
 * A door, not a destination. Nothing here ranks for anything, and a searcher
 * who lands on it has arrived at a page whose only content is a button — so it
 * asks not to be indexed, and `robots.ts` says the same thing from the other
 * side.
 */
export const metadata: Metadata = {
  title: "Giriş",
  description:
    "Google hesabınızla giriş yapın. Örnek belgeler giriş yapmadan da okunabilir.",
  robots: { index: false, follow: true },
  // Set even though this page asks not to be indexed. Without it the page
  // inherits the root's `/` and names the home page as its canonical, which is
  // a contradiction — "do not index me, and by the way I am that page" — and it
  // becomes a live bug the day the `noindex` above is reconsidered.
  alternates: { canonical: "/signin" },
  openGraph: { url: "/signin" },
};

// `LayoutProps` is generated per route by Next; the plain `children` type
// fails the route validator it also generates.
export default function SignInLayout({ children }: LayoutProps<"/signin">) {
  return children;
}
