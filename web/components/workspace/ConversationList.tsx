"use client";

import { useState } from "react";

import { useLocale } from "@/components/LocaleProvider";
import type { ConversationSummary } from "@/lib/types";

/**
 * Saved chats, newest first.
 *
 * A conversation can outlive the document it is about — uploads are deleted
 * after 24 hours and the chat is not. Those are shown, labelled, and not
 * openable: reopening one would put citations on screen with no document left
 * to check them against, which is the one thing this interface must never do.
 */
export function ConversationList({
  conversations,
  activeId,
  onOpen,
  onDelete,
  onNew,
  titled = true,
}: {
  conversations: ConversationSummary[];
  activeId: string | null;
  onOpen: (conversation: ConversationSummary) => void;
  onDelete: (id: string) => void;
  onNew: () => void;
  /** False where a tab already names the panel, so the heading would repeat it. */
  titled?: boolean;
}) {
  const { t } = useLocale();
  const [confirming, setConfirming] = useState<string | null>(null);

  return (
    <div>
      {titled ? (
        <div className="mb-2 flex items-center justify-between gap-2">
          <h2 className="text-xs font-medium uppercase tracking-wide text-ink-faint">
            {t.conversations.title}
          </h2>
          <button
            type="button"
            onClick={onNew}
            className="rounded-lg border border-line px-2 py-0.5 text-[11px] text-ink-muted transition-colors hover:border-line-strong hover:text-ink"
          >
            {t.conversations.newChat}
          </button>
        </div>
      ) : (
        // Named by the tab, so the row is the action alone — and with the whole
        // width to itself it reads as the thing to do here.
        <button
          type="button"
          onClick={onNew}
          className="mb-2.5 w-full rounded-xl border border-dashed border-line-strong py-2 text-xs font-medium text-ink-muted transition-colors hover:border-accent/50 hover:text-accent"
        >
          + {t.conversations.newChat}
        </button>
      )}

      {conversations.length === 0 ? (
        <p className="text-xs text-ink-faint">{t.conversations.empty}</p>
      ) : (
        <ul className="space-y-1.5">
          {conversations.map((conversation) => {
            const active = conversation.id === activeId;
            const openable = conversation.document_exists;
            return (
              <li
                key={conversation.id}
                className={`rounded-xl border px-2.5 py-2 transition-colors ${
                  active
                    ? "border-accent bg-accent-soft"
                    : "border-line bg-surface"
                }`}
              >
                <div className="flex items-start gap-2">
                  <button
                    type="button"
                    disabled={!openable}
                    onClick={() => onOpen(conversation)}
                    className={`min-w-0 flex-1 text-left ${
                      openable ? "cursor-pointer" : "cursor-default opacity-60"
                    }`}
                  >
                    <span className="block truncate text-xs leading-5 text-ink">
                      {conversation.title || "…"}
                    </span>
                    <span className="mt-0.5 block truncate text-[11px] text-ink-faint">
                      {openable
                        ? conversation.document_filename
                        : t.conversations.documentGone}
                      {" · "}
                      {conversation.message_count} {t.conversations.messages}
                    </span>
                  </button>

                  {confirming !== conversation.id && (
                    <button
                      type="button"
                      onClick={() => setConfirming(conversation.id)}
                      aria-label={t.conversations.remove}
                      title={t.conversations.remove}
                      className="shrink-0 rounded p-0.5 text-ink-faint transition-colors hover:text-danger"
                    >
                      <svg
                        aria-hidden
                        viewBox="0 0 16 16"
                        className="size-3.5"
                        fill="none"
                        stroke="currentColor"
                        strokeWidth="1.4"
                      >
                        <path d="M3 4h10M6.5 4V2.8h3V4M5 4l.6 9h4.8L11 4" />
                      </svg>
                    </button>
                  )}
                </div>

                {confirming === conversation.id && (
                  <div className="mt-2 flex items-center gap-2">
                    <span className="text-[11px] text-ink-muted">
                      {t.conversations.confirmRemove}
                    </span>
                    <button
                      type="button"
                      onClick={() => {
                        setConfirming(null);
                        onDelete(conversation.id);
                      }}
                      className="rounded border border-danger/50 px-1.5 py-0.5 text-[11px] text-danger"
                    >
                      {t.conversations.confirmYes}
                    </button>
                    <button
                      type="button"
                      onClick={() => setConfirming(null)}
                      className="rounded border border-line px-1.5 py-0.5 text-[11px] text-ink-muted"
                    >
                      {t.conversations.confirmNo}
                    </button>
                  </div>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
