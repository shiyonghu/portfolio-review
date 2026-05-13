from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt


def _next_output_path(prefix: str) -> Path:
    output_dir = Path("outputs")
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir / f"{prefix}-{uuid4().hex}.png"


def plot_pie(labels: list[str], values: list[float], title: str = "Portfolio Pie") -> str:
    if not labels or not values or len(labels) != len(values):
        raise ValueError("labels and values must be non-empty and same length")
    fig, ax = plt.subplots(figsize=(8, 6))
    ax.pie(values, labels=labels, autopct="%1.1f%%")
    ax.set_title(title)
    out_path = _next_output_path("pie")
    fig.tight_layout()
    fig.savefig(out_path)
    plt.close(fig)
    return str(out_path)


def plot_line(x: list[str], y: list[float], title: str = "Portfolio Trend") -> str:
    if not x or not y or len(x) != len(y):
        raise ValueError("x and y must be non-empty and same length")
    fig, ax = plt.subplots(figsize=(8, 4.5))
    ax.plot(x, y, marker="o")
    ax.set_title(title)
    ax.grid(True, alpha=0.25)
    out_path = _next_output_path("line")
    fig.tight_layout()
    fig.savefig(out_path)
    plt.close(fig)
    return str(out_path)
