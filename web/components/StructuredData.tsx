import { DEFAULT_LOCALE, dictionaries } from "@/lib/i18n";
import { AUTHOR, REPO_URL, SITE_URL } from "@/lib/site";

/**
 * What this is, in the vocabulary a search engine reads.
 *
 * Three linked nodes rather than one: the site, the thing the site *is*, and
 * the person who built it. A portfolio project is judged on the third as much
 * as the first, and `sameAs` is what ties a name here to a profile elsewhere.
 *
 * Everything asserted here is also visible on the page. Structured data that
 * claims more than the page shows is the kind that gets a site penalised, and
 * it would be the same dishonesty this project is arguing against.
 */
export function StructuredData() {
  const meta = dictionaries[DEFAULT_LOCALE].meta;

  const graph = {
    "@context": "https://schema.org",
    "@graph": [
      {
        "@type": "WebSite",
        "@id": `${SITE_URL}/#website`,
        url: SITE_URL,
        name: "BioPolicy",
        description: meta.description,
        inLanguage: ["tr", "en"],
        publisher: { "@id": `${SITE_URL}/#author` },
      },
      {
        "@type": "SoftwareApplication",
        "@id": `${SITE_URL}/#app`,
        name: "BioPolicy",
        url: SITE_URL,
        applicationCategory: "BusinessApplication",
        operatingSystem: "Any (web)",
        description: meta.description,
        inLanguage: ["tr", "en"],
        author: { "@id": `${SITE_URL}/#author` },
        codeRepository: REPO_URL,
        license: "https://opensource.org/licenses/MIT",
        // A demo with a daily allowance rather than a price. Saying "free"
        // without saying "limited" would be the flattering half of the truth.
        offers: {
          "@type": "Offer",
          price: "0",
          priceCurrency: "USD",
          description:
            "Ücretsiz demo, hesap başına günlük soru ve belge sınırıyla.",
        },
        featureList: [
          "Sigorta poliçeleri ve sözleşmeler üzerinde soru-cevap",
          "Her cevabın dayandığı maddeyi belgede işaretleme",
          "Belgede olmayan bilgi için cevap vermeyi reddetme",
          "Taranmış belgeler için OCR",
          "Türkçe ve İngilizce",
        ],
      },
      {
        "@type": "Person",
        "@id": `${SITE_URL}/#author`,
        name: AUTHOR.name,
        url: AUTHOR.url,
        sameAs: [AUTHOR.url],
      },
    ],
  };

  return (
    <script
      type="application/ld+json"
      // The payload is built here from constants, never from user input; the
      // only escaping that matters is the one that keeps a `<` from closing the
      // script tag early.
      dangerouslySetInnerHTML={{
        __html: JSON.stringify(graph).replace(/</g, "\\u003c"),
      }}
    />
  );
}
