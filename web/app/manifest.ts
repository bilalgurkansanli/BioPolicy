import type { MetadataRoute } from "next";

import { DEFAULT_LOCALE, dictionaries } from "@/lib/i18n";

/**
 * The web app manifest.
 *
 * Modest on purpose. This is not a progressive web app and claiming to be one
 * would be the same kind of overstatement the structured data avoids: there is
 * no offline mode, no service worker, and a document viewer is not much use
 * without a network. What the manifest is here for is the ordinary half —
 * a name and an icon when someone adds the site to a phone's home screen, and
 * one more place the site describes itself consistently.
 *
 * `display: "browser"` rather than `"standalone"` follows from that. Standalone
 * hides the address bar, and an app that asks people to upload their insurance
 * policy should not be the app that hides which domain they are on.
 *
 * The icons are the ones Next.js already generates routes for from
 * `app/icon.png` and `app/apple-icon.png`, referenced by their public paths so
 * there is one source file per icon rather than two.
 */
export default function manifest(): MetadataRoute.Manifest {
  const meta = dictionaries[DEFAULT_LOCALE].meta;

  return {
    name: "BioPolicy",
    short_name: "BioPolicy",
    description: meta.description,
    start_url: "/",
    display: "browser",
    lang: DEFAULT_LOCALE,
    dir: "ltr",
    categories: ["productivity", "business", "utilities"],
    background_color: "#070b14",
    theme_color: "#070b14",
    icons: [
      { src: "/icon.png", sizes: "any", type: "image/png", purpose: "any" },
      { src: "/apple-icon.png", sizes: "any", type: "image/png", purpose: "maskable" },
    ],
  };
}
