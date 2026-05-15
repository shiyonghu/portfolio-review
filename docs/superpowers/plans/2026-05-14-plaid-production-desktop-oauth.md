# Plaid Production desktop popup OAuth (omit `redirect_uri`) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** When `PLAID_ENV=production`, create Plaid Link tokens **without** a `redirect_uri` so Production complies with Plaid’s HTTPS redirect rule while keeping a **desktop popup–only** OAuth path; when `PLAID_ENV=sandbox`, keep sending `http://localhost:8765` as `redirect_uri`.

**Architecture:** `create_app` already stores `Settings` on `app.state.settings`. `create_link_token` builds `LinkTokenCreateRequest` with shared fields, then adds `redirect_uri` **only** for `sandbox`. The `plaid-python` OpenAPI model marks `redirect_uri` as optional ([`LinkTokenCreateRequest`](https://github.com/plaid/plaid-python/blob/master/plaid/model/link_token_create_request.py)); omitting the constructor argument avoids sending the field in the API body. Tests assert serialized `to_dict()` contains or omits `redirect_uri` by environment.

**Tech stack:** Python 3.12+, `plaid-python` (see `[pyproject.toml](../../pyproject.toml)`), FastAPI, pytest.

**Authoritative spec:** `[docs/superpowers/specs/2026-05-14-plaid-production-desktop-oauth-design.md](../specs/2026-05-14-plaid-production-desktop-oauth-design.md)`.

---

## File structure

| Path | Responsibility |
| ---- | ---------------- |
| Modify: `[portfolio/plaid/link_server.py](../../portfolio/plaid/link_server.py)` | Conditional `redirect_uri` on `LinkTokenCreateRequest` from `app.state.settings.plaid_env` |
| Modify: `[tests/test_link_server.py](../../tests/test_link_server.py)` | Assert sandbox includes `redirect_uri`; production omits it from serialized request |
| Modify: `[README.md](../../README.md)` | Short note under Plaid setup: Production = desktop + popups, no `redirect_uri`; Sandbox keeps localhost redirect |

---

### Task 1: Tests for `redirect_uri` by `PLAID_ENV` (TDD)

**Files:**

- Modify: `tests/test_link_server.py`

- [ ] **Step 1: Add production settings helper and failing test**

Append to `tests/test_link_server.py` (after `_settings`, reuse pattern):

```python
def _settings_production(tmp_path) -> Settings:
    return Settings(
        plaid_client_id="test-client-id",
        plaid_secret="test-secret",
        plaid_env="production",
        db_path=str(tmp_path / "portfolio.db"),
        ollama_base_url="http://localhost:11434",
        ollama_model="llama3.1",
    )


def test_create_link_token_production_omits_redirect_uri_in_request_body(tmp_path) -> None:
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.link_token = "link-production-456"
    mock_client.link_token_create.return_value = mock_response
    app = create_app(_settings_production(tmp_path), plaid_client=mock_client)

    with TestClient(app) as client:
        response = client.post("/api/create_link_token")

    assert response.status_code == 200
    mock_client.link_token_create.assert_called_once()
    request = mock_client.link_token_create.call_args[0][0]
    payload = request.to_dict()
    assert "redirect_uri" not in payload, payload
```

- [ ] **Step 2: Run test — expect FAIL**

Run:

```bash
cd /Users/shiyonghu/workspace/portfolio-review && python3 -m pytest tests/test_link_server.py::test_create_link_token_production_omits_redirect_uri_in_request_body -v
```

Expected: **FAIL** — `AssertionError` because `redirect_uri` is still present in `payload` (current code always sets it).

- [ ] **Step 3: Extend sandbox test to assert `redirect_uri` is present**

In `test_create_link_token_returns_token`, after loading `request` from the mock, add:

```python
    assert request.to_dict().get("redirect_uri") == "http://localhost:8765"
```

- [ ] **Step 4: Run both link_token tests — sandbox passes, production still fails until implementation**

Run:

```bash
python3 -m pytest tests/test_link_server.py::test_create_link_token_returns_token tests/test_link_server.py::test_create_link_token_production_omits_redirect_uri_in_request_body -v
```

Expected: `test_create_link_token_returns_token` **PASS** (after Step 3); production test **FAIL** until Task 2.

- [ ] **Step 5: Commit** (only if the user asked to commit)

```bash
git add tests/test_link_server.py
git commit -m "test(plaid): assert redirect_uri by PLAID_ENV for link token create"
```

---

### Task 2: Conditional `redirect_uri` in `link_server.py`

**Files:**

- Modify: `portfolio/plaid/link_server.py` (function `create_link_token` inside `create_app`)

- [ ] **Step 1: Replace the fixed `LinkTokenCreateRequest` construction**

Find the block:

```python
        plaid_request = LinkTokenCreateRequest(
            user=LinkTokenCreateRequestUser(client_user_id=f"portfolio-{uuid4()}"),
            client_name="Portfolio Review",
            products=[Products("investments")],
            country_codes=[CountryCode("US")],
            language="en",
            # Register http://localhost:8765 as an allowed redirect URI in Plaid.
            redirect_uri="http://localhost:8765",
        )
```

Replace with:

```python
        link_kwargs: dict[str, Any] = {
            "user": LinkTokenCreateRequestUser(client_user_id=f"portfolio-{uuid4()}"),
            "client_name": "Portfolio Review",
            "products": [Products("investments")],
            "country_codes": [CountryCode("US")],
            "language": "en",
        }
        if app.state.settings.plaid_env == "sandbox":
            # Sandbox only: http localhost allowed by Plaid. Register in Dashboard allowlist.
            link_kwargs["redirect_uri"] = "http://localhost:8765"
        plaid_request = LinkTokenCreateRequest(**link_kwargs)
```

(`Any` is already imported in `link_server.py` from `typing`.)

- [ ] **Step 2: Run tests**

Run:

```bash
python3 -m pytest tests/test_link_server.py -v
```

Expected: **all PASS** (including `test_create_link_token_production_omits_redirect_uri_in_request_body`).

- [ ] **Step 3: Commit** (only if the user asked to commit)

```bash
git add portfolio/plaid/link_server.py
git commit -m "fix(plaid): omit redirect_uri in production for desktop popup OAuth"
```

---

### Task 3: README — operator expectations

**Files:**

- Modify: `README.md`

- [ ] **Step 1: Add a short subsection after the `.env` / `PLAID_ENV` bullets (near the existing Plaid env lines)**

Insert (adjust heading level to match surrounding README structure, e.g. `####` if inside `### Setup`):

```markdown
#### Plaid Production and OAuth (desktop only)

With `PLAID_ENV=production`, this app **does not** send a `redirect_uri` to Plaid, so you are not required to register an HTTPS localhost URL. OAuth institutions open in a **popup or new tab** in a normal desktop browser; **allow popups** for `http://localhost:8765` (or whatever host you use). **Mobile browsers and in-app webviews** are not supported for OAuth with this setup—use a desktop browser. Sandbox continues to send `http://localhost:8765` as `redirect_uri` for optional redirect-flow testing; add that URI to the Sandbox allowlist in the Plaid Dashboard.
```

- [ ] **Step 2: Commit** (only if the user asked to commit)

```bash
git add README.md
git commit -m "docs: explain production Plaid OAuth without redirect_uri"
```

---

## Self-review

1. **Spec coverage:** Conditional `redirect_uri` (sandbox vs production) → Task 2 + Task 1. Limitations / desktop-only → Task 3 README. Dashboard “may be empty” → README + spec; no code. Optional startup log for `plaid_env` → omitted (spec marked optional); YAGNI.
2. **Placeholder scan:** None.
3. **Type consistency:** `Settings.plaid_env` is already `str` constrained to `sandbox` | `production` in `[portfolio/config.py](../../portfolio/config.py)`; comparison uses lowercase literals matching `from_env`.

---

**Plan complete and saved to `docs/superpowers/plans/2026-05-14-plaid-production-desktop-oauth.md`. Two execution options:**

**1. Subagent-Driven (recommended)** — Dispatch a fresh subagent per task, review between tasks, fast iteration.

**2. Inline Execution** — Execute tasks in this session using executing-plans, batch execution with checkpoints.

**Which approach do you want?**
