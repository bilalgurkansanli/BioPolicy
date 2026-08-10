"""Can a stranger read somebody else's policy?

Two layers have to hold, and they fail in different ways.

**The API** guards every route that takes a document id. The realistic failure
is not one of them being wrong today — it is the eighth route, added later, that
forgets the clause. So the first half of this file walks the application's own
route table and calls *every* one of them as a user who owns nothing. A new
endpoint is covered the day it is added, without anyone remembering to.

**Row-level security** is what stops the browser's key going around the API
entirely. The anon key ships to every visitor because sign-in needs it, and
Supabase exposes PostgREST on the same project, so a permissive policy on
`documents` or `chunks` would publish the full text of every uploaded policy no
matter how careful the routes are. It is checked here against the live project
rather than asserted from the migration, because a policy that was replaced by
hand in the dashboard reads exactly like one that was never changed.

Both are marked `integration`: they need the real database, and the second needs
the real Supabase URL and anon key. `pytest -m "not integration"` skips them.

The control matters as much as the assertions. A probe where everything is
denied proves the routes are broken, not that they are safe — so a sample
document must still come back 200 in the same run.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator

import httpx
import pytest
from fastapi.testclient import TestClient

from api.auth import AuthenticatedUser, optional_user, required_user
from api.config import get_settings
from api.db import create_pool
from api.main import create_app

pytestmark = pytest.mark.integration

INTRUDER = AuthenticatedUser(
    id=uuid.UUID("00000000-0000-4000-8000-0000deadbeef"),
    email="intruder@example.com",
    is_anonymous=False,
)

# What a document-scoped route may answer a stranger. 404 rather than 403
# throughout: whether an id exists is not something a stranger should be able to
# probe. 401 and 403 are accepted so the assertion survives a route that later
# grows a stricter guard.
DENIED = {401, 403, 404}


@pytest.fixture(name="targets")
async def targets_fixture() -> dict[str, str]:
    pool = await create_pool()
    try:
        private = await pool.fetchrow(
            "select id from documents where not is_sample and status = 'ready' "
            "order by created_at desc limit 1"
        )
        sample = await pool.fetchrow("select id from documents where is_sample limit 1")
        conversation = await pool.fetchrow("select id from conversations limit 1")
    finally:
        await pool.close()

    if private is None or sample is None:
        pytest.skip("needs one private and one sample document in the database")
    return {
        "private": str(private["id"]),
        "sample": str(sample["id"]),
        "conversation": str(conversation["id"]) if conversation else "",
    }


@pytest.fixture(name="intruder")
def intruder_fixture() -> Iterator[TestClient]:
    """Entered as a context manager, which is what runs the lifespan.

    Without it the app boots with no `app_state`, every route answers 503, and
    a file asserting "a stranger is refused" passes for the wrong reason — the
    strongest way to write a security test that tests nothing.
    """
    app = create_app()
    app.dependency_overrides[required_user] = lambda: INTRUDER
    app.dependency_overrides[optional_user] = lambda: INTRUDER
    with TestClient(app) as client:
        yield client


# --- the API ------------------------------------------------------------------


def _document_routes() -> list[tuple[str, str]]:
    """Every route whose path names a document, from the app's own schema.

    Derived rather than listed, so this cannot fall behind the router: an
    endpoint added next month is probed the day it appears.

    Read from `openapi()` rather than by walking `app.routes`. This version of
    FastAPI keeps an included router as one opaque object instead of flattening
    its routes onto the app, so the obvious traversal finds the three default
    routes and nothing else — and a probe that iterates over nothing passes.
    The schema is also the better definition of what needs checking: it is the
    surface the application publishes.

    `/chat` takes its document id in the body rather than the path and is
    asserted separately.
    """
    schema = create_app().openapi()
    found: list[tuple[str, str]] = []
    for path, operations in schema.get("paths", {}).items():
        if "{document_id}" not in path:
            continue
        for method in operations:
            if method.upper() not in {"HEAD", "OPTIONS"}:
                found.append((method.upper(), path))
    return sorted(found)


def test_there_are_document_routes_to_check() -> None:
    """Guards the guard: a rename that empties the list would make every
    assertion below pass by iterating over nothing."""
    assert len(_document_routes()) >= 5


def test_no_document_route_answers_a_stranger(
    intruder: TestClient, targets: dict[str, str]
) -> None:
    served = []
    for method, path in _document_routes():
        url = path.replace("{document_id}", targets["private"]).replace("{page}", "1")
        response = intruder.request(method, url)
        if response.status_code not in DENIED:
            served.append(f"{method} {path} -> {response.status_code}")

    assert not served, f"reachable by a stranger: {served}"


def test_a_stranger_cannot_ask_questions_about_it(
    intruder: TestClient, targets: dict[str, str]
) -> None:
    """The widest leak of all: an answer quotes the document verbatim."""
    response = intruder.post(
        "/api/chat",
        json={
            "document_id": targets["private"],
            "question": "Sigortalı kim?",
            "language": "tr",
        },
    )

    assert response.status_code in DENIED


def test_the_samples_are_still_readable(intruder: TestClient, targets: dict[str, str]) -> None:
    """The control. Without it, a router that 404s everything passes the file."""
    assert intruder.get(f"/api/documents/{targets['sample']}").status_code == 200


def test_a_stranger_cannot_read_or_delete_a_conversation(
    intruder: TestClient, targets: dict[str, str]
) -> None:
    if not targets["conversation"]:
        pytest.skip("no conversation in the database")

    for method in ("GET", "DELETE"):
        response = intruder.request(method, f"/api/conversations/{targets['conversation']}")
        assert response.status_code in DENIED, f"{method} conversation -> {response.status_code}"


# --- row-level security, around the API ---------------------------------------


async def test_the_browser_key_cannot_read_a_private_document() -> None:
    """Straight at PostgREST with the key every visitor holds.

    Asked for the private rows explicitly rather than counting what comes back:
    the samples are public by design, so "some rows returned" is not a finding.
    An earlier version of this probe made exactly that mistake and reported a
    leak that was three sample documents.
    """
    settings = get_settings()
    if not (settings.supabase_url and settings.supabase_anon_key):
        pytest.skip("needs SUPABASE_URL and SUPABASE_ANON_KEY")

    base = settings.supabase_url.rstrip("/")
    headers = {
        "apikey": settings.supabase_anon_key,
        "Authorization": f"Bearer {settings.supabase_anon_key}",
    }

    pool = await create_pool()
    try:
        private = await pool.fetchrow(
            "select id from documents where not is_sample and status = 'ready' limit 1"
        )
        sample = await pool.fetchrow("select id from documents where is_sample limit 1")
    finally:
        await pool.close()
    if private is None or sample is None:
        pytest.skip("needs one private and one sample document in the database")

    async with httpx.AsyncClient(timeout=30.0) as client:

        async def rows(table: str, params: dict[str, str]) -> list[dict[str, object]]:
            response = await client.get(f"{base}/rest/v1/{table}", headers=headers, params=params)
            assert response.status_code == 200, f"{table}: HTTP {response.status_code}"
            body = response.json()
            return body if isinstance(body, list) else []

        assert await rows("documents", {"select": "id", "is_sample": "eq.false"}) == [], (
            "private documents are listable with the browser key"
        )

        assert await rows("documents", {"select": "id", "id": f"eq.{private['id']}"}) == [], (
            "a private document is readable by id with the browser key"
        )

        assert (
            await rows("chunks", {"select": "content", "document_id": f"eq.{private['id']}"}) == []
        ), "the text of a private document is readable with the browser key"

        assert (
            await rows("page_lines", {"select": "id", "document_id": f"eq.{private['id']}"}) == []
        ), "the OCR geometry of a private document is readable with the browser key"

        # The control again, at this layer: the policy is `own or sample`, and a
        # policy denying everything would pass every assertion above.
        assert await rows("documents", {"select": "id", "id": f"eq.{sample['id']}"}) != [], (
            "the samples are not readable either — the policy denies everything, "
            "which breaks the demo rather than securing it"
        )


async def test_the_storage_bucket_is_private() -> None:
    """A signed URL is a lock on a door, and this is the wall.

    Public, every stored PDF would be fetchable by path and the whole
    signed-URL path decorative.
    """
    settings = get_settings()
    if not (settings.supabase_url and settings.supabase_service_role_key):
        pytest.skip("needs SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY")

    base = settings.supabase_url.rstrip("/")
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(
            f"{base}/storage/v1/bucket",
            headers={
                "apikey": settings.supabase_service_role_key,
                "Authorization": f"Bearer {settings.supabase_service_role_key}",
            },
        )
    assert response.status_code == 200

    buckets = {b["name"]: b["public"] for b in response.json()}
    assert settings.supabase_storage_bucket in buckets, f"no such bucket: {buckets}"
    assert buckets[settings.supabase_storage_bucket] is False, (
        f"bucket {settings.supabase_storage_bucket!r} is public — "
        "every uploaded policy is readable by URL"
    )
