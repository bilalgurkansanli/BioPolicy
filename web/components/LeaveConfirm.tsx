"use client";

import { useEffect, useRef } from "react";
import { createPortal } from "react-dom";

/**
 * Asks before leaving the site.
 *
 * Only on the narrow layout, and the reason is the label. On a wide screen the
 * link reads "Diğer Projelerim için Tıklayınız" and nobody taps it by accident.
 * On a phone there is no room for that sentence, so the control is an arrow —
 * and an unlabelled arrow beside a logo reads as "back", which here means
 * leaving for another domain entirely. The dialog is what turns an ambiguous
 * arrow into a stated intention.
 *
 * Dismissal is deliberately generous: the backdrop, the No button, and Escape
 * all close it. Only the one affirmative control leaves.
 *
 * ## Why it is portalled out of the header
 *
 * `position: fixed` is relative to the viewport only while no ancestor has
 * established a containing block, and `backdrop-filter` establishes one. The
 * header carries `backdrop-blur-md`, so a fixed child of it is laid out inside
 * a 64px-tall box: `inset-0` covered the header rather than the screen, and the
 * dialog appeared pinned under the top edge with its own title cut off.
 *
 * Nothing about the markup looks wrong when that happens, which is what makes
 * it worth writing down. The fix is to render into `document.body`, where there
 * is no such ancestor.
 */
export function LeaveConfirm({
  open,
  title,
  body,
  confirmLabel,
  cancelLabel,
  href,
  onClose,
}: {
  open: boolean;
  title: string;
  body: string;
  confirmLabel: string;
  cancelLabel: string;
  href: string;
  onClose: () => void;
}) {
  const confirmRef = useRef<HTMLAnchorElement>(null);

  // Escape closes, and the page underneath stops scrolling while it is open.
  // Both are restored on unmount rather than on close, so a dialog dismissed by
  // navigating away does not leave the body locked.
  useEffect(() => {
    if (!open) return;

    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);

    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";

    // Focus the affirmative control rather than the dialog: a reader who opened
    // this meant to leave, and Tab from here reaches Cancel next.
    confirmRef.current?.focus();

    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = previous;
    };
  }, [open, onClose]);

  // No mount guard, and none needed. Portals need a DOM to target and the
  // server has none — but `open` starts false and only a click sets it, so the
  // server and the first hydration pass both stop here and `createPortal` is
  // never reached without a document.
  //
  // The obvious `useState(false)` plus `useEffect(() => setMounted(true))` is
  // exactly what `react-hooks/set-state-in-effect` exists to reject, and it
  // would pay a cascading render to solve a problem this component cannot have.
  if (!open) return null;

  return createPortal(
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="leave-confirm-title"
      className="fixed inset-0 z-50 flex items-center justify-center p-5"
    >
      {/* The backdrop is a button so a tap anywhere outside dismisses, and so
          the behaviour is reachable from the keyboard rather than being a
          mouse-only affordance. `aria-hidden` keeps it out of the reading
          order — Escape and the Cancel button are the announced ways out. */}
      <button
        type="button"
        aria-hidden
        tabIndex={-1}
        onClick={onClose}
        className="absolute inset-0 cursor-default bg-paper/70 backdrop-blur-sm"
      />

      <div className="relative w-full max-w-sm rounded-2xl border border-line bg-surface p-5 shadow-[0_24px_60px_-24px_rgba(0,0,0,0.6)]">
        <h2
          id="leave-confirm-title"
          className="text-base font-semibold text-ink"
        >
          {title}
        </h2>
        <p className="mt-1.5 text-sm leading-6 text-ink-muted">{body}</p>

        <div className="mt-4 flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
          <button
            type="button"
            onClick={onClose}
            className="rounded-full border border-line px-4 py-2 text-sm font-medium text-ink-muted transition-colors hover:border-line-strong hover:text-ink"
          >
            {cancelLabel}
          </button>
          {/* An anchor, not a button with a handler: leaving is a navigation,
              and a real link can be opened in a new tab, copied, or read by
              anything that inspects links. Same tab, because a departure that
              leaves this page open behind it is not one. */}
          <a
            ref={confirmRef}
            href={href}
            className="cta-gradient cta-sheen rounded-full px-4 py-2 text-center text-sm font-semibold text-on-accent"
          >
            {confirmLabel}
          </a>
        </div>
      </div>
    </div>,
    document.body,
  );
}
