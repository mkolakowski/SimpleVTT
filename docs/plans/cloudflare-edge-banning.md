# Cloudflare edge-banning integration — Design Plan

> **Status:** ⚪ proposed · Phase 1 unstarted.
> **Tracked in:** [`TODO.md`](../../TODO.md) → Manually Added → "Cloudflare IP-banning integration".
> **Sibling plans:**
> - [`demo-magic-link.md`](demo-magic-link.md) — Phase 3 "Try the demo" anonymous-mint endpoint is **hard-blocked** on this plan shipping first.
> - [`fail2ban-crowdsec-integration.md`](fail2ban-crowdsec-integration.md) — the detection counterpart. CrowdSec already has a native Cloudflare bouncer, so operators who run both get edge-level banning out of the canonical log lines for free.

---

## Goal

Move SimpleVTT's banning decisions from the FastAPI request layer to the Cloudflare edge so a determined attacker can't simply retry against the origin. When the GM clicks "Ban IP at edge" in the campaign admin panel, or when a future auto-ban hook fires from an in-app rate-limit detector, the IP gets added to a configured Cloudflare WAF custom rule or IP Access Rule via Cloudflare's REST API. Requests from that IP never reach SimpleVTT again until the operator unbans.

This is the **enforcement** half of the three-piece security spine started in v2.423.2:

1. [`demo-magic-link.md`](demo-magic-link.md) — the auth surface that needs protecting.
2. [`fail2ban-crowdsec-integration.md`](fail2ban-crowdsec-integration.md) — the detection layer (canonical log lines + reference configs).
3. **This plan** — the enforcement layer (edge banning via Cloudflare).

Each ships independently, but the three compose: an operator who deploys all three gets canonical log emission → CrowdSec parses → CrowdSec's native Cloudflare bouncer bans at the edge → SimpleVTT never sees the attacker again. The "Ban IP at edge" button in the campaign admin panel is the in-app sibling of that flow — same Cloudflare API, same edge enforcement, but driven from a GM judgment call (e.g. "this disruptive player is harassing the table; ban their IP") rather than a log signal.

**Out of scope: in-app rate-limiting / banning at the FastAPI layer.** SimpleVTT's per-request rate limit (if and when it lands) is a different concern with a different threat model. This plan is strictly about *enforcing* a ban decision *at the Cloudflare edge*. The decision can come from anywhere — GM click, future auto-ban hook, ops engineer running a `cscli decisions add` mirror — but enforcement lives at the edge.

---

## Threat model

What we're defending against, in roughly decreasing severity:

1. **Disruptive players abusing in-game features.** GM identifies a player flooding the roll log / spamming the chat / repeatedly disconnecting + reconnecting to grief the table. **Defense:** GM clicks "Ban IP at edge" in the campaign admin panel. The Cloudflare API call is fire-and-forget; the next request from that IP gets a 403 from Cloudflare's edge, never touches SimpleVTT.
2. **Attacker who's already been kicked by fail2ban / CrowdSec at the host firewall but is rotating IPs faster than the host can keep up.** **Defense:** the CrowdSec → Cloudflare bouncer path (out of scope for this plan but unblocked by it). The bouncer reads CrowdSec decisions and translates them to Cloudflare rules using the same API client this plan ships.
3. **Phase 3 of [`demo-magic-link.md`](demo-magic-link.md): an anonymous public-mint endpoint exists, and an attacker tries to drain mints faster than the per-IP rate limit can keep up.** **Defense:** the Phase 3 demo plan calls for this Cloudflare plan as a hard precondition. If a single IP exceeds 3 mints/hour the in-app rate limit refuses + this integration optionally bans that IP at the edge for the rest of the hour.
4. **Compromised admin account uses the "Ban IP at edge" button to lock legitimate users out.** **Defense:** every ban call writes a row to a new `admin_audit_log` table (who banned what IP, when, against which scope) so an ops engineer can spot abuse + revert. The unban path is GM-button + ops `cscli`/`curl` accessible. Admin compromise still lets an attacker do plenty of damage; this is mitigation, not prevention.
5. **Cloudflare API token leak.** Attacker gains access to the configured token. **Defense:** the token is scoped to a *single zone* and the *Access Rules* permission only — it can ban IPs against that zone but can't read DNS, can't change WAF rules at large, can't pivot. Token rotation is operator-driven and the env var is hot-reloadable on container restart.
6. **DoS via ban-flood.** Attacker triggers the auto-ban hook (Phase 3) repeatedly against spoofed `X-Forwarded-For` to fill the Cloudflare IP Access Rule list. **Defense:** `TRUSTED_PROXY_HOPS` from [`fail2ban-crowdsec-integration.md`](fail2ban-crowdsec-integration.md) makes IP attribution truthful before the ban call. Plus the Cloudflare API rate-limits the SimpleVTT app token by default.

What we're **not** defending against:

- **Cloudflare downtime.** If Cloudflare is down, SimpleVTT serves directly to whoever finds the origin IP. The "edge" enforcement layer is contingent on Cloudflare being up; SimpleVTT's own FastAPI auth is the fallback.
- **Origin IP exposure.** Cloudflare proxies the public hostname; if an attacker finds the origin IP they bypass the edge entirely. Solving this means Cloudflare Tunnel / Argo / a firewall rule that only accepts traffic from Cloudflare ASN — that's an operator concern, not a SimpleVTT feature.
- **Application-layer attacks behind a legitimate IP.** A banned IP attacker rotating to a new IP is the same as a credential-stuffer rotating IPs — that's the fail2ban/CrowdSec detection layer's job to catch.

---

## Architecture

### Outbound client

New `app/integrations/cloudflare.py` — a thin async client wrapping `httpx.AsyncClient`. Exposes:

```python
async def add_ip_access_rule(
    ip: str,
    *,
    mode: Literal["block", "challenge", "whitelist"] = "block",
    notes: str | None = None,
    scope: Literal["zone", "account"] = "zone",
) -> str:
    """Add an IP access rule. Returns the Cloudflare rule id.

    Raises CloudflareDisabledError if the integration env vars
    aren't configured (so callers can gracefully skip rather than
    error a user-facing flow). Raises CloudflareApiError on a
    non-200 response from the API."""

async def remove_ip_access_rule(rule_id: str) -> None:
    """Delete an IP access rule by id. Idempotent — a 404 from
    Cloudflare is logged + treated as success."""

async def list_ip_access_rules(*, ip: str | None = None) -> list[CloudflareRule]:
    """List IP access rules, optionally filtered to one IP. Used
    by the GM panel's existing-bans display + the unban path."""
```

The client is stateless — every call reads the configured token + zone id from `os.getenv()` at call time (cached in a module-level `lru_cache(maxsize=1)` per process for the token, since it doesn't rotate within a process). No persistent connection / no background task.

### Configuration

Three env vars (per CLAUDE.md "Third-party APIs must be Docker Compose services"):

```bash
CLOUDFLARE_API_TOKEN=<scoped-token>          # Zone:Access Rules:Edit permission
CLOUDFLARE_ZONE_ID=<zone-id>                 # the zone for the SimpleVTT hostname
CLOUDFLARE_API_BASE_URL=https://api.cloudflare.com/client/v4   # overridable for dev mock
```

Plus an optional fourth that gates the *feature* (not the client):

```bash
SIMPLEVTT_CLOUDFLARE_BANNING_ENABLED=true    # default false; admin UI button only renders when true
```

**Why a fourth env var:** the client is useful to instantiate even when banning is disabled (the CrowdSec bouncer path could use it directly), but the *GM-facing button* should only render on instances that have opted in. Without the fourth gate, an operator who configures the token + zone for the CrowdSec bouncer would also auto-expose the in-app ban button, which they may not want.

### Compose-side mocking (per CLAUDE.md "Third-party APIs must be Docker Compose services")

Cloudflare's API isn't a service we run — but the docker-compose stack ships a wiremock service for dev so the integration is testable without burning real Cloudflare quota:

```yaml
# docker-compose.yml additions
services:
  cloudflare-mock:
    image: wiremock/wiremock:latest
    ports:
      - "8014:8080"   # mapped only in dev profile
    volumes:
      - ./docs/integrations/cloudflare/mock:/home/wiremock
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8080/__admin/health"]
      interval: 5s
      timeout: 3s
      retries: 5
  app:
    environment:
      CLOUDFLARE_API_BASE_URL: http://cloudflare-mock:8080/client/v4
      # CLOUDFLARE_API_TOKEN + ZONE_ID set to dev-fixture values
```

The wiremock fixture lives under `docs/integrations/cloudflare/mock/` and serves canned `/zones/<id>/firewall/access_rules/rules` responses. The harness tests drive the wiremock directly to assert the integration translates GM clicks into correct API calls.

### Schema

New table for the admin-audit log, applied via `_apply_inline_migrations()` (SCHEMA_VERSION bump):

```sql
CREATE TABLE admin_audit_log (
    id          BIGSERIAL PRIMARY KEY,
    actor_id    BIGINT NOT NULL REFERENCES users(id),
    action      TEXT NOT NULL,              -- e.g. "cloudflare.ban_ip", "cloudflare.unban_ip"
    target      TEXT NOT NULL,              -- e.g. "1.2.3.4"
    scope       TEXT,                       -- "campaign:<id>" or "global"
    cloudflare_rule_id TEXT,                -- for ban actions, the rule id Cloudflare returned
    notes       TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX admin_audit_log_actor_idx ON admin_audit_log (actor_id, created_at);
CREATE INDEX admin_audit_log_target_idx ON admin_audit_log (target, created_at);
```

The table is generic by design — Phase 1 logs cloudflare-ban + cloudflare-unban events, but future admin-audit-worthy actions (campaign-delete, user-purge, demo-magic-link mint per [`demo-magic-link.md`](demo-magic-link.md)) drop into the same schema.

### Endpoints

- **`POST /api/campaign/{cid}/ban_ip`** — GM-only (existing campaign-GM gate). Body: `{"ip": "1.2.3.4", "notes": "harassment in session 2026-06-18"}`. Validates the IP shape, calls `cloudflare.add_ip_access_rule(...)`, writes the audit row, returns `{ok, rule_id, expires_at: null}`. Refuses 503 if the integration env vars aren't configured (so the UI can hide the button gracefully).
- **`POST /api/campaign/{cid}/unban_ip`** — GM-only. Body: `{"rule_id": "<cf-rule-id>"}` (or `{"ip": "1.2.3.4"}` to look it up). Removes the Cloudflare rule, writes a `cloudflare.unban_ip` audit row.
- **`GET /api/campaign/{cid}/edge_bans`** — GM-only. Lists active edge bans (Cloudflare-side) + the audit-log history for this campaign. Drives the GM panel's "Banned IPs" subsection.

All three are gated on `SIMPLEVTT_CLOUDFLARE_BANNING_ENABLED=true` *and* the operator having configured `CLOUDFLARE_API_TOKEN`. Either-or both off → 503 with a clear "feature not configured" body so the UI knows to hide the affordance.

### UI surface

A new "Edge bans" subsection in the campaign GM panel (`app/templates/campaign_settings.html` or wherever future kick-player / boot affordances land — they'll likely cohabitate):

- Input: an IP address text field + a notes text field + a "Ban at edge" button.
- List: active bans with each row showing IP / notes / banned-by / banned-at / [Unban] button.
- Banner above the list: "These bans apply at the Cloudflare edge — the banned IP will not be able to reach this server until you unban or until Cloudflare clears its rule (rules persist indefinitely by default)."

The whole subsection is hidden when the feature isn't configured (driven by a server-side `cloudflare_banning_enabled` template flag).

### Log emission

Each ban / unban call emits a canonical log line per [`fail2ban-crowdsec-integration.md`](fail2ban-crowdsec-integration.md):

```
cloudflare.ban_ok ip=1.2.3.4 actor_id=42 rule_id=abc123 scope=campaign:7
cloudflare.ban_failed ip=1.2.3.4 actor_id=42 reason=upstream_503
cloudflare.unban_ok rule_id=abc123 actor_id=42
cloudflare.unban_failed rule_id=abc123 actor_id=42 reason=not_found
```

The `ban_failed` events are an observability signal, not a banning trigger — they exist so an operator can spot Cloudflare API outages without scraping the FastAPI access log.

---

## Phase plan

### Phase 1 — Client + manual ban/unban + audit log + wiremock dev (v2.5x.0)

1. New `app/integrations/cloudflare.py` async client with the three methods + the dual exception types.
2. New `app/database.py` migration block: `admin_audit_log` table + indices. **SCHEMA_VERSION +1.**
3. New `app/routes/admin_audit_routes.py` with the three endpoints (ban / unban / list).
4. New `docs/integrations/cloudflare/mock/` wiremock fixture serving canned IP-access-rule responses.
5. New `cloudflare-mock` service in `docker-compose.yml`, dev profile only.
6. GM panel partial: "Edge bans" subsection, gated on the new template flag.
7. Harness tests: ban happy-path (button → API call → audit row → broadcast), unban happy-path, list happy-path, feature-gated-off path (503), Cloudflare-API-error path (503 + audit failed row), non-GM caller rejected (403).

### Phase 2 — CrowdSec bouncer wiring documentation (v2.5x.1)

1. `docs/integrations/cloudflare/crowdsec-bouncer.md` — operator how-to for wiring CrowdSec's `cs-cloudflare-blocker` against the same Cloudflare token / zone. The bouncer translates CrowdSec decisions directly into Cloudflare rules using the same API — SimpleVTT doesn't need to participate, just document the path.
2. Compose-side test that runs CrowdSec + the bouncer against the wiremock to assert the end-to-end "synthetic event → CrowdSec scenario fires → bouncer adds rule → wiremock receives" chain.

### Phase 3 — Auto-ban hook from in-app rate limit (v2.5x.2, gated on demo-magic-link Phase 3)

1. A new in-app rate-limit primitive (per-IP, per-endpoint) emits `cloudflare.auto_ban_requested` when it trips repeatedly.
2. The auto-ban handler reads a configurable threshold + ban duration and calls `cloudflare.add_ip_access_rule(...)` with a `notes` string identifying the trigger.
3. **Hard precondition:** the demo-magic-link Phase 3 anonymous "Try the demo" endpoint exists and is wired through the rate limit. Without that, there's no Phase-3 callsite for the auto-ban hook.

---

## Non-goals

- **In-app rate limiting / banning at the FastAPI layer.** Separate concern. This plan is strictly *Cloudflare-edge* enforcement.
- **Cloudflare DNS management.** Out of scope. The token's permissions are scoped to Access Rules only.
- **Authoring full WAF rules.** Only IP Access Rules. The full WAF rule language is rich (path patterns, header matching, country blocks); we're not building a UI for it. Operators who want richer rules use the Cloudflare dashboard directly.
- **Origin-protection (hide origin IP from attackers who probe DNS).** That's a Cloudflare Tunnel / firewall concern, operator-side.
- **Per-campaign vs. global ban scope.** Phase 1 ships campaign-scoped bans (the GM bans against their own campaign; the audit row records `scope=campaign:<id>`). Cloudflare itself doesn't have a per-campaign notion — every ban applies to the whole zone. That's a small leak in the abstraction we accept; the audit log distinguishes which GM banned for which reason. A future "global ban only" mode is filed for Phase 4 if needed.
- **Replacing the existing FastAPI auth.** Edge banning is a defense-in-depth layer, not a replacement.

---

## Open questions

- **Default ban mode: `block` or `challenge`?** Lean `block` (full 403 at the edge) — `challenge` (Cloudflare CAPTCHA) is a softer default but a determined attacker just solves the CAPTCHA. Operators can override via the `mode` body field on the ban endpoint.
- **Ban duration: indefinite or with expiry?** Cloudflare IP Access Rules don't have a native expiry — bans persist until removed. Phase 1 ships indefinite; if operator demand surfaces, Phase 4 could add a `expires_at` field that a periodic sweep cleans up.
- **Should the GM-facing UI also expose the unban path to non-GMs (e.g. a player banned by mistake can self-unban)?** No. Bans are GM action; if the GM bans a player by mistake the unban is a GM correction.
- **Per-zone vs. account-scoped token?** Default per-zone (smaller blast radius if token leaks). Account-scoped is filed as an opt-in for operators who run multiple zones (`CLOUDFLARE_API_SCOPE=account`).

---

## Test contract

**Phase 1:**

- `POST /api/campaign/<cid>/ban_ip` with valid IP + GM auth + feature configured → 200 + `{ok, rule_id, …}`. Wiremock receives a `POST` to `/zones/<id>/firewall/access_rules/rules` with the IP + block mode. `admin_audit_log` row exists with `action=cloudflare.ban_ip`, `target=<ip>`, `cloudflare_rule_id=<wiremock-returned-id>`.
- Same call when `SIMPLEVTT_CLOUDFLARE_BANNING_ENABLED` is unset → 503, no wiremock call, no audit row.
- Same call from a non-GM user → 403.
- Same call when wiremock returns 500 → 503 from `/ban_ip`, `admin_audit_log` row with `action=cloudflare.ban_failed`, `notes` carrying the upstream error.
- `POST /api/campaign/<cid>/unban_ip` with a known rule_id → 200 + audit row. Wiremock receives a `DELETE`.
- `GET /api/campaign/<cid>/edge_bans` returns the active wiremock-side rules + the audit-log history.

**Phase 2:**

- Compose-side smoke: bring up CrowdSec + the Cloudflare bouncer + the wiremock; replay a `demo_magic_link.verify_rejected` storm; assert the wiremock receives the ban call from the bouncer (not from SimpleVTT directly).

Tests live as `tests/harness/test_cloudflare_banning.py` and `tests/audit/test_admin_audit_log.py` for Phase 1; `tests/audit/test_crowdsec_bouncer.py` for Phase 2.

---

## Out-of-band cross-links

- [`demo-magic-link.md`](demo-magic-link.md) Phase 3 is hard-blocked on this plan's Phase 1 shipping.
- [`fail2ban-crowdsec-integration.md`](fail2ban-crowdsec-integration.md) Phase 2 (CrowdSec configs) composes with this plan's Phase 2 (CrowdSec → Cloudflare bouncer) to give operators a fully-automated detection-to-edge-ban path.
- The CLAUDE.md [Third-party APIs must be Docker Compose services](../../CLAUDE.md#third-party-apis-must-be-docker-compose-services) rule is what shapes the wiremock-in-compose decision.
