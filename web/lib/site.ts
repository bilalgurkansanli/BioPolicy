/**
 * Where this deployment thinks it lives.
 *
 * Every absolute URL the crawlers need — canonical, sitemap, Open Graph image —
 * is built from this one value. Hard-coding the domain in each of them is how a
 * preview deployment ends up telling Google that its canonical URL is
 * production, and how production ends up advertising a preview's image.
 *
 * `NEXT_PUBLIC_SITE_URL` is the override; Vercel supplies `VERCEL_PROJECT_
 * PRODUCTION_URL` on its own, which is what makes preview builds point at the
 * real domain rather than at themselves.
 */

const FALLBACK = "https://biopolicy.bilalgurkansanli.com";

function resolve(): string {
  const explicit = process.env.NEXT_PUBLIC_SITE_URL;
  if (explicit) return explicit.replace(/\/$/, "");

  const vercel = process.env.VERCEL_PROJECT_PRODUCTION_URL;
  if (vercel) return `https://${vercel.replace(/\/$/, "")}`;

  return FALLBACK;
}

export const SITE_URL = resolve();

/** The repository, quoted in structured data as the thing this page is about. */
export const REPO_URL = "https://github.com/bilalgurkansanli/BioPolicy";

export const AUTHOR = {
  name: "Bilal Gürkan Şanlı",
  url: "https://github.com/bilalgurkansanli",
} as const;
