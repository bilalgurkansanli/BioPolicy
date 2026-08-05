/**
 * Wire types for the Python API.
 *
 * Hand-written rather than generated. The API is small enough that a generator
 * would be more machinery than it saves, and writing them out means a field
 * that changes shape shows up as a type error in review rather than as
 * `undefined` in a rendered answer.
 */

export type InjectionFinding = {
  rule: string;
  why: string;
  excerpt: string;
};

export type DocumentSummary = {
  id: string;
  filename: string;
  page_count: number | null;
  source_type: string | null;
  detected_lang: string | null;
  status: string;
  is_sample: boolean;
  /**
   * Instruction-shaped text found in the document at ingest.
   *
   * `null` and `[]` mean different things and the interface must keep them
   * apart: `null` is a document that was never scanned (it predates the check),
   * `[]` is one that was scanned and came back clean. Showing a reassuring
   * badge for the first would be a claim nobody made.
   */
  injection_findings?: InjectionFinding[] | null;
};

export type BBox = {
  x0: number;
  top: number;
  x1: number;
  bottom: number;
};

export type Citation = {
  context_id: string;
  quote: string;
  /** Where the chunk starts. */
  page: number;
  /** Where it ends — a chunk can run past a page break, and so can the quote. */
  page_end: number;
  section_path: string | null;
  bbox: BBox | null;
  /**
   * True when the quote was found verbatim in the chunk. False means it
   * survived fuzzy matching — the same clause, but not character-identical.
   * Surfaced in the UI rather than hidden, because the difference is exactly
   * the kind of thing a citation-grounded system should not be quiet about.
   */
  exact: boolean;
};

export type Answer = {
  /** The thread this turn was saved to. Sent back on the next question. */
  conversation_id: string | null;
  answer: string;
  refused: boolean;
  suppressed: boolean;
  suppression_reason: string | null;
  confidence: "high" | "medium" | "low";
  caveats: string[];
  groundedness: number | null;
  verified: boolean | null;
  citations: Citation[];
  dropped_citations: number;
  cost_usd: number;
};

export type RetrievalComplete = {
  chunk_ids: string[];
  count: number;
  searched: string;
  rewritten: boolean;
};

export type ChatEvent =
  | { event: "retrieval_started" }
  | { event: "retrieval_complete"; data: RetrievalComplete }
  | { event: "answering" }
  | { event: "verifying" }
  | { event: "done"; data: Answer }
  | { event: "error"; data: { code: string; message: string } };

export type HistoryTurn = { role: "user" | "assistant"; content: string };

export type DocumentStatus = {
  id: string;
  status: string;
  /** Position in the pipeline, so progress is real rather than a spinner. */
  stage_index: number;
  stage_count: number;
  page_count: number | null;
  source_type: string | null;
  detected_lang: string | null;
  chunk_count: number;
  error: string | null;
};

export type Allowance = {
  unlimited: boolean;
  questions_used: number;
  questions_limit: number;
  /** `null` when unlimited — distinct from zero, and never shown as one. */
  questions_left: number | null;
  documents_used: number;
  documents_limit: number;
  documents_left: number | null;
};

export type Me = {
  id: string;
  email: string | null;
  allowance: Allowance;
};

export type ConversationSummary = {
  id: string;
  title: string;
  document_id: string;
  document_filename: string;
  /** False once the document expired. The conversation outlives it. */
  document_exists: boolean;
  updated_at: string;
  message_count: number;
};

export type StoredMessage = {
  id: string;
  role: "user" | "assistant";
  content: string;
  citations: Citation[];
  groundedness: number | null;
  refused: boolean;
  suppressed: boolean;
  created_at: string;
};

export type Conversation = {
  id: string;
  messages: StoredMessage[];
};

export type PageLines = {
  page: number;
  /** One visual row of text, boxed. Empty for a page with a text layer. */
  lines: { text: string; bbox: BBox }[];
};

export type Spend = {
  total_usd: number;
  budget_usd: number;
  questions: number;
  /** `null` before the first question, rather than a division by zero. */
  per_question_usd: number | null;
  provider_calls: number;
  priced_calls: number;
  /** Fraction of provider calls the figure covers. Below 1.0 by design. */
  priced_share: number;
  first_call_at: string | null;
};

export type Capabilities = {
  stages: string[];
  max_upload_bytes: number;
  retention_hours: number;
};

export type UploadTicket = {
  document_id: string;
  storage_path: string;
  upload_url: string;
  token: string;
  expires_in: number;
  max_bytes: number;
};
