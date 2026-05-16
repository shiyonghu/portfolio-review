from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any


def _to_bool_int(value: Any) -> int | None:
    if value is None:
        return None
    return 1 if bool(value) else 0


def _sum_optional_numbers(left: Any, right: Any) -> float | None:
    values = [value for value in (left, right) if value is not None]
    if not values:
        return None
    return sum(float(value) for value in values)


def _merge_duplicate_holding(existing: dict[str, Any], incoming: dict[str, Any]) -> None:
    existing["quantity"] = _sum_optional_numbers(existing.get("quantity"), incoming.get("quantity"))
    existing["value"] = float(existing.get("value") or 0.0) + float(incoming.get("value") or 0.0)
    if existing["quantity"]:
        existing["unit_price"] = existing["value"] / existing["quantity"]


def normalize_plaid_item(
    accounts: Sequence[Mapping[str, Any]],
    holdings_response: Mapping[str, Any],
    balances_response: Mapping[str, Any],
    snapshot_date: str,
) -> list[dict[str, Any]]:
    """Normalize Plaid holdings + balances into holdings_snapshot-style rows."""
    account_by_id = {str(account["account_id"]): account for account in accounts}
    securities = holdings_response.get("securities", [])
    security_by_id = {
        str(security["security_id"]): security
        for security in securities
        if security.get("security_id") is not None
    }

    rows: list[dict[str, Any]] = []
    investment_row_by_snapshot_key: dict[tuple[str, str, str, str], dict[str, Any]] = {}

    for holding in holdings_response.get("holdings", []):
        security_id = holding.get("security_id")
        if security_id is None:
            continue

        account_id = str(holding.get("account_id") or "")
        if account_id not in account_by_id:
            continue
        security = security_by_id.get(str(security_id), {})
        ticker = str(security.get("ticker_symbol") or "").strip()
        asset_name = ticker or str(security_id)

        row = {
            "snapshot_date": snapshot_date,
            "account_id": account_id,
            "source": "plaid",
            "asset_name": asset_name,
            "display_name": security.get("name") or asset_name,
            "plaid_security_id": str(security_id),
            "plaid_type": security.get("type"),
            "plaid_subtype": security.get("subtype"),
            "is_cash_equivalent": _to_bool_int(security.get("is_cash_equivalent")),
            "quantity": holding.get("quantity"),
            "unit_price": holding.get("institution_price"),
            "price_as_of": holding.get("institution_price_as_of"),
            "value": holding.get("institution_value") or 0.0,
        }
        snapshot_key = (snapshot_date, account_id, asset_name, "plaid")
        existing_row = investment_row_by_snapshot_key.get(snapshot_key)
        if existing_row is None:
            investment_row_by_snapshot_key[snapshot_key] = row
            rows.append(row)
        else:
            _merge_duplicate_holding(existing_row, row)

    for balance_account in balances_response.get("accounts", []):
        account_id = str(balance_account.get("account_id") or "")
        if account_id not in account_by_id:
            continue

        account = account_by_id[account_id]
        account_type = str(account.get("type") or balance_account.get("type") or "").lower()
        if account_type != "depository":
            continue

        current = (balance_account.get("balances") or {}).get("current")
        if current is None:
            continue

        rows.append(
            {
                "snapshot_date": snapshot_date,
                "account_id": account_id,
                "source": "plaid",
                "asset_name": "cash",
                "display_name": "cash",
                "plaid_security_id": None,
                "plaid_type": "cash",
                "plaid_subtype": account.get("subtype"),
                "is_cash_equivalent": 1,
                "quantity": None,
                "unit_price": 1.0,
                "price_as_of": None,
                "value": current,
            }
        )

    return rows
