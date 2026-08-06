import type { MetadataRoute } from "next";

import { SITE_URL } from "@/lib/site";

/**
 * Crawlers are welcome; two paths are not worth their time.
 *
 * `/api/` is the FastAPI service behind the rewrite — JSON with no reader on
 * the other end, and every useful route there needs a token anyway. `/signin`
 * is a page whose only content is a button.
 *
 * Nothing here is a security measure. A disallow is a request, and the things
 * that actually protect this deployment are in `docs/SECURITY.md`.
 */
export default function robots(): MetadataRoute.Robots {
  return {
    rules: [{ userAgent: "*", allow: "/", disallow: ["/api/", "/signin"] }],
    sitemap: `${SITE_URL}/sitemap.xml`,
    host: SITE_URL,
  };
}
