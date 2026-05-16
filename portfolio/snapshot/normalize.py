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


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    return float(value)


def _is_stock_plan_account(account: Mapping[str, Any], balance_account: Mapping[str, Any] | None) -> bool:
    subtype = account.get("subtype") or (balance_account or {}).get("subtype")
    return str(subtype or "").lower() == "stock plan"


def _is_cash_security(security: Mapping[str, Any], asset_name: str) -> bool:
    return (
        bool(security.get("is_cash_equivalent"))
        or str(security.get("type") or "").lower() == "cash"
        or asset_name == "CUR:USD"
    )


def _holding_value(holding: Mapping[str, Any], *, is_stock_plan: bool, is_cash: bool) -> float:
    institution_value = _to_float(holding.get("institution_value"))
    vested_value = _to_float(holding.get("vested_value"))
    if not is_stock_plan:
        return institution_value or 0.0
    if is_cash:
        return institution_value if institution_value is not None else (vested_value or 0.0)
    if vested_value is not None:
        return vested_value
    return institution_value or 0.0


def _holding_quantity(holding: Mapping[str, Any], *, is_stock_plan: bool, is_cash: bool) -> float | None:
    if is_stock_plan and not is_cash and holding.get("vested_quantity") is not None:
        return _to_float(holding.get("vested_quantity"))
    return _to_float(holding.get("quantity"))


def _can_apply_stock_plan_balance_fallback(
    holding: Mapping[str, Any],
    *,
    is_stock_plan: bool,
    is_cash: bool,
    normalized_value: float,
) -> bool:
    return (
        is_stock_plan
        and not is_cash
        and holding.get("vested_value") is None
        and normalized_value == 0.0
    )


def _merge_duplicate_holding(existing: dict[str, Any], incoming: dict[str, Any]) -> None:
    existing["quantity"] = _sum_optional_numbers(existing.get("quantity"), incoming.get("quantity"))
    existing["value"] = float(existing.get("value") or 0.0) + float(incoming.get("value") or 0.0)
    if existing["quantity"]:
        existing["unit_price"] = existing["value"] / existing["quantity"]
    existing["__is_cash"] = bool(existing.get("__is_cash")) or bool(incoming.get("__is_cash"))
    existing["__stock_plan_balance_fallback_candidate"] = bool(
        existing.get("__stock_plan_balance_fallback_candidate")
    ) and bool(incoming.get("__stock_plan_balance_fallback_candidate"))


def _apply_stock_plan_balance_fallbacks(
    rows: list[dict[str, Any]],
    *,
    accounts: Mapping[str, Mapping[str, Any]],
    balance_accounts: Mapping[str, Mapping[str, Any]],
) -> None:
    for account_id, account in accounts.items():
        balance_account = balance_accounts.get(account_id)
        if not _is_stock_plan_account(account, balance_account):
            continue
        current = _to_float(((balance_account or {}).get("balances") or {}).get("current"))
        if current is None or current <= 0:
            continue

        account_rows = [
            row
            for row in rows
            if row.get("account_id") == account_id and row.get("source") == "plaid"
        ]
        non_cash_rows = [row for row in account_rows if not bool(row.get("__is_cash"))]
        if len(non_cash_rows) != 1:
            continue

        row = non_cash_rows[0]
        if not row.get("__stock_plan_balance_fallback_candidate"):
            continue
        if float(row.get("value") or 0.0) != 0.0:
            continue

        cash_value = sum(float(cash_row.get("value") or 0.0) for cash_row in account_rows if cash_row is not row)
        row["value"] = max(current - cash_value, 0.0)


def normalize_plaid_item(
    accounts: Sequence[Mapping[str, Any]],
    holdings_response: Mapping[str, Any],
    balances_response: Mapping[str, Any],
    snapshot_date: str,
) -> list[dict[str, Any]]:
    """Normalize Plaid holdings + balances into holdings_snapshot-style rows."""
    account_by_id = {str(account["account_id"]): account for account in accounts}
    balance_account_by_id = {
        str(account["account_id"]): account
        for account in balances_response.get("accounts", [])
        if account.get("account_id") is not None
    }
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
        account = account_by_id[account_id]
        balance_account = balance_account_by_id.get(account_id)
        is_stock_plan = _is_stock_plan_account(account, balance_account)
        is_cash = _is_cash_security(security, asset_name)
        value = _holding_value(holding, is_stock_plan=is_stock_plan, is_cash=is_cash)
        quantity = _holding_quantity(holding, is_stock_plan=is_stock_plan, is_cash=is_cash)

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
            "quantity": quantity,
            "unit_price": holding.get("institution_price"),
            "price_as_of": holding.get("institution_price_as_of"),
            "value": value,
            "__is_cash": is_cash,
            "__stock_plan_balance_fallback_candidate": _can_apply_stock_plan_balance_fallback(
                holding,
                is_stock_plan=is_stock_plan,
                is_cash=is_cash,
                normalized_value=value,
            ),
        }
        snapshot_key = (snapshot_date, account_id, asset_name, "plaid")
        existing_row = investment_row_by_snapshot_key.get(snapshot_key)
        if existing_row is None:
            investment_row_by_snapshot_key[snapshot_key] = row
            rows.append(row)
        else:
            _merge_duplicate_holding(existing_row, row)

    _apply_stock_plan_balance_fallbacks(
        rows,
        accounts=account_by_id,
        balance_accounts=balance_account_by_id,
    )

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

    return [
        {key: value for key, value in row.items() if not key.startswith("__")}
        for row in rows
    ]
