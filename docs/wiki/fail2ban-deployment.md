# fail2ban deployment guide

This guide walks an operator through enabling SimpleVTT's
out-of-the-box fail2ban integration: from `docker compose --profile
fail2ban up -d` to a verified ban policy that actually drops
banned traffic at the host firewall or the Cloudflare edge.

> **Background.** SimpleVTT emits canonical audit-log lines for
> every banning-relevant event (failed login, magic-link replay,
> API probe). fail2ban tails those lines and bans IPs that cross
> configurable thresholds. The architecture, threat model, and
> per-event line shape are documented in
> [`docs/plans/fail2ban-crowdsec-integration.md`](/wiki/doc/plan-fail2ban-crowdsec-integration).
> Read that first if you want the "why"; this page is the "how."

---

## At a glance

| Phase | Version | What you get |
|---|---|---|
| 4a | v2.469.0 | `audit_logs` shared volume + `RotatingFileHandler` tee from `simplevtt.audit` logger to `/var/log/simplevtt/audit.log`. |
| 4b | v2.470.0 | `fail2ban` service in `docker-compose.yml`, gated by `--profile fail2ban`. Image `crazymax/fail2ban:1.0.2`. |
| 4c | v2.471.0 | Env-templated jail thresholds (`FAIL2BAN_LOGIN_MAXRETRY`, `_FINDTIME`, `_BANTIME`, etc.). Rendered at container start by `render-jail.sh`. |
| 4d | v2.472.0 | Cloudflare bouncer action — bans land in the v2.430.0 Cloudflare access-rule list. No host privilege. |
| 4e | v2.473.0 | ipset bouncer action — bans land in host iptables via `ipset`. Requires `network_mode: host` + `cap_add: [NET_ADMIN]` via an opt-in compose override. |
| 4f | v2.475.0 | End-to-end smoke test that verifies the whole chain bans an IP after 6 failed logins. |
| 5 | v2.477.0 | `simplevtt-scanner` jail — bans IPs that probe many missing paths (404s) in a short window. On by default. |
| — | v2.481.0 | `simplevtt-flood` jail — bans IPs that hammer the app with a high request volume regardless of outcome. **Opt-in** (pairs with v2.480.0 per-request logging). |

---

## Step 1 — pick your ban action

The default `--profile fail2ban` stack starts with the image's
in-container iptables target. That works for testing but doesn't
reach the host firewall. For production, pick one:

- **Cloudflare bouncer (recommended for sites behind Cloudflare).**
  Zero host privilege. Bans land at the global edge.
- **ipset bouncer (for sites NOT behind Cloudflare).** Requires
  `network_mode: host` + `cap_add: [NET_ADMIN]`. Drops banned
  traffic at the host's iptables.
- **Default in-container iptables (for testing only).** Doesn't
  reach the host. Useful for verifying wiring before going
  production.

You can run both Cloudflare AND ipset by space-separating them in
`FAIL2BAN_ACTION` (`cloudflare-bouncer ipset-bouncer`).

---

## Step 2 — copy `.env.example` to `.env` and tune

The env file ships with sensible defaults for a small public deploy:

```
FAIL2BAN_LOGIN_MAXRETRY=5
FAIL2BAN_LOGIN_FINDTIME=5m
FAIL2BAN_LOGIN_BANTIME=1h
FAIL2BAN_MAGIC_LINK_REPLAY_BANTIME=24h
FAIL2BAN_API_PROBE_MAXRETRY=20
FAIL2BAN_DEFAULT_BANTIME=1h
FAIL2BAN_ACTION=%(action_)s
```

**Bigger deploys.** A site fielding lots of legitimate cross-NAT
traffic (corporate, university, library) wants higher
`FAIL2BAN_LOGIN_MAXRETRY` (10–15) and shorter `FAIL2BAN_LOGIN_BANTIME`
(15m–30m). The defaults err strict to protect smaller deploys
that can't afford the false-positive cost of letting bots
through.

**Replay-bantime is 24 h on purpose.** Magic-link replay is
never legitimate — a stolen token landing twice is a smoking
gun. The 24 h ban is per-event, not per-N-events.

---

## Step 3 — turn on a real ban action

### Option A: Cloudflare bouncer (no host privilege)

You need the v2.430.0 Cloudflare integration env vars:

```
CLOUDFLARE_API_TOKEN=<your token, scoped to Zone:Firewall:Edit>
CLOUDFLARE_ZONE_ID=<your zone id>
CLOUDFLARE_API_BASE_URL=https://api.cloudflare.com/client/v4
```

Then in the same `.env`:

```
FAIL2BAN_ACTION=cloudflare-bouncer
```

Reuses the same token + zone as the in-app GM ban button. If
you've already configured that, you're done.

### Option B: ipset bouncer (privileged opt-in)

Set in `.env`:

```
FAIL2BAN_ACTION=ipset-bouncer
```

Then layer the privileged compose override on top of the main
file when bringing up the profile:

```bash
docker compose \
  -f docker-compose.yml \
  -f docs/integrations/fail2ban/docker-compose.fail2ban-ipset.yml \
  --profile fail2ban up -d
```

The override adds `network_mode: host` + `cap_add: [NET_ADMIN]`
to the fail2ban service ONLY. The base compose is unchanged.

> **Safety warning.** `network_mode: host` removes container
> network isolation; the fail2ban process can read + mutate the
> host's iptables. The narrowest cap (`NET_ADMIN`) is added —
> NOT `--privileged`. But the elevation is real. For shared-
> tenancy or strict-isolation hosts, prefer Cloudflare bouncer
> instead.

---

## Step 4 — bring up the profile

```bash
docker compose --profile fail2ban up -d
```

This starts the existing app + db + the new `fail2ban` service.
The base `docker compose up` flow is unchanged — the profile gate
keeps fail2ban dormant for default deploys.

---

## Step 5 — verify it's working

```bash
docker compose --profile fail2ban exec fail2ban \
    fail2ban-client status simplevtt-auth
```

You should see:

```
Status for the jail: simplevtt-auth
|- Filter
|  |- Currently failed: 0
|  |- Total failed:     0
|  `- File list:        /var/log/simplevtt/audit.log
`- Actions
   |- Currently banned: 0
   |- Total banned:     0
   `- Banned IP list:
```

If you see this, the jail is loaded against the right log file.
If you see "Sorry but the jail 'simplevtt-auth' does not exist" —
the v2.471.0 render-jail.sh hasn't run; check
`docker compose --profile fail2ban logs fail2ban` for the
`[render-jail.sh] rendered N jail` line.

### Confirm thresholds match `.env`

```bash
docker compose --profile fail2ban exec fail2ban \
    fail2ban-client get simplevtt-auth maxretry
# → 5
docker compose --profile fail2ban exec fail2ban \
    fail2ban-client get simplevtt-auth findtime
# → 300
docker compose --profile fail2ban exec fail2ban \
    fail2ban-client get simplevtt-auth bantime
# → 3600
```

A mismatch means render-jail.sh dropped a value — check the
`[render-jail.sh]` log line for "rendered" count and the env
allowlist.

### Run the end-to-end smoke test

The v2.475.0 harness exercises the full chain (login → audit log
→ fail2ban tail → ban):

```bash
python3 -m pytest tests/harness/test_fail2ban_end_to_end.py -v
```

Both tests should pass within ~10 s. If they skip with "fail2ban
container not running," you didn't bring up the profile in
Step 4.

---

## Step 6 — production checklist

- [ ] **`TRUSTED_PROXY_HOPS=1` if you're behind a reverse proxy.**
  Without this, fail2ban sees the proxy's IP on every event and
  bans your own infrastructure. Set to the number of trusted
  proxies between the public internet and your app container
  (typically 1 for nginx/Traefik/Cloudflare, 2 for chained
  setups).
- [ ] **Pick `FAIL2BAN_ACTION`.** Default `%(action_)s` is
  cosmetic-only.
- [ ] **Persist `fail2ban_data` volume.** It's declared at the
  top of `docker-compose.yml`; a `docker compose down -v` wipes
  your ban DB. For production deploys, don't pass `-v` on
  shutdown.
- [ ] **Review the threat model.** Read
  [the plan doc](/wiki/doc/plan-fail2ban-crowdsec-integration)'s
  "Threat model" section so you know what fail2ban is and isn't
  defending against.
- [ ] **Monitor via the existing logs.** fail2ban logs to STDOUT
  via `F2B_LOG_TARGET=STDOUT`; `docker compose --profile fail2ban
  logs -f fail2ban` shows ban decisions in real time.

---

## Common pitfalls

### Container restart-looping on first boot

Check the logs:

```bash
docker compose --profile fail2ban logs --tail 50 fail2ban
```

- **`envsubst: not found`** — you're on a SimpleVTT version
  before v2.473.1. Upgrade.
- **`File exists: /etc/fail2ban/jail.d`** — same. v2.473.1 fixes
  it.
- **`/scripts/render-jail.sh: not found`** — the bind mount
  failed; verify the file at `docs/integrations/fail2ban/scripts/
  render-jail.sh` exists in your checkout.

### "Currently banned: 0" after many failed logins

- **Check the source IP.** If you're testing from inside docker
  on the same host, the connection IP may be `127.0.0.1` and
  fail2ban explicitly skips localhost. Test from a different
  network or set `TRUSTED_PROXY_HOPS=1` and use
  `X-Forwarded-For: <test-ip>`.
- **Threshold not met.** Default is 5 failures in 5 minutes.
  Fire 6+ in tight succession.
- **Filter doesn't match.** Run
  `fail2ban-regex /var/log/simplevtt/audit.log
  /etc/fail2ban/filter.d/simplevtt-auth.conf` inside the
  container. Non-zero match count means the wiring is intact;
  zero means the audit-log line shape changed and the filter
  needs an update.

### `TRUSTED_PROXY_HOPS=0` with Cloudflare in front

You ban your own Cloudflare IPs. Symptom: bans land for IPs you
recognize as 162.158.x or 104.20.x (Cloudflare's IP ranges). Fix:

```
TRUSTED_PROXY_HOPS=1
```

Then restart the app container. fail2ban will start banning the
real client IPs (which Cloudflare passes in `CF-Connecting-IP` /
`X-Forwarded-For`).

---

## Optional: the request-flood jail (`simplevtt-flood`)

The `simplevtt-auth` and `simplevtt-scanner` jails ban on *failures*
— failed logins and 404 probes. Neither catches an IP that hammers
**valid** endpoints at high speed (credential-free scraping, a
runaway script, a layer-7 flood). The `simplevtt-flood` jail
(v2.481.0) closes that gap by banning on raw request *rate*,
counting every request regardless of status.

It rides the opt-in per-request `visitor.request` audit event
(v2.480.0), so arming it is a **two-switch** operation — both must
be on:

```bash
# 1. App side — emit a visitor.request audit line per request.
VISITOR_REQUEST_LOG_ENABLED=true
TRUSTED_PROXY_HOPS=1            # required: record the real client IP,
                               # not the tunnel/proxy's internal one

# 2. fail2ban side — arm the flood jail.
FAIL2BAN_FLOOD_ENABLED=true
FAIL2BAN_FLOOD_MAXRETRY=300    # ban after 300 requests…
FAIL2BAN_FLOOD_FINDTIME=1m     # …within 1 minute…
FAIL2BAN_FLOOD_BANTIME=1h      # …for 1 hour.
```

Then `docker compose up -d app` (to pick up the app-side flag) and
`docker compose --profile fail2ban up -d fail2ban` (to render the
jail with `enabled = true`).

**Why it's OFF by default.** Per-request logging is high-volume and
privacy-sensitive (see the [privacy policy](/wiki/privacy)), and a
mis-tuned rate ceiling can ban legitimate heavy users. Both
switches default OFF so an operator turns them on deliberately, as a
pair. With `VISITOR_REQUEST_LOG_ENABLED=false`, no `visitor.request`
lines exist and the jail matches nothing even if armed.

**Tuning the ceiling.** A normal page load fires a few dozen
requests (HTML + CSS/JS assets + token polls + WS upgrade). 300/min
sits well above human browsing but trips a scripted hammer. If you
serve image-heavy maps or run aggressive client polling, watch
`fail2ban-client status simplevtt-flood` for false positives after
enabling and raise `FAIL2BAN_FLOOD_MAXRETRY` if your real users trip
it.

**Verify:**

```bash
docker compose exec fail2ban fail2ban-client status simplevtt-flood
```

If you see `Sorry but the jail 'simplevtt-flood' does not exist`,
`FAIL2BAN_FLOOD_ENABLED` rendered as `false` — check your `.env` and
the `[render-jail.sh] rendered N jail` startup log line.

---

## Where to look next

- The plan doc: [`docs/plans/fail2ban-crowdsec-integration.md`](/wiki/doc/plan-fail2ban-crowdsec-integration)
  has the full architecture, threat model, and per-event line
  format.
- CrowdSec sibling: SimpleVTT also ships first-class CrowdSec
  configs (`docs/integrations/crowdsec/`). The same audit log
  feeds both engines; you can run either or both.
- Cloudflare integration: [v2.430.0 cloudflare-edge-banning](/wiki/doc/plan-cloudflare-edge-banning)
  has the in-app side of the same ban list.
