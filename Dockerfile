# =============================================================================
# BioPolicy API — container image for Vercel Fluid compute.
#
# Cold start is the user's first impression of this product, so the image is
# built to stay small. Two things make that possible:
#
#   * Multi-stage: `uv` and the build cache never reach the runtime layer.
#   * No system binaries. The PDF stack (pypdfium2 + pdfplumber) ships
#     self-contained wheels — no poppler, no tesseract, no ML weights. That was
#     the whole point of the parser choice in docs/adr/002; this file is where
#     the decision gets paid back.
#
# Dependencies are installed BEFORE the application source is copied, so editing
# a Python file rebuilds one small layer instead of reinstalling 117 packages.
# =============================================================================

# --- build stage -------------------------------------------------------------
FROM python:3.12-slim-bookworm AS builder

# Pinned rather than :latest — a reproducible build is worth more than a current
# installer, and this is the one tool that decides every other version.
COPY --from=ghcr.io/astral-sh/uv:0.11.32 /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /app

# Layer 1: dependencies only. `--no-install-project` stops uv building the local
# package here, which would invalidate this layer on every source edit.
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project

# Layer 2: the application itself.
COPY api/ ./api/
COPY README.md ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

# --- runtime stage -----------------------------------------------------------
FROM python:3.12-slim-bookworm AS runtime

# WHY a non-root user: this process parses untrusted PDFs from the public
# internet. pdfminer and pdfium are C and Python parsers with a real CVE history.
# A container escape needs a privilege to escalate from; don't hand it one.
RUN groupadd --system --gid 1001 biopolicy \
    && useradd --system --uid 1001 --gid biopolicy --create-home biopolicy

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    # Never write caches into the read-only-ish app dir at runtime.
    HOME=/home/biopolicy

WORKDIR /app

COPY --from=builder --chown=biopolicy:biopolicy /app/.venv /app/.venv
COPY --from=builder --chown=biopolicy:biopolicy /app/api /app/api

USER biopolicy

# Vercel injects PORT. The default is only for `docker run` locally.
ENV PORT=8000
EXPOSE 8000

# WHY exec form wrapped in sh: we need ${PORT} expanded at runtime, but we also
# need uvicorn to be PID 1 so it receives SIGTERM directly and can drain
# in-flight SSE streams instead of being killed mid-answer.
CMD ["sh", "-c", "exec uvicorn api.main:app --host 0.0.0.0 --port ${PORT} --workers 1 --timeout-graceful-shutdown 20 --no-access-log"]
