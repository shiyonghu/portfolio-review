from portfolio.classify.rules import classify_holding, classify_holding_with_source


def test_cash_rule_from_asset_name() -> None:
    assert classify_holding({"asset_name": "cash", "plaid_type": None}) == "Cash"


def test_cash_equivalent_rule_classifies_as_cash() -> None:
    assert classify_holding_with_source({"asset_name": "SPAXX**", "is_cash_equivalent": 1}) == (
        "Cash",
        "rule",
    )


def test_yaml_override_wins_over_cash_equivalent_rule() -> None:
    holding = {"asset_name": "SPAXX**", "is_cash_equivalent": 1}
    overrides = {"SPAXX**": "Bond"}
    assert classify_holding_with_source(holding, overrides) == ("Bond", "yaml")


def test_fixed_income_maps_to_bond() -> None:
    assert classify_holding({"asset_name": "X", "plaid_type": "fixed income"}) == "Bond"


def test_yaml_override_wins() -> None:
    holding = {"asset_name": "VTI", "plaid_type": "fixed income"}
    overrides = {"VTI": "Equity"}
    assert classify_holding(holding, overrides) == "Equity"


def test_yaml_override_classifies_etf() -> None:
    holding = {"asset_name": "VTI", "plaid_type": "etf"}
    overrides = {"VTI": "Equity"}
    assert classify_holding_with_source(holding, overrides) == ("Equity", "yaml")


def test_unknown_etf_is_unclassified_by_rules() -> None:
    holding = {"asset_name": "NEWETF", "plaid_type": "etf"}
    assert classify_holding_with_source(holding, {}) == (None, None)


def test_real_estate_asset_kind_default() -> None:
    assert classify_holding({"asset_name": "Home", "asset_kind": "real_estate"}) == "RealEstate"


def test_private_equity_asset_kind_default() -> None:
    assert (
        classify_holding({"asset_name": "Fund X", "asset_kind": "private_equity"})
        == "Equity"
    )


def test_returns_none_when_unclassified() -> None:
    assert classify_holding({"asset_name": "Unknown"}) is None
