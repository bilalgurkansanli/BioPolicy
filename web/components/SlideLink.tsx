"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, type ComponentPropsWithoutRef, type MouseEvent } from "react";

/** Only a backstop for a missed `animationend`; the animation itself times it. */
const EXIT_TIMEOUT_MS = 500;

/** If the navigation never lands, the page must not stay off-screen forever. */
const RECOVERY_MS = 1500;

const EXIT_ANIMATIONS = new Set([
  "biopolicy-slide-out-left",
  "biopolicy-slide-out-right",
]);

type SlideLinkProps = Omit<
  ComponentPropsWithoutRef<typeof Link>,
  "onClick" | "href"
> & {
  href: string;
  /**
   * Which way the site moves. "forward" is a step deeper — the landing page into
   * the workspace — and "back" is the same step retraced.
   */
  direction: "forward" | "back";
};

/**
 * A link that slides the page rather than replacing it.
 *
 * The navigation is deferred until the outgoing animation has actually ended,
 * rather than run against a timer of the same length: a timer that fires early
 * cuts the movement off, and one that fires late leaves a still frame in the
 * middle of it. The incoming half is started by <PageTransition> on the frame
 * the new page is committed, so nothing here has to guess when that is.
 */
export function SlideLink({
  href,
  direction,
  children,
  ...rest
}: SlideLinkProps) {
  const router = useRouter();
  const pathname = usePathname();

  useEffect(() => {
    router.prefetch(href);
  }, [router, href]);

  const handleClick = (event: MouseEvent<HTMLAnchorElement>) => {
    // Modified clicks belong to the browser: they open tabs and windows, and
    // animating the page the user is deliberately leaving behind is wrong.
    if (
      event.metaKey ||
      event.ctrlKey ||
      event.shiftKey ||
      event.altKey ||
      event.button !== 0
    ) {
      return;
    }
    if (pathname === href) return;
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;

    event.preventDefault();
    const root = document.documentElement;
    const { body } = document;

    // A transition started while the previous one is still arriving has to
    // clear it, or both halves would match a rule at once.
    root.classList.remove("page-arriving", "page-forward", "page-back");

    let navigated = false;
    const go = () => {
      if (navigated) return;
      navigated = true;
      body.removeEventListener("animationend", onExitEnd);
      router.push(href);
      window.setTimeout(
        () => root.classList.remove("page-leaving"),
        RECOVERY_MS,
      );
    };

    function onExitEnd(animation: AnimationEvent) {
      if (animation.target !== body) return;
      if (!EXIT_ANIMATIONS.has(animation.animationName)) return;
      go();
    }

    body.addEventListener("animationend", onExitEnd);
    root.classList.add(
      "page-leaving",
      direction === "back" ? "page-back" : "page-forward",
    );
    window.setTimeout(go, EXIT_TIMEOUT_MS);
  };

  return (
    <Link href={href} onClick={handleClick} {...rest}>
      {children}
    </Link>
  );
}
