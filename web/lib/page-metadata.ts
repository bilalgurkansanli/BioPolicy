import type { Metadata } from "next";

import { SITE_NAME } from "./site";

/**
 * The per-page half of the metadata, assembled so the shared half survives.
 *
 * ## The trap this exists to close
 *
 * Next merges metadata **per field, not per key**. A page that exports an
 * `openGraph` object replaces the root's outright, and everything it does not
 * restate is gone — including the card image Next attaches from the root
 * segment's `opengraph-image.png`. The same is true of `twitter`, which does
 * not inherit from `openGraph` either: set one and omit the other and the page
 * previews correctly when pasted in one place and as the *home page* when
 * pasted in another.
 *
 * Neither failure is an error. Measured on a production build before this
 * helper existed: `/app` and `/privacy` served `twitter:card content="summary"`
 * and no `og:image` at all, while `/` served `summary_large_image` with the
 * 1200x630 card. The pages worth sharing were the ones sharing badly.
 *
 * ## Why a function rather than a spread
 *
 * A `...SHARED_OG` spread would have to be repeated in both objects on every
 * page, which is the same duplication one level down. Here the card image and
 * the card type are named once, and a route supplies only what is actually its
 * own: a name, a path and a description.
 *
 * The locale is the default one throughout — metadata is resolved at build time
 * and a crawler has no preference to read (ADR 011).
 */

/**
 * Served by the route Next generates from `app/opengraph-image.png`. Referenced
 * by path rather than re-imported per segment, so the 225 KB file stays in the
 * repository once. `metadataBase` in the root layout is what makes it absolute.
 */
const CARD_IMAGE = "/opengraph-image.png";

type PageMetadata = {
  /** The route's name, read from `meta.pages` so the tab, the `<h1>` and the card agree. */
  name: string;
  /** Absolute path. Becomes the canonical and the card's URL. */
  path: string;
  /** The search snippet. Written for someone deciding whether to click. */
  description: string;
  /**
   * The card line, when a shorter one reads better. A snippet is read in a
   * results list and a card is read in a chat window; the second is truncated
   * harder. Defaults to the description.
   */
  card?: string;
};

export function pageMetadata({
  name,
  path,
  description,
  card = description,
}: PageMetadata): Metadata {
  // The root's title template supplies the site name for the tab. Open Graph
  // has no template, so the full string is stated here.
  const title = `${SITE_NAME} — ${name}`;

  return {
    title: name,
    description,
    // Without this a page inherits the root's `/` and declares itself a
    // duplicate of the home page.
    alternates: { canonical: path },
    openGraph: { url: path, title, description: card, images: CARD_IMAGE },
    twitter: {
      card: "summary_large_image",
      title,
      description: card,
      images: CARD_IMAGE,
    },
  };
}
