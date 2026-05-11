import json
import os
import time
from datetime import datetime, timezone
from typing import Type, TypeVar

from google import genai
from google.genai import types
from pydantic import BaseModel

from src.config import GEMINI_MODEL, LOGS_DIR, PRICE_INPUT_PER_M, PRICE_OUTPUT_PER_M

T = TypeVar("T", bound=BaseModel)

_client: genai.Client | None = None


def _get_client() -> genai.Client:
    global _client
    if _client is None:
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY not set — copy .env.example to .env and add your key")
        _client = genai.Client(api_key=api_key)
    return _client


def _write_log(entry: dict):
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    with open(LOGS_DIR / "gemini_calls.jsonl", "a") as f:
        f.write(json.dumps(entry) + "\n")


def call(
    prompt: str,
    schema: Type[T],
    pdf_bytes: bytes | None = None,
    context: dict | None = None,
) -> T:
    client = _get_client()

    log_entry: dict = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "schema": schema.__name__,
        "context": context,
        "pdf_size_bytes": len(pdf_bytes) if pdf_bytes else None,
        "outcome": None,
        "latency_ms": None,
        "input_tokens": None,
        "output_tokens": None,
        "cost_usd": None,
        "error": None,
    }

    if pdf_bytes:
        contents = [
            types.Part.from_bytes(data=pdf_bytes, mime_type="application/pdf"),
            prompt,
        ]
    else:
        contents = prompt

    last_exc: Exception | None = None
    for attempt in range(3):
        t0 = time.monotonic()
        try:
            response = client.models.generate_content(
                model=GEMINI_MODEL,
                contents=contents,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=schema,
                    thinking_config=types.ThinkingConfig(thinking_budget=0),
                    max_output_tokens=65536,
                ),
            )
            latency_ms = int((time.monotonic() - t0) * 1000)
            result = schema.model_validate_json(response.text)

            usage = getattr(response, "usage_metadata", None)
            input_tokens = getattr(usage, "prompt_token_count", None)
            output_tokens = getattr(usage, "candidates_token_count", None)
            cost_usd = None
            if input_tokens is not None and output_tokens is not None:
                cost_usd = round(
                    input_tokens / 1_000_000 * PRICE_INPUT_PER_M
                    + output_tokens / 1_000_000 * PRICE_OUTPUT_PER_M,
                    6,
                )

            log_entry.update(
                outcome="ok",
                latency_ms=latency_ms,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cost_usd=cost_usd,
            )
            _write_log(log_entry)
            return result

        except Exception as exc:
            err_str = str(exc)
            is_retryable = any(code in err_str for code in ("429", "500", "503", "RESOURCE_EXHAUSTED", "UNAVAILABLE"))
            latency_ms = int((time.monotonic() - t0) * 1000)

            if is_retryable and attempt < 2:
                wait = 5 * (2 ** attempt)  # 5s, 10s
                log_entry["error"] = f"attempt {attempt + 1}: {type(exc).__name__}: {exc} — retrying in {wait}s"
                last_exc = exc
                time.sleep(wait)
                continue

            log_entry.update(outcome="failed", latency_ms=latency_ms, error=f"{type(exc).__name__}: {exc}")
            _write_log(log_entry)
            raise

    log_entry.update(outcome="failed", error=str(last_exc))
    _write_log(log_entry)
    raise last_exc  # type: ignore[misc]
