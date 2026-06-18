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

Status: **Phase 2 unstarted.** Reference configs (parsers +
scenarios) and a compose-side smoke test land with the next ship
on the integration plan.

### Cloudflare — edge banning

Status: **Phase 1 unstarted.** See
[`docs/plans/cloudflare-edge-banning.md`](../plans/cloudflare-edge-banning.md).

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

Planned events (per
[`docs/plans/fail2ban-crowdsec-integration.md`](../plans/fail2ban-crowdsec-integration.md)
and
[`docs/plans/demo-magic-link.md`](../plans/demo-magic-link.md)):

- `demo_magic_link.mint_ok` / `verify_ok` / `verify_rejected`
- `api.unauthorized` / `api.forbidden`
- `ws.connect_rejected`
- `cloudflare.ban_ok` / `ban_failed` / `unban_ok` / `unban_failed`
