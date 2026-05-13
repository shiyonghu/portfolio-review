from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from portfolio.classify.yaml_store import load_classification_overrides

Bucket = str

_PLAID_TYPE_BUCKETS: dict[str, Bucket] = {
    "cash": "Cash",
    "fixed income": "Bond",
    "bond": "Bond",
    "equity": "Equity",
    "stock": "Equity",
    "etf": "Equity",
    "mutual fund": "Equity",
    "gold": "Gold",
    "commodity": "Commodity",
    "crypto": "Crypto",
    "cryptocurrency": "Crypto",
    "real estate": "RealEstate",
}

_ASSET_KIND_DEFAULTS: dict[str, Bucket] = {
    "real_estate": "RealEstate",
    "private_equity": "Equity",
}


def _normalize(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip().lower()


def classify_holding(
    holding: Mapping[str, Any],
    yaml_overrides: Mapping[str, str] | None = None,
) -> Bucket | None:
    """Classify a holding by YAML, Plaid metadata, then asset_kind defaults."""
    overrides = yaml_overrides or load_classification_overrides()

    asset_name = str(holding.get("asset_name") or "").strip()
    if asset_name:
        if asset_name in overrides:
            return overrides[asset_name]
        upper_name = asset_name.upper()
        if upper_name in overrides:
            return overrides[upper_name]

    plaid_type = _normalize(holding.get("plaid_type"))
    if plaid_type in _PLAID_TYPE_BUCKETS:
        return _PLAID_TYPE_BUCKETS[plaid_type]

    plaid_subtype = _normalize(holding.get("plaid_subtype"))
    if plaid_subtype in _PLAID_TYPE_BUCKETS:
        return _PLAID_TYPE_BUCKETS[plaid_subtype]

    asset_kind = _normalize(holding.get("asset_kind"))
    if asset_kind in _ASSET_KIND_DEFAULTS:
        return _ASSET_KIND_DEFAULTS[asset_kind]

    if _normalize(asset_name) == "cash":
        return "Cash"

    return None
