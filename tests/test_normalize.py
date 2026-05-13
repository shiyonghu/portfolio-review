from portfolio.snapshot.normalize import normalize_plaid_item


ACCOUNTS_FIXTURE = [
    {
        "account_id": "acc-invest",
        "type": "investment",
        "subtype": "brokerage",
        "name": "Brokerage Account",
    },
    {
        "account_id": "acc-checking",
        "type": "depository",
        "subtype": "checking",
        "name": "Checking Account",
    },
]

HOLDINGS_RESPONSE_FIXTURE = {
    "holdings": [
        {
            "account_id": "acc-invest",
            "security_id": "sec-vti",
            "institution_value": 1200.0,
            "quantity": 5.0,
            "institution_price": 240.0,
            "institution_price_as_of": "2026-05-12",
        },
        {
            "account_id": "acc-invest",
            "security_id": "sec-noticker",
            "institution_value": 300.0,
            "quantity": 3.0,
            "institution_price": 100.0,
            "institution_price_as_of": "2026-05-12",
        },
    ],
    "securities": [
        {
            "security_id": "sec-vti",
            "ticker_symbol": "VTI",
            "name": "Vanguard Total Stock Market ETF",
            "type": "etf",
            "subtype": "large cap",
            "is_cash_equivalent": False,
        },
        {
            "security_id": "sec-noticker",
            "name": "Private Fund",
            "type": "other",
            "subtype": "other",
            "is_cash_equivalent": False,
        },
    ],
}

BALANCES_RESPONSE_FIXTURE = {
    "accounts": [
        {
            "account_id": "acc-checking",
            "type": "depository",
            "subtype": "checking",
            "balances": {"current": 2500.0},
            "name": "Checking Account",
        }
    ]
}


def test_investment_holding_uses_ticker_as_asset_name() -> None:
    rows = normalize_plaid_item(
        accounts=ACCOUNTS_FIXTURE,
        holdings_response=HOLDINGS_RESPONSE_FIXTURE,
        balances_response=BALANCES_RESPONSE_FIXTURE,
        snapshot_date="2026-05-13",
    )

    row = next(r for r in rows if r["plaid_security_id"] == "sec-vti")
    assert row["asset_name"] == "VTI"
    assert row["source"] == "plaid"
    assert row["snapshot_date"] == "2026-05-13"


def test_investment_holding_falls_back_to_security_id_when_ticker_missing() -> None:
    rows = normalize_plaid_item(
        accounts=ACCOUNTS_FIXTURE,
        holdings_response=HOLDINGS_RESPONSE_FIXTURE,
        balances_response=BALANCES_RESPONSE_FIXTURE,
        snapshot_date="2026-05-13",
    )

    row = next(r for r in rows if r["plaid_security_id"] == "sec-noticker")
    assert row["asset_name"] == "sec-noticker"


def test_depository_account_adds_cash_row_from_current_balance() -> None:
    rows = normalize_plaid_item(
        accounts=ACCOUNTS_FIXTURE,
        holdings_response=HOLDINGS_RESPONSE_FIXTURE,
        balances_response=BALANCES_RESPONSE_FIXTURE,
        snapshot_date="2026-05-13",
    )

    cash_row = next(r for r in rows if r["account_id"] == "acc-checking")
    assert cash_row["asset_name"] == "cash"
    assert cash_row["value"] == 2500.0
    assert cash_row["plaid_type"] == "cash"
