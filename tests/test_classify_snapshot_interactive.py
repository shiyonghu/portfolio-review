from __future__ import annotations

from collections import deque

import pytest

from portfolio.classify.ollama_suggest import BucketSuggestion
from portfolio.config import Settings
from portfolio.db.connection import get_connection, init_db
from portfolio.snapshot.runner import classify_snapshot


@pytest.fixture
def settings(tmp_path) -> Settings:
    return Settings(
        plaid_client_id="x",
        plaid_secret="y",
        plaid_env="sandbox",
        db_path=str(tmp_path / "t.db"),
        ollama_base_url="http://localhost:11434",
        ollama_model="test",
    )


def test_classify_snapshot_interactive_y_persists_llm_confirmed(
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "portfolio.snapshot.runner.fetch_bucket_suggestion",
        lambda holding, s, http_client=None: BucketSuggestion(
            suggested_bucket="Equity",
            error=None,
        ),
    )

    conn = get_connection(settings.db_path)
    init_db(conn)
    conn.execute(
        "INSERT INTO items (item_id, institution_name, status) VALUES ('i1', 't', 'active')",
    )
    conn.execute(
        """
        INSERT INTO accounts (
            account_id, item_id, source, name, type, subtype,
            owner_tag, included, tax_treatment
        ) VALUES ('a1', 'i1', 'plaid', 'Broker', 'investment', 'brokerage',
                  'household', 1, 'taxable')
        """,
    )
    conn.execute(
        """
        INSERT INTO holdings_snapshot (
            snapshot_date, account_id, source, asset_name, display_name,
            plaid_security_id, plaid_type, plaid_subtype, is_cash_equivalent,
            quantity, unit_price, price_as_of, value, bucket
        ) VALUES (
            '2026-05-01', 'a1', 'plaid', '__ZZ_UNIQUE_UNKNOWN__', 'Unknown Co',
            NULL, 'other', NULL, 0,
            1.0, 10.0, '2026-05-01', 10.0, NULL
        )
        """,
    )
    conn.commit()

    lines = deque(["y"])
    classify_snapshot(
        conn,
        "2026-05-01",
        settings,
        read_line=lambda _p: lines.popleft(),
        write=lambda _s: None,
    )

    row = conn.execute(
        "SELECT bucket, source FROM classifications WHERE asset_name = ?",
        ("__ZZ_UNIQUE_UNKNOWN__",),
    ).fetchone()
    assert row is not None
    assert row["bucket"] == "Equity"
    assert row["source"] == "llm_confirmed"

    snap = conn.execute(
        "SELECT bucket FROM holdings_snapshot WHERE asset_name = ?",
        ("__ZZ_UNIQUE_UNKNOWN__",),
    ).fetchone()
    assert snap["bucket"] == "Equity"


def test_classify_snapshot_unknown_etf_uses_llm_confirmation(
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict] = []

    monkeypatch.setattr(
        "portfolio.snapshot.runner.load_classification_overrides",
        lambda: {},
    )

    def fake_fetch_bucket_suggestion(holding, s, http_client=None):
        calls.append(dict(holding))
        return BucketSuggestion(suggested_bucket="Gold", error=None)

    monkeypatch.setattr(
        "portfolio.snapshot.runner.fetch_bucket_suggestion",
        fake_fetch_bucket_suggestion,
    )

    conn = get_connection(settings.db_path)
    init_db(conn)
    conn.execute(
        "INSERT INTO items (item_id, institution_name, status) VALUES ('i1', 't', 'active')",
    )
    conn.execute(
        """
        INSERT INTO accounts (
            account_id, item_id, source, name, type, subtype,
            owner_tag, included, tax_treatment
        ) VALUES ('a1', 'i1', 'plaid', 'Broker', 'investment', 'brokerage',
                  'household', 1, 'taxable')
        """,
    )
    conn.execute(
        """
        INSERT INTO holdings_snapshot (
            snapshot_date, account_id, source, asset_name, display_name,
            plaid_security_id, plaid_type, plaid_subtype, is_cash_equivalent,
            quantity, unit_price, price_as_of, value, bucket
        ) VALUES (
            '2026-05-01', 'a1', 'plaid', '__ZZ_UNKNOWN_ETF__', 'SPDR Gold Shares',
            NULL, 'etf', NULL, 0,
            1.0, 200.0, '2026-05-01', 200.0, NULL
        )
        """,
    )
    conn.commit()

    lines = deque(["y"])
    classify_snapshot(
        conn,
        "2026-05-01",
        settings,
        read_line=lambda _p: lines.popleft(),
        write=lambda _s: None,
    )

    assert len(calls) == 1
    assert calls[0]["asset_name"] == "__ZZ_UNKNOWN_ETF__"
    assert calls[0]["plaid_type"] == "etf"

    row = conn.execute(
        "SELECT bucket, source FROM classifications WHERE asset_name = ?",
        ("__ZZ_UNKNOWN_ETF__",),
    ).fetchone()
    assert row is not None
    assert row["bucket"] == "Gold"
    assert row["source"] == "llm_confirmed"

    snap = conn.execute(
        "SELECT bucket FROM holdings_snapshot WHERE asset_name = ?",
        ("__ZZ_UNKNOWN_ETF__",),
    ).fetchone()
    assert snap["bucket"] == "Gold"
