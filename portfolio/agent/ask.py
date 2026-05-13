from __future__ import annotations

import sqlite3

from portfolio.agent.ollama import chat_with_tools
from portfolio.config import Settings


def ask_portfolio_question(
    conn: sqlite3.Connection,
    settings: Settings,
    question: str,
) -> str:
    return chat_with_tools(conn=conn, settings=settings, question=question)
