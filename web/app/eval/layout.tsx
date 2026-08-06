import type { Metadata } from "next";

/**
 * The evaluation page's metadata. Its description names the numbers rather
 * than the page, because a search result for "does this thing work" should
 * answer the question in the snippet.
 */
export const metadata: Metadata = {
  title: "Değerlendirme",
  description:
    "70 soruluk değerlendirme kümesinin sonuçları, üreten komutun yazdığı haliyle: doğru ret oranı, yanlış ret oranı, alıntı geçerliliği, maliyet — hoşa gitmeyenler dahil.",
  alternates: { canonical: "/eval" },
  openGraph: {
    url: "/eval",
    title: "Değerlendirme — BioPolicy",
    description:
      "70 soruluk kümede ölçülen sonuçlar, elle yazılmadan, hoşa gitmeyenler dahil.",
  },
};

// `LayoutProps` is generated per route by Next; the plain `children` type
// fails the route validator it also generates.
export default function EvaluationLayout({ children }: LayoutProps<"/eval">) {
  return children;
}
