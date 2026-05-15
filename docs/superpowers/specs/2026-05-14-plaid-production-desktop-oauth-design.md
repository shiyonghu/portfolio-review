# Plaid Production — Desktop Popup OAuth (No `redirect_uri`)

**Date:** 2026-05-14  
**Status:** Approved  
**Origin:** Brainstorming: HTTPS redirect requirement vs. local-only setup ([Plaid Link OAuth](https://plaid.com/docs/link/oauth/)).

## Purpose

Describe how **portfolio-review** supports **Plaid Production** when the Link UI runs only as **desktop web in a normal browser**, using Plaid’s **popup-based OAuth** path and **not** registering or sending an HTTPS `redirect_uri`.

## Decision

- For **`PLAID_ENV=production`**, **`/link/token/create` must not include `redirect_uri`** (omit the field entirely from `LinkTokenCreateRequest`).
- For **`PLAID_ENV=sandbox`**, keep sending a **`http://localhost:<port>`** `redirect_uri` (see *Sandbox*) so optional testing of return-url / `receivedRedirectUri` flows remains possible without TLS.

Rationale: Plaid states that on **desktop web** and **mobile web**, OAuth can open the bank in a **new window or tab** when no `redirect_uri` is supplied; omitting `redirect_uri` avoids the Production rule that redirect URIs must use HTTPS ([create and register a redirect URI](https://plaid.com/docs/link/oauth/#create-and-register-a-redirect-uri)). The **Sandbox-only** exception allowing `http://localhost` does not apply to Production, so Production either needs HTTPS callbacks or no `redirect_uri`; this spec chooses the latter for v1.

## Explicit limitations (accepted for v1)

The following are **out of scope** or **known-weak** until a future HTTPS `redirect_uri` is implemented:

| Scenario | Behavior |
| -------- | -------- |
| **Mobile web** (phone browser) | OAuth may open in a context where popups are unreliable; conversion may suffer. Not supported as a first-class journey. |
| **Embedded / in-app browsers** (e.g. webviews opened from Mail, Maps, social apps) | Plaid documents that **without** `redirect_uri`, **webview** users may be blocked because popups are often unsupported; **reinitializing Link at a redirect URI** is required for those sessions. Not supported. |
| **App-to-app** (native iOS/Android) | Not applicable to this repo’s FastAPI + browser Link UI today. |
| **Future “hosted Link” or mobile SDK** | Would require revisiting and almost certainly adding HTTPS `redirect_uri` (or platform-specific Android package name). |

**User expectation:** End users complete Link only on **desktop**, in **Chrome / Safari / Firefox / Edge** (or similar), with **popups allowed** for the origin serving Link (typically `http://localhost:<port>` for the main page).

## Architecture

- **Configuration:** `Settings` already exposes `plaid_env` (`sandbox` | `production`). No new env vars are *required* for this decision path.
- **Link token creation** (`portfolio/plaid/link_server.py` or shared helper): build `LinkTokenCreateRequest` **conditionally**:
  - `sandbox` → set `redirect_uri` to the configured localhost URL (current behavior: align with whatever host/port the setup server uses; today `http://localhost:8765` is hardcoded and should stay consistent with the allowlist in Plaid Dashboard for Sandbox).
  - `production` → **do not** set `redirect_uri` (Python SDK: omit argument / pass `None` if the SDK requires explicit omission — verify against `plaid-python` for the installed version).
- **TLS for Production main page:** **Not required** by this spec for the redirect constraint, because Production will not use a browser redirect back to the app’s callback URL. The main Link page may remain **HTTP localhost** for local-only usage. (Separately, users should still treat Production secrets as sensitive.)

## OAuth UX (desktop popup)

- First launch: user clicks “Launch Plaid Link”; institution OAuth opens in a **popup** (or new tab per Plaid/browser behavior).
- User completes bank OAuth; popup closes or hands off; Link `onSuccess` / `onExit` behave as today.
- **No** `receivedRedirectUri` handling is **required** for this path on desktop web when `redirect_uri` is omitted (per Plaid’s desktop web row in [reinitializing Link](https://plaid.com/docs/link/oauth/#reinitializing-link)). The implementation **must not** assume a return URL with `oauth_state_id` in Production for v1.

## Sandbox

- Continue to pass **`http://localhost:<port>`** (or a single configured value) as `redirect_uri` so developers can still exercise OAuth return flows if they open Link in a webview or follow Plaid’s testing guidance later.
- Plaid Dashboard: Sandbox **Allowed redirect URIs** should still list that HTTP localhost URI.

## Production — Plaid Dashboard and compliance

- **Allowed redirect URIs:** May be **empty** for this integration style, or may contain unused HTTPS URIs from experiments; Plaid’s **link/token/create** call for Production **must not** send `redirect_uri` if we are committed to popup-only.
- **OAuth / institution registration** (company profile, US OAuth institutions, etc.) remains independent: follow Plaid’s Production checklist; this spec only addresses the **redirect URI vs. HTTPS** tension.

## Error handling and support

- If users report “stuck after bank login” on **phone** or **in-app browser**, response is: **use desktop Chrome/Safari with popups enabled**; long-term fix is HTTPS `redirect_uri` + reinitialization (prior brainstorm option 1).
- Optional: log or surface `plaid_env` at server startup so support can confirm Production vs Sandbox.

## Testing

| Environment | What to verify |
| ----------- | ---------------- |
| **Sandbox** | Link still creates with `redirect_uri=http://localhost:8765` (or configured); OAuth test institutions still work. |
| **Production** (trial or live keys) | `link/token/create` payload has **no** `redirect_uri`; connect at least one **OAuth** institution from desktop browser with popups allowed; confirm `onSuccess` and token exchange. |

## Future work (not in this spec)

- HTTPS localhost (or hosted) `redirect_uri`, dedicated callback route, `receivedRedirectUri`, and mobile/webview support if product scope expands.

## Self-review (2026-05-14)

- **Placeholders:** None intended; port numbers should match the actual CLI/server default wherever documented (README / `.env.example`).
- **Consistency:** Production omits URI; Sandbox keeps HTTP localhost — matches Plaid’s Sandbox exception and avoids forcing local TLS for Production.
- **Scope:** Single concern (redirect / OAuth surface); no unrelated refactors.
- **Ambiguity:** If `plaid-python` ever requires explicit `redirect_uri=None` vs omitting the key, implementation plan should cite the SDK version and chosen pattern.
