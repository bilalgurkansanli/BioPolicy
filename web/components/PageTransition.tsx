"use client";

import { usePathname } from "next/navigation";
import { useEffect, useLayoutEffect } from "react";

/** Long enough to outlast the arrival animation in globals.css. */
const ARRIVAL_MS = 420;

// `useLayoutEffect` is the point of this component, but React renders client
// components on the server too and warns that it does nothing there.
const useBeforePaintEffect =
  typeof window === "undefined" ? useEffect : useLayoutEffect;

/**
 * Hands a page transition over from its outgoing half to its incoming one, on
 * the frame the new page is painted.
 *
 * This lives in the layout rather than in the link that started the transition
 * because only the layout survives the navigation. Timing the hand-over from
 * the link — a frame callback, a timeout — means guessing when the next page
 * will be ready, and guessing early puts the old page back on screen for a
 * frame or two before it disappears again. That flash is the jolt this avoids:
 * a layout effect on the new path runs after the new page has been committed to
 * the DOM and before anything is painted.
 *
 * The direction class is left in place for the arrival and taken off after it,
 * so a page opened directly — no transition, no classes — never slides.
 */
export function PageTransition() {
  const pathname = usePathname();

  useBeforePaintEffect(() => {
    const root = document.documentElement;
    if (!root.classList.contains("page-leaving")) return;

    root.classList.replace("page-leaving", "page-arriving");

    const timer = window.setTimeout(() => {
      root.classList.remove("page-arriving", "page-forward", "page-back");
    }, ARRIVAL_MS);

    return () => window.clearTimeout(timer);
  }, [pathname]);

  return null;
}
