import type { Metadata } from "next";

/**
 * The workspace's own metadata. The page itself is a client component and
 * cannot export any, so it lives beside it.
 *
 * Written in the default locale like the rest: the interface language is a
 * stored preference, and a crawler has no preference to read (ADR 011).
 */
export const metadata: Metadata = {
  title: "Workspace",
  description:
    "Pick a document and ask it a question. The answer arrives with the clause it came from, marked on the page — and when the document does not say, neither does the system.",
  alternates: { canonical: "/app" },
  openGraph: {
    url: "/app",
    title: "Workspace — BioPolicy",
    description:
      "Pick a document and ask it a question. The answer arrives with the clause it came from, marked on the page.",
  },
};

// `LayoutProps` is generated per route by Next; the plain `children` type
// fails the route validator it also generates.
export default function WorkspaceLayout({ children }: LayoutProps<"/app">) {
  return children;
}
