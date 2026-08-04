"""Token handling, and which routes are closed.

The verification itself — signature, audience, issuer — is PyJWT's job and is
not re-tested here. What is tested is the layer around it: which headers are
accepted, what a rejected token is allowed to reveal, and the fact that the
routes that spend money are not open.

The last of those is the one worth a test. "Auth was added" and "auth is
enforced on the endpoint that costs a dollar a day" are different claims, and
only the second one is checkable.
"""

from __future__ import annotations

from typing import cast

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from api.auth import _bearer
from api.main import create_app


@pytest.fixture(name="client")
def client_fixture() -> TestClient:
    return TestClient(create_app())


class _Request:
    def __init__(self, header: str | None) -> None:
        self.headers = {"Authorization": header} if header is not None else {}


@pytest.mark.parametrize(
    "header",
    [
        None,
        "",
        "token-without-a-scheme",
        "Basic dXNlcjpwYXNz",
        "Bearer",
        "Bearer   ",
    ],
)
def test_only_a_bearer_token_is_read_from_the_header(header: str | None) -> None:
    assert _bearer(_Request(header)) is None  # type: ignore[arg-type]


def test_the_scheme_is_matched_case_insensitively() -> None:
    """`bearer` is as valid as `Bearer` — RFC 7235 says the scheme is not cased.

    Rejecting the lowercase form produces a 401 that no client can debug,
    because the token is perfectly good.
    """
    assert _bearer(_Request("bearer abc.def.ghi")) == "abc.def.ghi"  # type: ignore[arg-type]


# -----------------------------------------------------------------------------
# which routes are closed
# -----------------------------------------------------------------------------


def test_asking_a_question_requires_a_token(client: TestClient) -> None:
    """The route that spends money is not open."""
    response = client.post(
        "/api/chat",
        json={"document_id": "00000000-0000-0000-0000-000000000000", "question": "hi"},
    )
    assert response.status_code == 401


def test_reserving_an_upload_requires_a_token(client: TestClient) -> None:
    response = client.post(
        "/api/documents/upload-url", json={"filename": "policy.pdf", "byte_size": 1000}
    )
    assert response.status_code == 401


def test_listing_your_own_documents_requires_a_token(client: TestClient) -> None:
    assert client.get("/api/documents/mine").status_code == 401


def test_deleting_requires_a_token(client: TestClient) -> None:
    response = client.delete("/api/documents/00000000-0000-0000-0000-000000000000")
    assert response.status_code == 401


def test_the_public_samples_stay_public(client: TestClient) -> None:
    """The demo has to work before anyone signs in.

    503 here means the database is not reachable from the test environment,
    which is a different thing from being refused — and is still not a 401.
    """
    assert client.get("/api/documents/samples").status_code in {200, 503}


def test_the_internal_endpoints_are_not_reachable_without_the_job_secret(
    client: TestClient,
) -> None:
    """These delete data and cost money. A bad secret is a 403, a missing
    configuration is a 503, and neither is ever a success."""
    for path in ("/api/internal/purge", "/api/internal/process-queue"):
        response = client.post(path, headers={"X-Job-Secret": "wrong"})
        assert response.status_code in {403, 503}


def test_a_rejected_token_does_not_explain_why() -> None:
    """Expired versus forged is a useful distinction to an attacker only.

    The reason is logged server-side; the client is told to sign in again.
    """
    from api.auth import _unauthorized

    error: HTTPException = _unauthorized()
    assert error.status_code == 401
    # `HTTPException.detail` is typed `str` upstream but accepts any JSON body,
    # which is how every error in this API carries a machine-readable code.
    detail = cast(dict[str, str], error.detail)
    assert detail == {"code": "unauthorized", "message": "Sign in again and retry."}
