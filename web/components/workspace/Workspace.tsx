"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { useLocale } from "@/components/LocaleProvider";
import { AnswerCard } from "@/components/workspace/AnswerCard";
import { DocumentList } from "@/components/workspace/DocumentList";
import { PdfViewer, type Highlight } from "@/components/workspace/PdfViewer";
import { StageProgress, type Stage } from "@/components/workspace/StageProgress";
import { askQuestion, fetchSamples, fetchViewingUrl } from "@/lib/api";
import { SUGGESTIONS } from "@/lib/i18n";
import type {
  Answer,
  Citation,
  DocumentSummary,
  HistoryTurn,
  RetrievalComplete,
} from "@/lib/types";

type Message =
  | { kind: "question"; id: string; text: string }
  | { kind: "answer"; id: string; answer: Answer }
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

  const [messages, setMessages] = useState<Message[]>([]);
  const [stage, setStage] = useState<Stage | null>(null);
  const [retrieval, setRetrieval] = useState<RetrievalComplete | null>(null);
  const [question, setQuestion] = useState("");
  const [highlight, setHighlight] = useState<Highlight | null>(null);
  const [activeCitation, setActiveCitation] = useState<string | null>(null);
  const [mobilePane, setMobilePane] = useState<"chat" | "document">("chat");

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
        if ((error as Error).name !== "AbortError") {
          setMessages((current) => [
            ...current,
            { kind: "error", id: `${id}:e` },
          ]);
        }
      } finally {
        abortRef.current = null;
        setStage(null);
      }
    },
    [locale, messages, selected, stage],
  );

  const showCitation = useCallback(
    (citation: Citation, key: string) => {
      setActiveCitation(key);
      if (citation.bbox) {
        setHighlight({
          page: citation.page,
          bbox: citation.bbox,
          nonce: Date.now(),
        });
      }
      setMobilePane("document");
    },
    [],
  );

  const suggestions = selected
    ? (SUGGESTIONS[selected.filename]?.[locale] ?? [])
    : [];

  return (
    <div className="mx-auto flex w-full max-w-[1600px] flex-1 flex-col px-3 py-3 sm:px-4">
      <div className="mb-2 flex gap-1 rounded-lg border border-line p-0.5 lg:hidden">
        {(["chat", "document"] as const).map((pane) => (
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
            {pane === "chat" ? t.workspace.answerTitle : t.workspace.documents}
          </button>
        ))}
      </div>

      <div className="grid min-h-0 flex-1 gap-3 lg:grid-cols-[260px_minmax(0,1fr)_minmax(0,1fr)]">
        {/* Document picker */}
        <aside
          className={`min-h-0 overflow-y-auto ${
            mobilePane === "document" ? "hidden lg:block" : ""
          }`}
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
        </aside>

        {/* Conversation */}
        <section
          className={`flex min-h-0 flex-col rounded-lg border border-line bg-paper ${
            mobilePane === "document" ? "hidden lg:flex" : ""
          }`}
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

          <form
            onSubmit={(event) => {
              event.preventDefault();
              void ask(question);
            }}
            className="border-t border-line p-3"
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
                  disabled={!selected || question.trim().length === 0}
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
            <p className="mt-2 text-[11px] text-ink-faint">
              {t.workspace.disclaimer}
            </p>
          </form>
        </section>

        {/* Document */}
        <section
          className={`min-h-0 overflow-hidden rounded-lg border border-line ${
            mobilePane === "chat" ? "hidden lg:block" : ""
          }`}
        >
          <PdfViewer
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
