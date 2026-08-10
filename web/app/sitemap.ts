import type { MetadataRoute } from "next";

import { SITE_URL } from "@/lib/site";

/**
 * Three URLs, which is all there are.
 *
 * `/signin` is left out deliberately: it is a door, not a destination, and a
 * search result that lands on it has sent someone to a page whose only content
 * is a button. It carries `noindex` in its own metadata for the same reason.
 *
 * The locale is a stored preference rather than a URL segment (ADR 011), so
 * there is one entry per page rather than one per language.
 *
 * `lastModified` is the build time for every entry, and that is a weaker claim
 * than it looks: a deploy that changed one page dates all seven. Crawlers
 * discount a `lastmod` that moves on everything at once, so this is honest in
 * effect rather than precise — a per-page date would need the git history of
 * each route, which is not worth a build-time subprocess.
 */
export default function sitemap(): MetadataRoute.Sitemap {
  const lastModified = new Date();

  return [
    {
      url: SITE_URL,
      lastModified,
      changeFrequency: "monthly",
      priority: 1,
    },
    {
      url: `${SITE_URL}/app`,
      lastModified,
      changeFrequency: "monthly",
      priority: 0.8,
    },
    {
      // Changes whenever the evaluation is re-run, which is the only page here
      // whose content is regenerated rather than edited.
      url: `${SITE_URL}/eval`,
      lastModified,
      changeFrequency: "weekly",
      priority: 0.6,
    },
    // Listed so they are reachable and citable from outside the app. Low
    // priority and yearly: nobody arrives here from a search, but a policy
    // that cannot be linked to is not much of a policy.
    ...(["privacy", "terms", "cookies"] as const).map((slug) => ({
      url: `${SITE_URL}/${slug}`,
      lastModified,
      changeFrequency: "yearly" as const,
      priority: 0.3,
    })),
  ];
}
