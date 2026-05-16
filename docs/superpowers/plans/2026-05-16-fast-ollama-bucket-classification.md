# Fast Ollama Bucket Classification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Ollama holding classification return quickly by requesting only a bucket JSON object and bounding model generation.

**Architecture:** Keep the existing `portfolio/classify/ollama_suggest.py` boundary: rules and user prompting stay unchanged, and tighten the LLM request/parse contract to bucket-only JSON. The model should receive a compact classification prompt, `temperature: 0`, and a small `num_predict` cap; the app should parse only `{"bucket":"..."}` and remove `reason` from the suggestion contract.

**Tech Stack:** Python 3.12+, `httpx`, Ollama `/api/chat`, existing pytest unit tests.

---

## File Structure

- Modify: `portfolio/classify/ollama_suggest.py`
  - Build a shorter bucket-only prompt.
  - Send Ollama generation options that discourage long output.
  - Parse bucket-only JSON and remove `BucketSuggestion.reason`.
- Modify: `tests/test_ollama_suggest.py`
  - Update parser and request tests from bucket+reason to bucket-only.
  - Assert the Ollama request sends `options.temperature == 0` and a small `options.num_predict`.
  - Assert the prompt no longer asks for a reason.
- Modify: `portfolio/classify/prompt.py`
  - Remove display logic for `suggestion.reason`.

---

### Task 1: Lock Down Bucket-Only Parsing

**Files:**

- Modify: `tests/test_ollama_suggest.py`
- Modify: `portfolio/classify/ollama_suggest.py`
- **Step 1: Update parser tests for bucket-only JSON**

Change `test_parse_plain_json` so the parser returns only bucket and error:

```python
def test_parse_plain_json() -> None:
    bucket, err = parse_bucket_json_payload('{"bucket":"Equity"}')
    assert err is None
    assert bucket == "Equity"
```

Change `test_parse_json_in_markdown_fence` to bucket-only JSON:

```python
def test_parse_json_in_markdown_fence() -> None:
    raw = """Here is the result:
```json
{"bucket": "Bond"}
```

"""
    bucket, err = parse_bucket_json_payload(raw)
    assert err is None
    assert bucket == "Bond"

```

Update the remaining parser tests to unpack two return values:

```python
def test_invalid_bucket_rejected() -> None:
    bucket, err = parse_bucket_json_payload('{"bucket":"Banana"}')
    assert bucket is None
    assert err is not None


def test_malformed_json() -> None:
    bucket, err = parse_bucket_json_payload("not json")
    assert bucket is None
    assert err is not None
```

- **Step 2: Run parser tests and record current behavior**

Run:

```bash
pytest tests/test_ollama_suggest.py::test_parse_plain_json tests/test_ollama_suggest.py::test_parse_json_in_markdown_fence -v
```

Expected before implementation: FAIL with a tuple unpacking error because the current parser returns `(bucket, reason, error)`.

- **Step 3: Remove `reason` from the parser contract**

In `portfolio/classify/ollama_suggest.py`, change the parser signature and return values:

```python
def parse_bucket_json_payload(content: str) -> tuple[str | None, str | None]:
    """Parse model output into `(bucket, error)`. `error` is set when parsing/validation fails."""
    text = (content or "").strip()
    fenced = _extract_markdown_fence_body(text)
    if fenced is not None:
        text = fenced.strip()
    brace = text.find("{")
    if brace < 0:
        return None, "No JSON object found"
    try:
        obj, _end = json.JSONDecoder().raw_decode(text, brace)
    except json.JSONDecodeError as exc:
        return None, f"Invalid JSON: {exc}"
    if not isinstance(obj, dict):
        return None, "JSON root must be an object"
bucket_raw = obj.get("bucket")
if not isinstance(bucket_raw, str):
    return None, "bucket must be a string"
bucket = bucket_raw.strip()
if not is_allowed_bucket(bucket):
    return None, f"Unknown bucket: {bucket_raw!r}"
return bucket, None
```

Do not read, return, or preserve `reason`. If an older model response includes a `reason` key, ignore it as extra JSON data.

- **Step 4: Run parser tests**

Run:

```bash
pytest tests/test_ollama_suggest.py::test_parse_plain_json tests/test_ollama_suggest.py::test_parse_json_in_markdown_fence tests/test_ollama_suggest.py::test_invalid_bucket_rejected tests/test_ollama_suggest.py::test_malformed_json -v
```

Expected: all selected tests pass.

- **Step 5: Commit**

```bash
git add tests/test_ollama_suggest.py portfolio/classify/ollama_suggest.py
git commit -m "refactor(classify): remove Ollama reason parsing"
```

---

### Task 2: Add Fast Ollama Request Options

**Files:**

- Modify: `tests/test_ollama_suggest.py`
- Modify: `portfolio/classify/ollama_suggest.py`
- **Step 1: Update the request test to require fast generation options**

In `test_fetch_bucket_suggestion_uses_chat_api`, update the mocked response to bucket-only content:

```python
return httpx.Response(
    200,
    json={"message": {"content": '{"bucket":"Gold"}'}},
)
```

Then change the assertions at the end of the test to:

```python
assert isinstance(result, BucketSuggestion)
assert result.suggested_bucket == "Gold"
assert result.error is None
assert captured["url"].endswith("/api/chat")
assert captured["body"]["model"] == "test-model"
assert captured["body"]["stream"] is False
assert captured["body"]["format"] == "json"
assert captured["body"]["options"] == {
    "temperature": 0,
    "num_predict": 30,
}
```

Add a prompt assertion so the test guards against reintroducing reason generation:

```python
prompt = captured["body"]["messages"][-1]["content"]
assert "reason" not in prompt.lower()
assert "analysis" not in prompt.lower()
assert '{"bucket":"<bucket>"}' in prompt
```

- **Step 2: Run the request test and verify it fails**

Run:

```bash
pytest tests/test_ollama_suggest.py::test_fetch_bucket_suggestion_uses_chat_api -v
```

Expected: FAIL because the current request body has no `options`, asks for `reason`, and the test now expects bucket-only behavior.

- **Step 3: Add constants for generation options**

In `portfolio/classify/ollama_suggest.py`, near `_OLLAMA_CHAT_TIMEOUT_SEC`, add:

```python
_OLLAMA_NUM_PREDICT = 30
```

Use a single named constant so future tuning is obvious. Do not make this configurable until there is a real need.

- **Step 4: Remove `reason` from `BucketSuggestion` and fetch handling**

In `portfolio/classify/ollama_suggest.py`, change the dataclass to:

```python
@dataclass(frozen=True)
class BucketSuggestion:
    suggested_bucket: str | None
    error: str | None = None
```

Update every `BucketSuggestion(...)` constructor in `fetch_bucket_suggestion` to remove `reason=""`.

Change response parsing from:

```python
bucket, reason, err = parse_bucket_json_payload(content)
if err is not None:
    return BucketSuggestion(suggested_bucket=None, reason=reason or "", error=err)
return BucketSuggestion(suggested_bucket=bucket, reason=reason or "", error=None)
```

to:

```python
bucket, err = parse_bucket_json_payload(content)
if err is not None:
    return BucketSuggestion(suggested_bucket=None, error=err)
return BucketSuggestion(suggested_bucket=bucket, error=None)
```

- **Step 5: Replace the prompt with a compact bucket-only prompt**

Change `_build_user_prompt` to:

```python
def _build_user_prompt(holding: dict[str, Any]) -> str:
    allowed = ", ".join(ORDERED_BUCKETS)
    payload = json.dumps(_holding_prompt_json(holding), sort_keys=True, default=str)
    return (
        "Classify the holding. Return only the answer.\n"
        "Return exactly one compact JSON object and stop.\n"
        f"Buckets: {allowed}\n"
        f"Holding: {payload}\n"
        'Output exactly: {"bucket":"<bucket>"}'
    )
```

This prompt deliberately avoids asking for `reason`, avoids inviting analysis, and gives the model a stop-shaped final line.

- **Step 6: Add Ollama options to the request body**

Change the body in `fetch_bucket_suggestion` to include `options`:

```python
body = {
    "model": settings.ollama_model,
    "messages": [{"role": "user", "content": _build_user_prompt(holding)}],
    "stream": False,
    "format": "json",
    "options": {
        "temperature": 0,
        "num_predict": _OLLAMA_NUM_PREDICT,
    },
}
```

Do not change the 60s HTTP timeout in this task. The timeout is still useful for model loading or a stuck local server; `num_predict` addresses the unbounded generation symptom.

- **Step 7: Run the request test**

Run:

```bash
pytest tests/test_ollama_suggest.py::test_fetch_bucket_suggestion_uses_chat_api -v
```

Expected: PASS.

- **Step 8: Commit**

```bash
git add tests/test_ollama_suggest.py portfolio/classify/ollama_suggest.py
git commit -m "fix(classify): bound Ollama bucket generation"
```

---

### Task 3: Verify Timeout and Prompt UX Still Work

**Files:**

- Modify: `portfolio/classify/prompt.py`
- Modify: `tests/test_classify_prompt.py`
- Modify: `tests/test_classify_snapshot_interactive.py`
- Modify: `tests/test_ollama_suggest.py`
- **Step 1: Confirm timeout test still expects the same soft error**

Leave `test_fetch_bucket_suggestion_timeout_returns_soft_error` functionally unchanged:

```python
def test_fetch_bucket_suggestion_timeout_returns_soft_error() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("simulated read timeout")

    settings = Settings(
        plaid_client_id="",
        plaid_secret="",
        plaid_env="sandbox",
        db_path=":memory:",
        ollama_base_url="http://ollama.test",
        ollama_model="test-model",
    )
    holding = {"asset_name": "SLOW", "source": "plaid"}
    transport = httpx.MockTransport(handler)
    with httpx.Client(transport=transport) as client:
        result = fetch_bucket_suggestion(holding, settings, http_client=client)

    assert result.suggested_bucket is None
    assert result.error is not None
    assert "60" in result.error
    assert "Ollama" in result.error
```

- **Step 2: Run all Ollama suggestion tests**

Run:

```bash
pytest tests/test_ollama_suggest.py -v
```

Expected: PASS.

- **Step 3: Remove `reason` from prompt display and tests**

In `portfolio/classify/prompt.py`, remove this block from `_print_card`:

```python
if suggestion.reason:
    write(f"Reason: {suggestion.reason}\n")
```

In `tests/test_classify_prompt.py`, update all `BucketSuggestion(...)` constructors:

```python
BucketSuggestion(suggested_bucket="Equity", error=None)
BucketSuggestion(suggested_bucket=None, error="offline")
BucketSuggestion(suggested_bucket="Gold", error=None)
BucketSuggestion(suggested_bucket=None, error=None)
```

Do not add a replacement assertion for `Reason:`. The UI should now show only the suggested bucket.

- **Step 4: Run prompt tests**

Run:

```bash
pytest tests/test_classify_prompt.py -v
```

Expected: PASS.

- **Step 5: Remove `reason` from snapshot test mocks**

In `tests/test_classify_snapshot_interactive.py`, update the monkeypatched suggestion:

```python
lambda holding, s, http_client=None: BucketSuggestion(
    suggested_bucket="Equity",
    error=None,
)
```

- **Step 6: Run snapshot interactive tests**

Run:

```bash
pytest tests/test_classify_snapshot_interactive.py -v
```

Expected: PASS. This confirms bucket-only suggestions still flow through user confirmation and persistence.

- **Step 7: Run the focused classification suite**

Run:

```bash
pytest tests/test_ollama_suggest.py tests/test_classify_prompt.py tests/test_classify_snapshot_interactive.py tests/test_classify_rules.py -v
```

Expected: PASS.

- **Step 8: Commit**

```bash
git add portfolio/classify/prompt.py tests/test_classify_prompt.py tests/test_classify_snapshot_interactive.py tests/test_ollama_suggest.py
git commit -m "test(classify): verify bucket-only suggestions"
```

After this commit, agent implementation is complete. Do not treat Task 4 as part of the agent implementation plan.

---

### Task 4: Human-Only Optional Manual Ollama Smoke Test

This task is for the human developer to run locally after Tasks 1-3 are implemented and verified. Agents should not execute or gate completion on this task because it depends on the human's local Ollama installation, model availability, and desired manual confidence level.

**Files:**

- No file changes.
- **Step 1: Start or confirm Ollama is running**

Run:

```bash
ollama list
```

Expected: the configured model from `OLLAMA_MODEL` or default `llama3.1` is present. If it is missing, run:

```bash
ollama pull qwen3.5:4b
```

- **Step 2: Exercise the request shape with a tiny local script**

Run:

```bash
python - <<'PY'
from portfolio.classify.ollama_suggest import fetch_bucket_suggestion
from portfolio.config import Settings

settings = Settings.from_env()
result = fetch_bucket_suggestion(
    {"asset_name": "GLD", "display_name": None, "plaid_type": "etf"},
    settings,
)
print(result)
PY
```

Expected: the command returns well before 60 seconds with a `BucketSuggestion` whose `suggested_bucket` is one of `Cash`, `Bond`, `Equity`, `Gold`, `Commodity`, `Crypto`, or `RealEstate`. For `GLD`, `Gold` is ideal but not required for this smoke test; the unit tests validate shape, not model intelligence.

- **Step 3: If manual smoke still times out, inspect model load separately**

Run:

```bash
time ollama run "${OLLAMA_MODEL:-qwen3.5:4b}" 'Return {"bucket":"Gold"}'
```

Expected: if this also takes close to or over 60 seconds, the remaining root cause is local model startup or model size rather than this app's prompt. Use a smaller model or pre-warm Ollama before running `portfolio snapshot`.

---

## Self-Review

- Spec coverage: The plan addresses the user's requirements: stop requesting `reason`, keep only `bucket` in model output, and bound generation so Ollama returns faster.
- Placeholder scan: No `TBD`, `TODO`, or unspecified implementation steps remain.
- Type consistency: `parse_bucket_json_payload` returns `tuple[str | None, str | None]`; `BucketSuggestion` exposes only `suggested_bucket` and `error`; prompt and snapshot tests construct suggestions without `reason`.
- Scope control: No broad refactor, no config migration, and no prompt UI redesign are required.

