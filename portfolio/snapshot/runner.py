from __future__ import annotations

import json
import sqlite3
from datetime import date
from pathlib import Path
from typing import Any

from portfolio.classify.ollama_suggest import suggest_bucket
from portfolio.classify.rules import classify_holding_with_source
from portfolio.classify.yaml_store import load_classification_overrides
from portfolio.config import Settings
from portfolio.keychain.tokens import load_access_token
from portfolio.managed.service import materialize_managed_rows
from portfolio.plaid.client import fetch_balances, fetch_holdings, make_plaid_client
from portfolio.snapshot.export_csv import export_snapshot_csv
from portfolio.snapshot.normalize import normalize_plaid_item
from portfolio.snapshot.summary import rebuild_snapshot_summary

_HOLDINGS_COLUMNS = (
    "snapshot_date",
    "account_id",
    "source",
    "asset_name",
    "display_name",
    "plaid_security_id",
    "plaid_type",
    "plaid_subtype",
    "is_cash_equivalent",
    "quantity",
    "unit_price",
    "price_as_of",
    "value",
    "bucket",
)


def delete_snapshot_date(conn: sqlite3.Connection, snapshot_date: str) -> None:
    conn.execute("DELETE FROM holdings_snapshot WHERE snapshot_date = ?", (snapshot_date,))
    conn.execute("DELETE FROM snapshot_summary WHERE snapshot_date = ?", (snapshot_date,))
    conn.commit()


def insert_holdings_snapshot(
    conn: sqlite3.Connection,
    rows: list[dict[str, Any]],
) -> None:
    if not rows:
        return
    conn.executemany(
        """
        INSERT INTO holdings_snapshot (
            snapshot_date, account_id, source, asset_name, display_name,
            plaid_security_id, plaid_type, plaid_subtype, is_cash_equivalent,
            quantity, unit_price, price_as_of, value, bucket
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [tuple(row.get(column) for column in _HOLDINGS_COLUMNS) for row in rows],
    )
    conn.commit()


def _lookup_asset_kind(conn: sqlite3.Connection, asset_name: str) -> str | None:
    row = conn.execute(
        """
        SELECT asset_kind
        FROM user_managed_holdings
        WHERE asset_name = ? AND is_active = 1
        ORDER BY effective_date DESC, id DESC
        LIMIT 1
        """,
        (asset_name,),
    ).fetchone()
    return str(row["asset_kind"]) if row is not None else None


def classify_snapshot(conn: sqlite3.Connection, snapshot_date: str, settings: Settings) -> None:
    overrides = load_classification_overrides()
    rows = conn.execute(
        """
        SELECT DISTINCT asset_name, plaid_type, plaid_subtype, source
        FROM holdings_snapshot
        WHERE snapshot_date = ?
        """,
        (snapshot_date,),
    ).fetchall()

    for row in rows:
        asset_name = str(row["asset_name"])
        existing = conn.execute(
            "SELECT bucket FROM classifications WHERE asset_name = ?",
            (asset_name,),
        ).fetchone()
        if existing is not None:
            continue

        holding = dict(row)
        if holding.get("source") == "user_managed":
            holding["asset_kind"] = _lookup_asset_kind(conn, asset_name)

        bucket, source = classify_holding_with_source(holding, overrides)
        if bucket is None:
            bucket = suggest_bucket(holding, settings)
            source = "llm_confirmed" if bucket else None
        if bucket is None or source is None:
            continue

        conn.execute(
            """
            INSERT INTO classifications (asset_name, bucket, source, classified_at)
            VALUES (?, ?, ?, datetime('now'))
            ON CONFLICT(asset_name) DO UPDATE SET
                bucket = excluded.bucket,
                source = excluded.source,
                classified_at = excluded.classified_at
            """,
            (asset_name, bucket, source),
        )

    conn.execute(
        """
        UPDATE holdings_snapshot
        SET bucket = (
            SELECT c.bucket
            FROM classifications c
            WHERE c.asset_name = holdings_snapshot.asset_name
        )
        WHERE snapshot_date = ?
        """,
        (snapshot_date,),
    )
    conn.commit()


def _archive_raw_payload(base_dir: Path, item_id: str, suffix: str, payload: dict[str, Any]) -> None:
    base_dir.mkdir(parents=True, exist_ok=True)
    (base_dir / f"{item_id}-{suffix}.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def run_snapshot(conn: sqlite3.Connection, settings: Settings, snapshot_date: str | None = None) -> dict[str, Any]:
    target_date = snapshot_date or date.today().isoformat()
    raw_dir = Path("snapshots/raw") / target_date
    csv_path = Path("snapshots/csv") / f"{target_date}.csv"

    delete_snapshot_date(conn, target_date)

    plaid_rows: list[dict[str, Any]] = []
    client = make_plaid_client(settings)
    items = conn.execute("SELECT item_id FROM items ORDER BY item_id").fetchall()
    for item in items:
        item_id = str(item["item_id"])
        token = load_access_token(item_id)
        if not token:
            continue
        holdings = fetch_holdings(client, token)
        balances = fetch_balances(client, token)
        _archive_raw_payload(raw_dir, item_id, "holdings", holdings)
        _archive_raw_payload(raw_dir, item_id, "balances", balances)

        accounts = conn.execute(
            "SELECT account_id, subtype FROM accounts WHERE item_id = ?",
            (item_id,),
        ).fetchall()
        plaid_rows.extend(
            normalize_plaid_item(
                accounts=[dict(a) for a in accounts],
                holdings_response=holdings,
                balances_response=balances,
                snapshot_date=target_date,
            )
        )

    managed_rows = materialize_managed_rows(conn, target_date)
    insert_holdings_snapshot(conn, plaid_rows + managed_rows)
    classify_snapshot(conn, target_date, settings)
    rebuild_snapshot_summary(conn, target_date)
    export_snapshot_csv(conn, target_date, csv_path)

    return {
        "snapshot_date": target_date,
        "raw_dir": raw_dir,
        "csv_path": csv_path,
        "holdings_count": len(plaid_rows) + len(managed_rows),
    }
