# Stock Plan Valuation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Normalize Plaid stock-plan accounts so vested holdings are counted, unvested holdings are excluded, and narrow zero-value stock-plan cases can fall back to account balance.

**Architecture:** Keep the change inside `portfolio/snapshot/normalize.py`. The normalizer will choose stock-plan values before duplicate aggregation, then apply one post-aggregation balance fallback for single-security zero-value stock-plan accounts. No database schema changes are required.

**Tech Stack:** Python 3.12, pytest, existing Plaid raw payload shape, SQLite `holdings_snapshot` ingestion.

**Authoritative spec:** `docs/superpowers/specs/2026-05-16-stock-plan-valuation-design.md`

---

## File Structure

- Modify `tests/test_normalize.py`: add focused regression tests for vested stock-plan values and zero-value account-balance fallback.
- Modify `portfolio/snapshot/normalize.py`: add stock-plan value selection helpers and post-aggregation fallback.
- No changes to `portfolio/db/schema.sql`: normalized rows still fit the current `holdings_snapshot` columns.

---

## Task 1: Add Stock-Plan Regression Tests

**Files:**

- Modify: `tests/test_normalize.py`

- [ ] **Step 1: Add stock-plan account fixtures**

Append these fixtures after `BALANCES_RESPONSE_FIXTURE`:

```python
STOCK_PLAN_ACCOUNTS_FIXTURE = [
    {
        "account_id": "acc-vested-stock-plan",
        "type": "investment",
        "subtype": "stock plan",
        "name": "Example Stock Plan",
    },
    {
        "account_id": "acc-zero-value-stock-plan",
        "type": "investment",
        "subtype": "stock plan",
        "name": "Stock Plan Example A",
    },
]
```

- [ ] **Step 2: Add the vested-value test**

Append this test near the existing duplicate-holding aggregation test:

```python
def test_stock_plan_uses_vested_value_and_excludes_unvested_lots() -> None:
    holdings_response = {
        "holdings": [
            {
                "account_id": "acc-vested-stock-plan",
                "security_id": "sec-cash",
                "institution_value": 100.0,
                "quantity": 100.0,
                "institution_price": 1.0,
                "institution_price_as_of": "2026-05-16",
                "vested_quantity": 0.0,
                "vested_value": 100.0,
            },
            {
                "account_id": "acc-vested-stock-plan",
                "security_id": "sec-equity",
                "institution_value": 1000.0,
                "quantity": 10.0,
                "institution_price": 100.0,
                "institution_price_as_of": "2026-05-15",
                "vested_quantity": 0.0,
                "vested_value": 0.0,
            },
            {
                "account_id": "acc-vested-stock-plan",
                "security_id": "sec-equity",
                "institution_value": 2000.0,
                "quantity": 20.0,
                "institution_price": 100.0,
                "institution_price_as_of": "2026-05-15",
                "vested_quantity": 0.0,
                "vested_value": 0.0,
            },
            {
                "account_id": "acc-vested-stock-plan",
                "security_id": "sec-equity",
                "institution_value": 3000.0,
                "quantity": 30.0,
                "institution_price": 100.0,
                "institution_price_as_of": "2026-05-15",
                "vested_quantity": 0.0,
                "vested_value": 0.0,
            },
            {
                "account_id": "acc-vested-stock-plan",
                "security_id": "sec-equity",
                "institution_value": 4000.0,
                "quantity": 40.0,
                "institution_price": 100.0,
                "institution_price_as_of": "2026-05-15",
                "vested_quantity": 0.0,
                "vested_value": 0.0,
            },
            {
                "account_id": "acc-vested-stock-plan",
                "security_id": "sec-equity",
                "institution_value": 5000.0,
                "quantity": 50.0,
                "institution_price": 100.0,
                "institution_price_as_of": "2026-05-15",
                "vested_quantity": 50.0,
                "vested_value": 5000.0,
            },
        ],
        "securities": [
            {
                "security_id": "sec-equity",
                "ticker_symbol": "EXEQ",
                "name": "Example Equity",
                "type": "equity",
                "subtype": "common stock",
                "is_cash_equivalent": False,
            },
            {
                "security_id": "sec-cash",
                "ticker_symbol": "CUR:USD",
                "name": "U S Dollar",
                "type": "cash",
                "subtype": None,
                "is_cash_equivalent": True,
            },
        ],
    }
    balances_response = {
        "accounts": [
            {
                "account_id": "acc-vested-stock-plan",
                "type": "investment",
                "subtype": "stock plan",
                "balances": {"current": 5100.0},
            }
        ]
    }

    rows = normalize_plaid_item(
        accounts=[STOCK_PLAN_ACCOUNTS_FIXTURE[0]],
        holdings_response=holdings_response,
        balances_response=balances_response,
        snapshot_date="2026-05-16",
    )

    equity_row = next(r for r in rows if r["asset_name"] == "EXEQ")
    cash_row = next(r for r in rows if r["asset_name"] == "CUR:USD")
    assert equity_row["value"] == 5000.0
    assert equity_row["quantity"] == 50.0
    assert cash_row["value"] == 100.0
    assert round(sum(r["value"] for r in rows), 2) == 5100.0
```

- [ ] **Step 3: Add the zero-value fallback test**

Append this test after the vested-value test:

```python
def test_stock_plan_single_zero_value_security_falls_back_to_current_balance() -> None:
    holdings_response = {
        "holdings": [
            {
                "account_id": "acc-zero-value-stock-plan",
                "security_id": "sec-zero-value-equity",
                "institution_value": 0.0,
                "quantity": 0.0,
                "institution_price": 100.0,
                "institution_price_as_of": "2026-05-15",
                "vested_quantity": None,
                "vested_value": None,
            }
        ],
        "securities": [
            {
                "security_id": "sec-zero-value-equity",
                "ticker_symbol": "EXZERO",
                "name": "Example Zero Value Equity",
                "type": "equity",
                "subtype": "common stock",
                "is_cash_equivalent": False,
            }
        ],
    }
    balances_response = {
        "accounts": [
            {
                "account_id": "acc-zero-value-stock-plan",
                "type": "investment",
                "subtype": "stock plan",
                "balances": {"current": 7500.0},
            }
        ]
    }

    rows = normalize_plaid_item(
        accounts=[STOCK_PLAN_ACCOUNTS_FIXTURE[1]],
        holdings_response=holdings_response,
        balances_response=balances_response,
        snapshot_date="2026-05-16",
    )

    assert len(rows) == 1
    assert rows[0]["asset_name"] == "EXZERO"
    assert rows[0]["value"] == 7500.0
    assert rows[0]["quantity"] == 0.0
```

- [ ] **Step 4: Run failing tests**

Run:

```bash
pytest tests/test_normalize.py -q
```

Expected before implementation: both new stock-plan tests fail. The existing tests should either pass or fail only because the new behavior is missing.

---

## Task 2: Implement Stock-Plan Value Selection

**Files:**

- Modify: `portfolio/snapshot/normalize.py`

- [ ] **Step 1: Add numeric and classification helpers**

Insert these helpers after `_sum_optional_numbers`:

```python
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
```

- [ ] **Step 2: Add stock-plan value helpers**

Insert these helpers after `_is_cash_security`:

```python
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
```

- [ ] **Step 3: Preserve fallback metadata during duplicate merges**

Extend `_merge_duplicate_holding`:

```python
def _merge_duplicate_holding(existing: dict[str, Any], incoming: dict[str, Any]) -> None:
    existing["quantity"] = _sum_optional_numbers(existing.get("quantity"), incoming.get("quantity"))
    existing["value"] = float(existing.get("value") or 0.0) + float(incoming.get("value") or 0.0)
    existing["__stock_plan_balance_fallback_candidate"] = bool(
        existing.get("__stock_plan_balance_fallback_candidate")
    ) and bool(incoming.get("__stock_plan_balance_fallback_candidate"))
    if existing["quantity"]:
        existing["unit_price"] = existing["value"] / existing["quantity"]
```

- [ ] **Step 4: Build balance lookup and use stock-plan values**

In `normalize_plaid_item`, add a balance lookup after `account_by_id`:

```python
    balance_account_by_id = {
        str(account["account_id"]): account
        for account in balances_response.get("accounts", [])
        if account.get("account_id") is not None
    }
```

Then in the holdings loop, before building `row`, compute:

```python
        account = account_by_id[account_id]
        balance_account = balance_account_by_id.get(account_id)
        is_stock_plan = _is_stock_plan_account(account, balance_account)
        is_cash = _is_cash_security(security, asset_name)
        value = _holding_value(holding, is_stock_plan=is_stock_plan, is_cash=is_cash)
        quantity = _holding_quantity(holding, is_stock_plan=is_stock_plan, is_cash=is_cash)
```

Change the row fields:

```python
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
```

- [ ] **Step 5: Add narrow stock-plan balance reconciliation**

Add this helper before `normalize_plaid_item`:

```python
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
```

Call it after the holdings loop and before the depository balance loop:

```python
    _apply_stock_plan_balance_fallbacks(
        rows,
        accounts=account_by_id,
        balance_accounts=balance_account_by_id,
    )
```

- [ ] **Step 6: Strip internal metadata before returning**

Replace the final return:

```python
    return [
        {key: value for key, value in row.items() if not key.startswith("__")}
        for row in rows
    ]
```

- [ ] **Step 7: Run targeted tests**

Run:

```bash
pytest tests/test_normalize.py -q
```

Expected after implementation: all `tests/test_normalize.py` tests pass.

---

## Task 3: Verify End-to-End Safety

**Files:**

- No source edits unless verification finds a regression.

- [ ] **Step 1: Run full test suite**

Run:

```bash
pytest -q
```

Expected: full suite passes.

- [ ] **Step 2: Check lints for changed files**

Use Cursor lints for:

```text
portfolio/snapshot/normalize.py
tests/test_normalize.py
```

Expected: no new diagnostics introduced by the implementation.

- [ ] **Step 3: Manually inspect the normalized expected values**

If a quick one-off check is useful after tests pass, run a small Python snippet or debugger against the two regression fixtures. Expected normalized values:

```text
EXZERO: 7500.0
EXEQ: 5000.0
CUR:USD: 100.0
vested-lots account total: 5100.0
```

---

## Self-review (2026-05-16)

- **Spec coverage:** Tests and implementation tasks cover vested-value selection, stock-plan cash handling, zero-value balance fallback, and preservation of ordinary brokerage aggregation.
- **No placeholders:** All tasks include exact files, code snippets, commands, and expected outcomes.
- **Type consistency:** Helper signatures use `Mapping[str, Any]` and `dict[str, Any]`, matching the current `normalize.py` imports.
- **Scope:** No schema changes, no unrelated classification or CSV changes.
