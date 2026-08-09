"""The 24-hour deletion promise.

The promise is printed on the interface, so it is a commitment. These tests
check the two things that make it real rather than decorative: that the file in
object storage is deleted *before* the rows that point at it, and that a failure
to delete the file leaves the row alive to be retried.

The failure mode being guarded against is subtle and looks like success: delete
the rows first and the purge appears to work, the audit table records it, and
the user's policy PDF is still sitting in the bucket with nothing left pointing
at it.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any, cast
from uuid import uuid4

from api.retention import ORPHAN_GRACE_INTERVAL, RetentionService
from api.tests.fakes import FakePool, FakeStorage

DOC = uuid4()
USER = uuid4()
PATH = f"uploads/{USER}/{DOC}.pdf"


def _service(
    *, removable: bool = True, expired: int = 1
) -> tuple[RetentionService, FakePool, FakeStorage]:
    rows = [{"id": DOC, "user_id": USER, "storage_path": PATH}] * expired
    pool = FakePool(fetch=[rows], fetchval=7)
    storage = FakeStorage(removable=removable)
    # One shared log, so the ordering between the bucket and the database is
    # visible as a single sequence rather than two lists that have to be
    # correlated by hand.
    storage.share_log(pool.log)
    service = RetentionService(cast(Any, pool), cast(Any, storage))
    return service, pool, storage


async def test_the_file_is_deleted_before_the_rows_that_point_at_it() -> None:
    """The ordering *is* the guarantee.

    Rows first loses the storage path, and with it the only way to find the
    file. A row without its file is recoverable; a file without its row is not
    even findable.
    """
    service, pool, storage = _service()

    report = await service.purge_expired()

    assert report.purged == 1
    order = pool.statements
    assert order.index("storage.remove") < order.index("delete from")
    assert storage.removed == [PATH]


async def test_the_audit_entry_is_written_only_after_both_halves_succeeded() -> None:
    service, pool, _ = _service()

    await service.purge_expired()

    order = pool.statements
    assert order.index("delete from") < order.index("insert into")
    # And inside the same transaction, so a crash cannot leave the rows deleted
    # with no record of it.
    assert order.index("begin") < order.index("delete from")
    assert order.index("insert into") < order.index("commit")


async def test_a_file_that_could_not_be_deleted_keeps_its_row() -> None:
    """Reported as a failure and retried, not quietly counted as purged."""
    service, pool, _ = _service(removable=False)

    report = await service.purge_expired()

    assert report.purged == 0
    assert report.failed == 1
    assert "delete from" not in pool.statements
    assert "insert into" not in pool.statements


async def test_the_number_of_chunks_removed_is_recorded() -> None:
    """An audit entry that says nothing is an audit entry nobody can check."""
    service, pool, _ = _service()

    await service.purge_expired()

    insert = next(args for name, args in pool.log if name == "insert into")
    assert insert == (DOC, USER, 7)


async def test_samples_are_excluded_from_every_sweep() -> None:
    """Deliberately an assertion about the query text.

    There is no way to observe this through the fake — the exclusion lives
    entirely in the WHERE clause, and dropping it would delete the public demo
    out from under itself 24 hours after deployment. Migration 0002 has a CHECK
    constraint covering the same mistake from the other side.
    """
    service, pool, _ = _service()

    await service.purge_expired()

    assert "not is_sample" in pool.queries[0]
    assert "expires_at < now()" in pool.queries[0]


async def test_deleting_on_request_takes_the_same_path_as_expiry() -> None:
    """ "Delete it now" and "it expired" must not diverge in what they leave."""
    pool = FakePool(fetchrow=[{"id": DOC, "user_id": USER, "storage_path": PATH}], fetchval=3)
    storage = FakeStorage()
    storage.share_log(pool.log)
    service = RetentionService(cast(Any, pool), cast(Any, storage))

    assert await service.purge_document(DOC) is True

    order = pool.statements
    assert order.index("storage.remove") < order.index("delete from")
    assert order.index("delete from") < order.index("insert into")


async def test_deleting_an_unknown_document_reports_failure_rather_than_success() -> None:
    pool = FakePool(fetchrow=[None])
    storage = FakeStorage()
    storage.share_log(pool.log)
    service = RetentionService(cast(Any, pool), cast(Any, storage))

    assert await service.purge_document(uuid4()) is False
    assert storage.removed == []


async def test_closing_an_account_empties_the_bucket_before_the_account_goes() -> None:
    """The account is only safe to delete once every file of its own is gone.

    Rows cascade from `auth.users`; storage objects do not. If the account went
    first, the PDFs would be left with no row pointing at them, no owner to ask
    for them and no expiry to catch them — findable only by someone who already
    knew the path.
    """
    second = uuid4()
    pool = FakePool(
        fetch=[
            [
                {"id": DOC, "storage_path": PATH},
                {"id": second, "storage_path": f"uploads/{USER}/{second}.pdf"},
            ]
        ],
        fetchval=2,
    )
    storage = FakeStorage()
    storage.share_log(pool.log)
    service = RetentionService(cast(Any, pool), cast(Any, storage))

    assert await service.purge_user_documents(USER) is True

    assert len(storage.removed) == 2
    order = pool.statements
    assert order.index("storage.remove") < order.index("delete from")


async def test_a_bucket_that_refuses_a_delete_keeps_the_account_alive() -> None:
    """A false here is what stops the route from deleting the account."""
    pool = FakePool(fetch=[[{"id": DOC, "storage_path": PATH}]], fetchval=1)
    storage = FakeStorage(removable=False)
    storage.share_log(pool.log)
    service = RetentionService(cast(Any, pool), cast(Any, storage))

    assert await service.purge_user_documents(USER) is False
    assert "delete from" not in pool.statements


# --- orphaned objects ---------------------------------------------------------
#
# Migration 0007's database-side fallback deletes rows and cannot reach the
# bucket, producing the one state the ordering above exists to prevent: a file
# with no row, no owner and no expiry. It said the API reconciled them. Nothing
# did, and 6 PDFs sat in the development bucket, the oldest 5 days past its
# deletion date.


ORPHAN = "uploads/8b1c/dead-beef.pdf"


def _orphan_service(
    orphans: list[dict[str, object]], *, removable: bool = True
) -> tuple[RetentionService, FakePool, FakeStorage]:
    # First fetch is the expired-documents query, second is the orphan scan.
    pool = FakePool(fetch=[[], orphans])
    storage = FakeStorage(removable=removable)
    storage.share_log(pool.log)
    return RetentionService(cast(Any, pool), cast(Any, storage)), pool, storage


async def test_an_object_no_row_points_at_is_deleted() -> None:
    service, _, storage = _orphan_service([{"name": ORPHAN}])

    report = await service.purge_expired()

    assert report.orphans_deleted == 1
    assert storage.removed == [ORPHAN]


async def test_reconciliation_can_only_reach_uploads_and_only_after_a_grace_period() -> None:
    """Assertions about the query text, for the same reason the sample one is.

    Neither condition is observable through the fake, and dropping either is
    destructive in a way a test that watched behaviour would not notice: without
    the prefix a sample object becomes deletable, without the grace period an
    upload in flight does.
    """
    service, pool, _ = _orphan_service([])

    await service.purge_expired()

    scan = pool.queries[1]
    assert "like 'uploads/%'" in scan
    assert "not exists" in scan
    assert "created_at < now() - $2::interval" in scan


async def test_a_failed_orphan_scan_does_not_fail_the_purge() -> None:
    """Reading storage metadata is a privilege we hold, not one we control."""
    service, pool, _ = _orphan_service([])

    async def explode(query: str, *args: object) -> list[dict[str, object]]:
        if "storage.objects" in query:
            raise RuntimeError("permission denied for schema storage")
        return []

    pool.fetch = explode  # type: ignore[method-assign]

    report = await service.purge_expired()

    assert report.orphans_deleted == 0
    assert report.failed == 0


async def test_an_orphan_the_bucket_refuses_is_not_counted_as_deleted() -> None:
    service, _, _ = _orphan_service([{"name": ORPHAN}], removable=False)

    report = await service.purge_expired()

    assert report.orphans_deleted == 0


def test_the_grace_period_is_a_timedelta_not_a_string() -> None:
    """Looks pedantic; caught a real bug that every other test was blind to.

    asyncpg maps `interval` to `timedelta`. Passing `'1 hour'` reaches the driver
    as `'str' object has no attribute 'days'`, which the scan's own error handler
    swallows — so reconciliation reports zero orphans and looks like it worked.
    The fakes understand no SQL and cannot see it; only Postgres could, and did.
    """
    assert isinstance(ORPHAN_GRACE_INTERVAL, timedelta)
