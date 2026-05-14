from __future__ import annotations

import json
import sqlite3
from typing import Any

import httpx
from httpx import ConnectError, HTTPStatusError

from portfolio.agent.tools import SQL_SCHEMA_HINT, run_sql_for_agent
from portfolio.charts.plot import plot_line, plot_pie
from portfolio.config import Settings


def _tool_definitions() -> list[dict[str, Any]]:
    return [
        {
            "type": "function",
            "function": {
                "name": "run_sql",
                "description": (
                    "Run read-only SELECT SQL on the local portfolio database. "
                    + SQL_SCHEMA_HINT
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": (
                                "A single SELECT query without semicolons. "
                                "Use only tables listed in the tool description."
                            ),
                        }
                    },
                    "required": ["query"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "plot_pie",
                "description": "Create a pie chart and return the PNG path.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "labels": {"type": "array", "items": {"type": "string"}},
                        "values": {"type": "array", "items": {"type": "number"}},
                        "title": {"type": "string"},
                    },
                    "required": ["labels", "values"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "plot_line",
                "description": "Create a line chart and return the PNG path.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "x": {"type": "array", "items": {"type": "string"}},
                        "y": {"type": "array", "items": {"type": "number"}},
                        "title": {"type": "string"},
                    },
                    "required": ["x", "y"],
                },
            },
        },
    ]


def _parse_arguments(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        parsed = json.loads(raw) if raw else {}
        if isinstance(parsed, dict):
            return parsed
    raise ValueError("Invalid tool arguments")


def _dispatch_tool(
    conn: sqlite3.Connection,
    tool_name: str,
    arguments: dict[str, Any],
) -> dict[str, Any]:
    if tool_name == "run_sql":
        return run_sql_for_agent(conn, str(arguments["query"]))
    if tool_name == "plot_pie":
        path = plot_pie(
            labels=[str(v) for v in arguments["labels"]],
            values=[float(v) for v in arguments["values"]],
            title=str(arguments.get("title", "Portfolio Pie")),
        )
        return {"path": path}
    if tool_name == "plot_line":
        path = plot_line(
            x=[str(v) for v in arguments["x"]],
            y=[float(v) for v in arguments["y"]],
            title=str(arguments.get("title", "Portfolio Trend")),
        )
        return {"path": path}
    raise ValueError(f"Unknown tool: {tool_name}")


def chat_with_tools(
    conn: sqlite3.Connection,
    settings: Settings,
    question: str,
    max_rounds: int = 10,
) -> str:
    messages: list[dict[str, Any]] = [{"role": "user", "content": question}]

    base_url = settings.ollama_base_url.rstrip("/")
    with httpx.Client(timeout=60.0) as client:
        for _ in range(max_rounds):
            try:
                response = client.post(
                    f"{base_url}/api/chat",
                    json={
                        "model": settings.ollama_model,
                        "messages": messages,
                        "stream": False,
                        "tools": _tool_definitions(),
                    },
                )
                response.raise_for_status()
            except ConnectError as exc:
                raise RuntimeError(
                    f"Cannot reach Ollama at {base_url}. "
                    "Start Ollama (e.g. open the Ollama app or run `ollama serve`) "
                    f"and pull the model with `ollama pull {settings.ollama_model}`."
                ) from exc
            except HTTPStatusError as exc:
                if exc.response.status_code == 404:
                    raise RuntimeError(
                        f"Ollama model {settings.ollama_model!r} was not found. "
                        f"Pull it with `ollama pull {settings.ollama_model}`."
                    ) from exc
                raise
            payload = response.json()
            message = payload.get("message", {})
            tool_calls = message.get("tool_calls") or []
            content = str(message.get("content", "") or "")

            if not tool_calls:
                return content

            messages.append(
                {
                    "role": "assistant",
                    "content": content,
                    "tool_calls": tool_calls,
                }
            )

            for tool_call in tool_calls:
                function_meta = tool_call.get("function", {})
                tool_name = str(function_meta.get("name", ""))
                arguments = _parse_arguments(function_meta.get("arguments", {}))
                result = _dispatch_tool(conn, tool_name, arguments)
                messages.append(
                    {
                        "role": "tool",
                        "tool_name": tool_name,
                        "content": json.dumps(result, default=str),
                    }
                )

    return "Unable to complete request within tool-call limit."
