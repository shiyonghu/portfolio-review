from __future__ import annotations

import json
import sqlite3
from collections.abc import Callable
from datetime import date, datetime
from pathlib import Path
from typing import Any

from portfolio.classify.ollama_suggest import fetch_bucket_suggestion
from portfolio.classify.prompt import prompt_confirmed_bucket
from portfolio.classify.rules import classify_holding_with_source
from portfolio.classify.yaml_store import load_classification_overrides
from portfolio.config import Settings
from portfolio.fidelity.csv import (
    normalize_holdings as normalize_fidelity_holdings,
    validate_snapshot_accounts,
)
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

class SnapshotPlaidError(RuntimeError):
    """Plaid failed while snapshot context was available locally."""


def _format_plaid_fetch_error(
    operation: str,
    item_id: str,
    accounts: list[dict[str, Any]],
    exc: Exception,
) -> str:
    account_details = ", ".join(
        (
            f"{account['account_id']}"
            f" (included={account['included']}, type={account['type']}, subtype={account['subtype']})"
        )
        for account in accounts
    )
    if not account_details:
        account_details = "none configured"

    parts = [
        f"Plaid {operation} failed for item_id={item_id}",
        f"accounts=[{account_details}]",
    ]
    status = getattr(exc, "status", None)
    reason = getattr(exc, "reason", None)
    body = getattr(exc, "body", None)
    if status is not None:
        parts.append(f"status={status}")
    if reason:
        parts.append(f"reason={reason}")
    if body:
        parts.append(f"body={body}")
    return "; ".join(parts)


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


def classify_snapshot(
    conn: sqlite3.Connection,
    snapshot_date: str,
    settings: Settings,
    *,
    read_line: Callable[[str], str] | None = None,
    write: Callable[[str], None] | None = None,
) -> None:
    overrides = load_classification_overrides()
    read = read_line if read_line is not None else input
    write_fn = write if write is not None else (lambda m: print(m, end="", flush=True))

    rows = conn.execute(
        """
        SELECT
            asset_name,
            MAX(display_name) AS display_name,
            MAX(plaid_type) AS plaid_type,
            MAX(plaid_subtype) AS plaid_subtype,
            MAX(is_cash_equivalent) AS is_cash_equivalent,
            MAX(source) AS source
        FROM holdings_snapshot
        WHERE snapshot_date = ?
        GROUP BY asset_name
        ORDER BY asset_name
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
        if bucket is not None and source is not None:
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
            continue

        suggestion = fetch_bucket_suggestion(holding, settings)
        action, chosen = prompt_confirmed_bucket(
            asset_name=asset_name,
            suggestion=suggestion,
            read_line=read,
            write=write_fn,
        )
        if action == "quit":
            break
        if action == "persist" and chosen:
            conn.execute(
                """
                INSERT INTO classifications (asset_name, bucket, source, classified_at)
                VALUES (?, ?, ?, datetime('now'))
                ON CONFLICT(asset_name) DO UPDATE SET
                    bucket = excluded.bucket,
                    source = excluded.source,
                    classified_at = excluded.classified_at
                """,
                (asset_name, chosen, "llm_confirmed"),
            )
        # skip: no row written

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


def _json_default(value: Any) -> str:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return str(value)


def _archive_raw_payload(base_dir: Path, item_id: str, suffix: str, payload: dict[str, Any]) -> None:
    base_dir.mkdir(parents=True, exist_ok=True)
    (base_dir / f"{item_id}-{suffix}.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True, default=_json_default),
        encoding="utf-8",
    )


def run_snapshot(
    conn: sqlite3.Connection,
    settings: Settings,
    snapshot_date: str | None = None,
    *,
    fidelity_csv: Path | None = None,
) -> dict[str, Any]:
    target_date = snapshot_date or date.today().isoformat()
    raw_dir = Path("snapshots/raw") / target_date
    csv_path = Path("snapshots/csv") / f"{target_date}.csv"

    fidelity_rows: list[dict[str, Any]] = []
    if fidelity_csv is not None:
        configured_accounts = {
            str(row["account_id"]): dict(row)
            for row in conn.execute(
                """
                SELECT account_id, included, tax_treatment
                FROM accounts
                WHERE source = 'fidelity'
                """
            ).fetchall()
        }
        included_accounts = validate_snapshot_accounts(
            fidelity_csv,
            configured_accounts=configured_accounts,
        )
        fidelity_rows = normalize_fidelity_holdings(
            fidelity_csv,
            snapshot_date=target_date,
            included_accounts=included_accounts,
        )

    delete_snapshot_date(conn, target_date)

    plaid_rows: list[dict[str, Any]] = []
    client = make_plaid_client(settings)
    items = conn.execute("SELECT item_id FROM items ORDER BY item_id").fetchall()
    for item in items:
        item_id = str(item["item_id"])
        token = load_access_token(item_id)
        if not token:
            continue
        accounts_for_item = [
            dict(account)
            for account in conn.execute(
                """
                SELECT account_id, included, type, subtype
                FROM accounts
                WHERE item_id = ?
                ORDER BY account_id
                """,
                (item_id,),
            ).fetchall()
        ]
        try:
            holdings = fetch_holdings(client, token)
        except Exception as exc:
            raise SnapshotPlaidError(
                _format_plaid_fetch_error("holdings fetch", item_id, accounts_for_item, exc)
            ) from exc
        try:
            balances = fetch_balances(client, token)
        except Exception as exc:
            raise SnapshotPlaidError(
                _format_plaid_fetch_error("balances fetch", item_id, accounts_for_item, exc)
            ) from exc
        _archive_raw_payload(raw_dir, item_id, "holdings", holdings)
        _archive_raw_payload(raw_dir, item_id, "balances", balances)

        accounts = conn.execute(
            """
            SELECT account_id, subtype, type
            FROM accounts
            WHERE item_id = ? AND included = 1
            """,
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
    insert_holdings_snapshot(conn, plaid_rows + fidelity_rows + managed_rows)
    classify_snapshot(conn, target_date, settings)
    rebuild_snapshot_summary(conn, target_date)
    export_snapshot_csv(conn, target_date, csv_path)

    return {
        "snapshot_date": target_date,
        "raw_dir": raw_dir,
        "csv_path": csv_path,
        "holdings_count": len(plaid_rows) + len(fidelity_rows) + len(managed_rows),
    }
