from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from portfolio.classify.buckets import ORDERED_BUCKETS
from portfolio.classify.ollama_suggest import (
    BucketSuggestion,
    fetch_bucket_suggestion,
    parse_bucket_json_payload,
)
from portfolio.config import Settings


def test_ordered_buckets_matches_rules_vocabulary() -> None:
    assert "RealEstate" in ORDERED_BUCKETS
    assert "Equity" in ORDERED_BUCKETS


def test_parse_plain_json() -> None:
    bucket, reason, err = parse_bucket_json_payload('{"bucket":"Equity","reason":"US stock ETF"}')
    assert err is None
    assert bucket == "Equity"
    assert reason is not None
    assert "ETF" in reason


def test_parse_json_in_markdown_fence() -> None:
    raw = """Here is the result:
```json
{"bucket": "Bond", "reason": "fixed income"}
```

"""
    bucket, reason, err = parse_bucket_json_payload(raw)
    assert err is None
    assert bucket == "Bond"
    assert reason is not None


def test_invalid_bucket_rejected() -> None:
    bucket, reason, err = parse_bucket_json_payload('{"bucket":"Banana","reason":"x"}')
    assert bucket is None
    assert err is not None


def test_malformed_json() -> None:
    bucket, reason, err = parse_bucket_json_payload("not json")
    assert bucket is None
    assert err is not None


def test_fetch_bucket_suggestion_uses_chat_api(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["body"] = json.loads(request.content.decode())
        return httpx.Response(
            200,
            json={"message": {"content": '{"bucket":"Gold","reason":"gold ETC"}'}},
        )

    settings = Settings(
        plaid_client_id="",
        plaid_secret="",
        plaid_env="sandbox",
        db_path=":memory:",
        ollama_base_url="http://ollama.test",
        ollama_model="test-model",
    )
    holding = {"asset_name": "GLD", "display_name": None, "plaid_type": "etf"}
    transport = httpx.MockTransport(handler)
    with httpx.Client(transport=transport) as client:
        result = fetch_bucket_suggestion(holding, settings, http_client=client)

    assert isinstance(result, BucketSuggestion)
    assert result.suggested_bucket == "Gold"
    assert result.error is None
    assert "gold" in result.reason.lower()
    assert captured["url"].endswith("/api/chat")
    assert captured["body"]["model"] == "test-model"
    assert captured["body"]["stream"] is False
    assert captured["body"]["format"] == "json"
