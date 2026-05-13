from __future__ import annotations

from pathlib import Path

import yaml

CLASSIFICATION_PATH = Path(__file__).resolve().parents[2] / "classification.yaml"


def load_classification_overrides(path: Path | None = None) -> dict[str, str]:
    target = path or CLASSIFICATION_PATH
    if not target.exists():
        return {}

    data = yaml.safe_load(target.read_text()) or {}
    if not isinstance(data, dict):
        return {}

    overrides: dict[str, str] = {}
    for key, value in data.items():
        if key is None or value is None:
            continue
        overrides[str(key)] = str(value)
    return overrides
