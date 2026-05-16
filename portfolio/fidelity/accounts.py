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

        include_default = _include_default(existing)
        included = _normalize_yes_no(
            _answer_or_default(
                ask(f"Include Fidelity account {account['name']} ({account_id})?", include_default),
                include_default,
            )
        )

        tax_treatment = None
        tax_treatment_override = None
        if included:
            tax_default = _tax_default(existing)
            tax_treatment = _normalize_tax_treatment(
                _answer_or_default(
                    ask(f"Tax treatment for Fidelity account {account['name']} ({account_id})?", tax_default),
                    tax_default,
                )
            )
            tax_treatment_override = tax_treatment

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


def _include_default(existing: sqlite3.Row | None) -> str:
    if existing is None:
        return "y"
    return "y" if existing["included"] else "n"


def _tax_default(existing: sqlite3.Row | None) -> str | None:
    if existing is None:
        return "taxable"
    return existing["tax_treatment_override"] or existing["tax_treatment"]


def _answer_or_default(value: str, default: str | None) -> str:
    if value.strip():
        return value
    if default is not None:
        return default
    return value


def _normalize_yes_no(value: str) -> bool:
    normalized = value.strip().lower()
    if normalized in {"y", "yes"}:
        return True
    if normalized in {"n", "no"}:
        return False
    raise ValueError("answer must be 'y'/'yes' or 'n'/'no'")


def _normalize_tax_treatment(value: str) -> str:
    normalized = value.strip().lower()
    if normalized in {"taxable", "tax-advantaged"}:
        return normalized
    raise ValueError("tax treatment must be 'taxable' or 'tax-advantaged'")
