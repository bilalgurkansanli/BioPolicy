import type { Metadata, Viewport } from "next";
import { Geist, Geist_Mono } from "next/font/google";

import { CookieConsent } from "@/components/CookieConsent";
import { LocaleProvider } from "@/components/LocaleProvider";
import { SessionProvider } from "@/components/SessionProvider";
import { StructuredData } from "@/components/StructuredData";
import { PageTransition } from "@/components/PageTransition";
import { DEFAULT_LOCALE, dictionaries } from "@/lib/i18n";
import { AUTHOR, REPO_URL, SITE_URL } from "@/lib/site";

import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

// Metadata is static and cannot follow a client-side preference, so it uses the
// default locale. The visible interface still switches; only the tab title and
// the crawler's copy stay in the default language.
const meta = dictionaries[DEFAULT_LOCALE].meta;

export const metadata: Metadata = {
  // Absolute URLs are built from this, so every canonical, sitemap entry and
  // card image points at the deployment that served the page rather than at
  // whatever domain was hard-coded when it was written.
  metadataBase: new URL(SITE_URL),
  title: {
    default: meta.title,
    // Every other page supplies its own name and inherits the rest.
    template: `%s — BioPolicy`,
  },
  description: meta.description,
  applicationName: "BioPolicy",
  authors: [AUTHOR],
  creator: AUTHOR.name,
  category: "technology",
  keywords: [
    "sigorta poliçesi",
    "poliçe sorgulama",
    "hukuki sözleşme",
    "yapay zeka",
    "RAG",
    "retrieval-augmented generation",
    "citation grounding",
    "insurance policy question answering",
    "legal document AI",
  ],
  alternates: { canonical: "/" },
  robots: {
    index: true,
    follow: true,
    googleBot: {
      index: true,
      follow: true,
      // The default is a 160-character snippet and no preview. This is a demo
      // whose whole argument is visual; letting it be previewed is the point.
      "max-snippet": -1,
      "max-image-preview": "large",
      "max-video-preview": -1,
    },
  },
  openGraph: {
    type: "website",
    siteName: "BioPolicy",
    // The interface switches language on a stored preference rather than a
    // URL, so there is one document per page and it is served in the default
    // locale. `alternateLocale` says the same content exists in Turkish without
    // claiming a second URL for it — which is the honest shape here, and why
    // there is no hreflang (ADR 011).
    locale: "en_US",
    alternateLocale: ["tr_TR"],
    url: "/",
    title: meta.title,
    description: meta.description,
  },
  twitter: {
    card: "summary_large_image",
    title: meta.title,
    description: meta.description,
  },
  other: {
    // Not a meta tag Google reads, but the one a reviewer looks for.
    repository: REPO_URL,
  },
};

// Split from `metadata` because Next treats it as its own export: the browser
// chrome follows the theme rather than staying white above a near-black page.
export const viewport: Viewport = {
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#f7f9fd" },
    { media: "(prefers-color-scheme: dark)", color: "#070b14" },
  ],
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html
      lang={DEFAULT_LOCALE}
      className={`${geistSans.variable} ${geistMono.variable} antialiased`}
    >
      {/* `min-h-dvh` on the body, and nothing pinning the root's height.

          `html { height: 100% }` with `body { min-height: 100% }` is the old
          way to make the body fill the screen, and it pins the root to the
          viewport while its content runs past it — measured here, 844px of root
          holding 2254px of page. The overflow then propagates to the viewport,
          which is why it scrolls at all, and a `position: sticky` child ends up
          resolving against a scrollport that is not the box it lives in. Mobile
          browsers reconcile that during the first scroll, which is seen as the
          header sinking a few pixels.
      
          `min-h-dvh` asks for the same thing — a body at least a screen tall —
          without giving the root a height it has to lie about. */}
      <body className="flex min-h-dvh flex-col font-sans">
        {/* Describes the site rather than the page, so it belongs on all of
            them and is rendered once, here. */}
        <StructuredData />
        <PageTransition />
        <LocaleProvider>
          <SessionProvider>{children}</SessionProvider>
          {/* Inside the locale provider because the banner has to be readable,
              and outside the session because it is asked of everyone. */}
          <CookieConsent />
        </LocaleProvider>
      </body>
    </html>
  );
}
