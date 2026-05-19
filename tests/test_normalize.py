import pytest

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


def test_duplicate_investment_holdings_are_aggregated_by_snapshot_key() -> None:
    holdings_response = {
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
                "security_id": "sec-vti",
                "institution_value": 480.0,
                "quantity": 2.0,
                "institution_price": 240.0,
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
            }
        ],
    }

    rows = normalize_plaid_item(
        accounts=ACCOUNTS_FIXTURE,
        holdings_response=holdings_response,
        balances_response={"accounts": []},
        snapshot_date="2026-05-13",
    )

    assert len(rows) == 1
    assert rows[0]["asset_name"] == "VTI"
    assert rows[0]["value"] == 1680.0
    assert rows[0]["quantity"] == 7.0


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


def test_skips_self_directed_brokerage_reference_holding() -> None:
    accounts = [
        {
            "account_id": "acc-401k",
            "type": "investment",
            "subtype": "401k",
            "name": "401(k)",
        },
    ]
    holdings_response = {
        "holdings": [
            {
                "account_id": "acc-401k",
                "security_id": "sec-fund",
                "institution_value": 551.83,
                "quantity": 4.804,
                "institution_price": 114.87,
            },
            {
                "account_id": "acc-401k",
                "security_id": "sec-self-directed",
                "institution_value": 1_033_445.97,
                "quantity": 1_033_445.97,
                "institution_price": 1.0,
            },
        ],
        "securities": [
            {
                "security_id": "sec-fund",
                "name": "Instl 500 Index Trust",
                "type": "mutual fund",
                "is_cash_equivalent": False,
            },
            {
                "security_id": "sec-self-directed",
                "name": "Self-Directed Brokerage Fund",
                "type": "mutual fund",
                "is_cash_equivalent": False,
            },
        ],
    }

    rows = normalize_plaid_item(
        accounts=accounts,
        holdings_response=holdings_response,
        balances_response={"accounts": []},
        snapshot_date="2026-05-18",
    )

    assert len(rows) == 1
    assert rows[0]["plaid_security_id"] == "sec-fund"
    assert rows[0]["display_name"] == "Instl 500 Index Trust"
    assert all(r["plaid_security_id"] != "sec-self-directed" for r in rows)


@pytest.mark.parametrize(
    ("security_name", "expected_in_snapshot"),
    [
        ("Self-Directed Brokerage Fund", False),
        ("self directed fund", False),
        ("SELF DIRECT BROKERAGE", False),
        ("Instl 500 Index Trust", True),
    ],
)
def test_self_directed_reference_name_filter(security_name: str, expected_in_snapshot: bool) -> None:
    accounts = [
        {
            "account_id": "acc-401k",
            "type": "investment",
            "subtype": "401k",
            "name": "401(k)",
        },
    ]
    holdings_response = {
        "holdings": [
            {
                "account_id": "acc-401k",
                "security_id": "sec-test",
                "institution_value": 100.0,
                "quantity": 1.0,
                "institution_price": 100.0,
            },
        ],
        "securities": [
            {
                "security_id": "sec-test",
                "name": security_name,
                "type": "mutual fund",
                "is_cash_equivalent": False,
            },
        ],
    }

    rows = normalize_plaid_item(
        accounts=accounts,
        holdings_response=holdings_response,
        balances_response={"accounts": []},
        snapshot_date="2026-05-18",
    )

    if expected_in_snapshot:
        assert len(rows) == 1
        assert rows[0]["plaid_security_id"] == "sec-test"
    else:
        assert rows == []


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


def test_included_depository_uses_account_type_from_db() -> None:
    accounts = [{"account_id": "acc-savings", "subtype": "savings", "type": "depository"}]
    balances = {
        "accounts": [
            {
                "account_id": "acc-savings",
                "type": "depository",
                "subtype": "savings",
                "balances": {"current": 210.0},
            },
            {
                "account_id": "acc-checking",
                "type": "depository",
                "subtype": "checking",
                "balances": {"current": 110.0},
            },
        ]
    }

    rows = normalize_plaid_item(
        accounts=accounts,
        holdings_response={"holdings": [], "securities": []},
        balances_response=balances,
        snapshot_date="2026-05-13",
    )

    assert len(rows) == 1
    assert rows[0]["account_id"] == "acc-savings"
    assert rows[0]["value"] == 210.0


def test_included_depository_falls_back_to_balance_type_when_db_type_missing() -> None:
    """Balance API type is used when persisted account row has no type yet."""
    accounts = [{"account_id": "acc-savings", "subtype": "savings"}]
    balances = {
        "accounts": [
            {
                "account_id": "acc-savings",
                "type": "depository",
                "subtype": "savings",
                "balances": {"current": 210.0},
            },
            {
                "account_id": "acc-checking",
                "type": "depository",
                "subtype": "checking",
                "balances": {"current": 110.0},
            },
        ]
    }

    rows = normalize_plaid_item(
        accounts=accounts,
        holdings_response={"holdings": [], "securities": []},
        balances_response=balances,
        snapshot_date="2026-05-13",
    )

    assert len(rows) == 1
    assert rows[0]["account_id"] == "acc-savings"
    assert rows[0]["value"] == 210.0
