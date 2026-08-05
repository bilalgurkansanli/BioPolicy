/**
 * Wire types for the Python API.
 *
 * Hand-written rather than generated. The API is small enough that a generator
 * would be more machinery than it saves, and writing them out means a field
 * that changes shape shows up as a type error in review rather than as
 * `undefined` in a rendered answer.
 */

export type DocumentSummary = {
  id: string;
  filename: string;
  page_count: number | null;
  source_type: string | null;
  detected_lang: string | null;
  status: string;
  is_sample: boolean;
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
  page: number;
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

export type PageLines = {
  page: number;
  /** One visual row of text, boxed. Empty for a page with a text layer. */
  lines: { text: string; bbox: BBox }[];
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
