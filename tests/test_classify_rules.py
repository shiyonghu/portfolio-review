from portfolio.classify.rules import classify_holding


def test_cash_rule_from_asset_name() -> None:
    assert classify_holding({"asset_name": "cash", "plaid_type": None}) == "Cash"


def test_fixed_income_maps_to_bond() -> None:
    assert classify_holding({"asset_name": "X", "plaid_type": "fixed income"}) == "Bond"


def test_yaml_override_wins() -> None:
    holding = {"asset_name": "VTI", "plaid_type": "fixed income"}
    overrides = {"VTI": "Equity"}
    assert classify_holding(holding, overrides) == "Equity"


def test_real_estate_asset_kind_default() -> None:
    assert classify_holding({"asset_name": "Home", "asset_kind": "real_estate"}) == "RealEstate"


def test_private_equity_asset_kind_default() -> None:
    assert (
        classify_holding({"asset_name": "Fund X", "asset_kind": "private_equity"})
        == "Equity"
    )


def test_returns_none_when_unclassified() -> None:
    assert classify_holding({"asset_name": "Unknown"}) is None
