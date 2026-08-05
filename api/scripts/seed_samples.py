"""Ingest the three bundled sample documents.

    python -m api.scripts.seed_samples
    python -m api.scripts.seed_samples --force   # re-ingest even if already ready

Samples are what the public demo serves without an upload, so they are ingested
through the **same pipeline as a user upload** rather than through a shortcut.
A seeding path that bypassed parsing or embedding would mean the demo exercises
code no real user ever hits, and the eval would measure that shortcut instead of
the product.

They differ from user uploads in exactly two ways, both deliberate:

* `is_sample = true`, so RLS lets anyone read them.
* A far-future `expires_at`, so the retention job never deletes the demo out
  from under itself.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path
from uuid import UUID

import asyncpg
from supabase import acreate_client

from api.config import get_settings
from api.constants import STATUS_READY
from api.db import create_pool
from api.documents import DocumentRepository
from api.ingest.chunker import Chunker
from api.ingest.ocr import GeminiOCR
from api.ingest.parsers import PdfParser
from api.ingest.pipeline import IngestionPipeline
from api.retrieval.gemini_embedder import GeminiEmbedder
from api.retrieval.store import ChunkStore
from eval.sample_content import ALL_DOCUMENTS, HARD_DOCUMENTS, INJECTION_DOCUMENTS

SAMPLES_DIR = Path(__file__).resolve().parents[2] / "eval" / "golden" / "samples"

# A dedicated owner for the bundled documents. Samples still need a real
# `auth.users` row because `documents.user_id` is a foreign key — making it
# nullable "just for samples" would weaken the constraint that keeps every
# other document attributable.
SAMPLE_OWNER_EMAIL = "samples@biopolicy.internal"

GREEN, RED, YELLOW, DIM, RESET = "\033[32m", "\033[31m", "\033[33m", "\033[2m", "\033[0m"


async def ensure_sample_owner(pool: asyncpg.Pool) -> UUID:
    """Find or create the auth user that owns the bundled documents."""
    existing = await pool.fetchval("select id from auth.users where email = $1", SAMPLE_OWNER_EMAIL)
    if existing:
        return UUID(str(existing))

    settings = get_settings()
    client = await acreate_client(
        settings.supabase_url or "", settings.supabase_service_role_key or ""
    )
    response = await client.auth.admin.create_user(
        {
            "email": SAMPLE_OWNER_EMAIL,
            "email_confirm": True,
            "user_metadata": {"role": "sample-owner"},
        }
    )
    if response.user is None:
        raise RuntimeError("Supabase did not return a user for the sample owner")
    print(f"  {DIM}created sample owner {SAMPLE_OWNER_EMAIL}{RESET}")
    return UUID(response.user.id)


async def ensure_bucket() -> None:
    """Create the storage bucket if it does not exist. Idempotent.

    Three settings matter and none of them are defaults:

    * **`public=False`.** A public bucket would make every uploaded policy
      readable by anyone with the URL, which defeats the entire access model —
      RLS on `documents` and `chunks` would be guarding the metadata while the
      PDF itself sat open on the internet.
    * **A size limit**, so a malicious upload cannot fill the bucket. It matches
      `MAX_UPLOAD_BYTES` so the two limits cannot drift apart.
    * **`application/pdf` only.** The API validates magic bytes as well, but a
      bucket-level restriction is enforced by the storage service itself and
      survives a bug in our validation.
    """
    settings = get_settings()
    client = await acreate_client(
        settings.supabase_url or "", settings.supabase_service_role_key or ""
    )
    bucket = settings.supabase_storage_bucket

    existing = {b.name for b in await client.storage.list_buckets()}
    if bucket in existing:
        return

    await client.storage.create_bucket(
        bucket,
        options={
            "public": False,
            "file_size_limit": settings.max_upload_bytes,
            "allowed_mime_types": ["application/pdf"],
        },
    )
    print(f"  {DIM}created private bucket {bucket!r}{RESET}")


async def upload(storage_path: str, data: bytes) -> None:
    """Put the PDF in the bucket so the viewer can fetch it later."""
    settings = get_settings()
    client = await acreate_client(
        settings.supabase_url or "", settings.supabase_service_role_key or ""
    )
    bucket = client.storage.from_(settings.supabase_storage_bucket)
    await bucket.upload(
        storage_path,
        data,
        {"content-type": "application/pdf", "upsert": "true"},
    )


# The adversarial documents are ingested like any other but are **not** demo
# samples: they exist so the evaluation can be embarrassed, and putting them in
# the public picker would put a deliberately self-contradicting policy in front
# of a visitor with no explanation.
#
# `is_sample = false` keeps them out of `/api/documents/samples`. That would
# normally also mean a 24-hour expiry, so their `expires_at` is pushed out —
# they are fixtures, not uploads.
#
# The injection document is the same kind of fixture and the rule matters more
# for it, not less: it is a policy written to hijack whatever reads it, and the
# public picker is the one place it must never appear.
FIXTURE_SLUGS: frozenset[str] = frozenset(
    d["slug"] for d in (*HARD_DOCUMENTS, *INJECTION_DOCUMENTS)
)


async def run(*, force: bool, which: str) -> int:
    settings = get_settings()
    wanted = {
        "demo": {d["slug"] for d in ALL_DOCUMENTS},
        "hard": {d["slug"] for d in HARD_DOCUMENTS},
        "injection": {d["slug"] for d in INJECTION_DOCUMENTS},
        "all": {d["slug"] for d in (*ALL_DOCUMENTS, *HARD_DOCUMENTS, *INJECTION_DOCUMENTS)},
    }[which]
    pdfs = sorted(p for p in SAMPLES_DIR.glob("*.pdf") if p.stem in wanted)
    if not pdfs:
        print(f"{RED}No sample PDFs found.{RESET} Run: python -m eval.generate_samples")
        return 1

    pool = await create_pool()
    try:
        await ensure_bucket()
        owner = await ensure_sample_owner(pool)
        documents = DocumentRepository(pool)
        store = ChunkStore(pool)

        ocr = (
            GeminiOCR(settings.google_api_key or "", settings.gemini_ocr_model)
            if settings.google_api_key and settings.gemini_ocr_model
            else None
        )
        pipeline = IngestionPipeline(
            documents=documents,
            store=store,
            parser=PdfParser(ocr=ocr),
            embedder=GeminiEmbedder(settings.google_api_key or "", settings.gemini_embedding_model),
            chunker=Chunker(),
        )

        print(f"{len(pdfs)} sample documents\n")
        failures = 0

        for path in pdfs:
            data = path.read_bytes()
            storage_path = f"samples/{path.name}"

            fixture = path.stem in FIXTURE_SLUGS
            record = await documents.find_by_path(storage_path)
            if record and record.status == STATUS_READY and not force:
                count = await store.chunk_count(record.id)
                print(f"  {DIM}SKIP{RESET}     {path.name}  ({count} chunks already stored)")
                continue

            print(f"  ...      {path.name}")
            await upload(storage_path, data)

            if record is None:
                record = await documents.create(
                    user_id=owner,
                    filename=path.name,
                    storage_path=storage_path,
                    byte_size=len(data),
                    is_sample=not fixture,
                )
                if fixture:
                    # A fixture that expires is a fixture that silently stops
                    # being there, and the report would blame the model.
                    await pool.execute(
                        "update documents set expires_at = now() + interval '100 years' "
                        "where id = $1",
                        record.id,
                    )

            result = await pipeline.run_safely(record, data)
            if result is None:
                refreshed = await documents.get(record.id)
                print(f"  {RED}FAILED{RESET}   {path.name}")
                print(f"           {refreshed.error_message if refreshed else 'unknown'}")
                failures += 1
                continue

            print(
                f"  {GREEN}OK{RESET}       {path.name}  "
                f"{result.page_count}p · {result.source_type} · "
                f"{result.chunk_count} chunks ({result.table_chunks} tables) · "
                f"{result.ocr_pages} OCR · {result.duration_seconds}s"
            )

        print()
        if failures:
            print(f"{RED}{failures} document(s) failed.{RESET}")
            return 1
        print(f"{GREEN}All samples ingested.{RESET}")
        return 0
    finally:
        await pool.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--force", action="store_true", help="Re-ingest documents that are already ready."
    )
    parser.add_argument(
        "--set",
        choices=("demo", "hard", "injection", "all"),
        default="demo",
        help=(
            "demo: the three documents the public workspace serves (default). "
            "hard: the two adversarial evaluation fixtures. "
            "all: both."
        ),
    )
    args = parser.parse_args()
    return asyncio.run(run(force=args.force, which=args.set))


if __name__ == "__main__":
    sys.exit(main())
