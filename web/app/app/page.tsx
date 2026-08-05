"use client";

import { SiteHeader } from "@/components/SiteHeader";
import { Workspace } from "@/components/workspace/Workspace";

/**
 * The workspace fills the viewport and does not scroll as a page: the
 * conversation and the document each own their own scroll region, so clicking a
 * citation can move the document without moving the answer out of view.
 */
export default function WorkspacePage() {
  return (
    // Masked as a whole rather than pane by pane: everything inside is either
    // the visitor's document, their question, or an answer quoting the
    // document, and session recording is not a place any of it belongs. Clicks
    // and layout still reach the analytics, so the funnel stays measurable; the
    // text does not. This is the promise the cookie notice makes.
    <div data-clarity-mask="true" className="flex h-dvh flex-col overflow-hidden">
      <SiteHeader />
      <Workspace />
    </div>
  );
}
