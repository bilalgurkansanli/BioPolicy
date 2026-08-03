"""Project-wide constants.

Values here are referenced by both application code and SQL migrations. If you
change one, grep for it — several are duplicated into migration files that
cannot import Python.
"""

from typing import Final

# -----------------------------------------------------------------------------
# Embeddings
# -----------------------------------------------------------------------------
# WHY 1536 and not the model's native 3072:
#
# `gemini-embedding-001` emits 3072-dimensional vectors by default. pgvector's
# `vector` type accepts up to 16000 dimensions for *storage*, but an HNSW index
# can only be built over at most 2000 of them. An unindexed 3072-d column would
# force a sequential scan across every chunk on every query — fine for a demo
# with 200 rows, useless at any real size.
#
# The model is Matryoshka-trained: the dimensions are ordered by how much
# information they carry, so truncating to a prefix is a designed-for operation
# rather than lossy mangling. 1536 sits comfortably under the index ceiling,
# halves storage and distance-computation cost, and retains nearly all retrieval
# quality. We request it explicitly via `output_dimensionality` on every call —
# document and query embeddings MUST use the same value or the distances are
# meaningless.
#
# The SQL column type `vector(1536)` in migration 0002 is derived from this
# constant by hand. They must agree.
EMBEDDING_DIM: Final[int] = 1536

# Gemini's embedding endpoint accepts a limited number of texts per request.
EMBEDDING_BATCH_SIZE: Final[int] = 32

# WHY task types: Gemini embeds asymmetrically. A document ("Flood damage is
# excluded under Article 7.") and a question about it ("is flooding covered?")
# are not the same kind of text, and telling the model which one it is at
# encode-time measurably improves retrieval. Mixing these up — embedding
# documents as queries — silently degrades recall with no error anywhere.
EMBED_TASK_DOCUMENT: Final[str] = "RETRIEVAL_DOCUMENT"
EMBED_TASK_QUERY: Final[str] = "RETRIEVAL_QUERY"

# -----------------------------------------------------------------------------
# Chunking
# -----------------------------------------------------------------------------
# Starting points only. Section 5 of the spec is explicit: tune these against
# the eval set, do not guess. Any change here invalidates every stored embedding
# and requires a re-ingest.
CHUNK_TARGET_TOKENS: Final[int] = 700
CHUNK_OVERLAP_TOKENS: Final[int] = 120

# -----------------------------------------------------------------------------
# Retrieval
# -----------------------------------------------------------------------------
# Candidates pulled from each retrieval arm before fusion.
VECTOR_CANDIDATES: Final[int] = 30
KEYWORD_CANDIDATES: Final[int] = 30

# WHY k=60: Reciprocal Rank Fusion scores a document as sum(1 / (k + rank)).
# The constant dampens the influence of the very top ranks so that a chunk which
# appears at rank 3 in *both* arms can outrank one that appears at rank 1 in only
# one of them — which is exactly the behaviour we want when semantic and keyword
# search disagree. k=60 is the value from the original RRF paper and is the
# near-universal default; it is not tuned here and would only be worth tuning
# with far more eval data than we have.
RRF_K: Final[int] = 60

# Chunks assembled into the final prompt context.
CONTEXT_CHUNK_COUNT: Final[int] = 8

# -----------------------------------------------------------------------------
# Conversation memory
# -----------------------------------------------------------------------------
MEMORY_VERBATIM_TURNS: Final[int] = 4
MEMORY_SUMMARY_MAX_TOKENS: Final[int] = 150

# -----------------------------------------------------------------------------
# Groundedness thresholds (Section 7.3)
# -----------------------------------------------------------------------------
GROUNDEDNESS_SERVE: Final[float] = 0.8  # >= this: serve normally
GROUNDEDNESS_WARN: Final[float] = 0.5  # >= this: serve with a visible warning
# Below GROUNDEDNESS_WARN: suppress the answer and return a refusal.

# Minimum similarity for a cited quote to count as present in its chunk, after
# whitespace normalisation. Loose enough to survive OCR noise, tight enough that
# a fabricated quote does not pass.
CITATION_FUZZY_THRESHOLD: Final[float] = 0.90

# -----------------------------------------------------------------------------
# Ingestion
# -----------------------------------------------------------------------------
# Fraction of pages carrying an extractable text layer.
NATIVE_TEXT_RATIO: Final[float] = 0.8  # above: treat whole document as native
SCANNED_TEXT_RATIO: Final[float] = 0.2  # below: treat whole document as scanned
# Between the two: 'mixed', routed per page.

# Rendering DPI for pages sent to vision OCR. Higher is more legible but costs
# more image tokens; 200 is the usual sweet spot for document text.
OCR_RENDER_DPI: Final[int] = 200

# A page needs more than this many extractable characters to count as having a
# real text layer. Scanned PDFs frequently carry a handful of stray characters
# from a header stamp or a form field, which would otherwise fool the detector.
MIN_CHARS_FOR_TEXT_LAYER: Final[int] = 50

# -----------------------------------------------------------------------------
# Document status machine
# -----------------------------------------------------------------------------
STATUS_QUEUED: Final[str] = "queued"
STATUS_PARSING: Final[str] = "parsing"
STATUS_OCR: Final[str] = "ocr"
STATUS_CHUNKING: Final[str] = "chunking"
STATUS_EMBEDDING: Final[str] = "embedding"
STATUS_READY: Final[str] = "ready"
STATUS_FAILED: Final[str] = "failed"

DOCUMENT_STATUSES: Final[tuple[str, ...]] = (
    STATUS_QUEUED,
    STATUS_PARSING,
    STATUS_OCR,
    STATUS_CHUNKING,
    STATUS_EMBEDDING,
    STATUS_READY,
    STATUS_FAILED,
)

# Ordered for progress display in the UI. 'failed' is terminal and not a step.
PIPELINE_STAGES: Final[tuple[str, ...]] = (
    STATUS_QUEUED,
    STATUS_PARSING,
    STATUS_OCR,
    STATUS_CHUNKING,
    STATUS_EMBEDDING,
    STATUS_READY,
)

# -----------------------------------------------------------------------------
# Uploads
# -----------------------------------------------------------------------------
PDF_MAGIC_BYTES: Final[bytes] = b"%PDF-"
ALLOWED_MIME_TYPES: Final[frozenset[str]] = frozenset({"application/pdf"})
