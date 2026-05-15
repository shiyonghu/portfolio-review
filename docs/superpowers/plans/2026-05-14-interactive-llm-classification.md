# Interactive LLM classification (snapshot) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** When YAML and rule-based classification return no bucket for an `asset_name` during `portfolio snapshot`, call Ollama for a JSON suggestion, prompt the user on stdin (`y` / `n` / `m` / `q`), and persist `classifications` with `source = llm_confirmed` only after confirmation—then backfill `holdings_snapshot.bucket` as today.

**Architecture:** Keep rule logic in `[portfolio/classify/rules.py](../../portfolio/classify/rules.py)`. Add a small shared `[portfolio/classify/buckets.py](../../portfolio/classify/buckets.py)` for the seven allowed bucket strings. Extend `[portfolio/classify/ollama_suggest.py](../../portfolio/classify/ollama_suggest.py)` with an httpx call to `POST {OLLAMA_BASE_URL}/api/chat` (non-streaming, `format: "json"`), parse assistant `message.content` into `{bucket, reason}`, validate against allowed set. Add `[portfolio/classify/prompt.py](../../portfolio/classify/prompt.py)` for the stdin UX with injectable `read_line` / `write`. Change `[portfolio/snapshot/runner.py](../../portfolio/snapshot/runner.py)` `classify_snapshot` to aggregate holdings per `asset_name`, sort pending names, run rules then Ollama+prompt; remove the incorrect “auto `llm_confirmed` if `suggest_bucket` returns” behavior. Document behavior in `[portfolio/cli.py](../../portfolio/cli.py)` snapshot help and `[README.md](../../README.md)`.

**Tech stack:** Python 3.12+, `httpx` (already in `[pyproject.toml](../../pyproject.toml)`), Typer CLI, SQLite, Ollama HTTP API (same host/model pattern as `[portfolio/agent/ollama.py](../../portfolio/agent/ollama.py)`).

**Authoritative spec:** `[docs/superpowers/specs/2026-05-13-portfolio-review-design.md](../specs/2026-05-13-portfolio-review-design.md)` — section *Interactive LLM classification during `portfolio snapshot` (v1)*.

---

## File structure


| Path                                                                                                       | Responsibility                                                                                                         |
| ---------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------- |
| Create: `[portfolio/classify/buckets.py](../../portfolio/classify/buckets.py)`                             | `ORDERED_BUCKETS` tuple + `is_allowed_bucket(name) -> bool`                                                            |
| Create: `[portfolio/classify/prompt.py](../../portfolio/classify/prompt.py)`                               | `prompt_confirmed_bucket(...)` returning `Literal["persist", "skip", "quit"]` + optional `bucket`                      |
| Modify: `[portfolio/classify/ollama_suggest.py](../../portfolio/classify/ollama_suggest.py)`               | `fetch_bucket_suggestion(holding, settings) -> BucketSuggestion` dataclass; JSON parse + httpx                         |
| Modify: `[portfolio/snapshot/runner.py](../../portfolio/snapshot/runner.py)`                               | SQL aggregation, sorted loop, interactive branch, `classify_snapshot(..., read_line=..., write=...)`                   |
| Modify: `[portfolio/cli.py](../../portfolio/cli.py)`                                                       | Expand `snapshot` command docstring                                                                                    |
| Modify: `[README.md](../../README.md)`                                                                     | Short paragraph: unknown assets prompt during snapshot; Ollama required                                                |
| Create: `[tests/test_ollama_suggest.py](../../tests/test_ollama_suggest.py)`                               | Parser + validation unit tests (no real Ollama)                                                                        |
| Create: `[tests/test_classify_prompt.py](../../tests/test_classify_prompt.py)`                             | Prompt behavior with fake `read_line` / `write`                                                                        |
| Create: `[tests/test_classify_snapshot_interactive.py](../../tests/test_classify_snapshot_interactive.py)` | DB fixture + monkeypatch `fetch_bucket_suggestion` + scripted prompts → assert `classifications` / `holdings_snapshot` |


---

### Task 1: Shared bucket constants

**Files:**

- Create: `portfolio/classify/buckets.py`
- Test: inline assertion in `tests/test_ollama_suggest.py` (Task 2) or tiny test here
- **Step 1: Add `buckets.py`**

```python
# portfolio/classify/buckets.py
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
```

- **Step 2: Commit**

```bash
git add portfolio/classify/buckets.py
git commit -m "feat(classify): add shared ordered bucket constants"
```

---

### Task 2: JSON parsing and Ollama response handling (TDD)

**Files:**

- Modify: `portfolio/classify/ollama_suggest.py`
- Create: `tests/test_ollama_suggest.py`
- **Step 1: Write failing tests**

Create `tests/test_ollama_suggest.py`:

```python
from __future__ import annotations

import pytest

from portfolio.classify.ollama_suggest import parse_bucket_json_payload


def test_parse_plain_json() -> None:
    bucket, reason, err = parse_bucket_json_payload('{"bucket":"Equity","reason":"US stock ETF"}')
    assert err is None
    assert bucket == "Equity"
    assert "ETF" in reason


def test_parse_json_in_markdown_fence() -> None:
    raw = """Here is the result:
```json
{"bucket": "Bond", "reason": "fixed income"}
```

"""
    bucket, reason, err = parse_bucket_json_payload(raw)
    assert err is None
    assert bucket == "Bond"

def test_invalid_bucket_rejected() -> None:
    bucket, reason, err = parse_bucket_json_payload('{"bucket":"Banana","reason":"x"}')
    assert bucket is None
    assert err is not None

def test_malformed_json() -> None:
    bucket, reason, err = parse_bucket_json_payload("not json")
    assert bucket is None
    assert err is not None

```

Implement `parse_bucket_json_payload` in `ollama_suggest.py` (extract first `{...}` or fenced block, `json.loads`, validate with `is_allowed_bucket`). Export it for tests.

- [ ] **Step 2: Run tests (expect failures until Step 3 passes)**

Run: `pytest tests/test_ollama_suggest.py -v`

Expected: FAIL until parser exists.

- [ ] **Step 3: Implement `parse_bucket_json_payload`**

Minimal implementation: strip whitespace; if content starts with `` ``` ``, extract inner block; find outermost JSON object via `json.JSONDecoder().raw_decode` from first `{`; load dict; read `bucket`/`reason` strings; validate bucket with `is_allowed_bucket`.

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_ollama_suggest.py -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add portfolio/classify/ollama_suggest.py tests/test_ollama_suggest.py
git commit -m "feat(classify): parse Ollama JSON bucket suggestions"
```

---

### Task 3: `fetch_bucket_suggestion` httpx integration

**Files:**

- Modify: `portfolio/classify/ollama_suggest.py`
- **Step 1: Add dataclass + `fetch_bucket_suggestion`**
- Use `httpx.Client(timeout=60.0)` like `[portfolio/agent/ollama.py](../../portfolio/agent/ollama.py)`.
- `POST {base}/api/chat` with `{"model": settings.ollama_model, "messages": [{"role": "user", "content": prompt}], "stream": False, "format": "json"}`.
- User prompt: include allowed bucket list + serialized holding JSON (only safe keys).
- On success: `parse_bucket_json_payload(message["content"])`.
- On `ConnectError` / 404: return `BucketSuggestion(suggested_bucket=None, reason="", error="...")` with user-facing text mirroring agent errors.
- **Step 2: Unit test with `httpx.MockTransport`**

Add `test_fetch_bucket_suggestion_uses_chat_api` registering a handler for `POST .../api/chat` returning a canned `{"message":{"content":"{\"bucket\":\"Gold\",\"reason\":\"gold ETC\"}"}}` body; assert `suggested_bucket == "Gold"`.

Run: `pytest tests/test_ollama_suggest.py -v`

Expected: PASS

- **Step 3: Commit**

```bash
git add portfolio/classify/ollama_suggest.py tests/test_ollama_suggest.py
git commit -m "feat(classify): call Ollama for bucket suggestions"
```

---

### Task 4: Stdin prompt module

**Files:**

- Create: `portfolio/classify/prompt.py`
- Create: `tests/test_classify_prompt.py`
- **Step 1: Write failing tests** for `prompt_confirmed_bucket`

Behavior to lock:

- `y` with valid `suggested_bucket` → `("persist", suggested_bucket)`
- `y` with `suggested_bucket is None` → re-prompt (loop) until valid input or `q`
- `n` → `("skip", None)`
- `q` → `("quit", None)`
- `m` then valid menu index → `("persist", chosen)`
- `m` then invalid → re-prompt

Use `read_line: Callable[[str], str]` and `write: Callable[[str], None]`; tests pass a `deque` of scripted responses.

- **Step 2: Implement `prompt_confirmed_bucket`**

Use `ORDERED_BUCKETS` from `buckets.py` for the manual menu (1–7).

- **Step 3: Run tests**

Run: `pytest tests/test_classify_prompt.py -v`

Expected: PASS

- **Step 4: Commit**

```bash
git add portfolio/classify/prompt.py tests/test_classify_prompt.py
git commit -m "feat(classify): interactive bucket confirmation prompts"
```

---

### Task 5: Wire `classify_snapshot` in runner

**Files:**

- Modify: `portfolio/snapshot/runner.py`
- **Step 1: Replace DISTINCT query** with grouped query for the snapshot date, e.g.:

```sql
SELECT
  asset_name,
  MAX(display_name) AS display_name,
  MAX(plaid_type) AS plaid_type,
  MAX(plaid_subtype) AS plaid_subtype,
  MAX(source) AS source
FROM holdings_snapshot
WHERE snapshot_date = ?
GROUP BY asset_name
ORDER BY asset_name
```

(If `MAX(source)` is wrong for edge cases, use `MIN` or document; v1 assumes one dominant source per symbol.)

- **Step 2: Extend `classify_snapshot` signature**

```python
def classify_snapshot(
    conn: sqlite3.Connection,
    snapshot_date: str,
    settings: Settings,
    *,
    read_line: Callable[[str], str] | None = None,
    write: Callable[[str], None] | None = None,
) -> None:
```

Defaults: `read_line=input`, `write` as a thin wrapper around `print(..., flush=True)`.

- **Step 3: Loop body**

For each row: skip if `classifications` exists. Build `holding` dict including `asset_kind` for `user_managed`. `bucket, source = classify_holding_with_source(...)`.

If `bucket is not None`: upsert as today with returned `source`.

If `bucket is None`:

1. `suggestion = fetch_bucket_suggestion(holding, settings)`
2. `action, chosen = prompt_confirmed_bucket(..., suggestion, read_line=read_line, write=write)`
3. If `action == "quit"`: `break`
4. If `action == "persist"` and `chosen`: upsert with `source="llm_confirmed"`
5. If `action == "skip"`: `continue`

Remove any path that sets `llm_confirmed` without going through the prompt.

- **Step 4: Keep final bulk UPDATE + commit** unchanged after the loop.
- **Step 5: Integration test**

`tests/test_classify_snapshot_interactive.py`: `init_db`, insert `accounts` + `holdings_snapshot` for one unknown ticker (no YAML rule), monkeypatch `fetch_bucket_suggestion` to return Equity, pass `read_line` that returns `"y"`, call `classify_snapshot`, assert `classifications` row and `holdings_snapshot.bucket` updated.

Run: `pytest tests/test_classify_snapshot_interactive.py -v`

Expected: PASS

- **Step 6: Commit**

```bash
git add portfolio/snapshot/runner.py tests/test_classify_snapshot_interactive.py
git commit -m "feat(snapshot): interactive Ollama classification with confirmation"
```

---

### Task 6: CLI and README

**Files:**

- Modify: `portfolio/cli.py`
- Modify: `README.md`
- **Step 1: Docstring** on `snapshot()` — state that unknown assets after YAML/rules may prompt for classification and require Ollama running.
- **Step 2: README** — under classification / snapshot section, one short paragraph + env vars (`OLLAMA_BASE_URL`, `OLLAMA_MODEL`) pointer to `.env.example`.
- **Step 3: Commit**

```bash
git add portfolio/cli.py README.md
git commit -m "docs: document interactive LLM classification on snapshot"
```

---

### Task 7: Full verification

- **Step 1: Run full test suite**

Run: `pytest -q`

Expected: all PASS

- **Step 2: Optional manual smoke** (human): run `portfolio snapshot` with Ollama up and a holding that falls through rules; exercise `y`, `n`, `m`, `q`.
- **Step 3: Commit** (if only doc tweaks from smoke)

---

## Spec coverage (self-review)


| Spec requirement                        | Task                                                        |
| --------------------------------------- | ----------------------------------------------------------- |
| Ollama + confirm only after user action | Task 4, 5                                                   |
| `source = llm_confirmed`                | Task 5 upsert                                               |
| Seven buckets only                      | Tasks 1–3 parser + prompt menu                              |
| Deterministic `asset_name` order        | Task 5 SQL `ORDER BY asset_name`                            |
| Holding context fields                  | Task 3 prompt + Task 5 holding dict                         |
| `y` / `n` / `m` / `q` semantics         | Task 4                                                      |
| Injectable I/O for tests                | Tasks 4–5                                                   |
| v1 no automation hatch                  | No extra flags (document only)                              |
| Quit preserves prior confirmations      | Task 4 returns quit; Task 5 breaks loop after prior upserts |


**Placeholder scan:** None intended; all tasks name concrete files and behaviors.

---

## Execution handoff

Plan complete and saved to `[docs/superpowers/plans/2026-05-14-interactive-llm-classification.md](2026-05-14-interactive-llm-classification.md)`.

**1. Subagent-driven (recommended)** — Fresh subagent per task, review between tasks.

**2. Inline execution** — Run tasks in this session using superpowers:executing-plans with checkpoints.

Which approach do you want for implementation?