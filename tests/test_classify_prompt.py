from __future__ import annotations

from collections import deque

from portfolio.classify.buckets import ORDERED_BUCKETS
from portfolio.classify.ollama_suggest import BucketSuggestion
from portfolio.classify.prompt import prompt_confirmed_bucket


def test_y_accepts_suggestion() -> None:
    out: list[str] = []

    def write(s: str) -> None:
        out.append(s)

    lines = deque(["y"])
    action, bucket = prompt_confirmed_bucket(
        asset_name="FOO",
        suggestion=BucketSuggestion(suggested_bucket="Equity", error=None),
        read_line=lambda _p: lines.popleft(),
        write=write,
    )
    assert action == "persist"
    assert bucket == "Equity"


def test_y_without_suggestion_reprompts_then_m() -> None:
    lines = deque(["y", "m", "3"])
    action, bucket = prompt_confirmed_bucket(
        asset_name="BAR",
        suggestion=BucketSuggestion(suggested_bucket=None, error="offline"),
        read_line=lambda _p: lines.popleft(),
        write=lambda _s: None,
    )
    assert action == "persist"
    assert ORDERED_BUCKETS[2] == "Equity"
    assert bucket == "Equity"


def test_n_skips() -> None:
    action, bucket = prompt_confirmed_bucket(
        asset_name="X",
        suggestion=BucketSuggestion(suggested_bucket="Gold", error=None),
        read_line=lambda _p: "n",
        write=lambda _s: None,
    )
    assert action == "skip"
    assert bucket is None


def test_q_quits() -> None:
    action, bucket = prompt_confirmed_bucket(
        asset_name="X",
        suggestion=BucketSuggestion(suggested_bucket="Gold", error=None),
        read_line=lambda _p: "q",
        write=lambda _s: None,
    )
    assert action == "quit"
    assert bucket is None


def test_m_invalid_then_valid() -> None:
    lines = deque(["m", "0", "m", "2"])
    action, bucket = prompt_confirmed_bucket(
        asset_name="Z",
        suggestion=BucketSuggestion(suggested_bucket=None, error=None),
        read_line=lambda _p: lines.popleft(),
        write=lambda _s: None,
    )
    assert action == "persist"
    assert bucket == "Bond"
