"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";

import { UserAvatar } from "@/components/Avatar";
import { useLocale } from "@/components/LocaleProvider";
import { useSession } from "@/components/SessionProvider";
import { SlideLink } from "@/components/SlideLink";
import { GoogleMark } from "@/components/workspace/SignInGate";

/**
 * The account, in the header: who you are, what is left today, and the two
 * things you can do about it.
 *
 * The remaining count stays on the button rather than only inside the menu,
 * because it is what decides whether the next click will work — somebody who
 * has run out should see why without opening anything. Everything else lives
 * behind the picture, where a header has no room to spell it out.
 */
export function AccountMenu() {
  const { t } = useLocale();
  const { ready, signedIn, me, profile, signOut, deleteAccount, configured } =
    useSession();
  const [open, setOpen] = useState(false);
  // Which question the menu is currently asking, rather than one boolean
  // per destructive action. Two booleans can both be true, and the state
  // where the menu asks about signing out and deleting at the same time is
  // one the markup below would have to defend against.
  const [confirming, setConfirming] = useState<"signOut" | "delete" | null>(
    null,
  );
  const [signingOut, setSigningOut] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [deleteFailed, setDeleteFailed] = useState(false);
  const root = useRef<HTMLDivElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  const router = useRouter();

  // Closing resets the question: a menu that was dismissed on "are you sure?"
  // must not reopen still asking it.
  const close = useCallback(() => {
    setOpen(false);
    setConfirming(null);
    setDeleteFailed(false);
  }, []);

  useEffect(() => {
    if (!open) return;

    const onPointerDown = (event: PointerEvent) => {
      if (!root.current?.contains(event.target as Node)) close();
    };
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key !== "Escape") return;
      close();
      // Escape has to give the focus back, or the next tab starts from the top
      // of the page instead of the control the menu belongs to.
      trigger.current?.focus();
    };

    document.addEventListener("pointerdown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("pointerdown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [open, close]);

  if (!configured || !ready) return null;

  if (!signedIn) {
    // To the sign-in screen rather than straight to Google: that page is where
    // the privacy policy and the terms are, and sending someone to a consent
    // dialogue before they can read what they are agreeing to is backwards.
    return (
      <SlideLink
        href="/signin"
        direction="forward"
        className="inline-flex h-9 items-center gap-2 rounded-full border border-line-strong bg-surface px-3.5 text-sm font-medium text-ink transition-colors hover:border-accent/40 hover:bg-surface-sunken"
      >
        <GoogleMark />
        <span className="hidden sm:inline">{t.account.signInLink}</span>
      </SlideLink>
    );
  }

  // Null while the account call is in flight or has failed, which is not the
  // same as unlimited. Both would render as "∞", so an unknown allowance is not
  // rendered at all rather than claiming a privilege nobody granted.
  const allowance = me?.allowance ?? null;
  const questionsLeft = allowance?.questions_left ?? null;
  const email = me?.email ?? profile?.email ?? null;
  const name = profile?.name ?? email;

  const erase = async () => {
    setDeleting(true);
    setDeleteFailed(false);
    try {
      await deleteAccount();
      // Off the workspace, whether or not that is where this happened: it holds
      // the deleted account's documents and conversations, and leaving them on
      // screen would be showing something that no longer exists. Unmounting is
      // what disposes of them.
      router.push("/");
    } catch {
      setDeleting(false);
      setDeleteFailed(true);
    }
  };

  return (
    <div className="relative" ref={root}>
      <button
        ref={trigger}
        type="button"
        onClick={() => (open ? close() : setOpen(true))}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label={t.account.menu}
        className={`flex items-center gap-1.5 rounded-full border py-0.5 pl-0.5 pr-2 transition-colors ${
          open
            ? "border-line-strong bg-surface-sunken"
            : "border-line bg-surface hover:border-line-strong"
        }`}
      >
        <UserAvatar size={28} />
        {allowance && (
          <span
            className={`font-mono text-[11px] ${
              questionsLeft === 0 ? "text-danger" : "text-ink-muted"
            }`}
          >
            {/* Unlimited is `null`, and must not render as a zero. */}
            {questionsLeft === null ? "∞" : questionsLeft}
          </span>
        )}
        <svg
          aria-hidden
          viewBox="0 0 16 16"
          fill="none"
          className={`size-3 text-ink-faint transition-transform duration-200 ${
            open ? "rotate-180" : ""
          }`}
        >
          <path
            d="m4 6 4 4 4-4"
            stroke="currentColor"
            strokeWidth="1.6"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
      </button>

      {open && (
        <div
          role="menu"
          aria-label={t.account.menu}
          // Anchored to the viewport on a phone, to the button from `sm` up.
          //
          // The trigger sits near the left of the header, and a 288px panel
          // hung off its right edge runs off the screen: measured at 375px it
          // started at -135, so the name and the email were cut in half. Right
          // alignment is correct on a desktop, where the control is at the far
          // right of a wide row, and wrong on a phone for the same reason.
          //
          // `fixed inset-x-4` gives it the full width less an even margin, which
          // is what a menu this size should do on a phone anyway. It stays a DOM
          // child of the wrapper, so the click-outside and Escape handling that
          // keys off `root.contains` is unaffected. `top-[4.6rem]` clears the
          // 4rem header and keeps the same gap under it as the desktop rule.
          className="menu-pop fixed inset-x-4 top-[4.6rem] z-40 overflow-hidden rounded-2xl border border-line bg-surface shadow-[0_28px_60px_-28px_rgb(15_23_42_/_0.5)] sm:absolute sm:inset-x-auto sm:right-0 sm:top-[calc(100%+0.6rem)] sm:w-72"
        >
          <div className="flex items-center gap-3 border-b border-line p-4">
            <UserAvatar size={40} />
            <div className="min-w-0">
              <p className="truncate text-sm font-medium text-ink">{name}</p>
              {email && name !== email && (
                <p className="truncate text-xs text-ink-faint">{email}</p>
              )}
            </div>
          </div>

          {allowance && (
            <div className="border-b border-line px-4 py-3">
              <p className="text-[11px] font-medium uppercase tracking-wide text-ink-faint">
                {t.account.remaining}
              </p>
              <div className="mt-2 grid grid-cols-2 gap-2">
                <Allowance
                  left={allowance.questions_left}
                  label={t.account.questions}
                  unlimited={t.account.unlimited}
                />
                <Allowance
                  left={allowance.documents_left}
                  label={t.account.documents}
                  unlimited={t.account.unlimited}
                />
              </div>
            </div>
          )}

          {confirming === "signOut" ? (
            /* Asked in the menu, in the same shape as the delete question, and
               not in a `window.confirm`. A native dialogue takes over the whole
               window and arrives with no styling, no translation and no memory
               of which account it is about — for a question this ordinary that
               is a bigger interruption than the action deserves.

               Signing out is not destructive: the conversations and documents
               are still there afterwards. So the confirm button is the ordinary
               filled one rather than the red one the delete panel uses, and the
               copy says what survives instead of warning about what is lost. */
            <div className="p-4">
              <p className="text-sm font-medium text-ink">
                {t.account.signOutTitle}
              </p>
              <p className="mt-1.5 text-xs leading-5 text-ink-muted">
                {t.account.signOutBody}
              </p>
              <div className="mt-4 flex gap-2">
                <button
                  type="button"
                  onClick={() => setConfirming(null)}
                  disabled={signingOut}
                  className="h-9 flex-1 rounded-full border border-line-strong text-xs font-medium text-ink transition-colors hover:bg-surface-sunken disabled:opacity-50"
                >
                  {t.account.signOutCancel}
                </button>
                <button
                  type="button"
                  // Out of the workspace and onto the sign-in screen: staying
                  // put would leave a signed-out visitor looking at a gate where
                  // the conversation used to be.
                  //
                  // `signingOut` is never cleared on success. The navigation
                  // unmounts this menu, and setting state on the way out is
                  // either a no-op or a warning depending on the React version.
                  onClick={() => {
                    setSigningOut(true);
                    void signOut()
                      .then(() => router.push("/signin?signed-out"))
                      .catch(() => setSigningOut(false));
                  }}
                  disabled={signingOut}
                  className="h-9 flex-1 rounded-full bg-gradient-to-b from-accent-fill-from to-accent-fill-to text-xs font-semibold text-on-accent transition-opacity hover:opacity-90 disabled:opacity-60"
                >
                  {signingOut ? t.account.signingOut : t.account.signOutConfirm}
                </button>
              </div>
            </div>
          ) : confirming === "delete" ? (
            <div className="p-4">
              <p className="text-sm font-medium text-ink">{t.account.deleteTitle}</p>
              <p className="mt-1.5 text-xs leading-5 text-ink-muted">
                {t.account.deleteBody}
              </p>
              {deleteFailed && (
                <p className="mt-3 rounded-xl border border-danger/40 bg-danger-soft p-2.5 text-xs leading-5 text-danger">
                  {t.account.deleteFailed}
                </p>
              )}
              <div className="mt-4 flex gap-2">
                <button
                  type="button"
                  onClick={() => setConfirming(null)}
                  disabled={deleting}
                  className="h-9 flex-1 rounded-full border border-line-strong text-xs font-medium text-ink transition-colors hover:bg-surface-sunken disabled:opacity-50"
                >
                  {t.account.deleteCancel}
                </button>
                <button
                  type="button"
                  onClick={() => void erase()}
                  disabled={deleting}
                  className="h-9 flex-1 rounded-full bg-danger text-xs font-semibold text-paper transition-opacity hover:opacity-90 disabled:opacity-60"
                >
                  {deleting ? t.account.deleting : t.account.deleteConfirm}
                </button>
              </div>
            </div>
          ) : (
            <div className="p-1.5">
              <button
                type="button"
                role="menuitem"
                onClick={() => setConfirming("signOut")}
                className="flex w-full items-center gap-2.5 rounded-xl px-2.5 py-2 text-left text-sm text-ink transition-colors hover:bg-surface-sunken"
              >
                <SignOutIcon />
                {t.account.signOut}
              </button>
              <button
                type="button"
                role="menuitem"
                onClick={() => setConfirming("delete")}
                className="flex w-full items-center gap-2.5 rounded-xl px-2.5 py-2 text-left text-sm text-danger transition-colors hover:bg-danger-soft"
              >
                <TrashIcon />
                {t.account.deleteAccount}
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function Allowance({
  left,
  label,
  unlimited,
}: {
  left: number | null;
  label: string;
  unlimited: string;
}) {
  return (
    <div
      className={`rounded-xl px-3 py-2 ${
        left === 0 ? "bg-danger-soft" : "bg-surface-sunken"
      }`}
    >
      <p
        className={`font-mono text-lg tabular-nums leading-none ${
          left === 0 ? "text-danger" : "text-ink"
        }`}
      >
        {left === null ? "∞" : left}
      </p>
      <p className="mt-1 truncate text-[11px] text-ink-faint">
        {left === null ? unlimited : label}
      </p>
    </div>
  );
}

function SignOutIcon() {
  return (
    <svg
      aria-hidden
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.7"
      strokeLinecap="round"
      strokeLinejoin="round"
      className="size-[18px] text-ink-faint"
    >
      <path d="M14 3h4a1 1 0 0 1 1 1v16a1 1 0 0 1-1 1h-4" />
      <path d="M10 8 6 12l4 4M6 12h9" />
    </svg>
  );
}

function TrashIcon() {
  return (
    <svg
      aria-hidden
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.7"
      strokeLinecap="round"
      strokeLinejoin="round"
      className="size-[18px]"
    >
      <path d="M4 7h16M10 4h4M9 7v12M15 7v12" />
      <path d="M6 7l1 13a1 1 0 0 0 1 1h8a1 1 0 0 0 1-1l1-13" />
    </svg>
  );
}
