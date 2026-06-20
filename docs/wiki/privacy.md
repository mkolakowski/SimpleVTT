# Privacy: what SimpleVTT tracks

This page documents every piece of data SimpleVTT collects,
where it lives, how long it sticks around, and what an operator
can do to change those defaults.

> **This page is descriptive, not a legal privacy policy.** If
> you run a public SimpleVTT instance and your jurisdiction
> requires a published privacy notice (GDPR, CCPA, COPPA, …),
> use this page as a *starting point* — not a substitute for a
> policy reviewed by counsel.

---

## Quick map

| Bucket | What's in it | Where it lives | Retention |
|---|---|---|---|
| User accounts | email, password hash, display name, role | postgres | Indefinite (operator deletes) |
| Sessions | signed cookie with `user_id` | browser cookie | Browser session by default |
| Audit log events | login attempts, magic-link mints, 401/403/404 probes | `/var/log/simplevtt/audit.log` | 10 MB × 5 backups (~50 MB) |
| Game state | campaigns, characters, sheets, battles, chat, rolls | postgres | Indefinite |
| Uploaded assets | maps, tokens, audio, thumbnails | `uploads_data` volume | Indefinite |
| Homebrew content | JSON content packs | `homebrew_data` volume | Indefinite |
| Database backups | `pg_dump` snapshots | `backup_data` volume | 7 daily + 4 weekly |

---

## Account data

When a user registers (local registration, `APP_ALLOW_LOCAL_REGISTRATION=true`)
or signs in via Google SSO (`GOOGLE_SSO_ENABLED=true`),
the following lands in the `users` table:

- **Email address.** Used as the login identifier and (if you
  enable email features later) the contact channel.
- **Password hash.** Bcrypt-style (`passlib`). The plaintext
  password is **never** stored or logged.
- **Display name.** What other players see in chat / character
  sheets.
- **Color.** Personalization knob; persists across sessions.
- **Role** (`admin` / `user`). Operators set admins via the
  `ADMINS=email1,email2` env var.
- **Google SSO uid** (when applicable). Opaque identifier issued
  by Google; lets us recognize the same user on subsequent
  sign-ins without storing the Google password.

What the user can do:
- Change display name + color via the user settings page.
- Change password via the user settings page (re-bcrypts;
  old hash is overwritten).
- Account deletion — currently operator-driven (admin portal);
  self-service deletion is a filed feature.

---

## Session data

Sessions are signed cookies (Starlette `SessionMiddleware` with
`APP_SECRET_KEY`). The cookie holds:

- `user_id` (integer FK to `users.id`).
- Per-page navigation breadcrumbs (transient — cleared on logout).

The cookie is signed but **not encrypted** — anyone with the
cookie can read its contents but can't forge a valid signature
without `APP_SECRET_KEY`. The user_id alone is useless without
the database.

Default expiry: browser session (cookie cleared on browser
close). An operator can extend this via Starlette config in
`app/main.py`.

---

## Audit log events

This is the most operationally interesting category. SimpleVTT
emits canonical text-format log lines for every event a
fail2ban / CrowdSec engine cares about. The events land at:

- **stdout** (always — `docker compose logs app` shows them).
- **`/var/log/simplevtt/audit.log`** (since v2.469.0 — the
  shared volume the fail2ban container tails). Rotated at
  10 MB × 5 backups.

### Events emitted today

| Event tag | When it fires | Keys logged |
|---|---|---|
| `auth.login_ok` | Successful sign-in | `ip`, `ua`, `user_id` |
| `auth.login_failed` | Bad password / unknown email | `ip`, `ua`, `username` (the typed value) |
| `auth.signup_failed` | Registration rejected | `ip`, `ua`, `reason` |
| `demo_magic_link.mint_ok` | Admin minted a magic link | `ip`, `ua`, `sub`, `jti`, `admin_id` |
| `demo_magic_link.verify_ok` | Magic-link login succeeded | `ip`, `ua`, `sub`, `jti` |
| `demo_magic_link.verify_rejected` | Magic-link login refused | `ip`, `ua`, `reason` |
| `api.unauthorized` | 401 on a protected endpoint | `ip`, `ua`, `path` |
| `api.forbidden` | 403 on a protected endpoint | `ip`, `ua`, `path` |
| `api.not_found` *(v2.477.0)* | 404 on any path | `ip`, `ua`, `path` |
| `admin.<action>` | Admin destructive action (delete user, delete campaign, ...) | `ip`, `ua`, `admin_id`, action-specific |
| `cloudflare.ban_ok` / `cloudflare.unban_ok` | Admin-initiated Cloudflare edge ban / unban | `ip`, `ua`, `admin_id`, `target_ip` |

### What's logged about *the typed credential*

When `auth.login_failed` fires, the **typed username** lands in
the log — even if that username doesn't match any user. This is
the default for credential-stuffing detection ("we want to see
the wordlist contents") but can be a privacy concern in some
jurisdictions. To redact, override the audit call site in
`app/auth.py` to log `username="<redacted>"`. Passwords are
**never** logged in any form.

### IP attribution

The `ip` key on every event records the direct connection IP by
default. If your deploy sits behind a reverse proxy (nginx,
Traefik, Cloudflare), set `TRUSTED_PROXY_HOPS=N` (the number of
trusted proxy hops) so the audit log records the real client IP
from `X-Forwarded-For` instead of the proxy's IP. Default `0`
(don't trust the header) is safe but records the proxy's IP for
behind-proxy deploys.

---

## Game state

Everything that happens at the table lives in postgres:

- **Campaigns** + memberships.
- **Characters** + sheets (D&D 5e attributes, HP, attacks,
  spells, inventory).
- **Battle state** (combatant list, initiative, hp, buffs) —
  ephemeral per-battle; the realtime hub keeps it in memory and
  the database persists it on `PUT /battle`.
- **Chat messages** + roll history (every die roll fires a row).
- **Maps + tokens** metadata (the assets themselves are in
  `uploads_data`).
- **Homebrew content** — campaign-scoped or system-wide
  homebrew JSON.

Game state is indefinitely retained; operators manage deletion
through the admin portal or direct DB access.

---

## Uploaded assets

Map images, token images, audio clips, and thumbnails land in
the `uploads_data` named volume at
`/app/app/static/uploads/{maps,tokens,audio,thumbnails}`. The
uploader's `user_id` is recorded in postgres for ownership; the
binary content is in the volume.

A campaign deletion *does* delete the database-side metadata but
**does not** automatically delete orphaned binary files in the
volume. An operator who wants to reclaim disk space periodically
runs a cleanup pass against the volume.

---

## Database backups

The `backup` service (started by default) runs `pg_dump` on cron
(default: daily at 03:00 UTC; overridable via `BACKUP_CRON` env)
and keeps:

- 7 daily snapshots, rotating.
- 4 weekly snapshots, rotating.

Backups live in the `backup_data` volume on the host. Backups
contain **everything** the database contains — including
password hashes, session cookies (sort of — only their server
state), audit-trail-relevant user data, etc. Operators are
responsible for protecting the backup volume in line with their
threat model.

---

## Third-party data flows

SimpleVTT talks to external services only in these specific
cases:

- **Google SSO** (when `GOOGLE_SSO_ENABLED=true`). On user-
  initiated sign-in, SimpleVTT redirects to Google's OAuth
  endpoint. Google receives: the operator's `redirect_uri` + the
  OAuth scopes (typically `email` + `profile`). SimpleVTT
  receives: an opaque token + the user's email + display name.
  No further data exchange happens.
- **Cloudflare API** (when `SIMPLEVTT_CLOUDFLARE_BANNING_ENABLED=true`
  AND an admin clicks the ban button OR fail2ban's
  cloudflare-bouncer action fires). SimpleVTT POSTs `{IP,
  mode:block}` to the Cloudflare access-rules API. Cloudflare
  receives: the banned IP + a free-form "notes" string
  identifying the source (admin id or "fail2ban
  simplevtt-auth"). No request payloads, no user data, no
  session info.
- **No analytics, no telemetry.** SimpleVTT does not phone home,
  does not call out to any vendor for metrics, does not run any
  third-party JS. The browser-side code talks only to your
  SimpleVTT origin + (if you set it up) Cloudflare's edge.

---

## Data we deliberately *don't* track

By design:

- **No per-request access log.** SimpleVTT does **not** log
  every HTTP request. Only banning-relevant events (the audit log
  table above) get logged. There is a [filed TODO](/wiki/doc/todo)
  for an opt-in Cloudflare-tunnel-aware visitor request log, but
  it's intentionally OFF by default.
- **No browser fingerprinting.** No canvas, font, or WebGL
  probes. No third-party trackers.
- **No password content.** Plaintext passwords are never logged
  even on failure paths.
- **No PII on `auth.login_ok`.** Successful logins record
  `user_id`, not email — so a log breach can't be cross-
  referenced to email addresses without the database.

---

## What an operator controls

Every privacy-relevant knob is a single env var:

| Env var | Default | Effect |
|---|---|---|
| `AUDIT_LOG_PATH` | `/var/log/simplevtt/audit.log` | File path for the audit log tee. Set to empty string to disable the file handler (stdout-only). |
| `TRUSTED_PROXY_HOPS` | `0` | How many `X-Forwarded-For` hops to trust. Set to `1` behind one reverse proxy, `2` behind two, etc. |
| `APP_ALLOW_LOCAL_REGISTRATION` | `true` | Whether anyone can create an account. Set `false` to lock signups. |
| `GOOGLE_SSO_ENABLED` | `false` | Whether Google SSO is offered. |
| `SIMPLEVTT_CLOUDFLARE_BANNING_ENABLED` | `false` | Whether the in-app Cloudflare ban button + fail2ban Cloudflare bouncer can talk to the Cloudflare API. |
| `BACKUP_CRON` / `KEEP_DAILY` / `KEEP_WEEKLY` | `0 3 * * *` / `7` / `4` | Backup cadence + retention. Set `KEEP_*=0` to disable backups entirely. |

For full env-var documentation see [`.env.example`](/wiki/doc/changelog)
at the repo root.

---

## If a user asks: "what do you have on me?"

Run this against your database (replacing `<email>`):

```sql
-- Account data
SELECT id, email, display_name, role, created_at FROM users
WHERE email = '<email>';

-- Campaigns they belong to
SELECT c.id, c.name FROM campaigns c
JOIN campaign_memberships m ON m.campaign_id = c.id
JOIN users u ON u.id = m.user_id
WHERE u.email = '<email>';

-- Characters they own
SELECT id, name, campaign_id FROM characters
WHERE owner_user_id = (SELECT id FROM users WHERE email = '<email>');

-- Recent audit events about them
-- (audit log is text, not in postgres; grep the log file directly)
```

For audit-log entries about a specific user, grep the file:

```bash
docker compose exec app \
    grep "user_id=<their_id>" /var/log/simplevtt/audit.log
```

For a deletion request, the admin portal has user delete; that
cascades through campaigns + characters + rolls. The audit log
file is NOT automatically scrubbed — that's an operator
decision (the audit log is forensic evidence; scrubbing it on
user request reduces its value as a security record).

---

## See also

- [fail2ban deployment guide](/wiki/fail2ban-deployment) — the
  audit log's primary consumer.
- [fail2ban / CrowdSec integration plan](/wiki/doc/plan-fail2ban-crowdsec-integration)
  — design doc for the audit log line shape + threat model.
- [Cloudflare edge-banning plan](/wiki/doc/plan-cloudflare-edge-banning)
  — the in-app ban button's design.
- [Demo magic-link plan](/wiki/doc/plan-demo-magic-link) — the
  passwordless login flow's privacy model.
