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

/**
 * What every tab title begins with.
 *
 * Shared rather than written twice: the root layout builds its title template
 * from this, and `LocaleProvider` rebuilds the same string on the client when
 * the reader's language is not the one the page was prerendered in. Two copies
 * of a separator and a name is how a tab ends up reading "BioPolicy - Workspace"
 * in one language and "BioPolicy — Çalışma alanı" in the other.
 */
export const SITE_NAME = "BioPolicy";

/**
 * Search Console's ownership token, when the deployment has been given one.
 *
 * Read from the environment rather than pasted into the source, and not because
 * it is a secret — it is served in the HTML of every page. It is because the
 * token proves ownership of *one* property, and this repository is public: a
 * fork that built with it embedded would serve a claim on somebody else's site.
 * Empty means the `verification` block is omitted entirely rather than emitted
 * with a blank content attribute.
 */
export const GOOGLE_SITE_VERIFICATION =
  process.env.NEXT_PUBLIC_GOOGLE_SITE_VERIFICATION ?? "";

/** The repository, quoted in structured data as the thing this page is about. */
export const REPO_URL = "https://github.com/bilalgurkansanli/BioPolicy";

export const AUTHOR = {
  name: "Bilal Gürkan Şanlı",
  url: "https://github.com/bilalgurkansanli",
  /**
   * Other places the same person is. This is what `sameAs` is for in structured
   * data — not a link list, an identity claim: it tells a search engine that the
   * author of this site and the owner of those profiles are one entity rather
   * than three people with the same name.
   *
   * Only profiles that are actually his go here. A `sameAs` pointing at someone
   * else is a false statement in the one vocabulary search engines read
   * literally, and unlike a wrong description it is not self-correcting.
   */
  sameAs: [
    "https://github.com/bilalgurkansanli",
    "https://projects.bilalgurkansanli.com",
  ],
} as const;
