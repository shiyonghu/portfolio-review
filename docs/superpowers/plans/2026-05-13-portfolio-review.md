# Portfolio Review Tool Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a local macOS CLI that links accounts via Plaid, snapshots holdings into SQLite, classifies assets, exports CSV, and answers questions via Ollama with read-only SQL and charts.

**Architecture:** Python Typer CLI; FastAPI localhost server for Plaid Link; SQLite as source of truth with `holdings_snapshot` + `snapshot_summary`; Keychain for Plaid access tokens; `.env` for Plaid client credentials; Ollama for classification suggestions and Ask Agent tool-calling.

**Tech Stack:** Python 3.12, Typer, FastAPI, uvicorn, plaid-python, sqlite3, keyring, PyYAML, httpx (Ollama), matplotlib, pytest

**Design spec:** [docs/superpowers/specs/2026-05-13-portfolio-review-design.md](../specs/2026-05-13-portfolio-review-design.md)

---

## File structure

```
portfolio-review/
├── .env.example
├── .gitignore
├── pyproject.toml
├── classification.yaml
├── portfolio/
│   ├── __init__.py
│   ├── __main__.py              # python -m portfolio
│   ├── cli.py                   # Typer app entry
│   ├── config.py                # Settings from env
│   ├── db/
│   │   ├── __init__.py
│   │   ├── schema.sql
│   │   ├── connection.py
│   │   └── queries.py
│   ├── keychain/
│   │   ├── __init__.py
│   │   └── tokens.py
│   ├── plaid/
│   │   ├── __init__.py
│   │   ├── client.py
│   │   ├── link_server.py
│   │   └── ingest.py
│   ├── classify/
│   │   ├── __init__.py
│   │   ├── yaml_store.py
│   │   ├── rules.py
│   │   └── ollama_suggest.py
│   ├── snapshot/
│   │   ├── __init__.py
│   │   ├── runner.py
│   │   ├── normalize.py
│   │   ├── summary.py
│   │   └── export_csv.py
│   ├── managed/
│   │   ├── __init__.py
│   │   └── service.py
│   ├── agent/
│   │   ├── __init__.py
│   │   ├── ollama.py
│   │   ├── tools.py
│   │   └── ask.py
│   └── charts/
│       ├── __init__.py
│       └── plot.py
├── tests/
│   ├── conftest.py
│   ├── test_db.py
│   ├── test_classify_rules.py
│   ├── test_normalize.py
│   ├── test_managed_valuations.py
│   ├── test_summary.py
│   └── test_export_csv.py
├── snapshots/raw/               # gitignored contents
├── snapshots/csv/
└── outputs/
```

---

### Task 1: Project scaffold

**Files:**
- Create: `pyproject.toml`, `.gitignore`, `.env.example`, `portfolio/__init__.py`, `portfolio/__main__.py`, `portfolio/cli.py`, `tests/conftest.py`

- [ ] **Step 1: Create `pyproject.toml`**

```toml
[project]
name = "portfolio-review"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
  "typer>=0.12",
  "fastapi>=0.115",
  "uvicorn>=0.32",
  "plaid-python>=27",
  "keyring>=25",
  "pyyaml>=6",
  "httpx>=0.27",
  "matplotlib>=3.9",
  "python-dotenv>=1.0",
]

[project.optional-dependencies]
dev = ["pytest>=8", "pytest-asyncio>=0.24"]

[project.scripts]
portfolio = "portfolio.cli:app"

[tool.pytest.ini_options]
testpaths = ["tests"]
```

- [ ] **Step 2: Create `.gitignore`**

```
.env
__pycache__/
*.pyc
.pytest_cache/
portfolio.db
snapshots/raw/
outputs/
*.egg-info/
.venv/
```

- [ ] **Step 3: Create `.env.example`**

```bash
PLAID_CLIENT_ID=
PLAID_SECRET=
PLAID_ENV=sandbox
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=llama3.1
PORTFOLIO_DB_PATH=portfolio.db
```

- [ ] **Step 4: Minimal Typer app**

`portfolio/cli.py`:

```python
import typer

app = typer.Typer(help="Portfolio review tool")

@app.callback()
def main():
    pass

if __name__ == "__main__":
    app()
```

`portfolio/__main__.py`:

```python
from portfolio.cli import app
app()
```

- [ ] **Step 5: Install and verify**

```bash
cd /Users/shiyonghu/workspace/portfolio-review
python3.12 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
portfolio --help
```

Expected: Typer help text.

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml .gitignore .env.example portfolio/ tests/conftest.py
git commit -m "chore: scaffold portfolio-review project"
```

---

### Task 2: Database schema and connection

**Files:**
- Create: `portfolio/db/schema.sql`, `portfolio/db/connection.py`, `tests/test_db.py`

- [ ] **Step 1: Write failing test**

`tests/test_db.py`:

```python
from portfolio.db.connection import get_connection, init_db

def test_init_db_creates_holdings_snapshot(tmp_path):
    db_path = tmp_path / "test.db"
    conn = get_connection(db_path)
    init_db(conn)
    tables = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    ).fetchall()
    names = {r[0] for r in tables}
    assert "holdings_snapshot" in names
    assert "snapshot_summary" in names
    assert "user_managed_holdings" in names
```

- [ ] **Step 2: Run test — expect FAIL**

```bash
pytest tests/test_db.py -v
```

- [ ] **Step 3: Implement `schema.sql`** (full DDL from design spec)

Include tables: `items`, `accounts`, `user_managed_holdings`, `holdings_snapshot`, `classifications`, `snapshot_summary` with UNIQUE constraints as specified.

- [ ] **Step 4: Implement `connection.py`**

```python
import sqlite3
from pathlib import Path

SCHEMA_PATH = Path(__file__).with_name("schema.sql")

def get_connection(db_path: Path | str) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA_PATH.read_text())
    conn.commit()
```

- [ ] **Step 5: Run test — expect PASS**

```bash
pytest tests/test_db.py -v
```

- [ ] **Step 6: Commit**

```bash
git add portfolio/db/ tests/test_db.py
git commit -m "feat: add SQLite schema and init"
```

---

### Task 3: Config module

**Files:**
- Create: `portfolio/config.py`, `tests/test_config.py`

- [ ] **Step 1: Write failing test**

```python
import os
from portfolio.config import Settings

def test_settings_from_env(monkeypatch):
    monkeypatch.setenv("PLAID_CLIENT_ID", "cid")
    monkeypatch.setenv("PLAID_SECRET", "sec")
    monkeypatch.setenv("PLAID_ENV", "sandbox")
    s = Settings.from_env()
    assert s.plaid_client_id == "cid"
    assert s.plaid_env == "sandbox"
```

- [ ] **Step 2–5: Implement `Settings` dataclass** loading from `python-dotenv`; properties: `plaid_client_id`, `plaid_secret`, `plaid_env`, `db_path`, `ollama_base_url`, `ollama_model`.

- [ ] **Step 6: Commit**

```bash
git commit -m "feat: add Settings from environment"
```

---

### Task 4: Keychain access token storage

**Files:**
- Create: `portfolio/keychain/tokens.py`, `tests/test_keychain_tokens.py`

- [ ] **Step 1: Write failing test** (mock `keyring`)

```python
from unittest.mock import patch
from portfolio.keychain.tokens import save_access_token, load_access_token

@patch("keyring.set_password")
def test_save_access_token(mock_set):
    save_access_token("item_abc", "access_xyz")
    mock_set.assert_called_once_with("portfolio-review", "item_abc", "access_xyz")

@patch("keyring.get_password", return_value="access_xyz")
def test_load_access_token(mock_get):
    assert load_access_token("item_abc") == "access_xyz"
```

- [ ] **Step 2–5: Implement** using service name `portfolio-review`, account = `item_id`.

- [ ] **Step 6: Commit**

---

### Task 5: Plaid client wrapper

**Files:**
- Create: `portfolio/plaid/client.py`, `tests/test_plaid_client.py`

- [ ] **Step 1: Implement `make_plaid_client(settings)`** returning configured `PlaidApi` for sandbox or production.

- [ ] **Step 2: Implement helpers**

```python
def exchange_public_token(client, public_token: str) -> str: ...
def fetch_balances(client, access_token: str) -> dict: ...
def fetch_holdings(client, access_token: str) -> dict: ...
```

- [ ] **Step 3: Unit test** with mocked SDK responses (no live Plaid in CI).

- [ ] **Step 4: Commit**

---

### Task 6: Plaid Link server and `portfolio setup`

**Files:**
- Create: `portfolio/plaid/link_server.py`, extend `portfolio/cli.py`

- [ ] **Step 1: FastAPI app** with:
  - `GET /` — serves HTML loading Plaid Link (link_token from session)
  - `POST /api/create_link_token`
  - `POST /api/exchange_public_token` — saves token to Keychain, upserts `items`/`accounts`

- [ ] **Step 2: Typer command**

```python
@app.command()
def setup():
    """Link brokerage/bank accounts via Plaid."""
    # start uvicorn on localhost:8765, open browser
```

- [ ] **Step 3: Manual smoke test** with Sandbox credentials in local `.env` (user runs; not automated).

- [ ] **Step 4: Commit**

---

### Task 7: Account preferences CLI

**Files:**
- Modify: `portfolio/cli.py`, `portfolio/db/queries.py`

- [ ] **Step 1: Commands**

```python
@app.command("accounts-list")
def accounts_list(): ...

@app.command("accounts-configure")
def accounts_configure(
    account_id: str,
    included: bool = True,
    owner_tag: str = "household",
    tax_treatment: str | None = None,
): ...
```

- [ ] **Step 2: `derive_tax_treatment(subtype) -> Literal["taxable", "tax-advantaged"]`** — brokerage, checking, savings → `taxable`; 401k, IRA, Roth IRA, HSA, 529, pension, etc. → `tax-advantaged`.

- [ ] **Step 3: Test** `derive_tax_treatment` for brokerage → `taxable`; IRA, Roth IRA, 401k, 529, HSA → `tax-advantaged`.

- [ ] **Step 4: Commit**

---

### Task 8: Classification YAML and rules

**Files:**
- Create: `classification.yaml`, `portfolio/classify/yaml_store.py`, `portfolio/classify/rules.py`, `tests/test_classify_rules.py`

- [ ] **Step 1: Seed `classification.yaml`**

```yaml
VTI: Equity
BND: Bond
GLD: Gold
```

- [ ] **Step 2: Write failing tests**

```python
from portfolio.classify.rules import classify_holding

def test_cash_rule():
    assert classify_holding({"asset_name": "cash", "plaid_type": None}) == "Cash"

def test_fixed_income():
    assert classify_holding({"asset_name": "X", "plaid_type": "fixed income"}) == "Bond"

def test_real_estate_kind():
    assert classify_holding({"asset_name": "Home", "asset_kind": "real_estate"}) == "RealEstate"
```

- [ ] **Step 3: Implement `classify_holding`** — YAML lookup → Plaid rules → asset_kind defaults → return `None` if unclassified.

- [ ] **Step 4: Commit**

---

### Task 9: Normalize Plaid response → holding rows

**Files:**
- Create: `portfolio/snapshot/normalize.py`, `tests/test_normalize.py`

- [ ] **Step 1: Write failing tests** using fixture JSON resembling Plaid `/investments/holdings/get` + balances.

Test cases:
- Investment holding → `asset_name` = ticker
- Missing ticker → `asset_name` = `plaid_security_id`
- Depository account → one row `asset_name='cash'`, `value=current balance`

- [ ] **Step 2: Implement `normalize_plaid_item(accounts, holdings_response, balances_response, snapshot_date)`** returning list of dicts ready for insert.

- [ ] **Step 3: Commit**

---

### Task 10: User-managed holdings service

**Files:**
- Create: `portfolio/managed/service.py`, `tests/test_managed_valuations.py`

- [ ] **Step 1: Write failing test for carry-forward**

```python
def test_valuation_as_of_date():
    # valuations on 2026-01-01 = 1M, 2026-06-01 = 1.1M
    # as_of 2026-03-01 -> 1M; as_of 2026-07-01 -> 1.1M
```

- [ ] **Step 2: Implement**

```python
def add_managed_asset(conn, ...) -> str: ...
def append_valuation(conn, asset_name, value, effective_date, source) -> str: ...
def resolve_valuation(conn, asset_name, as_of_date) -> dict | None: ...
def materialize_managed_rows(conn, snapshot_date) -> list[dict]: ...
```

Creating synthetic `accounts` row with `source='manual'` on add.

- [ ] **Step 3: Typer subgroup `portfolio managed`**

```python
managed_app = typer.Typer()
managed_app.command("add")(managed_add)
managed_app.command("update")(managed_update)
managed_app.command("list")(managed_list)
app.add_typer(managed_app, name="managed")
```

- [ ] **Step 4: Commit**

---

### Task 11: Snapshot runner — persist, classify, summary

**Files:**
- Create: `portfolio/snapshot/runner.py`, `portfolio/snapshot/summary.py`, `portfolio/classify/ollama_suggest.py`, `tests/test_summary.py`

- [ ] **Step 1: `delete_snapshot_date(conn, snapshot_date)`** — delete from `holdings_snapshot` and `snapshot_summary`.

- [ ] **Step 2: `insert_holdings_snapshot(conn, rows)`**

- [ ] **Step 3: `classify_snapshot(conn, snapshot_date, settings)`**
  - For each distinct `asset_name` without bucket: rules → if None, call Ollama suggest → **Typer prompt** confirm → upsert `classifications` + YAML.
  - Update `holdings_snapshot.bucket` for all rows on that date.

- [ ] **Step 4: `rebuild_snapshot_summary(conn, snapshot_date)`**

```sql
INSERT INTO snapshot_summary (id, snapshot_date, bucket, tax_treatment, owner_tag, total_value)
SELECT lower(hex(randomblob(16))), hs.snapshot_date, hs.bucket,
       a.tax_treatment, a.owner_tag, SUM(hs.value)
FROM holdings_snapshot hs
JOIN accounts a ON a.account_id = hs.account_id
WHERE hs.snapshot_date = ? AND a.included = 1 AND hs.bucket IS NOT NULL
GROUP BY hs.snapshot_date, hs.bucket, a.tax_treatment, a.owner_tag
```

- [ ] **Step 5: Test summary aggregation** with fixture DB rows.

- [ ] **Step 6: `portfolio snapshot` command** orchestrating: fetch all items → archive raw JSON → normalize → materialize managed → classify → summary.

- [ ] **Step 7: Commit**

---

### Task 12: CSV export

**Files:**
- Create: `portfolio/snapshot/export_csv.py`, `tests/test_export_csv.py`

- [ ] **Step 1: Write failing test** — export produces detail + summary sections; no `quantity` column.

- [ ] **Step 2: Implement `export_snapshot_csv(conn, snapshot_date, out_path)`**

- [ ] **Step 3: Wire into `portfolio snapshot`**

- [ ] **Step 4: Commit**

---

### Task 13: Console summary after snapshot

**Files:**
- Modify: `portfolio/snapshot/runner.py`

- [ ] **Step 1: Print**
  - `SUM(total_value)` for date from `snapshot_summary`
  - Per-bucket percentages
  - Drift vs previous snapshot date (if any)
  - Items with `status != ok` from `items`
  - Unclassified holdings above threshold

- [ ] **Step 2: Commit**

---

### Task 14: Ask Agent — tools and Ollama loop

**Files:**
- Create: `portfolio/agent/tools.py`, `portfolio/agent/ollama.py`, `portfolio/agent/ask.py`, `portfolio/charts/plot.py`

- [ ] **Step 1: `run_sql(conn, query)`** — reject non-SELECT; reject `;`; row cap 500.

- [ ] **Step 2: `plot_pie` / `plot_line`** using matplotlib → `outputs/<uuid>.png`

- [ ] **Step 3: Ollama chat loop** with tool definitions; max 10 tool rounds.

- [ ] **Step 4: `portfolio ask "question"`** command.

- [ ] **Step 5: Manual smoke test** with Ollama running locally.

- [ ] **Step 6: Commit**

---

### Task 15: End-to-end documentation in README (optional, user did not request — skip unless needed)

Per YAGNI, skip README unless user asks.

---

## Self-review checklist

| Spec requirement | Task |
|------------------|------|
| Plaid setup + Keychain | 4, 5, 6 |
| Account include/owner/tax | 7 |
| User-managed holdings | 10 |
| Snapshot replace semantics | 11 |
| asset_name ticker fallback | 9 |
| classification YAML + Ollama | 8, 11 |
| snapshot_summary | 11 |
| CSV no quantity | 12 |
| Ask Agent SQL + charts | 14 |
| Sandbox until Production approved | 3, 5 (env) |

## Execution handoff

**Plan saved to:** `docs/superpowers/plans/2026-05-13-portfolio-review.md`

**Chosen approach:** **Subagent-Driven** — fresh subagent per task (Tasks 1–14), with spec-compliance review then code-quality review after each task. Parent session coordinates only; subagents get self-contained task prompts from this plan.

**Process (per task):**
1. Dispatch implementer subagent with full task text + design spec path
2. Spec reviewer subagent — confirm match to [design spec](../specs/2026-05-13-portfolio-review-design.md)
3. Code quality reviewer subagent
4. Mark task complete; proceed to next task

**When ready to start:** begin with **Task 1: Project scaffold**.
