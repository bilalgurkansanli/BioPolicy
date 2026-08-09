"use client";

import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from "react";

import { BrandAvatar, UserAvatar } from "@/components/Avatar";
import { useLocale } from "@/components/LocaleProvider";
import { useSession } from "@/components/SessionProvider";
import { AnswerCard } from "@/components/workspace/AnswerCard";
import { ConsideredPanel } from "@/components/workspace/ConsideredPanel";
import { ConversationList } from "@/components/workspace/ConversationList";
import { DocumentList } from "@/components/workspace/DocumentList";
import { MyDocumentList } from "@/components/workspace/MyDocumentList";
import { InjectionNotice } from "@/components/workspace/InjectionNotice";
import { PolicyProfile } from "@/components/workspace/PolicyProfile";
import { RefusalTour } from "@/components/workspace/RefusalTour";
import { SignInGate } from "@/components/workspace/SignInGate";
import { PdfViewer, type Highlight } from "@/components/workspace/PdfViewer";
import {
  StageProgress,
  type Stage,
} from "@/components/workspace/StageProgress";
import { Uploader, type UploadFailure } from "@/components/workspace/Uploader";
import {
  ApiError,
  askQuestion,
  deleteConversation,
  deleteDocument,
  fetchCapabilities,
  fetchConversation,
  fetchConversations,
  fetchDocumentStatus,
  fetchMyDocuments,
  fetchSamples,
  fetchViewingUrl,
} from "@/lib/api";
import { SUGGESTIONS } from "@/lib/i18n";
import { NotSignedInError } from "@/lib/supabase";
import type {
  Answer,
  Capabilities,
  Citation,
  ConsideredChunk,
  ConversationSummary,
  DocumentStatus,
  DocumentSummary,
  HistoryTurn,
  RetrievalComplete,
} from "@/lib/types";

// How often an in-flight ingestion is re-checked. Ingestion of a native PDF
// finishes in a few seconds and a scanned one in tens of seconds, so this is
// frequent enough to feel live without polling a finished document to death.
const STATUS_POLL_MS = 2000;

/** The panes the small-screen switcher moves between. */
const PANES = ["documents", "chat", "viewer"] as const;
type Pane = (typeof PANES)[number];

/** The two halves of the sidebar. */
const SIDEBAR_TABS = ["documents", "chats"] as const;

type Message =
  | { kind: "question"; id: string; text: string }
  // `considered` is present on a live answer and absent on one restored from
  // history — the passages a question retrieved are not stored with the turn.
  // Absent rather than empty, so the panel can tell "nothing was unused" from
  // "we no longer know what was retrieved".
  | {
      kind: "answer";
      id: string;
      answer: Answer;
      considered?: ConsideredChunk[];
    }
  // A limit is not a failure: the system worked and declined. Rendered as its
  // own kind so it does not look like something broke.
  | { kind: "refused"; id: string; title: string; message: string }
  | { kind: "error"; id: string };

export function Workspace() {
  const { locale, t } = useLocale();

  const [documents, setDocuments] = useState<DocumentSummary[] | null>(null);
  const [documentsFailed, setDocumentsFailed] = useState(false);
  const [selected, setSelected] = useState<DocumentSummary | null>(null);
  // Tagged with the document it belongs to, so switching documents does not
  // need a synchronous reset — a URL for the previous document simply stops
  // matching.
  const [viewing, setViewing] = useState<{
    documentId: string;
    url: string;
  } | null>(null);

  const { signedIn, me, refresh: refreshAccount, configured } = useSession();

  const [conversations, setConversations] = useState<ConversationSummary[]>([]);
  const [conversationId, setConversationId] = useState<string | null>(null);

  const [mine, setMine] = useState<DocumentSummary[]>([]);
  const [ingesting, setIngesting] = useState<Record<string, DocumentStatus>>(
    {},
  );
  const [capabilities, setCapabilities] = useState<Capabilities | null>(null);
  const [uploadFailure, setUploadFailure] = useState<UploadFailure | null>(
    null,
  );

  const [messages, setMessages] = useState<Message[]>([]);
  const [stage, setStage] = useState<Stage | null>(null);
  const [retrieval, setRetrieval] = useState<RetrievalComplete | null>(null);
  const [question, setQuestion] = useState("");
  const [highlight, setHighlight] = useState<Highlight | null>(null);
  const [activeCitation, setActiveCitation] = useState<string | null>(null);
  const [mobilePane, setMobilePane] = useState<Pane>("chat");
  // The sidebar holds two things that grow without limit — the documents
  // and the conversations — and stacking them made one column that scrolled
  // past everything else. One at a time, each with its own scroll.
  const [sidebarTab, setSidebarTab] = useState<"documents" | "chats">(
    "documents",
  );

  const abortRef = useRef<AbortController | null>(null);
  const transcriptRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const controller = new AbortController();
    fetchSamples(controller.signal)
      .then((samples) => {
        setDocuments(samples);
        setSelected((current) => current ?? samples[0] ?? null);
      })
      .catch((error: unknown) => {
        if ((error as Error).name !== "AbortError") setDocumentsFailed(true);
      });
    return () => controller.abort();
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    fetchCapabilities(controller.signal)
      .then(setCapabilities)
      .catch(() => undefined);
    return () => controller.abort();
  }, []);

  // Everything owned by the account, re-read whenever the session changes —
  // including the moment a sign-in redirect lands back on this page.
  useEffect(() => {
    if (!signedIn) return;
    const controller = new AbortController();
    void (async () => {
      try {
        const [documents, threads] = await Promise.all([
          fetchMyDocuments(controller.signal),
          fetchConversations(controller.signal),
        ]);
        if (controller.signal.aborted) return;
        setMine(documents);
        setConversations(threads);
      } catch {
        // A session that expired between the check and the call. The gate
        // renders from `signedIn`, which the auth listener corrects.
      }
    })();
    return () => controller.abort();
  }, [signedIn]);

  // Poll anything still moving through the pipeline.
  useEffect(() => {
    const pending = mine.filter(
      (document) =>
        (ingesting[document.id]?.status ?? document.status) !== "ready" &&
        (ingesting[document.id]?.status ?? document.status) !== "failed",
    );
    if (pending.length === 0) return;

    const timer = setInterval(() => {
      for (const document of pending) {
        void fetchDocumentStatus(document.id)
          .then((status) => {
            setIngesting((current) => ({ ...current, [document.id]: status }));
            if (status.status === "ready") {
              setMine((current) =>
                current.map((item) =>
                  item.id === document.id
                    ? {
                        ...item,
                        status: "ready",
                        page_count: status.page_count,
                        source_type: status.source_type,
                        detected_lang: status.detected_lang,
                      }
                    : item,
                ),
              );
            }
          })
          .catch(() => undefined);
      }
    }, STATUS_POLL_MS);
    return () => clearInterval(timer);
  }, [mine, ingesting]);

  useEffect(() => {
    if (!selected) return;
    const controller = new AbortController();
    const documentId = selected.id;
    fetchViewingUrl(documentId, controller.signal)
      .then(({ url }) => setViewing({ documentId, url }))
      .catch(() => undefined);
    return () => controller.abort();
  }, [selected]);

  useEffect(() => {
    transcriptRef.current?.scrollTo({
      top: transcriptRef.current.scrollHeight,
      behavior: "smooth",
    });
  }, [messages, stage]);

  const selectDocument = useCallback((document: DocumentSummary) => {
    // Switching documents clears the conversation. Carrying a Turkish home
    // policy's history into a question about a commercial liability contract
    // would let a follow-up resolve against the wrong document entirely.
    abortRef.current?.abort();
    setSelected(document);
    // A thread belongs to one document. Carrying it across would collect
    // answers about one policy under a conversation titled after another.
    setConversationId(null);
    setMessages([]);
    setStage(null);
    setRetrieval(null);
    setHighlight(null);
    setActiveCitation(null);
  }, []);

  const ask = useCallback(
    async (text: string) => {
      const trimmed = text.trim();
      if (!trimmed || !selected || stage !== null) return;

      const history: HistoryTurn[] = [];
      for (const message of messages) {
        if (message.kind === "question") {
          history.push({ role: "user", content: message.text });
        } else if (message.kind === "answer" && !message.answer.suppressed) {
          history.push({ role: "assistant", content: message.answer.answer });
        }
      }

      const id = `${Date.now()}`;
      setMessages((current) => [
        ...current,
        { kind: "question", id, text: trimmed },
      ]);
      setQuestion("");
      setRetrieval(null);
      setStage("retrieval");

      const controller = new AbortController();
      abortRef.current = controller;
      let considered: ConsideredChunk[] = [];

      try {
        for await (const event of askQuestion(
          {
            documentId: selected.id,
            question: trimmed,
            language: locale,
            // Bounded to the last four exchanges. Chunks are re-retrieved every
            // turn, so history only has to be long enough to resolve a pronoun.
            history: history.slice(-8),
            conversationId,
          },
          controller.signal,
        )) {
          switch (event.event) {
            case "retrieval_complete":
              setRetrieval(event.data);
              // Held locally as well as in state: `done` arrives in the same
              // loop and reading it back through `retrieval` would read the
              // value this closure captured, which is the previous turn's.
              considered = event.data.considered ?? [];
              break;
            case "answering":
              setStage("answering");
              break;
            case "verifying":
              setStage("verifying");
              break;
            case "done":
              setMessages((current) => [
                ...current,
                {
                  kind: "answer",
                  id: `${id}:a`,
                  answer: event.data,
                  considered,
                },
              ]);
              if (event.data.conversation_id) {
                setConversationId(event.data.conversation_id);
              }
              break;
            case "error":
              setMessages((current) => [
                ...current,
                { kind: "error", id: `${id}:e` },
              ]);
              break;
            default:
              break;
          }
        }
      } catch (error) {
        if ((error as Error).name === "AbortError") {
          // Stopped on purpose. Not a failure to report.
        } else if (
          error instanceof ApiError &&
          (error.isQuota || error.isBudget)
        ) {
          setMessages((current) => [
            ...current,
            {
              kind: "refused",
              id: `${id}:l`,
              title: error.isQuota ? t.upload.quotaTitle : t.upload.budgetTitle,
              message: error.message,
            },
          ]);
        } else if (error instanceof NotSignedInError) {
          // The session lapsed mid-question. The gate takes over on the next
          // render; nothing useful can be said in the transcript.
        } else {
          setMessages((current) => [
            ...current,
            { kind: "error", id: `${id}:e` },
          ]);
        }
      } finally {
        abortRef.current = null;
        setStage(null);
        // The allowance moved. Re-read it rather than decrementing a local
        // copy: the server is the only thing that knows what was actually
        // counted, and a question can be refused after it was sent.
        void refreshAccount();
        void fetchConversations()
          .then(setConversations)
          .catch(() => undefined);
      }
    },
    [conversationId, locale, messages, refreshAccount, selected, stage, t],
  );

  const onUploaded = useCallback((documentId: string, filename: string) => {
    // Shown immediately as `queued` rather than waiting for a refetch: the file
    // has landed and the visitor should see that before ingestion finishes.
    setMine((current) => [
      {
        id: documentId,
        filename,
        page_count: null,
        source_type: null,
        detected_lang: null,
        status: "queued",
        is_sample: false,
      },
      ...current,
    ]);
  }, []);

  const removeDocument = useCallback(async (documentId: string) => {
    try {
      await deleteDocument(documentId);
    } catch {
      // Deleting something already gone is the outcome we wanted anyway.
    }
    setMine((current) => current.filter((item) => item.id !== documentId));
    setIngesting((current) => {
      const next = { ...current };
      delete next[documentId];
      return next;
    });
    setSelected((current) => (current?.id === documentId ? null : current));
  }, []);

  const openConversation = useCallback(
    async (conversation: ConversationSummary) => {
      abortRef.current?.abort();
      const document =
        documents?.find((item) => item.id === conversation.document_id) ??
        mine.find((item) => item.id === conversation.document_id);
      if (!document) return;

      setSelected(document);
      setConversationId(conversation.id);
      setStage(null);
      setHighlight(null);
      setActiveCitation(null);

      try {
        const { messages: stored } = await fetchConversation(conversation.id);
        setMessages(
          stored.map((message, index) =>
            message.role === "user"
              ? { kind: "question", id: message.id, text: message.content }
              : {
                  kind: "answer",
                  id: message.id,
                  // Rebuilt into the same shape a live answer has, so one
                  // renderer covers both. The fields a stored turn cannot
                  // carry — the cost of a call made yesterday, the confidence
                  // the model reported — are absent rather than invented.
                  answer: {
                    conversation_id: conversation.id,
                    // A stored turn does not record whether it came from the
                    // cache, and inventing `false` would be a claim nobody
                    // made. `null` here means "computed", which is what the
                    // cost line below already says by showing $0.0000.
                    cached: null,
                    answer: message.content,
                    refused: message.refused,
                    suppressed: message.suppressed,
                    suppression_reason: null,
                    confidence: "high",
                    caveats: [],
                    groundedness: message.groundedness,
                    verified: message.groundedness !== null,
                    citations: message.citations,
                    dropped_citations: 0,
                    cost_usd: 0,
                  },
                  key: index,
                },
          ) as Message[],
        );
      } catch {
        setMessages([]);
      }
    },
    [documents, mine],
  );

  const removeConversation = useCallback(
    async (id: string) => {
      try {
        await deleteConversation(id);
      } catch {
        // Deleting something already gone is the outcome we wanted.
      }
      setConversations((current) => current.filter((item) => item.id !== id));
      setConversationId((current) => (current === id ? null : current));
      setMessages((current) => (conversationId === id ? [] : current));
    },
    [conversationId],
  );

  const startNewChat = useCallback(() => {
    abortRef.current?.abort();
    setConversationId(null);
    setMessages([]);
    setStage(null);
  }, []);

  const showCitation = useCallback((citation: Citation, key: string) => {
    setActiveCitation(key);
    if (citation.bbox) {
      setHighlight({
        page: citation.page,
        pageEnd: citation.page_end,
        bbox: citation.bbox,
        quote: citation.quote,
        nonce: Date.now(),
      });
    }
    setMobilePane("viewer");
  }, []);

  /**
   * Open a passage the answer did not cite.
   *
   * The snippet is used as the quote, so the viewer locates the opening of the
   * chunk precisely when it can. When it cannot — the snippet is truncated, and
   * a cut mid-word will not match — the block box takes over and the viewer
   * marks the region as approximate. That is the honest fallback rather than a
   * failure: nothing here claims to be a citation.
   */
  const showPassage = useCallback((chunk: ConsideredChunk) => {
    if (!chunk.bbox) return;
    setActiveCitation(null);
    setHighlight({
      page: chunk.page,
      pageEnd: chunk.page_end,
      bbox: chunk.bbox,
      quote: chunk.snippet.replace(/…$/, "").trim(),
      nonce: Date.now(),
    });
    setMobilePane("viewer");
  }, []);

  // `null` means unlimited, which is why this is not `?? 0`. Treating an
  // absent number as zero would lock the owner's own account out of the demo.
  const questionsLeft = me?.allowance.questions_left ?? null;
  const documentsLeft = me?.allowance.documents_left ?? null;
  const outOfQuestions = signedIn && questionsLeft === 0;
  const canAsk = signedIn && !outOfQuestions;

  const suggestions = selected
    ? (SUGGESTIONS[selected.filename]?.[locale] ?? [])
    : [];

  return (
    /* `min-h-0` is not decoration. A flex item defaults to `min-height: auto`,
       which refuses to shrink below its content — so this wrapper grew to the
       height of the whole PDF, pushed the grid past the viewport, and left the
       overflow clipped by the page. Every ancestor between the fixed-height
       page and the scroll container needs it; one missing link is enough. */
    <div className="mx-auto flex min-h-0 w-full max-w-[1600px] flex-1 flex-col px-3 py-3 sm:px-4">
      {/* Three panes, one at a time below `lg`. The viewer used to share the
          "documents" tab with the picker, which meant the tab labelled "sample
          documents" showed the PDF and the one labelled "answer" showed the
          picker too. */}
      <div className="mb-2 flex gap-1 rounded-full border border-line p-0.5 lg:hidden">
        {PANES.map((pane) => (
          <button
            key={pane}
            type="button"
            onClick={() => setMobilePane(pane)}
            aria-pressed={mobilePane === pane}
            className={`flex-1 rounded-full px-3 py-1.5 text-sm transition-colors ${
              mobilePane === pane
                ? "bg-ink text-paper"
                : "text-ink-muted hover:text-ink"
            }`}
          >
            {t.workspace.panes[pane]}
          </button>
        ))}
      </div>

      {/* WHY `auto-rows-[minmax(0,1fr)]`: without it the row is sized by its
          content, so a four-page PDF stretched the row to the height of the
          whole document. The scroll container then resolved `h-full` against
          that stretched row, matched its own content exactly, and had nothing
          left to scroll — while everything below the fold sat outside the
          `overflow-hidden` page and was unreachable. `minmax(0, …)` is what
          lets the row shrink below its content; `1fr` alone will not. */}
      <div className="grid min-h-0 flex-1 auto-rows-[minmax(0,1fr)] gap-3 lg:grid-cols-[260px_minmax(0,1fr)_minmax(0,1fr)]">
        {/* Document picker */}
        <aside
          className={`flex min-h-0 flex-col ${
            mobilePane === "documents" ? "" : "hidden"
          } lg:flex`}
        >
          {/* Only worth a switcher once there is a second thing to switch to:
              signed out, there are no conversations and the tabs would be a
              control with one option. */}
          {signedIn && (
            <div
              role="tablist"
              className="mb-3 flex shrink-0 gap-1 rounded-full border border-line p-0.5"
            >
              {SIDEBAR_TABS.map((tab) => {
                const active = sidebarTab === tab;
                return (
                  <button
                    key={tab}
                    type="button"
                    role="tab"
                    aria-selected={active}
                    onClick={() => setSidebarTab(tab)}
                    className={`flex-1 rounded-full px-3 py-1.5 text-xs font-medium transition-colors ${
                      active
                        ? "bg-accent-soft text-accent"
                        : "text-ink-muted hover:text-ink"
                    }`}
                  >
                    {tab === "documents"
                      ? t.workspace.panes.documents
                      : t.conversations.title}
                    {tab === "chats" && conversations.length > 0 && (
                      <span className="ml-1.5 font-mono text-[11px] tabular-nums opacity-70">
                        {conversations.length}
                      </span>
                    )}
                  </button>
                );
              })}
            </div>
          )}

          <div className="min-h-0 flex-1 overflow-y-auto">
            {signedIn && sidebarTab === "chats" ? (
              <ConversationList
                conversations={conversations}
                activeId={conversationId}
                onOpen={(conversation) => void openConversation(conversation)}
                onDelete={(id) => void removeConversation(id)}
                onNew={startNewChat}
                titled={false}
              />
            ) : (
              // A column, not a stack: the samples and the uploader are a fixed
              // height and stay put, and the one part that grows without limit
              // — what this visitor has uploaded — takes the space that is left
              // and scrolls inside it. Stacked, a fourth upload pushed the
              // samples off the top and the panel became one long scroll.
              <div className="flex h-full min-h-0 flex-col">
                <h2 className="mb-2 shrink-0 text-xs font-medium uppercase tracking-wide text-ink-faint">
                  {t.workspace.documents}
                </h2>
                {documentsFailed && (
                  <p className="text-sm text-danger">
                    {t.workspace.loadDocumentsFailed}
                  </p>
                )}
                {documents === null && !documentsFailed && (
                  <p className="text-sm text-ink-faint">
                    {t.workspace.loadingDocuments}
                  </p>
                )}
                {documents && (
                  <DocumentList
                    documents={documents}
                    selectedId={selected?.id ?? null}
                    onSelect={selectDocument}
                  />
                )}
                <p className="mt-3 shrink-0 text-xs leading-5 text-ink-faint">
                  {t.workspace.documentsNote}
                </p>

                {/* Two headings for one concern once there are uploads: the
                    dropzone becomes the first row of the visitor's own list
                    rather than a section of its own. */}
                <h2 className="mb-2 mt-6 shrink-0 text-xs font-medium uppercase tracking-wide text-ink-faint">
                  {mine.length > 0 ? t.upload.yours : t.upload.title}
                </h2>
                <div className="shrink-0">
                  <Uploader
                    maxBytes={capabilities?.max_upload_bytes ?? 25 * 1024 * 1024}
                    retentionHours={capabilities?.retention_hours ?? 24}
                    disabled={!configured || !signedIn || documentsLeft === 0}
                    onUploaded={onUploaded}
                    onFailure={setUploadFailure}
                    compact={mine.length > 0}
                  />
                  {signedIn && documentsLeft !== null && mine.length === 0 && (
                    <p className="mt-1.5 text-[11px] text-ink-faint">
                      {t.account.remaining}: {documentsLeft} {t.account.documents}
                    </p>
                  )}

                  {uploadFailure && (
                    <div className="mt-2 rounded-xl border border-danger/40 bg-danger-soft p-2.5">
                      <p className="text-xs font-medium text-danger">
                        {uploadFailure.title}
                      </p>
                      <p className="mt-1 text-[11px] leading-4 text-ink-muted">
                        {uploadFailure.message}
                      </p>
                    </div>
                  )}
                </div>

                {mine.length > 0 && (
                  <>
                    {/* A floor as well as a ceiling: on a short window the
                        fixed content above can leave this box a single row,
                        which is a scrollbar around nothing. Below the floor the
                        panel itself starts scrolling instead. */}
                    <div className="mt-2 min-h-36 flex-1 overflow-y-auto">
                      <MyDocumentList
                        documents={mine}
                        progress={ingesting}
                        selectedId={selected?.id ?? null}
                        onSelect={selectDocument}
                        onDelete={(id) => void removeDocument(id)}
                      />
                    </div>
                    <p className="mt-2 shrink-0 text-[11px] leading-4 text-ink-faint">
                      {signedIn && documentsLeft !== null && (
                        <>
                          {t.account.remaining}: {documentsLeft}{" "}
                          {t.account.documents} ·{" "}
                        </>
                      )}
                      {t.upload.retentionNote.replace(
                        "{hours}",
                        String(capabilities?.retention_hours ?? 24),
                      )}
                    </p>
                  </>
                )}
              </div>
            )}
          </div>
        </aside>

        {/* Conversation */}
        <section
          className={`min-h-0 flex-col rounded-xl border border-line bg-paper ${
            mobilePane === "chat" ? "flex" : "hidden"
          } lg:flex`}
        >
          <div
            ref={transcriptRef}
            className="min-h-0 flex-1 space-y-4 overflow-y-auto p-3"
          >
            {/* Above the transcript, not inside it: this is a fact about the
                document, and it stays true for every answer below it. */}
            {selected?.injection_findings && (
              <InjectionNotice findings={selected.injection_findings} />
            )}
            {/* Also above the transcript, and for the same reason — but the
                argument is stronger here. The profile is what somebody who has
                not read their policy needs *before* they can think of a
                question, so burying it under the empty state (where it would
                vanish the moment they asked one) would put it exactly where it
                stops being useful. */}
            {selected && (
              <PolicyProfile
                // Remount per document rather than reset on change: fresh
                // state comes free, and the alternative is a setState inside
                // the fetch effect.
                key={selected.id}
                documentId={selected.id}
                signedIn={signedIn}
                onCite={showCitation}
                activeCitation={activeCitation}
              />
            )}
            {messages.length === 0 && stage === null && (
              <div className="px-1 pt-6">
                <h3 className="text-base font-medium text-ink">
                  {t.workspace.emptyTitle}
                </h3>
                <p className="mt-1.5 max-w-md text-sm leading-6 text-ink-muted">
                  {t.workspace.emptyBody}
                </p>

                {/* Placed in the empty state, which is the only moment a
                    visitor has not yet spent a question on something easy. */}
                <RefusalTour />
                {suggestions.length > 0 && (
                  <div className="mt-5">
                    <h4 className="text-xs font-medium uppercase tracking-wide text-ink-faint">
                      {t.workspace.suggestions}
                    </h4>
                    <div className="mt-2 flex flex-col items-start gap-1.5">
                      {suggestions.map((suggestion) => (
                        <button
                          key={suggestion}
                          type="button"
                          disabled={!canAsk}
                          onClick={() => void ask(suggestion)}
                          className="rounded-full border border-accent/20 bg-accent-soft px-3.5 py-1.5 text-left text-sm text-accent transition-colors hover:border-accent/40 hover:bg-accent-soft/70 disabled:opacity-50"
                        >
                          {suggestion}
                        </button>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            )}

            {messages.map((message) => {
              if (message.kind === "question") {
                return (
                  <Turn key={message.id} side="user">
                    <p className="rounded-2xl rounded-tr-md bg-gradient-to-br from-accent-fill-from to-accent-fill-to px-3.5 py-2 text-sm leading-6 text-on-accent shadow-[0_8px_20px_-14px_var(--accent-glow)]">
                      {message.text}
                    </p>
                  </Turn>
                );
              }
              if (message.kind === "refused") {
                return (
                  <Turn key={message.id} side="assistant">
                    <div className="rounded-2xl rounded-tl-md border border-refuse/35 bg-refuse-soft p-4">
                      <h3 className="text-sm font-semibold text-refuse">
                        {message.title}
                      </h3>
                      <p className="mt-1 text-sm leading-6 text-ink-muted">
                        {message.message}
                      </p>
                    </div>
                  </Turn>
                );
              }
              if (message.kind === "error") {
                return (
                  <Turn key={message.id} side="assistant">
                    <div className="rounded-2xl rounded-tl-md border border-danger/40 bg-danger-soft p-4">
                      <h3 className="text-sm font-semibold text-danger">
                        {t.workspace.errorTitle}
                      </h3>
                      <p className="mt-1 text-sm text-ink-muted">
                        {t.workspace.errorBody}
                      </p>
                    </div>
                  </Turn>
                );
              }
              return (
                <Turn key={message.id} side="assistant">
                  <AnswerCard
                    answer={message.answer}
                    activeCitation={activeCitation}
                    onCite={(citation) => {
                      const index = message.answer.citations.indexOf(citation);
                      showCitation(citation, `${citation.context_id}:${index}`);
                    }}
                  >
                    {message.considered && (
                      <ConsideredPanel
                        considered={message.considered}
                        citations={message.answer.citations}
                        onOpen={showPassage}
                      />
                    )}
                  </AnswerCard>
                </Turn>
              );
            })}

            {stage !== null && (
              <Turn side="assistant">
                <StageProgress stage={stage} retrieval={retrieval} />
              </Turn>
            )}
          </div>

          <div className="border-t border-line p-3">
            {/* Three states, and only one of them is a composer. Showing a
                disabled input to somebody who is out of questions reads as a
                broken page; saying so does not. */}
            {!signedIn ? (
              <SignInGate />
            ) : outOfQuestions ? (
              <div className="rounded-xl border border-refuse/35 bg-refuse-soft p-4">
                <h3 className="text-sm font-semibold text-refuse">
                  {t.account.exhaustedTitle}
                </h3>
                <p className="mt-1.5 text-sm leading-6 text-ink-muted">
                  {t.account.exhaustedBody.replace(
                    "{limit}",
                    String(me?.allowance.questions_limit ?? 0),
                  )}
                </p>
              </div>
            ) : (
              <form
                onSubmit={(event) => {
                  event.preventDefault();
                  void ask(question);
                }}
              >
                <div className="flex gap-2">
                  <input
                    value={question}
                    onChange={(event) => setQuestion(event.target.value)}
                    placeholder={t.workspace.askPlaceholder}
                    maxLength={1000}
                    disabled={!selected}
                    className="min-w-0 flex-1 rounded-full border border-line bg-surface px-4 py-2.5 text-sm text-ink outline-none transition-shadow placeholder:text-ink-faint focus:border-accent focus:shadow-[0_0_0_3px_color-mix(in_srgb,var(--accent)_18%,transparent)]"
                  />
                  {stage === null ? (
                    <button
                      type="submit"
                      disabled={
                        !selected || !canAsk || question.trim().length === 0
                      }
                      className="cta-gradient cta-sheen shrink-0 rounded-full px-5 text-sm font-semibold text-on-accent shadow-[0_6px_18px_-8px_var(--accent-glow)] disabled:opacity-40 disabled:shadow-none"
                    >
                      {/* Wrapped so it sits above the sheen rather than under
                          it: `.cta-sheen` lifts element children only. */}
                      <span>{t.workspace.ask}</span>
                    </button>
                  ) : (
                    <button
                      type="button"
                      onClick={() => abortRef.current?.abort()}
                      className="shrink-0 rounded-full border border-line-strong px-5 text-sm font-medium text-ink transition-colors hover:bg-surface-sunken"
                    >
                      {t.workspace.stop}
                    </button>
                  )}
                </div>
                {questionsLeft !== null && (
                  <p className="mt-2 text-[11px] text-ink-faint">
                    {t.account.remaining}: {questionsLeft} {t.account.questions}
                  </p>
                )}
              </form>
            )}
            <p className="mt-2 text-[11px] text-ink-faint">
              {t.workspace.disclaimer}
            </p>
          </div>
        </section>

        {/* Document */}
        <section
          className={`min-h-0 overflow-hidden rounded-xl border border-line ${
            mobilePane === "viewer" ? "" : "hidden"
          } lg:block`}
        >
          <PdfViewer
            documentId={selected?.id ?? null}
            url={
              viewing && viewing.documentId === selected?.id
                ? viewing.url
                : null
            }
            highlight={highlight}
          />
        </section>
      </div>
    </div>
  );
}

/**
 * One side of the conversation, with a face on it.
 *
 * The two sides are told apart by more than colour: the question sits on the
 * right behind the visitor's own picture, the answer on the left behind the
 * mark. A transcript read at a glance should say who said what before a single
 * word of it is read.
 */
function Turn({
  side,
  children,
}: {
  side: "user" | "assistant";
  children: ReactNode;
}) {
  const user = side === "user";
  return (
    <div
      className={`flex items-start gap-2.5 ${user ? "flex-row-reverse" : ""}`}
    >
      <div className="mt-0.5">
        {user ? <UserAvatar size={28} /> : <BrandAvatar size={28} />}
      </div>
      {/* The answer carries citations and a cost line, so it takes the width it
          needs; a question is a sentence and is capped so it reads as one. */}
      <div className={user ? "min-w-0 max-w-[85%]" : "min-w-0 flex-1"}>
        {children}
      </div>
    </div>
  );
}
