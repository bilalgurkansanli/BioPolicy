import type { MetadataRoute } from "next";

import { SITE_URL } from "@/lib/site";

/**
 * Crawlers are welcome; one path is not worth their time.
 *
 * `/api/` is the FastAPI service behind the rewrite — JSON with no reader on
 * the other end, and every useful route there needs a token anyway.
 *
 * **`/signin` used to be disallowed here too, and that was the wrong tool.** It
 * carries `noindex` in its own metadata, and the two do not stack: a page a
 * crawler is forbidden to fetch is a page whose `noindex` the crawler never
 * reads. Linked from the header of every page, it could then be indexed as a
 * bare URL with no description — the exact outcome the `noindex` was added to
 * prevent, caused by the rule meant to reinforce it. Keeping it crawlable is
 * what lets the instruction on the page be obeyed.
 *
 * Nothing here is a security measure. A disallow is a request, and the things
 * that actually protect this deployment are in `docs/SECURITY.md`.
 */
export default function robots(): MetadataRoute.Robots {
  return {
    rules: [{ userAgent: "*", allow: "/", disallow: ["/api/"] }],
    sitemap: `${SITE_URL}/sitemap.xml`,
    host: SITE_URL,
  };
}
