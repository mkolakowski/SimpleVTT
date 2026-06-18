# SimpleVTT integrations

Reference configs and operator how-tos for wiring SimpleVTT into
third-party security and observability tools. Each subdirectory
holds drop-in configuration the operator copies into
`/etc/<tool>/`; the canonical log-line format the configs target is
defined in
[`docs/plans/fail2ban-crowdsec-integration.md`](../plans/fail2ban-crowdsec-integration.md).

## Available integrations

### fail2ban — IP banning from log-pattern matches

Status: **Phase 1 shipped (v2.424.0).** Detects auth failures
(`auth.login_failed` + `auth.signup_failed`) and bans the source
IP for 1 hour after 5 failures in 5 minutes.

Files:

- [`fail2ban/filter.d/simplevtt-auth.conf`](fail2ban/filter.d/simplevtt-auth.conf) — regex filter that matches the canonical audit-log line shape.
- [`fail2ban/jail.d/simplevtt.conf`](fail2ban/jail.d/simplevtt.conf) — jail that wires the filter to a ban action. Tune `maxretry` / `findtime` / `bantime` per your threat model.

Install:

```bash
sudo cp docs/integrations/fail2ban/filter.d/simplevtt-auth.conf /etc/fail2ban/filter.d/
sudo cp docs/integrations/fail2ban/jail.d/simplevtt.conf       /etc/fail2ban/jail.d/
# Edit logpath in /etc/fail2ban/jail.d/simplevtt.conf to point at
# your SimpleVTT log source.
sudo fail2ban-client reload
```

Verify it's running:

```bash
sudo fail2ban-client status simplevtt-auth
```

### CrowdSec — community-signal banning

Status: **Phase 2 shipped (v2.429.0).** Drop-in parser + 5 scenarios
under [`crowdsec/`](crowdsec/) cover credential stuffing, magic-link
bruteforce + replay, API-surface probing, and admin mint flooding.
Plus a compose override template at
[`crowdsec/docker-compose.crowdsec.yml`](crowdsec/docker-compose.crowdsec.yml)
the operator can use to bring up CrowdSec alongside SimpleVTT.

Files:

- [`crowdsec/parsers/s01-parse/simplevtt.yaml`](crowdsec/parsers/s01-parse/simplevtt.yaml) — grok parser matching the canonical audit-log line shape.
- [`crowdsec/scenarios/simplevtt-auth-bruteforce.yaml`](crowdsec/scenarios/simplevtt-auth-bruteforce.yaml) — 5× `auth.login_failed` in 5 min → 5-minute ban.
- [`crowdsec/scenarios/simplevtt-magic-link-bruteforce.yaml`](crowdsec/scenarios/simplevtt-magic-link-bruteforce.yaml) — 5× signature-rejected `verify_rejected` in 5 min → 5-minute ban.
- [`crowdsec/scenarios/simplevtt-magic-link-replay.yaml`](crowdsec/scenarios/simplevtt-magic-link-replay.yaml) — 1× replay → 24-hour ban (never legitimate).
- [`crowdsec/scenarios/simplevtt-api-probe.yaml`](crowdsec/scenarios/simplevtt-api-probe.yaml) — 10× 401/403 in 10 min → 5-minute ban.
- [`crowdsec/scenarios/simplevtt-admin-anomaly.yaml`](crowdsec/scenarios/simplevtt-admin-anomaly.yaml) — 10× `mint_ok` in 5 min → 1-hour ban (compromised admin signal).
- [`crowdsec/docker-compose.crowdsec.yml`](crowdsec/docker-compose.crowdsec.yml) — operator-side override; brings up CrowdSec with the shipped parser + scenarios mounted in.

See [`crowdsec/README.md`](crowdsec/README.md) for the install how-to
+ how to wire the CrowdSec → Cloudflare bouncer for edge enforcement.

### Cloudflare — edge banning

Status: **Phase 1 shipped (v2.427.0).** GM admins can ban IPs at the
Cloudflare edge via the `/admin` page. Every ban + unban writes a row
to the `admin_audit_log` table.

Files:

- [`cloudflare/mock/mappings/`](cloudflare/mock/) — wiremock stub
  responses for dev + integration testing. Documented in
  [`cloudflare/mock/README.md`](cloudflare/mock/README.md).

Configure (in `.env`):

```env
CLOUDFLARE_API_TOKEN=<scoped: Zone:Access Rules:Edit only>
CLOUDFLARE_ZONE_ID=<the zone for your SimpleVTT hostname>
SIMPLEVTT_CLOUDFLARE_BANNING_ENABLED=true
```

The UI section on `/admin` lights up when both the client config and
the `_ENABLED` gate are set. See
[`docs/plans/cloudflare-edge-banning.md`](../plans/cloudflare-edge-banning.md)
for the threat model + roadmap.

---

## The canonical log-line format

Every banning-relevant event flows through `app/audit_log.py`'s
`audit()` helper and lands as a single line in the standard
process log:

```
<event_tag> ip=<value> ua="<value>" [<key>=<value> ...]
```

- `event_tag` is a fixed `subsystem.event` string (e.g.
  `auth.login_failed`, `demo_magic_link.verify_rejected`).
- `ip` and `ua` are required on every event.
- Additional `key=value` pairs follow. Values with whitespace or
  special chars are double-quoted; bare identifiers pass through
  unquoted.

**X-Forwarded-For trust:** the `audit()` helper never trusts the
header by default. Set `TRUSTED_PROXY_HOPS=N` in the environment
to opt into trusting the last N hops of the header chain — set
this only when a known reverse proxy sits in front of the app.

### Currently emitted events (v2.424.0)

| Event | Severity | Source |
|---|---|---|
| `auth.login_ok` | INFO | Successful local-password login. |
| `auth.login_failed` | WARNING | Bad credentials at `/login`. |
| `auth.signup_failed` | WARNING | Registration error (`reason=email_taken` / `password_too_short`). |
| `api.unauthorized` | WARNING | Protected endpoint hit without auth (excludes the legitimate HTML browser-bounce to `/login`). `path=…` carries the requested path. |
| `api.forbidden` | WARNING | Logged-in user hit an endpoint they're not authorised for (e.g. non-admin user hitting `/admin`). Probable privilege-escalation probe. |
| `demo_magic_link.mint_ok` | INFO | Admin minted a demo magic-link. `sub=…` + `admin_id=…` for audit. |
| `demo_magic_link.verify_ok` | INFO | Demo magic-link verified + consumed. `sub=…` + `jti=…` + `user_id=…`. |
| `demo_magic_link.verify_rejected` | WARNING | `reason=signature` / `expired` / `payload` / `replay` / `unknown_sub` / `user_missing` / `missing_token`. `reason=replay` is "ban immediately" — never legitimate. |

| `cloudflare.ban_ok` | INFO | Edge-ban succeeded (v2.427.0). `ip_target=…` + `actor_id=…` + `rule_id=…`. |
| `cloudflare.ban_failed` | WARNING | Edge-ban failed (v2.427.0). `reason=connection|api_error` + `upstream_status=…` when applicable. |
| `cloudflare.unban_ok` | INFO | Edge-unban succeeded (v2.427.0). |
| `cloudflare.unban_failed` | WARNING | Edge-unban failed (v2.427.0). |

Planned events (per
[`docs/plans/fail2ban-crowdsec-integration.md`](../plans/fail2ban-crowdsec-integration.md)):

- `ws.connect_rejected`
