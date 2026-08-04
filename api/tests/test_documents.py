"""The document row and the object it points at.

One invariant holds this together: **the row's id is the id in its storage
path**. The id is minted before the file exists, because it names the object the
browser uploads to (constraint C1 — the file never passes through the API), and
the row is written afterwards.

Letting the database generate its own id at insert time is the natural thing to
write and it silently breaks that link: the upload succeeds, the row exists, and
the id handed back to the client identifies nothing. Every later call —
polling status, fetching a viewing URL, deleting — then 404s on a document that
is really there.
"""

from __future__ import annotations

from typing import Any, cast
from uuid import UUID, uuid4

from api.documents import DocumentRepository
from api.storage import upload_path
from api.tests.fakes import FakePool

USER = uuid4()


def _row(document_id: UUID, storage_path: str) -> dict[str, object]:
    return {
        "id": document_id,
        "user_id": USER,
        "filename": "policy.pdf",
        "storage_path": storage_path,
        "byte_size": 1234,
        "status": "queued",
        "is_sample": False,
        "page_count": None,
        "source_type": None,
        "detected_lang": None,
        "error_message": None,
        "attempts": 0,
    }


def test_the_storage_path_is_derived_from_the_ids_alone() -> None:
    """No user-controlled text in the path.

    A filename is arbitrary bytes from a stranger; a uuid cannot contain a
    traversal sequence or a leading slash. The user id being a path segment is
    also what makes ownership checkable from the path by itself.
    """
    document_id = uuid4()
    assert upload_path(USER, document_id) == f"uploads/{USER}/{document_id}.pdf"


async def test_the_row_is_created_under_the_id_that_names_the_object() -> None:
    document_id = uuid4()
    path = upload_path(USER, document_id)
    pool = FakePool(fetchrow=[_row(document_id, path)])

    record = await DocumentRepository(cast(Any, pool)).create(
        document_id=document_id,
        user_id=USER,
        filename="policy.pdf",
        storage_path=path,
        byte_size=1234,
    )

    # The id reaches the INSERT rather than being left to the default.
    _, args = pool.log[0]
    assert document_id in args
    # And the returned record agrees with the path it was stored at.
    assert str(record.id) in record.storage_path


async def test_an_id_is_still_generated_when_none_is_supplied() -> None:
    """The sample seeder has no ticket and should not have to invent one."""
    generated = uuid4()
    pool = FakePool(fetchrow=[_row(generated, "samples/konut.pdf")])

    record = await DocumentRepository(cast(Any, pool)).create(
        user_id=USER,
        filename="konut.pdf",
        storage_path="samples/konut.pdf",
        byte_size=10,
        is_sample=True,
    )

    _, args = pool.log[0]
    assert args[-1] is None  # coalesce() falls through to gen_random_uuid()
    assert record.id == generated
