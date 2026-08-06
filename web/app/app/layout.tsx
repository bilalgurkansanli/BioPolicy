import type { Metadata } from "next";

/**
 * The workspace's own metadata. The page itself is a client component and
 * cannot export any, so it lives beside it.
 *
 * Written in the default locale like the rest: the interface language is a
 * stored preference, and a crawler has no preference to read (ADR 011).
 */
export const metadata: Metadata = {
  title: "Çalışma ekranı",
  description:
    "Bir poliçe seçin, soru sorun. Cevap, dayandığı maddeyle birlikte belgenin üzerinde işaretli gelir; belge cevabı içermiyorsa sistem uydurmaz, reddeder.",
  alternates: { canonical: "/app" },
  openGraph: {
    url: "/app",
    title: "Çalışma ekranı — BioPolicy",
    description:
      "Bir poliçe seçin, soru sorun. Cevap, dayandığı maddeyle birlikte belgenin üzerinde işaretli gelir.",
  },
};

// `LayoutProps` is generated per route by Next; the plain `children` type
// fails the route validator it also generates.
export default function WorkspaceLayout({ children }: LayoutProps<"/app">) {
  return children;
}
