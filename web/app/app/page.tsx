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
    <div className="flex h-dvh flex-col overflow-hidden">
      <SiteHeader />
      <Workspace />
    </div>
  );
}
