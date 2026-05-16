from __future__ import annotations

from typing import TYPE_CHECKING, Callable, Literal

from portfolio.classify.buckets import ORDERED_BUCKETS

if TYPE_CHECKING:
    from portfolio.classify.ollama_suggest import BucketSuggestion

Action = Literal["persist", "skip", "quit"]


def _print_card(
    *,
    asset_name: str,
    suggestion: BucketSuggestion,
    write: Callable[[str], None],
) -> None:
    write(f"\n--- Unclassified: {asset_name} ---\n")
    if suggestion.error:
        write(f"Ollama / parse: {suggestion.error}\n")
    elif suggestion.suggested_bucket:
        write(f"Suggested bucket: {suggestion.suggested_bucket}\n")
    else:
        write("No suggestion available.\n")
    write("[y] accept  [n] skip  [m] manual pick  [q] quit classifier\n")


def prompt_confirmed_bucket(
    *,
    asset_name: str,
    suggestion: BucketSuggestion,
    read_line: Callable[[str], str],
    write: Callable[[str], None],
) -> tuple[Action, str | None]:
    """Prompt for `y`/`n`/`m`/`q`; return action and bucket to persist (if any)."""
    while True:
        _print_card(asset_name=asset_name, suggestion=suggestion, write=write)
        choice = read_line("Enter y/n/m/q: ").strip().lower()

        if choice == "n":
            return "skip", None
        if choice == "q":
            return "quit", None
        if choice == "y":
            if suggestion.suggested_bucket is not None:
                return "persist", suggestion.suggested_bucket
            write("No suggestion to accept; choose m, n, or q.\n")
            continue
        if choice == "m":
            for i, bucket in enumerate(ORDERED_BUCKETS, start=1):
                write(f"  {i} {bucket}\n")
            raw = read_line("Bucket number (1-7): ").strip()
            try:
                idx = int(raw)
            except ValueError:
                write("Invalid number.\n")
                continue
            if 1 <= idx <= len(ORDERED_BUCKETS):
                return "persist", ORDERED_BUCKETS[idx - 1]
            write("Choose 1-7.\n")
            continue

        write("Unrecognized input; try y, n, m, or q.\n")
