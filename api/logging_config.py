"""Structured logging.

One hard rule, from Section 10 of the spec: **never write document content or a
user's question into a log line that also identifies the user.** Those two facts
are individually mundane and jointly a privacy incident. The helpers here make
the safe thing the easy thing — log identifiers and counts, not text.

`redact()` exists for the cases where a fragment genuinely helps debugging; it
truncates hard and is still not safe to pair with a user id.
"""

from __future__ import annotations

import logging
import sys
from typing import Any

import structlog
from structlog.typing import EventDict, WrappedLogger

# Field names that must never appear in a log event. Enforced by a processor
# rather than by discipline, because discipline does not survive a 2am incident.
_FORBIDDEN_KEYS: frozenset[str] = frozenset(
    {
        "content",
        "question",
        "query_text",
        "answer",
        "chunk_text",
        "document_text",
        "quote",
        "prompt",
        "messages",
    }
)


def _drop_sensitive_fields(
    _logger: WrappedLogger, _method: str, event_dict: EventDict
) -> EventDict:
    """Strip content-bearing keys from every event, unconditionally.

    A caller who really needs a fragment must pass it through `redact()` under a
    key ending in `_preview`, which makes the intent visible at the call site and
    in the log itself.
    """
    for key in _FORBIDDEN_KEYS & event_dict.keys():
        event_dict[key] = "<redacted>"
    return event_dict


def redact(text: str | None, keep: int = 40) -> str:
    """Truncate free text for debugging. Never pair the result with a user id."""
    if not text:
        return ""
    collapsed = " ".join(text.split())
    if len(collapsed) <= keep:
        return collapsed
    return f"{collapsed[:keep]}… (+{len(collapsed) - keep} chars)"


def configure_logging(level: str = "INFO", *, json_output: bool = False) -> None:
    """Configure stdlib logging and structlog. Idempotent."""
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=getattr(logging, level.upper(), logging.INFO),
    )

    # uvicorn installs its own handlers; let them propagate into ours so request
    # logs and application logs come out in one consistent format.
    for noisy in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        logging.getLogger(noisy).handlers.clear()
        logging.getLogger(noisy).propagate = True

    # httpx logs every request at INFO, including full URLs, which for signed
    # storage URLs means logging a credential. Quiet it.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)

    renderer: Any = (
        structlog.processors.JSONRenderer()
        if json_output
        else structlog.dev.ConsoleRenderer(colors=True)
    )

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.stdlib.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            _drop_sensitive_fields,
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, level.upper(), logging.INFO)
        ),
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    logger: structlog.stdlib.BoundLogger = structlog.get_logger(name)
    return logger
