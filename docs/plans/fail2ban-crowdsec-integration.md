# fail2ban / CrowdSec log integration — Design Plan

> **Status:** ✅ Phase 1 + Phase 2 shipped (v2.426.0 + v2.429.0) — emission module + auth canonical events + API-surface 401/403 events + demo_magic_link.* events + cloudflare.* events + reference fail2ban configs covering all 8 event tags + CrowdSec parser + 5 reference scenarios + operator compose override template. Only the wiki-surface for `docs/integrations/README.md` and the compose-side smoke test (Phase 2B, gated on Docker Hub image reliability) remain filed.
> **Tracked in:** [`TODO.md`](../../TODO.md) → Manually Added → "fail2ban / CrowdSec log integration out of the box".
> **Sibling plans:**
> - [`demo-magic-link.md`](demo-magic-link.md) — defines half the consumer side of this contract (the `demo_magic_link.*` log lines).
> - The Cloudflare edge-banning TODO in [`TODO.md`](../../TODO.md#manually-added) — the in-app sibling for ban *enforcement*; this plan is about *detection*.

---

## Goal

Make SimpleVTT directly drop-in for the two most common open-source log-based IP-banning engines: **fail2ban** (the Debian-classic, regex-on-tail) and **CrowdSec** (the newer scenario-based engine with a community signal-sharing layer). An operator running SimpleVTT on a public box should be able to pick whichever engine they prefer and have a working ban policy after **copying two files into `/etc/<engine>/`** — no custom regex authoring, no log-format archaeology.

The deliverable is three things in one feature:

1. **A canonical structured log-line format** for every event a banning engine cares about — auth failures, demo-link replay, mint-from-non-admin, repeated 401/403, signup abuse if/when signups land. The format is fixed and stable so a single regex parses both engines' filter sets.
2. **Reference configs in-repo** under `docs/integrations/fail2ban/` and `docs/integrations/crowdsec/` that the operator copies into `/etc/<engine>/`. Both target the same canonical log lines so picking one engine over the other is a deployment choice, not a SimpleVTT change.
3. **An end-to-end smoke test** that spins up a CrowdSec container against the dev compose stack, replays the synthetic event stream, and asserts the canonical scenarios fire. (fail2ban's filter is regex-shaped enough that the unit test can exercise it directly; CrowdSec needs the container to validate the YAML pipeline.)

**Out of scope: actually banning IPs in SimpleVTT.** That's the [Cloudflare edge-banning sibling TODO](../../TODO.md#manually-added). This plan is strictly **detection** — emit the log lines, ship the configs, prove the engines fire. *Enforcement* happens at the firewall (fail2ban → iptables) or the edge (CrowdSec → Cloudflare bouncer / nftables bouncer / etc.) and is the operator's choice.

---

## Threat model

What we're surfacing for the banning engine to ban, in roughly decreasing severity:

1. **Credential-stuffing.** Attacker tries a list of leaked password pairs against `/login`. **Signal:** repeated `auth.login_failed` from one IP — fail2ban: 5×/5min, ban 1h. CrowdSec: standard `crowdsec/http-bf` scenario shape.
2. **Demo-magic-link enumeration.** Attacker rapid-fires `?login=<guess>` hoping to land a valid jti. **Signal:** repeated `demo_magic_link.verify_rejected reason=signature` from one IP — fail2ban: 5×/5min, ban 1h. Pairs with [`demo-magic-link.md`](demo-magic-link.md)'s threat model item #6.
3. **Demo-magic-link replay.** Attacker harvests a token from a logged proxy access log or screenshot and tries to use it past the single-use mark. **Signal:** **any** `demo_magic_link.verify_rejected reason=replay` is suspicious — fail2ban: 1×/1min, ban 24h. Replay is never legitimate; the consumed-jti table is the trusted side.
4. **Mint endpoint abuse.** Compromised admin (or a stolen admin cookie) tries to mint a flood of magic-links. **Signal:** unusual rate of `demo_magic_link.mint_ok` from a single admin id — CrowdSec scenario (rate-based, no fail2ban analog because fail2ban doesn't have admin-id grouping).
5. **API surface 401/403 hammering.** Attacker probes for unguarded endpoints. **Signal:** repeated `api.unauthorized` or `api.forbidden` from one IP across more than 5 distinct paths — fail2ban: 20×/5min, ban 1h. The path-diversity check separates "probe" from "single broken client retry-storming."
6. **Signup-form abuse** (when signups ship — currently optional via `ALLOW_SELF_SIGNUP`). **Signal:** repeated `auth.signup_failed` (or signup_throttled) — fail2ban: 5×/5min, ban 4h.
7. **WS connection storms.** Attacker opens hundreds of WS connections to amplify a broadcast-side DoS. **Signal:** repeated `ws.connect_rejected` or unusual rate of `ws.connect_ok` from one IP. **Filed as Phase 2** — requires a WS-side rate-limit hook that doesn't exist yet.

What we're **not** trying to ban from log signals:

- **Application bugs** (500s, internal errors) — those are an observability concern, not a security one. Logged separately as `app.error`, **never** a banning trigger.
- **Slow legitimate users on shared NAT** (multiple visitors behind one public IP). The ban thresholds are tuned to swallow burst-rate noise; the bigger defense is the Cloudflare integration which can ban at the IP+UA tuple. Filed as a Phase 2 note.
- **Account takeover with valid credentials.** A successful login from a new device isn't a banning signal (no false-positive-tolerable threshold). That's a Phase 3+ "suspicious login email" feature, not this plan.

---

## Canonical log-line format

Every banning-relevant event emits a single line at `INFO` (success path) or `WARNING` (rejection path), formatted as:

```
<event_tag> <key>=<value> [<key>=<value> ...]
```

**Rules:**

- `event_tag` is a fixed `subsystem.event` string. Lowercase, dot-separated, no spaces. Examples: `auth.login_failed`, `demo_magic_link.verify_rejected`, `api.unauthorized`, `ws.connect_rejected`.
- Keys are bare identifiers; values are either bare tokens (for short alphanumerics) or double-quoted strings (for anything with whitespace / unicode / quoting). The parser side handles both.
- **`ip`** and **`ua`** are required on every event. `ip` is the source IP (trusts `X-Forwarded-For` only when a known reverse-proxy header is set — operator wires that through env vars, **not** trusted by default). `ua` is the User-Agent string, double-quoted.
- Timestamp + level come from the standard Python logger, **not** from the event format — both engines parse the standard `%(asctime)s` prefix the existing `app/logging.py` config produces.

**Canonical events shipped in Phase 1:**

| Event | Severity | Required keys | Notes |
|---|---|---|---|
| `auth.login_ok` | INFO | `ip`, `ua`, `user_id` | Success — only logged, not a banning trigger; useful for CrowdSec's allowlist-after-success pattern. |
| `auth.login_failed` | WARNING | `ip`, `ua`, `username` (the typed value, **never** the actual user record's email if no match) | Credential-stuffing primary signal. |
| `auth.signup_failed` | WARNING | `ip`, `ua`, `reason` (`email_taken` / `invalid` / `disabled`) | Only when signups are enabled. |
| `demo_magic_link.mint_ok` | INFO | `ip`, `ua`, `sub`, `jti`, `admin_id` | Per [`demo-magic-link.md`](demo-magic-link.md). Logged for audit + CrowdSec admin-anomaly scenario. |
| `demo_magic_link.verify_ok` | INFO | `ip`, `ua`, `sub`, `jti` | Per `demo-magic-link.md`. |
| `demo_magic_link.verify_rejected` | WARNING | `ip`, `ua`, `reason` (`signature`/`expired`/`replay`/`gate_off`/`unknown_sub`) | Per `demo-magic-link.md`. |
| `api.unauthorized` | WARNING | `ip`, `ua`, `path` | Bare 401 on a protected endpoint. |
| `api.forbidden` | WARNING | `ip`, `ua`, `path` | Bare 403. Sometimes legitimate (CSRF mismatch on first request from a new tab), so the threshold is lenient. |
| `ws.connect_rejected` | WARNING | `ip`, `ua`, `reason` | **Phase 2** — needs a WS-side rate-limit hook that doesn't exist yet. |

**Parser regex (the contract both engines share):**

```
^(?<ts>\S+\s\S+)\s+(?<lvl>\S+)\s+(?<event>[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*)\s+(?<kvs>.*)$
```

Where `(?<kvs>...)` is a key=value tail the engine-specific filter further parses with `\bip=(?<ip>\S+)\b` etc. fail2ban and CrowdSec both have native key=value parsers.

---

## Architecture

### Emission layer

A thin `app/audit_log.py` module (new) wraps the standard `logging.getLogger("simplevtt.audit")` with a typed helper:

```python
def audit(event: str, *, level: int = logging.INFO, request: Request | None = None, **kv: Any) -> None:
    """Emit a canonical audit-log line.

    event   "auth.login_failed", "demo_magic_link.verify_ok", etc.
    request if provided, ip + ua are extracted from it (X-Forwarded-For
            handling lives here in one place, not at every call site)
    kv      arbitrary key=value pairs — strings are quote-escaped if
            they contain whitespace; ints/booleans go bare
    """
```

Call sites in `app/auth.py`, `app/routes/admin_routes.py`, the future `app/routes/demo_magic_link_routes.py`, etc. drop the audit call alongside (or instead of) their existing `logger.info(...)` lines. Phase 1 plumbs the events listed in the table above; later phases extend.

The module also owns the **header-trust config** for X-Forwarded-For: an env var `TRUSTED_PROXY_HOPS=N` (default 0 = don't trust the header) so an operator running behind a known reverse proxy gets the real client IP, not the proxy's. This matches Starlette's existing `ProxyHeadersMiddleware` behavior but keeps the audit-side decision in one place.

### Log destination

The existing `app/logging.py` config already produces a single text log on stdout that compose captures. Operators forward it to:

- **fail2ban side:** `journalctl -u docker.service` or a host-side `tail -F <compose log path>`. Reference jail config below.
- **CrowdSec side:** the CrowdSec datasource targets the same log file, or grabs the docker-compose `simplevtt-app` container's stdout via the Docker plugin.

**Phase 2** may add an optional **JSON-line side-channel** under a separate logger (`simplevtt.audit.json`) for operators who prefer structured logging (Datadog / Loki / Vector). Not required for Phase 1 — fail2ban and CrowdSec both prefer the line format.

### Reference configs

Ship under `docs/integrations/`:

```
docs/integrations/
├── README.md                              # which engine for which deployment
├── fail2ban/
│   ├── filter.d/
│   │   ├── simplevtt-auth.conf            # auth.login_failed + auth.signup_failed
│   │   ├── simplevtt-magic-link.conf      # demo_magic_link.verify_rejected
│   │   └── simplevtt-api.conf             # api.unauthorized + api.forbidden
│   └── jail.d/
│       └── simplevtt.conf                 # ties the three filters to ban actions
└── crowdsec/
    ├── parsers/
    │   └── s01-parse/
    │       └── simplevtt.yaml             # event_tag + key=value → typed event
    └── scenarios/
        ├── simplevtt-auth-bf.yaml         # credential-stuffing scenario
        ├── simplevtt-magic-link-bf.yaml   # token enumeration scenario
        ├── simplevtt-magic-link-replay.yaml # 1× replay = 24h ban
        ├── simplevtt-api-probe.yaml       # 401/403 across multiple paths
        └── simplevtt-admin-anomaly.yaml   # unusual mint_ok rate per admin
```

Each config block carries a header comment with a short rationale + the threshold + the recommended ban action, so an operator reading the config can change it without re-reading this plan.

### Validation

**Phase 1** ships a unit-test-style validation:

- `tests/audit/test_audit_log.py` — unit tests on the emission module. Verify each canonical event renders to a line that the parser regex matches and the key=value tail extracts cleanly.
- `tests/audit/test_fail2ban_filters.py` — load each `filter.d/*.conf` file, generate synthetic log lines for the events the filter is supposed to match (and counter-examples it shouldn't), assert the regex matches/doesn't.

**Phase 2** adds the compose-side smoke test:

- A new `crowdsec-test` service in `docker-compose.test.yml` (a compose override file, not the main compose). It runs the official `crowdsecurity/crowdsec:latest` image with the reference configs mounted in.
- A test fixture replays a synthetic event stream into the app container's log, then queries `cscli decisions list` to assert the scenarios fired.
- Pairs with [`demo-magic-link.md`](demo-magic-link.md) Phase 2 — the demo-magic-link plan may share this test infrastructure.

---

## Phase plan

### Phase 1 — Emission + canonical events + fail2ban configs (v2.424.0 — ✅ initial drop shipped)

1. ✅ **v2.424.0** — New `app/audit_log.py` with the `audit()` helper + `TRUSTED_PROXY_HOPS` env var (default 0 = never trust `X-Forwarded-For`).
2. ✅ **v2.424.0** — Plumbed the audit calls at `/login` (`auth.login_ok` + `auth.login_failed`) and `/register` (`auth.signup_failed` with `reason=password_too_short` / `reason=email_taken`).
3. ✅ **v2.424.0** — Reference fail2ban configs landed at `docs/integrations/fail2ban/filter.d/simplevtt-auth.conf` + `docs/integrations/fail2ban/jail.d/simplevtt.conf` + `docs/integrations/README.md` operator how-to.
4. ✅ **v2.424.0** — Unit tests for the emission module at `tests/harness/test_audit_log.py` (11 tests covering line shape, XFF trust toggling, value quoting, env-var fallback).
5. ✅ **v2.426.0** — API surface events (`api.unauthorized` + `api.forbidden`) plumbed into the global `_auth_redirect_handler`. Legitimate browser-bounce path (HTML request to guarded page → 303 to `/login`) is explicitly excluded so the log doesn't drown in normal navigation noise. fail2ban filter at `docs/integrations/fail2ban/filter.d/simplevtt-auth.conf` extended to cover the new event tags + the `demo_magic_link.verify_rejected` family. 3 new harness tests at `tests/harness/test_api_audit_emission.py`.
6. 🟠 **Filed for follow-up** — Wiki surfacing for `docs/integrations/README.md`. Skipped in v2.424.0 to keep the commit focused; the plan-doc cross-link is the only reachability path today.

### Phase 2 — CrowdSec configs + compose-side smoke test (v2.429.0 — ✅ configs shipped)

1. ✅ **v2.429.0** — CrowdSec parser at `docs/integrations/crowdsec/parsers/s01-parse/simplevtt.yaml` parses the canonical audit-log line shape, emits `evt.Meta.log_type = simplevtt-audit` and `evt.Parsed.evt_subtype = <subsystem.event>`.
2. ✅ **v2.429.0** — Five scenarios at `docs/integrations/crowdsec/scenarios/`: auth-bruteforce, magic-link-bruteforce, magic-link-replay (trigger / always-ban), api-probe, admin-mint-flood. Each is namespaced `simplevtt/<slug>`, carries `labels.service=simplevtt` + `labels.remediation=true`, and references the parser's `simplevtt-audit` log_type to scope correctly.
3. ✅ **v2.429.0** — Operator-side `docs/integrations/crowdsec/docker-compose.crowdsec.yml` override brings up CrowdSec with the shipped configs mounted in. Templated for the standard "logs forwarded to a host file" pattern.
4. ✅ **v2.429.0** — `docs/integrations/crowdsec/README.md` covers install, scenario table, wiring the CrowdSec → Cloudflare bouncer, and a manual smoke test using `cscli explain --type simplevtt-audit`. The `docs/integrations/README.md` index table also distinguishes fail2ban (small host + iptables) from CrowdSec (community signal + Cloudflare bouncer).
5. ✅ **v2.429.0** — YAML syntax + schema validation at `tests/harness/test_crowdsec_configs.py` (46 parametrized tests across 5 scenarios + 1 parser + README cross-link). Catches typo'd filter expressions, missing required keys, mis-namespaced scenarios, scenarios that forgot the `simplevtt-audit` log_type filter (would silently fire on unrelated CrowdSec events), and a parser drift that dropped the `log_type` static.
6. 🟠 **Filed for Phase 2B** — Real CrowdSec container smoke test that replays synthetic events and asserts scenarios fire via `cscli decisions list`. Gated on the CrowdSec image being reliably available from Docker Hub (the v2.427.0 wiremock pull was hung indefinitely, so a CrowdSec pull may be too — the YAML validation test is the no-network-dependency stand-in).

### Phase 3 — Audit log JSON side-channel (v2.5x.2, optional)

1. Add a secondary logger `simplevtt.audit.json` that emits the same events as JSON lines.
2. Document Datadog / Loki / Vector pickup patterns in `docs/integrations/structured-logs.md`.
3. **Hard precondition: a real operator asks for it.** Filed as Phase 3 so the slot is there but not built on spec.

---

## Non-goals

- **In-app IP banning.** That's the [Cloudflare edge-banning sibling TODO](../../TODO.md#manually-added). This plan is detection; that plan is enforcement.
- **Account-takeover detection** (new-device login, geo-anomalies). Separate feature (probably "suspicious-login email").
- **WAF-style content filtering** (SQL-injection regex on request bodies). The existing FastAPI + SQLAlchemy stack handles that at the parameter-binding layer; log-based detection is a poor fit for it.
- **Banning known-bad bot UAs** (curl, python-requests). Too many legitimate test/automation use cases. Filed only as a CrowdSec scenario the operator can opt into, not a default.
- **Reinventing fail2ban / CrowdSec.** SimpleVTT emits events; the engines do the banning. Keep the layering clean.

---

## Open questions

- **What does `username` carry in `auth.login_failed` when the user doesn't exist?** Options: (a) the typed value (potential PII leak to logs), (b) `<unknown>` (loses the "credential-stuffing list contents" signal), (c) a hash. Default to (a) but document the hash option in `docs/integrations/README.md` for privacy-sensitive deployments.
- **Should we trust `X-Forwarded-For` by default?** No — it's spoofable. The `TRUSTED_PROXY_HOPS` env var is opt-in. Document this loudly in the operator README.
- **Should `auth.login_ok` also log the rough geo (country) for the allowlist-after-success pattern?** Probably not in Phase 1 — adds a geoip dependency. CrowdSec has its own geoip layer; let it do that work.
- **fail2ban or CrowdSec for the default recommended config?** Lean CrowdSec — newer, better-maintained, native Cloudflare bouncer integration that lines up with the sibling TODO. fail2ban stays first-class for operators who already run it.

---

## Test contract

**Phase 1:**

- `audit("auth.login_failed", request=req, username="alice")` emits a line that:
  - matches the canonical parser regex,
  - has `event == "auth.login_failed"`,
  - extracts `ip=<request IP>`, `ua=<request UA>`, `username=alice`.
- The fail2ban `simplevtt-auth.conf` regex matches the line and extracts the IP into the engine's `<HOST>` group.
- A counter-example (`auth.login_ok ...`) **doesn't** match the failed-auth filter.

**Phase 2:**

- The CrowdSec test compose, fed 6 synthetic `auth.login_failed` lines from one IP within 5min, lists a decision against that IP via `cscli decisions list`.
- The same stream with 5 lines (one under the threshold) yields no decision.
- A `demo_magic_link.verify_rejected reason=replay` from any IP yields a decision immediately (1×/1min threshold).

Tests live as `tests/audit/test_audit_log.py`, `tests/audit/test_fail2ban_filters.py` (Phase 1), and `tests/audit/test_crowdsec_pipeline.py` (Phase 2 — gated on the override compose being available).

---

## Out-of-band cross-links

- [`demo-magic-link.md`](demo-magic-link.md) defines half the consumer side of the canonical log lines.
- The [Cloudflare edge-banning TODO](../../TODO.md#manually-added) is the enforcement-side counterpart — CrowdSec already has a Cloudflare bouncer, so an operator who deploys both gets edge-level banning out of the canonical log lines for free.
- [`app/logging.py`](../../app/logging.py) is the existing logger config the new `audit_log.py` module rides on top of.
