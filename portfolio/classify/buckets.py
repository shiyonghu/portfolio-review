from __future__ import annotations

ORDERED_BUCKETS: tuple[str, ...] = (
    "Cash",
    "Bond",
    "Equity",
    "Gold",
    "Commodity",
    "Crypto",
    "RealEstate",
)

_ALLOWED = frozenset(ORDERED_BUCKETS)


def is_allowed_bucket(name: str) -> bool:
    return name in _ALLOWED
