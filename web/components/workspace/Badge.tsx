/**
 * The small chips under a document's name.
 *
 * Shared rather than duplicated because the two lists describe the same
 * documents and a reader moves between them. The sample list said "taranmış ·
 * OCR" while an uploaded document — read exactly the same way — said nothing,
 * which read as the samples being a different kind of thing rather than as one
 * list being less complete than the other.
 *
 * `warn` is not an error tone here. It marks a fact worth noticing about how
 * the document was read: OCR is a transcription, and a transcription can be
 * wrong in ways a text layer cannot.
 */
export function Badge({
  children,
  tone = "plain",
}: {
  children: React.ReactNode;
  tone?: "plain" | "warn";
}) {
  return (
    <span
      className={`rounded px-1.5 py-0.5 ${
        tone === "warn"
          ? "bg-refuse-soft text-refuse"
          : "bg-surface-sunken text-ink-muted"
      }`}
    >
      {children}
    </span>
  );
}
