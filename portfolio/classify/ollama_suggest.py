from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

import httpx
from httpx import ConnectError, HTTPStatusError, TimeoutException

from portfolio.classify.buckets import ORDERED_BUCKETS, is_allowed_bucket
from portfolio.config import Settings

_OLLAMA_CHAT_TIMEOUT_SEC = 60.0
_OLLAMA_NUM_PREDICT = 30


def _extract_markdown_fence_body(text: str) -> str | None:
    """If `text` contains a ``` fenced block, return its inner body (first block only)."""
    m = re.search(r"```(?:json)?\s*\n?", text, flags=re.IGNORECASE)
    if not m:
        return None
    after = text[m.end() :]
    close = after.find("```")
    if close < 0:
        return None
    return after[:close]


def parse_bucket_json_payload(content: str) -> tuple[str | None, str | None]:
    """Parse model output into `(bucket, error)`. `error` is set when parsing/validation fails."""
    text = (content or "").strip()
    fenced = _extract_markdown_fence_body(text)
    if fenced is not None:
        text = fenced.strip()
    brace = text.find("{")
    if brace < 0:
        return None, "No JSON object found"
    try:
        obj, _end = json.JSONDecoder().raw_decode(text, brace)
    except json.JSONDecodeError as exc:
        return None, f"Invalid JSON: {exc}"
    if not isinstance(obj, dict):
        return None, "JSON root must be an object"
    bucket_raw = obj.get("bucket")
    if not isinstance(bucket_raw, str):
        return None, "bucket must be a string"
    bucket = bucket_raw.strip()
    if not is_allowed_bucket(bucket):
        return None, f"Unknown bucket: {bucket_raw!r}"
    return bucket, None


@dataclass(frozen=True)
class BucketSuggestion:
    suggested_bucket: str | None
    error: str | None = None


def _holding_prompt_json(holding: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key in ("asset_name", "display_name", "plaid_type", "plaid_subtype", "source"):
        if key in holding:
            out[key] = holding[key]
    if "asset_kind" in holding:
        out["asset_kind"] = holding["asset_kind"]
    return out


def _build_user_prompt(holding: dict[str, Any]) -> str:
    allowed = ", ".join(ORDERED_BUCKETS)
    payload = json.dumps(_holding_prompt_json(holding), sort_keys=True, default=str)
    return (
        "Classify the holding. Return only the answer.\n"
        "Return exactly one compact JSON object and stop.\n"
        f"Buckets: {allowed}\n"
        f"Holding: {payload}\n"
        'Output exactly: {"bucket":"<bucket>"}'
    )


def fetch_bucket_suggestion(
    holding: dict[str, Any],
    settings: Settings,
    *,
    http_client: httpx.Client | None = None,
) -> BucketSuggestion:
    """Call Ollama `/api/chat` with JSON format and return a parsed suggestion or error text."""
    base_url = settings.ollama_base_url.rstrip("/")
    body = {
        "model": settings.ollama_model,
        "messages": [{"role": "user", "content": _build_user_prompt(holding)}],
        "stream": False,
        "format": "json",
        "options": {
            "temperature": 0,
            "num_predict": _OLLAMA_NUM_PREDICT,
        },
    }

    def _do_request(client: httpx.Client) -> BucketSuggestion:
        try:
            response = client.post(f"{base_url}/api/chat", json=body)
            response.raise_for_status()
        except ConnectError as exc:
            return BucketSuggestion(
                suggested_bucket=None,
                error=(
                    f"Cannot reach Ollama at {base_url}. "
                    "Start Ollama (e.g. open the Ollama app or run `ollama serve`) "
                    f"and pull the model with `ollama pull {settings.ollama_model}`."
                ),
            )
        except HTTPStatusError as exc:
            if exc.response.status_code == 404:
                return BucketSuggestion(
                    suggested_bucket=None,
                    error=(
                        f"Ollama model {settings.ollama_model!r} was not found. "
                        f"Pull it with `ollama pull {settings.ollama_model}`."
                    ),
                )
            return BucketSuggestion(
                suggested_bucket=None,
                error=f"Ollama request failed: HTTP {exc.response.status_code}",
            )
        except TimeoutException:
            return BucketSuggestion(
                suggested_bucket=None,
                error=(
                    f"Ollama did not respond within {_OLLAMA_CHAT_TIMEOUT_SEC:.0f}s "
                    f"at {base_url}. The model may be loading or slow to generate; "
                    "try again, use a smaller/faster model, or pick a bucket manually (m) or skip (n)."
                ),
            )
        payload = response.json()
        message = payload.get("message", {})
        content = str(message.get("content", "") or "")
        bucket, err = parse_bucket_json_payload(content)
        if err is not None:
            return BucketSuggestion(suggested_bucket=None, error=err)
        return BucketSuggestion(suggested_bucket=bucket, error=None)

    if http_client is not None:
        return _do_request(http_client)
    with httpx.Client(timeout=_OLLAMA_CHAT_TIMEOUT_SEC) as client:
        return _do_request(client)
