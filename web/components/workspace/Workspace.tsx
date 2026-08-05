"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { useLocale } from "@/components/LocaleProvider";
import { useSession } from "@/components/SessionProvider";
import { AnswerCard } from "@/components/workspace/AnswerCard";
import { ConversationList } from "@/components/workspace/ConversationList";
import { DocumentList } from "@/components/workspace/DocumentList";
import { MyDocumentList } from "@/components/workspace/MyDocumentList";
import { SignInGate } from "@/components/workspace/SignInGate";
import { PdfViewer, type Highlight } from "@/components/workspace/PdfViewer";
import { StageProgress, type Stage } from "@/components/workspace/StageProgress";
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

type Message =
  | { kind: "question"; id: string; text: string }
  | { kind: "answer"; id: string; answer: Answer }
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
  const [ingesting, setIngesting] = useState<Record<string, DocumentStatus>>({});
  const [capabilities, setCapabilities] = useState<Capabilities | null>(null);
  const [uploadFailure, setUploadFailure] = useState<UploadFailure | null>(null);

  const [messages, setMessages] = useState<Message[]>([]);
  const [stage, setStage] = useState<Stage | null>(null);
  const [retrieval, setRetrieval] = useState<RetrievalComplete | null>(null);
  const [question, setQuestion] = useState("");
  const [highlight, setHighlight] = useState<Highlight | null>(null);
  const [activeCitation, setActiveCitation] = useState<string | null>(null);
  const [mobilePane, setMobilePane] = useState<Pane>("chat");

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
                { kind: "answer", id: `${id}:a`, answer: event.data },
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
        } else if (error instanceof ApiError && (error.isQuota || error.isBudget)) {
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

  const removeDocument = useCallback(
    async (documentId: string) => {
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
    },
    [],
  );

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

  const showCitation = useCallback(
    (citation: Citation, key: string) => {
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
    },
    [],
  );

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
      <div className="mb-2 flex gap-1 rounded-lg border border-line p-0.5 lg:hidden">
        {PANES.map((pane) => (
          <button
            key={pane}
            type="button"
            onClick={() => setMobilePane(pane)}
            aria-pressed={mobilePane === pane}
            className={`flex-1 rounded-md px-3 py-1.5 text-sm transition-colors ${
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
          className={`min-h-0 overflow-y-auto ${
            mobilePane === "documents" ? "" : "hidden"
          } lg:block`}
        >
          <h2 className="mb-2 text-xs font-medium uppercase tracking-wide text-ink-faint">
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
          <p className="mt-3 text-xs leading-5 text-ink-faint">
            {t.workspace.documentsNote}
          </p>

          <h2 className="mb-2 mt-6 text-xs font-medium uppercase tracking-wide text-ink-faint">
            {t.upload.title}
          </h2>
          <Uploader
            maxBytes={capabilities?.max_upload_bytes ?? 25 * 1024 * 1024}
            retentionHours={capabilities?.retention_hours ?? 24}
            disabled={!configured || !signedIn || documentsLeft === 0}
            onUploaded={onUploaded}
            onFailure={setUploadFailure}
          />
          {signedIn && documentsLeft !== null && (
            <p className="mt-1.5 text-[11px] text-ink-faint">
              {t.account.remaining}: {documentsLeft} {t.account.documents}
            </p>
          )}

          {uploadFailure && (
            <div className="mt-2 rounded-lg border border-danger/40 bg-danger-soft p-2.5">
              <p className="text-xs font-medium text-danger">
                {uploadFailure.title}
              </p>
              <p className="mt-1 text-[11px] leading-4 text-ink-muted">
                {uploadFailure.message}
              </p>
            </div>
          )}

          {signedIn && (
            <div className="mt-6">
              <ConversationList
                conversations={conversations}
                activeId={conversationId}
                onOpen={(conversation) => void openConversation(conversation)}
                onDelete={(id) => void removeConversation(id)}
                onNew={startNewChat}
              />
            </div>
          )}

          {mine.length > 0 && (
            <>
              <h2 className="mb-2 mt-6 text-xs font-medium uppercase tracking-wide text-ink-faint">
                {t.upload.yours}
              </h2>
              <MyDocumentList
                documents={mine}
                progress={ingesting}
                selectedId={selected?.id ?? null}
                onSelect={selectDocument}
                onDelete={(id) => void removeDocument(id)}
              />
              <p className="mt-2 text-[11px] leading-4 text-ink-faint">
                {t.upload.retentionNote.replace(
                  "{hours}",
                  String(capabilities?.retention_hours ?? 24),
                )}
              </p>
            </>
          )}
        </aside>

        {/* Conversation */}
        <section
          className={`min-h-0 flex-col rounded-lg border border-line bg-paper ${
            mobilePane === "chat" ? "flex" : "hidden"
          } lg:flex`}
        >
          <div
            ref={transcriptRef}
            className="min-h-0 flex-1 space-y-3 overflow-y-auto p-3"
          >
            {messages.length === 0 && stage === null && (
              <div className="px-1 pt-6">
                <h3 className="text-base font-medium text-ink">
                  {t.workspace.emptyTitle}
                </h3>
                <p className="mt-1.5 max-w-md text-sm leading-6 text-ink-muted">
                  {t.workspace.emptyBody}
                </p>
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
                          className="rounded-md border border-line bg-surface px-2.5 py-1.5 text-left text-sm text-ink-muted transition-colors hover:border-line-strong hover:text-ink"
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
                  <p
                    key={message.id}
                    className="ml-auto max-w-[85%] rounded-lg bg-surface-sunken px-3 py-2 text-sm leading-6 text-ink"
                  >
                    {message.text}
                  </p>
                );
              }
              if (message.kind === "refused") {
                return (
                  <div
                    key={message.id}
                    className="rounded-lg border border-refuse/35 bg-refuse-soft p-4"
                  >
                    <h3 className="text-sm font-semibold text-refuse">
                      {message.title}
                    </h3>
                    <p className="mt-1 text-sm leading-6 text-ink-muted">
                      {message.message}
                    </p>
                  </div>
                );
              }
              if (message.kind === "error") {
                return (
                  <div
                    key={message.id}
                    className="rounded-lg border border-danger/40 bg-danger-soft p-4"
                  >
                    <h3 className="text-sm font-semibold text-danger">
                      {t.workspace.errorTitle}
                    </h3>
                    <p className="mt-1 text-sm text-ink-muted">
                      {t.workspace.errorBody}
                    </p>
                  </div>
                );
              }
              return (
                <AnswerCard
                  key={message.id}
                  answer={message.answer}
                  activeCitation={activeCitation}
                  onCite={(citation) => {
                    const index = message.answer.citations.indexOf(citation);
                    showCitation(citation, `${citation.context_id}:${index}`);
                  }}
                />
              );
            })}

            {stage !== null && (
              <StageProgress stage={stage} retrieval={retrieval} />
            )}
          </div>

          <div className="border-t border-line p-3">
            {/* Three states, and only one of them is a composer. Showing a
                disabled input to somebody who is out of questions reads as a
                broken page; saying so does not. */}
            {!signedIn ? (
              <SignInGate />
            ) : outOfQuestions ? (
              <div className="rounded-lg border border-refuse/35 bg-refuse-soft p-4">
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
                    className="min-w-0 flex-1 rounded-lg border border-line bg-surface px-3 py-2 text-sm text-ink outline-none placeholder:text-ink-faint focus:border-accent"
                  />
                  {stage === null ? (
                    <button
                      type="submit"
                      disabled={
                        !selected || !canAsk || question.trim().length === 0
                      }
                      className="shrink-0 rounded-lg bg-ink px-4 text-sm font-medium text-paper transition-opacity disabled:opacity-40"
                    >
                      {t.workspace.ask}
                    </button>
                  ) : (
                    <button
                      type="button"
                      onClick={() => abortRef.current?.abort()}
                      className="shrink-0 rounded-lg border border-line-strong px-4 text-sm font-medium text-ink"
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
          className={`min-h-0 overflow-hidden rounded-lg border border-line ${
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
