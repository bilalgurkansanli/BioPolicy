"""Phase 0 smoke tests.

These assert the two things that must be true before anything else is worth
building: the app boots, and configuration is validated rather than assumed.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from api.config import Settings
from api.main import create_app


@pytest.fixture(name="client")
def client_fixture() -> TestClient:
    return TestClient(create_app())


def test_liveness_is_cheap_and_green(client: TestClient) -> None:
    response = client.get("/api/health/live")
    assert response.status_code == 200
    assert response.json() == {"status": "alive"}


def test_health_reports_provider_configuration(client: TestClient) -> None:
    response = client.get("/api/health")
    assert response.status_code == 200

    body = response.json()
    assert body["status"] in {"ok", "degraded"}
    assert set(body["providers"]) >= {"supabase", "database", "anthropic", "google"}
    for state in body["providers"].values():
        assert state in {"configured", "unconfigured", "ok", "error"}


def test_every_response_carries_a_request_id(client: TestClient) -> None:
    response = client.get("/api/health/live")
    assert response.headers.get("X-Request-ID")


def test_supplied_request_id_is_echoed(client: TestClient) -> None:
    """Lets the frontend correlate a user-visible failure with a server log."""
    response = client.get("/api/health/live", headers={"X-Request-ID": "abc-123"})
    assert response.headers["X-Request-ID"] == "abc-123"


# --- configuration -----------------------------------------------------------


def test_deployed_env_refuses_to_start_without_credentials() -> None:
    """The whole point of config.py: a half-configured deployment must not boot."""
    with pytest.raises(ValueError) as excinfo:
        Settings(app_env="production", _env_file=None)

    message = str(excinfo.value)
    assert "SUPABASE_URL" in message
    assert "ANTHROPIC_API_KEY" in message


def test_development_tolerates_missing_credentials() -> None:
    settings = Settings(app_env="development", _env_file=None)
    assert settings.missing_credentials()  # reported...
    assert settings.app_env == "development"  # ...but not fatal


def test_ocr_cap_must_bind() -> None:
    """Vision OCR dominates cost; its cap has to be the one that binds first."""
    with pytest.raises(ValueError, match="MAX_OCR_PAGE_COUNT"):
        Settings(
            app_env="development",
            max_page_count=10,
            max_ocr_page_count=99,
            _env_file=None,
        )


def test_embedding_dim_is_under_the_hnsw_ceiling() -> None:
    """Guards constants.py against a well-meaning bump back to the model default.

    pgvector will happily *store* 3072 dimensions and then silently refuse to
    build an HNSW index over them, leaving every query on a sequential scan. The
    failure is a performance cliff, not an error, so it needs a test.
    """
    from api.constants import EMBEDDING_DIM

    assert EMBEDDING_DIM <= 2000
