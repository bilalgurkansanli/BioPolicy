/**
 * Browser-side client for the Python API.
 *
 * Everything goes to `/api/*` on the same origin. The Next.js rewrite in
 * `next.config.ts` forwards it to the FastAPI service, so there is no CORS
 * preflight, no second origin to configure, and no absolute URL to get wrong
 * between environments.
 */

import type { Answer, ChatEvent, DocumentSummary, HistoryTurn } from "./types";

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
  }
}

async function getJson<T>(path: string, signal?: AbortSignal): Promise<T> {
  const response = await fetch(path, { signal });
  if (!response.ok) {
    throw new ApiError(`${path} responded ${response.status}`, response.status);
  }
  return (await response.json()) as T;
}

export function fetchSamples(signal?: AbortSignal): Promise<DocumentSummary[]> {
  return getJson<DocumentSummary[]>("/api/documents/samples", signal);
}

export function fetchViewingUrl(
  documentId: string,
  signal?: AbortSignal,
): Promise<{ url: string; expires_in: number }> {
  return getJson(`/api/documents/${documentId}/url`, signal);
}

/**
 * Parse an SSE byte stream into events.
 *
 * Written by hand because `EventSource` cannot issue a POST, and the question
 * belongs in a body rather than a query string — a URL is logged by every proxy
 * between here and the server, and the question is the one piece of user text
 * this system is careful never to store.
 */
async function* parseEventStream(
  body: ReadableStream<Uint8Array>,
): AsyncGenerator<{ name: string; data: string }> {
  const reader = body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    // Events are separated by a blank line. Servers differ on CRLF vs LF, so
    // normalise before splitting rather than matching both in the split.
    buffer = buffer.replace(/\r\n/g, "\n");
    let boundary = buffer.indexOf("\n\n");
    while (boundary !== -1) {
      const raw = buffer.slice(0, boundary);
      buffer = buffer.slice(boundary + 2);
      boundary = buffer.indexOf("\n\n");

      let name = "message";
      const dataLines: string[] = [];
      for (const line of raw.split("\n")) {
        if (line.startsWith("event:")) name = line.slice(6).trim();
        else if (line.startsWith("data:")) dataLines.push(line.slice(5).trim());
      }
      if (dataLines.length > 0 || name !== "message") {
        yield { name, data: dataLines.join("\n") };
      }
    }
  }
}

export async function* askQuestion(
  request: {
    documentId: string;
    question: string;
    language: string;
    history: HistoryTurn[];
  },
  signal?: AbortSignal,
): AsyncGenerator<ChatEvent> {
  const response = await fetch("/api/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    signal,
    body: JSON.stringify({
      document_id: request.documentId,
      question: request.question,
      language: request.language,
      history: request.history,
    }),
  });

  if (!response.ok || !response.body) {
    throw new ApiError(`chat responded ${response.status}`, response.status);
  }

  for await (const { name, data } of parseEventStream(response.body)) {
    switch (name) {
      case "retrieval_started":
      case "answering":
      case "verifying":
        yield { event: name } as ChatEvent;
        break;
      case "retrieval_complete":
        yield { event: "retrieval_complete", data: JSON.parse(data) };
        break;
      case "done":
        yield { event: "done", data: JSON.parse(data) as Answer };
        break;
      case "error":
        yield { event: "error", data: JSON.parse(data) };
        break;
      default:
        // An event the client does not know about is not an error. Ignoring it
        // means the server can add one without breaking deployed clients.
        break;
    }
  }
}
