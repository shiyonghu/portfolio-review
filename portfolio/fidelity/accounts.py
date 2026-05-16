from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Callable

from portfolio.fidelity.csv import discover_accounts

AskFn = Callable[[str, str | None], str]


def setup_fidelity_accounts(
    conn: sqlite3.Connection,
    csv_path: str | Path,
    *,
    ask: AskFn,
) -> int:
    """Discover Fidelity CSV accounts and persist inclusion/tax preferences."""
    accounts = discover_accounts(csv_path)
    existing_by_id = _existing_accounts(conn)
    _raise_on_source_collisions(accounts, existing_by_id)

    for account in accounts:
        account_id = account["account_id"]
        existing = existing_by_id.get(account_id)

        choice_default = _choice_default(existing)
        included, tax_treatment = _normalize_account_choice(
            _answer_or_default(
                ask(_choice_prompt(account), choice_default),
                choice_default,
            )
        )
        tax_treatment_override = tax_treatment if included else None

        conn.execute(
            """
            INSERT INTO accounts (
                account_id,
                item_id,
                source,
                name,
                type,
                subtype,
                owner_tag,
                included,
                tax_treatment,
                tax_treatment_override
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(account_id) DO UPDATE SET
                item_id = excluded.item_id,
                source = excluded.source,
                name = excluded.name,
                type = excluded.type,
                subtype = excluded.subtype,
                owner_tag = COALESCE(accounts.owner_tag, excluded.owner_tag),
                included = excluded.included,
                tax_treatment = excluded.tax_treatment,
                tax_treatment_override = excluded.tax_treatment_override
            """,
            (
                account_id,
                None,
                "fidelity",
                account["name"],
                "investment",
                None,
                "household",
                1 if included else 0,
                tax_treatment,
                tax_treatment_override,
            ),
        )

    conn.commit()
    return len(accounts)


def _existing_accounts(conn: sqlite3.Connection) -> dict[str, sqlite3.Row]:
    rows = conn.execute(
        """
        SELECT account_id, source, included, tax_treatment, tax_treatment_override
        FROM accounts
        """
    ).fetchall()
    return {str(row["account_id"]): row for row in rows}


def _raise_on_source_collisions(
    accounts: list[dict[str, str]],
    existing_by_id: dict[str, sqlite3.Row],
) -> None:
    for account in accounts:
        account_id = account["account_id"]
        existing = existing_by_id.get(account_id)
        if existing is not None and existing["source"] != "fidelity":
            raise ValueError(
                f"Fidelity account id {account_id} conflicts with existing {existing['source']} account"
            )


def _tax_default(existing: sqlite3.Row | None) -> str | None:
    if existing is None:
        return "taxable"
    return existing["tax_treatment_override"] or existing["tax_treatment"]


def _choice_prompt(account: dict[str, str]) -> str:
    return (
        f"Fidelity account {account['name']} ({account['account_id']})\n"
        "  1) Include as taxable\n"
        "  2) Include as tax-advantaged\n"
        "  3) Exclude from snapshots\n"
        "Choose"
    )


def _choice_default(existing: sqlite3.Row | None) -> str:
    if existing is None:
        return "1"
    if not existing["included"]:
        return "3"
    tax_treatment = _tax_default(existing)
    if tax_treatment == "tax-advantaged":
        return "2"
    return "1"


def _answer_or_default(value: str, default: str | None) -> str:
    if value.strip():
        return value
    if default is not None:
        return default
    return value


def _normalize_account_choice(value: str) -> tuple[bool, str | None]:
    normalized = value.strip().lower()
    if normalized in {"1", "t", "taxable"}:
        return True, "taxable"
    if normalized in {"2", "a", "advantaged", "tax-advantaged"}:
        return True, "tax-advantaged"
    if normalized in {"3", "n", "no", "exclude", "excluded"}:
        return False, None
    raise ValueError("choose 1, 2, 3, t, a, or n")


