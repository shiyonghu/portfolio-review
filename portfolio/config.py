"""Application settings from environment variables and optional `.env` file."""

from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

_VALID_PLAID_ENVS = frozenset({"sandbox", "production"})


@dataclass(frozen=True)
class Settings:
    plaid_client_id: str
    plaid_secret: str
    plaid_env: str
    db_path: str
    ollama_base_url: str
    ollama_model: str

    @classmethod
    def from_env(cls) -> Settings:
        load_dotenv()
        plaid_env = os.getenv("PLAID_ENV", "sandbox").strip().lower()
        if plaid_env not in _VALID_PLAID_ENVS:
            msg = f"PLAID_ENV must be sandbox or production, got {plaid_env!r}"
            raise ValueError(msg)
        return cls(
            plaid_client_id=os.getenv("PLAID_CLIENT_ID", ""),
            plaid_secret=os.getenv("PLAID_SECRET", ""),
            plaid_env=plaid_env,
            db_path=os.getenv("PORTFOLIO_DB_PATH", "portfolio.db"),
            ollama_base_url=os.getenv(
                "OLLAMA_BASE_URL",
                "http://localhost:11434",
            ),
            ollama_model=os.getenv("OLLAMA_MODEL", "qwen3.5:4b"),
        )
