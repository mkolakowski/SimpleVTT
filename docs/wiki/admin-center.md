# Admin Center

The **Admin Center** is a standalone, read-only operator dashboard
that runs on its own port (default **8015**) alongside the main app.
It surfaces everything SimpleVTT collects in one place: the canonical
audit log, derived traffic statistics, fail2ban ban state, and a
database data-inventory summary.

It is deliberately **read-only** — it never mutates game state. It
reuses the main app's Docker image but runs a separate ASGI app
(`app.admin_center.main:app`) and mounts the shared volumes
**read-only**.

> **Phase status.** Complete as of v2.485.0: audit-log viewer +
> traffic stats (v2.483.0), fail2ban ban panel (v2.484.0), and the
> database data-inventory summary (v2.485.0).

---

## At a glance

| Capability | Source | Status |
|---|---|---|
| Audit-event viewer (filterable) | `audit_logs` volume → `audit.log` | ✅ v2.483.0 |
| Traffic statistics (top IPs, paths, signal counters) | parsed audit log | ✅ v2.483.0 |
| fail2ban status + currently-banned IPs | `fail2ban_data` volume → `fail2ban.sqlite3` | ✅ v2.484.0 |
| Database data-inventory (users, campaigns, …) | app database (read-only) | ✅ v2.485.0 |

---

## Access

The Admin Center is **on by default** in `docker-compose.yml` and
comes up with `docker compose up -d`. Browse to:

```
http://localhost:8015
```

### Authentication

It is protected by **HTTP basic-auth**, independent of the main app's
session login. Two environment variables (set in `.env`):

| Env var | Default | Effect |
|---|---|---|
| `ADMIN_CENTER_USER` | `admin` | Basic-auth username. |
| `ADMIN_CENTER_PASS` | `changeme` | Basic-auth password. |
| `ADMIN_CENTER_PORT` | `8015` | Host + container port. |

> ⚠️ **Change the default password before exposing this off-host.**
> While `ADMIN_CENTER_PASS` is the shipped default, the dashboard
> renders a warning banner. The basic-auth check uses a constant-time
> comparison so it doesn't leak which half of the credential was
> wrong.

The `/healthz` endpoint is intentionally **unauthenticated** so the
docker-compose healthcheck can probe liveness without baking
credentials into the compose file. Every other path requires auth.

---

## Behind a Cloudflare Tunnel (or other reverse proxy)

The Admin Center works behind a Cloudflare Tunnel — including an
**external `cloudflared` you already run on another machine or
Cloudflare account**, not anything this project sets up. It's plain
HTTP + basic-auth, and Cloudflare passes the `Authorization` header
through untouched. Three things to get right:

### 1. Give the tunnel its own ingress rule

The rule that routes to the main app (`→ :8013`) does **not** cover
the Admin Center — add a second hostname pointing at port 8015. In
your `cloudflared` config:

```yaml
ingress:
  - hostname: vtt.example.com
    service: http://localhost:8013        # main app
  - hostname: vtt-admin.example.com
    service: http://localhost:8015        # admin center
  - service: http_status:404
```

- **`cloudflared` on the same host** as the Docker stack →
  `http://localhost:8015` works as shipped (compose publishes 8015 on
  all host interfaces).
- **`cloudflared` on a different machine/network** → it can't reach
  `localhost:8015`; target the Docker host's reachable IP
  (`http://<docker-host-ip>:8015`) and ensure that port is routable.
  Cleaner: run `cloudflared` on the same Docker network and target
  `http://admin-center:8015`, then stop publishing 8015 to the host
  at all.

### 2. Set `TRUSTED_PROXY_HOPS` for real visitor IPs

Through a tunnel the app sees every request coming **from the
`cloudflared` connector**, not the real client — the real IP rides in
`X-Forwarded-For` / `CF-Connecting-IP`. The audit log (and therefore
the Admin Center's traffic stats, top-IPs, and fail2ban panel) only
trusts that header when you set, on the **app** service:

```
TRUSTED_PROXY_HOPS=1
```

One `cloudflared` hop = `1`. Without it, every event records the
tunnel's internal IP and the IP stats are meaningless.

### 3. fail2ban *bans* need the edge action (and a matching zone)

The Admin Center **displays** whatever fail2ban records regardless.
But fail2ban's default action bans via the container's iptables,
which does nothing to tunnel traffic (packets arrive from
`cloudflared`, not the client). To actually block a tunnel visitor,
use the Cloudflare bouncer — and make sure its token is for the
**same Cloudflare zone your tunnel uses**:

```
FAIL2BAN_ACTION=cloudflare-bouncer
CLOUDFLARE_API_TOKEN=...      # SAME zone as the tunnel
CLOUDFLARE_ZONE_ID=...
```

If the token is for a different account/zone than the tunnel, the ban
is created but never applies. See
[fail2ban deployment](/wiki/fail2ban-deployment) for the bouncer
setup.

### Don't expose it unprotected

Publishing the Admin Center means publishing your audit log + banned
IPs + usernames. At minimum change `ADMIN_CENTER_PASS`. Strongly
better: put **Cloudflare Access (Zero Trust)** in front of the admin
hostname, or give it no public hostname at all and reach it over the
LAN, an SSH tunnel, or a `cloudflared access` session.

---

## What it shows (v2.483.0)

### Traffic signals

Named counters drawn from the audit log:

- Total audit events + unique source IPs.
- Failed logins (`auth.login_failed`), successful logins
  (`auth.login_ok`).
- `401` unauthorized, `403` forbidden, `404` not found.
- Visitor requests (`visitor.request`, only populated when
  per-request logging is enabled — see the
  [privacy policy](/wiki/privacy)).
- Data exports (`user.data_export`).

### Top source IPs / Top paths

The IPs that generate the most audit events, and the most-hit paths
(drawn from events that carry a `path` field — 404 probes, 401s,
visitor requests). Useful for spotting a scanner footprint before
fail2ban bans it.

### Recent events

A filterable table of the most recent parsed audit events — time,
level, event tag, source IP, and the remaining structured fields.
Filter by event tag via the dropdown.

### fail2ban — banned IPs (v2.484.0)

Reads fail2ban's own sqlite ban database (mounted read-only) and
shows the IPs that are **currently** banned — per jail, with when
they were banned and how long is left on the ban — plus the all-time
ban count and the active jail list. Expired-but-not-yet-purged bans
are filtered out; permanent bans (`bantime < 0`) are flagged.

When the `--profile fail2ban` stack isn't running, the shared volume
has no database and the panel shows an empty state rather than an
error.

> **Persistence note (v2.484.0).** The fail2ban service now mounts
> its `fail2ban_data` volume at `/data/db` (the crazymax image's
> actual `dbfile` location). Before v2.484.0 the volume mounted at
> the upstream-default `/var/lib/fail2ban`, so bans were silently
> lost on every container recreate. If you ran an earlier version,
> existing bans will repopulate as fail2ban re-bans offenders.

### Data inventory (v2.485.0)

A read-only row-count of the database — Users, Campaigns, Characters,
Campaign memberships, Dice rolls, Maps, Tokens, Encounters,
Playlists — plus an account breakdown (admins, disabled accounts,
Google-SSO vs password sign-ins). It is the by-the-numbers companion
to the [privacy policy](/wiki/privacy)'s data inventory: "here's what
we hold, by count." The admin-center service connects to the same
database as the main app (read-only use; it only runs `COUNT`
queries).

### JSON APIs

For scripting / scraping:

- `GET /api/stats` — the traffic-statistics roll-up.
- `GET /api/events?event=<prefix>&limit=<n>` — recent parsed events
  (filter by tag prefix, e.g. `auth.` or the exact `visitor.request`).
- `GET /api/fail2ban` — current ban state (jails + banned IPs).
- `GET /api/inventory` — database row counts.

All require basic-auth.

---

## How it reads the data

The Admin Center mounts the `audit_logs` named volume **read-only**
at `/var/log/simplevtt` and tails `audit.log` (the same file the main
app's `RotatingFileHandler` writes and fail2ban consumes). It parses
each canonical line — `<event> <key>=<value> …` — into structured
events. It holds no database of its own and never writes to the log.

Because the audit log rotates at 10 MB, the viewer tails up to the
last 5 000 lines; older events live in the rotated `audit.log.1` …
`audit.log.5` backups on the volume.

---

## Security notes

- **Read-only by design.** The service mounts shared volumes
  read-only and exposes no mutation endpoints. A compromise of the
  Admin Center can read collected data but cannot change game state,
  ban IPs, or delete records.
- **Separate credential.** Basic-auth is independent of the main app
  login, so you can hand someone audit-log visibility without giving
  them a game account, and rotate it independently.
- **Don't expose it publicly without a password change** and,
  ideally, a reverse proxy enforcing TLS. The dashboard surfaces IP
  addresses and usernames from the audit log.

---

## See also

- [Privacy Policy](/wiki/privacy) — the full inventory of what the
  audit log records and the operator knobs that control it.
- [fail2ban deployment](/wiki/fail2ban-deployment) — the banning
  pipeline whose status the Admin Center will surface.
