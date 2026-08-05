/**
 * Replay the page's text as if it were being typed again.
 *
 * Switching language rewrites every string on screen, and the page should look
 * like it. A single sweep across the whole page reads as a transition; text
 * being written reads as text being written, and the difference is that each
 * block starts on its own and fills in from the left.
 *
 * Three decisions carry the effect:
 *
 *   * **Per block, not per page.** Each text element is revealed by its own
 *     `clip-path`, so the page fills in the way a page is written — top down,
 *     one line at a time — rather than appearing all at once behind a wipe.
 *   * **Stepped, not smooth.** The reveal runs on `steps()`, so a line arrives
 *     in discrete jumps instead of sliding open. Smooth is a curtain; stepped
 *     is a keyboard.
 *   * **No fade.** Opacity is untouched. Text that is not there yet is clipped
 *     away, not faint — half-written is a state, half-visible is a dissolve.
 *
 * Layout never moves: clipping hides what has not been "typed" yet without
 * changing where anything sits, so nothing reflows and no scroll position
 * jumps mid-animation.
 */

const CLASS = "retype-line";

/** Tags that hold a line of text. Containers are left alone. */
const SELECTOR =
  "h1, h2, h3, h4, h5, h6, p, li, dt, dd, td, th, button, a, span, label, figcaption";

/** Roughly the length of the animation in globals.css, plus the last delay. */
export const RETYPE_MS = 700;

const STEP_MS = 16;
const MAX_DELAY_MS = 380;
const MAX_ELEMENTS = 140;

export function replayText(): void {
  const candidates = Array.from(
    document.querySelectorAll<HTMLElement>(SELECTOR),
  ).filter((element) => {
    if (!element.textContent?.trim()) return false;

    // Words, and only words. Clipping an element that also holds a mark or an
    // icon draws the picture in too, and clipping a filled button reveals its
    // background rather than its label — which reads as a progress bar, not as
    // typing.
    if (element.querySelector("img, svg, canvas, video")) return false;

    // An inline box that has wrapped is clipped in fragments, which looks like
    // a rendering fault rather than typing. Its block parent covers it anyway.
    if (getComputedStyle(element).display === "inline") return false;

    // Controls that are the same in both languages, above all the switch being
    // clicked: animating it makes the button look like it is answering rather
    // than the page.
    if (element.closest("[data-no-retype]")) return false;

    // Nested text would be revealed twice, once by its own animation and once
    // by its parent's clip — the inner one visibly behind the outer.
    return !element.parentElement?.closest(`.${CLASS}`);
  });

  // Top of the page first, so the eye follows the writing down rather than
  // watching the whole page twitch at once.
  const ordered = candidates
    .map((element) => ({ element, top: element.getBoundingClientRect().top }))
    .sort((a, b) => a.top - b.top)
    .slice(0, MAX_ELEMENTS);

  for (const [index, { element }] of ordered.entries()) {
    element.classList.add(CLASS);
    element.style.animationDelay = `${Math.min(index * STEP_MS, MAX_DELAY_MS)}ms`;
  }

  window.setTimeout(() => {
    for (const { element } of ordered) {
      element.classList.remove(CLASS);
      element.style.animationDelay = "";
    }
  }, RETYPE_MS);
}
