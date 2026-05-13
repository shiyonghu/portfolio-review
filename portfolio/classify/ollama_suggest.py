from __future__ import annotations

from typing import Any

from portfolio.config import Settings


def suggest_bucket(holding: dict[str, Any], settings: Settings) -> str | None:
    """LLM classification stub for v1 non-interactive snapshots."""
    _ = (holding, settings)
    return None
