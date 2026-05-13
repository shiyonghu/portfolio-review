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
    bucket, _ = classify_holding_with_source(holding, yaml_overrides)
    return bucket


def classify_holding_with_source(
    holding: Mapping[str, Any],
    yaml_overrides: Mapping[str, str] | None = None,
) -> tuple[Bucket | None, str | None]:
    """Classify a holding and return `(bucket, source)` for persistence."""
    overrides = yaml_overrides or load_classification_overrides()

    asset_name = str(holding.get("asset_name") or "").strip()
    if asset_name:
        if asset_name in overrides:
            return overrides[asset_name], "yaml"
        upper_name = asset_name.upper()
        if upper_name in overrides:
            return overrides[upper_name], "yaml"

    plaid_type = _normalize(holding.get("plaid_type"))
    if plaid_type in _PLAID_TYPE_BUCKETS:
        return _PLAID_TYPE_BUCKETS[plaid_type], "rule"

    plaid_subtype = _normalize(holding.get("plaid_subtype"))
    if plaid_subtype in _PLAID_TYPE_BUCKETS:
        return _PLAID_TYPE_BUCKETS[plaid_subtype], "rule"

    asset_kind = _normalize(holding.get("asset_kind"))
    if asset_kind in _ASSET_KIND_DEFAULTS:
        return _ASSET_KIND_DEFAULTS[asset_kind], "asset_kind_default"

    if _normalize(asset_name) == "cash":
        return "Cash", "rule"

    return None, None
