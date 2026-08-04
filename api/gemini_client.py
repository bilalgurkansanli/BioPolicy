"""How a Google GenAI client is built.

One function rather than two constructors, because the timeout is the kind of
setting that gets applied to the client someone remembered and not to the one
they did not. Both the embedder and the fallback/rewrite model go through here.
"""

from __future__ import annotations

from google import genai
from google.genai import types as genai_types

from api.constants import GEMINI_TIMEOUT_SECONDS


def build_client(api_key: str, *, timeout_seconds: float = GEMINI_TIMEOUT_SECONDS) -> genai.Client:
    """A client that cannot wait forever.

    `timeout_seconds` is overridden for OCR, where a single call transcribes a
    whole rendered page and legitimately takes far longer than a query-time
    call. Ingestion is asynchronous, so a slow page costs nobody a spinner.
    """
    return genai.Client(
        api_key=api_key,
        # The Google client has no default timeout, unlike the Anthropic one.
        # Its `timeout` is in milliseconds; passing seconds here would set a
        # 45ms ceiling and fail every call, which is why the conversion is
        # explicit rather than inline at the call site.
        http_options=genai_types.HttpOptions(timeout=int(timeout_seconds * 1000)),
    )
