# Demo magic-link login — Design Plan

> **Status:** ✅ Phase 1 shipped (v2.425.0) — mint endpoint, verify endpoint, single-use `demo_magic_links` table, admin UI partial, double-env-var gate, 13 harness tests. The happy path is exercised end-to-end against a temporarily-gated container; a permanent regression test for it is filed for a future `app-demo` compose override.
> **Tracked in:** [`TODO.md`](../../TODO.md) → Manually Added → "URL-based 'magic-link' login, demo-instance only".
> **Sibling plan:** [`demo-mode.md`](demo-mode.md) — the broader DEMO_MODE shell this builds on.
> **Sibling TODOs:** the fail2ban/CrowdSec log-integration TODO and the Cloudflare edge-banning TODO live next to this one in `Manually Added`; the three are designed to compose into a single security spine but each ships independently.

---

## Goal

Make the public demo instance trivially shareable: a `?login=<token>` query parameter on the landing URL drops the visitor straight into a pre-seeded demo account, no password typed, no email round-trip. The link is what gets pasted on socials / the README / the wiki landing page, and one click is the full onboarding.

**Strictly demo-only.** A production or self-hosted SimpleVTT deploy must refuse to mint or accept these tokens regardless of what the request payload claims, and that refusal must be enforced server-side at a level that a compromised admin account cannot reach.

**Strictly not a production passwordless-login feature.** Email-delivered magic links for real accounts are a different feature with a different threat model (account-recovery vector, phishing surface, long-term token storage) and belong to a separate plan if and when they're proposed.

---

## Threat model

What we're explicitly defending against, in roughly decreasing severity:

1. **Production deploy accidentally accepts a magic-link token.** Operator copies `.env.example` to production, an old `SIMPLEVTT_DEMO_MODE=true` line is in there, and now an attacker can mint a token against a real instance. **Defense:** the magic-link feature is gated by a **separate** env var (`SIMPLEVTT_DEMO_MAGIC_LINK_ENABLED=1`) that is **off by default** even when `SIMPLEVTT_DEMO_MODE=1`. Both gates must fire together; either alone is a no-op. Both gates are checked at module load + per-request — there is no in-memory toggle the admin UI can flip.
2. **Compromised admin account flips the gate from inside SimpleVTT.** The admin user (full SimpleVTT permissions) gains write access to settings.json or a config-reload endpoint and turns the magic-link feature on against a real instance. **Defense:** there is no settings.json or config-reload path that can flip this gate. The only way to enable it is to set the env var at process start and restart the container. An admin-account compromise in v1 can already do a lot of damage (delete campaigns, see all user data) — this design just refuses to *add* the magic-link surface as a new vector.
3. **Token replay.** A leaked URL (logged proxy access log, shared screenshot, browser history sync to a different device) is replayed by an attacker. **Defense:** tokens are **single-use**. A persisted `demo_magic_links` row records the jti on first verify; subsequent attempts with the same jti hit a fast `SELECT 1` and 401. The row is GC'd after the TTL passes.
4. **Token theft via stale clock.** Server clock is hours behind reality and a token that should be expired still verifies. **Defense:** `iat` (issued-at) check uses the server's clock; max age is short (≤15 min); skew tolerance is ±60s. A wildly mis-synced server fails the check on both ends.
5. **Signature forgery.** Attacker tries to mint tokens without the secret. **Defense:** HMAC-SHA256 over the canonical payload using the app's existing `SECRET_KEY`. Same key the JWT auth cookie already uses — if it's compromised, the demo magic-link is the least of the operator's concerns.
6. **Token-id enumeration.** Attacker rapid-fires `?login=<guess>` to find a valid token. **Defense:** jti is 128 random bits (`secrets.token_urlsafe(16)`); brute force is infeasible. Repeated failures log a `demo_magic_link.verify_rejected` line keyed for the sibling fail2ban/CrowdSec TODO so the attacker's IP gets banned after a handful of misses.
7. **Demo account state contamination.** A visitor leaves the demo in a weird state and the next visitor sees it. **Defense:** out-of-scope for this plan — the broader [`demo-mode.md`](demo-mode.md) reset-every-hour mechanism handles this. The magic-link doesn't widen the contamination window because demo accounts are already shared between visitors.

What we're **not** defending against in v1 (filed as Phase 2+ follow-ups, not v1-blocking):

- **DoS via mint-endpoint flooding.** An unauthenticated mint endpoint would be a free DoS vector; v1 keeps mint behind admin auth so only admins can issue. Phase 2 may expose an anonymous mint path with strict rate-limiting (mirrors what the [Cloudflare integration TODO](../../TODO.md#manually-added) would protect at the edge anyway).
- **Per-visitor account isolation.** The demo seeds three shared accounts (gm/player1/player2); two visitors logged in via two different magic links land in the same shared account. The "per-visitor ephemeral accounts" item is filed in [`demo-mode.md`](demo-mode.md) and out of scope here.
- **Geo-fencing demo access.** Out of scope — that's an edge concern, lives at Cloudflare not SimpleVTT.

---

## Architecture

### Gate

Two env vars, both deploy-time:

```bash
SIMPLEVTT_DEMO_MODE=true                    # existing — gates the whole demo shell
SIMPLEVTT_DEMO_MAGIC_LINK_ENABLED=true      # NEW — gates the magic-link surface
```

The magic-link feature only activates when **both** evaluate truthy. The check runs:

- At module import time (`app/routes/demo_magic_link_routes.py` refuses to register its router if the gate is off — the route literally doesn't exist on a hardened deploy).
- At per-request time on the mint endpoint + the verify endpoint (defense in depth — if some future refactor re-enables the router by accident, the request still fails closed).

There is **no** `app/config.py` Settings field that the admin UI can write to. The gate reads `os.getenv()` directly.

### Token shape

JSON payload, base64url-encoded, with an HMAC-SHA256 signature appended as a second base64url segment (compact JWT-without-the-`alg`-header shape, since the alg is fixed):

```json
{
  "sub": "demo-player1@example.com",   // pre-seeded demo account email
  "iat": 1716042000,                   // unix seconds
  "exp": 1716042900,                   // iat + 15 min (server-enforced max — payload value is advisory)
  "jti": "Wx9aBcD2eF1gHiJk",           // 16 bytes urlsafe-b64, the replay-protection key
  "inst": "demo"                       // instance tag — verifier checks against runtime DEMO_MODE
}
```

URL form: `https://demo.simplevtt.example/login?token=<payload>.<sig>`.

The verify path:

1. Slug-guard the token format (single dot, base64url chars only).
2. HMAC-verify the signature.
3. Decode the payload + check `inst == "demo"` AND runtime `SIMPLEVTT_DEMO_MODE=true` AND `SIMPLEVTT_DEMO_MAGIC_LINK_ENABLED=true`.
4. Check `iat + 15min >= now()` with ±60s skew.
5. Atomic `INSERT INTO demo_magic_links (jti, consumed_at) VALUES (?, NOW())` — duplicate-key violation = replay → 401.
6. Look up the `sub` user (must be a seeded demo account — verifier hard-rejects any sub that doesn't match the demo-seed allowlist).
7. Mint the regular auth cookie and 302 to `/`.

### Schema

New table, applied via `_apply_inline_migrations()` in `app/database.py` (SCHEMA_VERSION bump):

```sql
CREATE TABLE demo_magic_links (
    jti TEXT PRIMARY KEY,
    consumed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    sub TEXT NOT NULL
);
CREATE INDEX demo_magic_links_consumed_at_idx ON demo_magic_links (consumed_at);
```

GC: a cheap periodic sweep (every 5 min, on the same async loop that drives `demo_scheduler.py`) deletes rows older than `2× TTL`. Worst-case table size on a busy public demo: ~tens-of-thousands of rows, well within Postgres "table is empty" territory.

### Endpoints

- **`POST /admin/demo/mint-magic-link`** — admin-only (existing admin-cookie auth). Body: `{"sub": "demo-player1@example.com"}` (must be in the demo-seed allowlist). Response: `{"url": "<absolute URL with ?token=…>", "expires_at": "<iso8601>"}`. Refuses (404) if the magic-link gate is off — this is a behavioral signal to the admin that the feature isn't deployed, not just an auth fail.
- **`GET /demo-login?token=<payload>.<sig>`** — public. Verifies, consumes, mints auth cookie, 302 to `/`. Any failure (bad sig, expired, replay, wrong instance) returns 401 with a deliberately-vague body so an enumerating attacker can't distinguish replay from bad-sig.

### UI surface

Phase 1 ships the endpoints + a copy-and-paste affordance only:

- Admin page (`/admin`): "Mint demo magic link" form with a dropdown of the seeded demo accounts. On submit, render the URL into a read-only input + a "Copy" button. The URL doesn't auto-open — the admin pastes it into wherever they want to share.

Phase 2+ may add a public-landing "Try the demo" button that hits an anonymous mint + 302 flow, but that needs the Cloudflare rate-limit before it ships (see the [Cloudflare TODO](../../TODO.md#manually-added)).

### Log lines

Canonical lines emitted at `INFO` for the success path, `WARNING` for the rejection paths. Format is space-separated `key=value` pairs after a fixed event tag, designed so the same regex parses both fail2ban filters and CrowdSec scenarios (per the [fail2ban/CrowdSec sibling TODO](../../TODO.md#manually-added)):

```
demo_magic_link.mint_ok sub=demo-player1@example.com jti=<jti> admin_id=42 ip=1.2.3.4 ua="<ua>"
demo_magic_link.verify_ok sub=demo-player1@example.com jti=<jti> ip=1.2.3.4 ua="<ua>"
demo_magic_link.verify_rejected reason=signature ip=1.2.3.4 ua="<ua>"
demo_magic_link.verify_rejected reason=expired ip=1.2.3.4 ua="<ua>"
demo_magic_link.verify_rejected reason=replay jti=<jti> ip=1.2.3.4 ua="<ua>"
demo_magic_link.verify_rejected reason=gate_off ip=1.2.3.4 ua="<ua>"
demo_magic_link.verify_rejected reason=unknown_sub ip=1.2.3.4 ua="<ua>"
```

The fail2ban filter triggers on **5×`verify_rejected` from one IP in 5min**; the CrowdSec scenario does the same plus a separate "1× `mint_ok` from non-admin IP" trip (the admin IP allowlist comes from the deploy's normal admin-network spec, not this plan).

---

## Phase plan

### Phase 1 — Mint + verify + admin UI (v2.425.0 — ✅ shipped)

1. ✅ **v2.425.0** — Pure-logic helpers split into `app/demo_magic_link.py` (fastapi-free so unit tests run without container deps); HTTP layer in `app/routes/demo_magic_link_routes.py` with `POST /admin/demo/mint-magic-link` + `GET /demo-login`, double-gate check via `magic_link_enabled()`, canonical audit emissions (`demo_magic_link.mint_ok` / `verify_ok` / `verify_rejected reason=…`).
2. ✅ **v2.425.0** — New `demo_magic_links` table via the existing inline-migration pattern. SCHEMA_VERSION 69 → 70.
3. ✅ **v2.425.0** — Admin UI lives inline in `admin_home.html` (no separate partial — the section is gated `{% if magic_link_enabled %}` and only renders when both env vars are on). vanilla JS handles the fetch + result display + clipboard copy.
4. ✅ **v2.425.0** — 13 harness tests: 10 in-process unit tests on the helpers (mint/verify roundtrip, tampered payload + tampered sig, empty / no-dot / garbage tokens, jti uniqueness, gate predicate + truthy/falsy variants), 3 integration tests against the dev container (gate-off 404 paths). Happy-path mint + verify + replay was exercised manually with gates temporarily flipped on; a permanent regression test waits on the `app-demo` compose override (Phase 2 follow-up).
5. 🟠 **Filed for follow-up** — README mention of demo magic-link shareability. The `demo-mode.md` plan and the new `## Security` topic section in `TODO.md` already cross-link this plan; a README-level callout is the lightest-touch advertisement and lands in a doc-only follow-up if/when shareability matters operationally.

**Bug filed for Phase 2.** The 15-minute TTL is hardcoded in `app/demo_magic_link.py::_TOKEN_MAX_AGE_SECONDS`. An expired-token unit test was skipped because itsdangerous's timestamp reference is hard to monkey-patch cleanly from an external test (the lib imports `from time import time` at module load); itsdangerous's own test suite proves the timestamp path. Phase 2 may add a freezegun-based test or an env-var override for the TTL to ship an integration test for the expired-token path.

### Phase 2 — Reference fail2ban + CrowdSec configs (v2.5x.1)

1. Drop `docs/integrations/fail2ban/simplevtt.conf` (filter + jail) and `docs/integrations/crowdsec/simplevtt.yaml` (parser + scenarios) covering the canonical log lines above.
2. Compose-side smoke test: spin up a CrowdSec container against the dev compose, replay a synthetic verify-rejected loop, assert the scenario fires. (Pairs with the fail2ban/CrowdSec sibling TODO — may ship as part of that work instead of here.)

### Phase 3 — Public-landing "Try the demo" button (v2.5x.2, gated)

1. New `GET /demo/try` anonymous endpoint that mints + 302s. Refuses unless `SIMPLEVTT_DEMO_MAGIC_LINK_ANONYMOUS=1` (a third env var, opt-in beyond Phase 1).
2. Strict per-IP rate limit (e.g. 3 mints/IP/hour), tracked in `demo_magic_links` so reset-per-hour matches the demo wipe cadence.
3. **Hard precondition: the Cloudflare edge-banning integration ships first** (or the operator declares they don't need it). Without one of those, this endpoint is a DoS vector.

---

## Non-goals

- Magic-link login for real production accounts (email-delivered, long-lived, account-recovery vector — different plan).
- Per-visitor ephemeral demo accounts (filed in [`demo-mode.md`](demo-mode.md) → "Per-visitor ephemeral accounts").
- OAuth / SSO for the demo (would defeat the "one click, no friction" goal).
- Captcha on the verify path (the single-use + 15-min TTL + Cloudflare edge ban already cover the threat model).

---

## Open questions

- Should the verify path 302 to `/` or to `/campaign/demo-campaign`? Probably the latter — drops the visitor directly onto the tabletop. Resolve when Phase 1 ships.
- Token TTL: 15 min feels right for a "click the link in the next 15 min" UX. Should we expose it as `SIMPLEVTT_DEMO_MAGIC_LINK_TTL_SECONDS`? Probably yes for ops flexibility.
- Should the admin-side mint endpoint also work in **non-demo** mode for a hardened operator who's still testing locally? Strong inclination: **no.** The double-gate is the contract. Leave the test-local path to the harness suite, which can call the helpers directly.

---

## Test contract

- Mint happy-path: admin auth + both env vars on → 200 + URL + expires_at. WS broadcast: none (admin action, no game-state change).
- Verify happy-path: valid token + both env vars on → 302 to demo landing + auth cookie set. Log line: `demo_magic_link.verify_ok`.
- Gate-off (either env var false): mint and verify both 404 (no behavioral leak that the feature *could* exist if the other gate were on).
- Replay: second verify with same jti → 401, log line: `demo_magic_link.verify_rejected reason=replay`.
- Expired: hand-crafted token with `iat` > 15min ago → 401, log line: `demo_magic_link.verify_rejected reason=expired`.
- Bad signature: tampered payload → 401, log line: `demo_magic_link.verify_rejected reason=signature`.
- Unknown sub: token for an email that isn't in the demo-seed allowlist → 401, log line: `demo_magic_link.verify_rejected reason=unknown_sub`.

Tests live as `tests/harness/test_demo_magic_link.py`, one happy-path + the six error paths above.

---

## Out-of-band cross-links

- The [fail2ban/CrowdSec TODO](../../TODO.md#manually-added) defines the consumer side of the log-line contract above.
- The [Cloudflare TODO](../../TODO.md#manually-added) is the precondition for the Phase 3 anonymous-mint endpoint.
- The [`demo-mode.md`](demo-mode.md) plan is the broader DEMO_MODE shell — this plan adds the URL-login surface on top.
