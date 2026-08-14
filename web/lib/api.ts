/**
 * Browser-side client for the Python API.
 *
 * Everything goes to `/api/*` on the same origin. The Next.js rewrite in
 * `next.config.ts` forwards it to the FastAPI service, so there is no CORS
 * preflight, no second origin to configure, and no absolute URL to get wrong
 * between environments.
 *
 * The one exception is the upload itself, which goes straight to Supabase
 * Storage against a signed URL. That is constraint C1: a 200-page policy
 * exceeds a serverless request body limit, so the file never transits the API.
 */

import { accessToken, NotSignedInError } from "./supabase";
import type {
  Answer,
  Capabilities,
  ChatEvent,
  Conversation,
  ConversationSummary,
  DocumentStatus,
  DocumentSummary,
  HistoryTurn,
  Me,
  PageLines,
  PolicyProfile,
  Spend,
  UploadTicket,
} from "./types";

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
    /** Machine-readable, when the API supplied one: `daily_quota_exceeded`, … */
    readonly code: string | null = null,
  ) {
    super(message);
  }

  get isQuota(): boolean {
    return this.code === "daily_quota_exceeded";
  }

  get isBudget(): boolean {
    return this.code === "budget_exhausted";
  }

  /** Banned, deleted, or anonymous: the account may not spend at all. */
  get isBlocked(): boolean {
    return this.code === "account_not_usable";
  }
}

/**
 * Turn a failed response into an `ApiError` carrying the API's own code.
 *
 * The interface has to distinguish "you have asked enough questions today" from
 * "the demo is out of money" from "that went wrong" — three different things to
 * say, and only the code tells them apart. Falling back to the status text would
 * collapse all three into "429".
 */
async function toError(response: Response, path: string): Promise<ApiError> {
  let code: string | null = null;
  let message = `${path} responded ${response.status}`;
  try {
    const body = await response.json();
    const detail = body?.detail ?? body?.error;
    if (typeof detail === "string") {
      message = detail;
    } else if (detail && typeof detail === "object") {
      code = detail.code ?? null;
      message = detail.message ?? message;
    }
  } catch {
    // A response with no JSON body is still an error; the status carries it.
  }
  return new ApiError(message, response.status, code);
}

async function authHeaders(): Promise<Record<string, string>> {
  const token = await accessToken();
  // Thrown rather than sent empty, so the interface shows the sign-in gate
  // instead of surfacing a 401 as "something went wrong".
  if (!token) throw new NotSignedInError();
  return {
    "Content-Type": "application/json",
    Authorization: `Bearer ${token}`,
  };
}

/**
 * How a request treats identity.
 *
 * `"optional"` is the one that needed a name. Some endpoints serve the public
 * samples *and* a signed-in visitor's own documents, and they must send a token
 * when there is one without ever creating a session to get one. Treating them
 * as authenticated took the public demo down whenever anonymous sign-ins were
 * off: the samples are readable without an account, but the client refused to
 * ask for them without a token it could not obtain.
 */
type Auth = "none" | "optional" | "required";

async function request<T>(
  path: string,
  init: RequestInit & { auth?: Auth } = {},
): Promise<T> {
  const { auth = "none", ...rest } = init;

  let headers = rest.headers;
  if (auth === "required") {
    headers = { ...(await authHeaders()), ...(rest.headers ?? {}) };
  } else if (auth === "optional") {
    const token = await accessToken();
    if (token) {
      headers = { Authorization: `Bearer ${token}`, ...(rest.headers ?? {}) };
    }
  }

  const response = await fetch(path, { ...rest, headers });
  if (!response.ok) throw await toError(response, path);
  return response.status === 204 ? (undefined as T) : ((await response.json()) as T);
}

// -----------------------------------------------------------------------------
// documents
// -----------------------------------------------------------------------------

export function fetchSamples(signal?: AbortSignal): Promise<DocumentSummary[]> {
  return request<DocumentSummary[]>("/api/documents/samples", { signal });
}

/** What the demo has spent. Public, and deliberately allowed to be unflattering. */
export function fetchSpend(signal?: AbortSignal): Promise<Spend> {
  return request<Spend>("/api/stats", { signal });
}

/** Limits and stage names, so the interface does not hard-code either. */
export function fetchCapabilities(signal?: AbortSignal): Promise<Capabilities> {
  return request<Capabilities>("/api/documents/meta/stages", { signal });
}

export function fetchMyDocuments(signal?: AbortSignal): Promise<DocumentSummary[]> {
  return request<DocumentSummary[]>("/api/documents/mine", {
    signal,
    auth: "required",
  });
}

export function fetchDocumentStatus(
  documentId: string,
  signal?: AbortSignal,
): Promise<DocumentStatus> {
  return request<DocumentStatus>(`/api/documents/${documentId}`, {
    signal,
    auth: "optional",
  });
}

/**
 * Line geometry for one OCR'd page.
 *
 * Only ever called for a page whose text layer turned up nothing. A page with
 * text answers the same question locally, and a thirty-page scan runs to well
 * over a thousand lines of which almost none are needed.
 */
export function fetchPageLines(
  documentId: string,
  page: number,
  signal?: AbortSignal,
): Promise<PageLines> {
  return request<PageLines>(`/api/documents/${documentId}/pages/${page}/lines`, {
    signal,
    auth: "optional",
  });
}

/**
 * The cached typed extraction, or `null` when nobody has run it.
 *
 * Free to call — it reads a column. The read and the run are separate verbs
 * precisely so that opening a document is never a billable event.
 */
export function fetchPolicyProfile(
  documentId: string,
  signal?: AbortSignal,
): Promise<PolicyProfile | null> {
  return request<PolicyProfile | null>(`/api/documents/${documentId}/profile`, {
    signal,
    auth: "optional",
  });
}

/**
 * Sweep the document into the schema. Costs money the first time per document
 * and nothing afterwards — the API returns the cache when there is one.
 */
export function buildPolicyProfile(
  documentId: string,
  signal?: AbortSignal,
): Promise<PolicyProfile> {
  return request<PolicyProfile>(`/api/documents/${documentId}/profile`, {
    method: "POST",
    signal,
    auth: "required",
  });
}

export function fetchViewingUrl(
  documentId: string,
  signal?: AbortSignal,
): Promise<{ url: string; expires_in: number }> {
  return request(`/api/documents/${documentId}/url`, {
    signal,
    auth: "optional",
  });
}

export function deleteDocument(documentId: string): Promise<void> {
  return request<void>(`/api/documents/${documentId}`, {
    method: "DELETE",
    auth: "required",
  });
}

/**
 * Upload a PDF: reserve, send, confirm.
 *
 * `onProgress` is fed by XHR rather than fetch, because fetch still cannot
 * report upload progress. On a 25MB policy over a slow connection that is the
 * difference between a progress bar and a frozen screen.
 */
export async function uploadDocument(
  file: File,
  onProgress: (fraction: number) => void,
): Promise<string> {
  const ticket = await request<UploadTicket>("/api/documents/upload-url", {
    method: "POST",
    auth: "required",
    body: JSON.stringify({ filename: file.name, byte_size: file.size }),
  });

  await new Promise<void>((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("PUT", ticket.upload_url);
    xhr.setRequestHeader("Content-Type", "application/pdf");
    xhr.upload.addEventListener("progress", (event) => {
      if (event.lengthComputable) onProgress(event.loaded / event.total);
    });
    xhr.addEventListener("load", () =>
      xhr.status >= 200 && xhr.status < 300
        ? resolve()
        : reject(new ApiError("The upload was rejected.", xhr.status)),
    );
    xhr.addEventListener("error", () =>
      reject(new ApiError("The upload could not be completed.", 0)),
    );
    xhr.send(file);
  });

  const confirmed = await request<{ id: string; status: string }>("/api/documents", {
    method: "POST",
    auth: "required",
    body: JSON.stringify({
      document_id: ticket.document_id,
      filename: file.name,
    }),
  });
  return confirmed.id;
}

// -----------------------------------------------------------------------------
// account and conversations
// -----------------------------------------------------------------------------

/**
 * Who is signed in and what they have left today.
 *
 * The composer disables itself from this rather than letting someone type a
 * fourth question and refusing it afterwards. It is a display of the limit; the
 * server re-checks before spending anything.
 */
export function fetchMe(signal?: AbortSignal): Promise<Me> {
  return request<Me>("/api/me", { signal, auth: "required" });
}

/**
 * Delete the account and everything it owns.
 *
 * The server erases the uploaded files before the account, and refuses the
 * whole operation if any of them survive, so a 502 here means the account is
 * still there — the caller can say "try again" honestly.
 */
export function deleteAccount(): Promise<void> {
  return request<void>("/api/me", { method: "DELETE", auth: "required" });
}

export function fetchConversations(signal?: AbortSignal): Promise<ConversationSummary[]> {
  return request<ConversationSummary[]>("/api/conversations", {
    signal,
    auth: "required",
  });
}

export function fetchConversation(
  id: string,
  signal?: AbortSignal,
): Promise<Conversation> {
  return request<Conversation>(`/api/conversations/${id}`, {
    signal,
    auth: "required",
  });
}

export function deleteConversation(id: string): Promise<void> {
  return request<void>(`/api/conversations/${id}`, {
    method: "DELETE",
    auth: "required",
  });
}

// -----------------------------------------------------------------------------
// chat
// -----------------------------------------------------------------------------

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
    conversationId: string | null;
  },
  signal?: AbortSignal,
): AsyncGenerator<ChatEvent> {
  const response = await fetch("/api/chat", {
    method: "POST",
    headers: await authHeaders(),
    signal,
    body: JSON.stringify({
      document_id: request.documentId,
      question: request.question,
      language: request.language,
      history: request.history,
      conversation_id: request.conversationId,
    }),
  });

  // Quotas and the budget breaker answer before the stream opens, so they
  // arrive as ordinary status codes rather than as an `error` event the client
  // would have to special-case.
  if (!response.ok || !response.body) {
    throw await toError(response, "/api/chat");
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
