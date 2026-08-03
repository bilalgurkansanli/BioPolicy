from __future__ import annotations

from pathlib import Path

import pytest

SAMPLES = Path(__file__).resolve().parents[2] / "eval" / "golden" / "samples"


def _load(name: str) -> bytes:
    path = SAMPLES / name
    if not path.exists():  # pragma: no cover - developer-facing guard
        pytest.skip(
            f"Sample {name} is missing. Generate the fixtures with: python -m eval.generate_samples"
        )
    return path.read_bytes()


@pytest.fixture(scope="session")
def konut_pdf() -> bytes:
    """Turkish home insurance policy, native text layer, two coverage tables."""
    return _load("konut-sigortasi-tr.pdf")


@pytest.fixture(scope="session")
def commercial_pdf() -> bytes:
    """English commercial policy, native text layer, one schedule of limits."""
    return _load("commercial-property-liability-en.pdf")


@pytest.fixture(scope="session")
def scanned_pdf() -> bytes:
    """Turkish health policy rasterised to images — no text layer at all."""
    return _load("tamamlayici-saglik-tr-scanned.pdf")
