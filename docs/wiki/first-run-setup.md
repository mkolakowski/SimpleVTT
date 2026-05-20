# First-run setup

**Audience:** operators standing up a fresh SimpleVTT instance for the first time.
**Version stamp:** v2.43.17.

End-to-end walkthrough for the first 30 minutes: install Docker, clone the repo, configure the env, bring the stack up, register the first user, create a campaign, invite a player, run a smoke test. By the end you'll have a working instance with one GM + one player + a campaign + a map + a first dice roll on record.

Prereqs: a host with Docker + Docker Compose v2, ~1 GB free disk space, an HTTP port to expose (default 8013). Works on Linux (amd64/arm64), macOS (Intel + Apple Silicon), and a Raspberry Pi 4+.

## 1. Get the code

```bash
git clone https://github.com/<your-org-or-fork>/SimpleVTT.git
cd SimpleVTT
```

Two ways to run the stack:

| Compose file | When to use | What it does |
|--------------|-------------|---------------|
| `docker-compose.yml` | You want to track `main` or develop locally. | Builds the image from `Dockerfile` on every `docker compose up --build`. |
| `docker-compose.ghcr.yml` | You want a pinned, pre-built image. | Pulls `ghcr.io/<org>/simplevtt:${SIMPLEVTT_TAG}` (default `latest`). Faster `up`. |

The rest of this guide assumes the source build (`docker-compose.yml`). Swap in the `-f docker-compose.ghcr.yml` flag if you'd rather pull a pre-built tag.

## 2. Configure environment variables

```bash
cp .env.example .env
```

Edit `.env` and set at minimum:

```diff
- APP_SECRET_KEY=CHANGE_ME_TO_A_LONG_RANDOM_STRING
+ APP_SECRET_KEY=<paste a 48-byte token>

- APP_BASE_URL=http://localhost:8013
+ APP_BASE_URL=https://yourdomain.example   # or keep localhost for self-only

- ADMINS=example@example.com
+ ADMINS=you@example.com                     # your email — auto-promoted to admin on first login

- POSTGRES_PASSWORD=changeme_in_production
+ POSTGRES_PASSWORD=<a strong random password>
```

Generate the secret key with:

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

The other vars worth knowing on day one:

| Var | Default | What it does |
|-----|---------|--------------|
| `APP_PORT` | `8013` | Host port mapped to the container. |
| `APP_ALLOW_LOCAL_REGISTRATION` | `true` | Self-service signup on `/register`. Set `false` after you've registered all the accounts you want — players you invite get linked to existing users. |
| `APP_DEFAULT_THEME` | `sepia` | Theme applied to new users + logged-out pages. Valid: `dark`, `midnight`, `dim`, `light`, `forest`, `bubblegum`, `fire`, `oled`, `hobbiton`, `hearthstone`, `mosswood`, `inkwell`, `forge`, `sepia`. |
| `CHARACTER_TEMPLATES` | `generic,dnd5e` | Sheet template options surfaced in the UI. Drop one to hide it. |
| `GOOGLE_SSO_ENABLED` | `false` | Set `true` + fill the `GOOGLE_SSO_*` vars to enable Google login. See `.env.example` for the OAuth-console URL + redirect URI. |
| `DEMO_MODE` | `false` | When `true`, the lifespan handler periodically resets the DB to a seeded demo state. **Don't enable on production** — the wipe destroys data. Used only for the public demo. |

Everything else has sane defaults — come back when you need them.

## 3. Bring the stack up

```bash
docker compose up -d --build
```

This builds the `simplevtt-app:latest` image and starts three services:

- **`simplevtt-app`** — the FastAPI process. Listens on `${APP_PORT}` (default 8013).
- **`simplevtt-db`** — Postgres 16. Persists to the `db_data` volume. Health-checked.
- **`simplevtt-backup`** — runs `pg_dump` on the schedule in `BACKUP_CRON` (default 3 AM UTC daily, 7 daily + 4 weekly retention).

Watch the boot logs:

```bash
docker compose logs -f app
```

On a fresh DB you'll see migrations apply (`Applying migration block N: ...`) followed by `Uvicorn running on http://0.0.0.0:8013`. The migration system is forward-only inline (see [architecture overview](architecture-overview.md#schema-migrations)) — first boot creates every table from scratch via SQLAlchemy + records `SchemaInfo.version = 56` (or whatever the current value of `SCHEMA_VERSION` is).

Verify it's live:

```bash
curl http://localhost:8013/healthz
# → {"ok":true,"app_version":"2.43.17","schema_version":56}
```

If you see the JSON, you're up. If `curl` hangs or 502s, check `docker compose ps` (the `app` health should be `Up`) and `docker compose logs app`.

## 4. Register the first user

Open `http://localhost:8013` in your browser. You'll land on the index → the login page.

- Click **Register** (or visit `/register` directly).
- Email: the address you put in `ADMINS=` above. The login flow auto-promotes that email to `is_admin = true`.
- Display name: how you'll appear in the UI.
- Password: anything ≥ 8 chars.

After registration, you're logged in. The topnav shows `<your name>(admin)` and the Admin link is visible. Hit `/admin` to confirm you can see the admin panel (campaign list, user list, force-logout button).

## 5. Create your first campaign

From the index page:

1. Click **+ New Campaign** (or hit `POST /campaigns` via curl — same endpoint).
2. Name it (e.g. "My Tuesday Night Game").
3. Pick the game system. The default is `dnd5e` — the most-featured system. `generic` exists for non-D&D play.
4. Submit. You land on the campaign page (`/campaign/{id}`) — empty map, empty initiative tracker, empty roll log.

## 6. (Optional) Disable self-registration

Now that your admin account is set, you can close registration so randos can't sign up:

```diff
# .env
- APP_ALLOW_LOCAL_REGISTRATION=true
+ APP_ALLOW_LOCAL_REGISTRATION=false
```

```bash
docker compose up -d --build app   # rebuild to pick up the env change
```

The `/register` page will now 403. You'll need to create future accounts via the admin panel (`/admin → Add user`) or via the database directly.

Or leave it open if you want frictionless player onboarding.

## 7. Invite a player

Two flows:

### Flow A — open registration (easiest)

1. Send your player the URL: `https://yourdomain.example/register`.
2. They register an account.
3. You go to **Campaign settings → Members** and add them by email.
4. They reload `/campaign/{id}` and they're in.

### Flow B — admin-creates-account

1. You hit `/admin → Add user`.
2. Fill in their email + a temporary password.
3. Share the URL + the temp password.
4. They log in and reset their password under `/settings`.
5. You add them to the campaign via **Campaign settings → Members**.

Either way, the player needs a `Character` linked to their `User` before they can act in a campaign. You can create one for them on the **Characters** page (top-right of the topnav).

## 8. Upload a map + drop tokens

1. **Campaign settings → Maps tab → Upload Map.** PNG / JPG / WebP. Set the grid size (default 50 px).
2. **Activate** the map (click the radio next to it). The canvas on `/campaign/{id}` now shows it.
3. From the **Token tracker** drawer (right side), click **Add Token**. Pick a PC or a monster template. The token drops onto the map center.
4. Drag it. Connected clients see the move in real-time (~50 ms throttled WebSocket broadcast).

For the deeper coverage of maps + grids + tokens see the future "Maps + grids + tokens" wiki guide.

## 9. Smoke test — roll a die + cast a spell

While still on `/campaign/{id}`:

1. **Bottom-right Dice Roller card → Expression: `1d20+5`** → Roll. You should see:
   - A dice toast pop up at the bottom of the screen (animated d20).
   - A roll-log card in the right drawer.

2. **Drop a player token + a monster token on the map** (see step 8).
3. **Click the player token** → mini-sheet opens → **Attacks tab → click a weapon's "Strike" button**.
4. **Double-tap the monster token** → it's now the target. Re-click the weapon's Strike. The attack rolls + applies damage (if `auto_apply_damage` is on in campaign settings — default `false`).

If both of those work, the realtime + auto-resolution paths are healthy.

## 10. Set up backups

The `simplevtt-backup` sidecar already runs nightly per `BACKUP_CRON` (default 3 AM UTC). Backups land in the `backup_data` Docker volume:

```bash
docker compose exec backup ls -la /backups
# → simplevtt-daily-YYYY-MM-DD.sql.gz
```

To pull a backup to the host:

```bash
docker compose cp backup:/backups/simplevtt-daily-$(date -u +%F).sql.gz ./
```

Retention: `KEEP_DAILY=7` + `KEEP_WEEKLY=4` (default) — 7 daily + 4 weekly snapshots, then the oldest get pruned.

To restore: copy a `.sql.gz` to the `db` container, gunzip, and `psql` it into the database. (Restore is a bigger topic — see the future "Backups + restore" wiki guide.)

## 11. Configure HTTPS (optional)

The container speaks HTTP only. For internet-facing deploys put a reverse proxy in front:

- **Caddy** — simplest. Set `APP_BASE_URL=https://yourdomain.example` and run Caddy with `reverse_proxy localhost:8013`.
- **nginx** — same idea; nginx config samples are common.
- **Cloudflare Tunnel** — zero-config TLS + DDoS protection if you're behind it already.

When TLS terminates upstream, `--proxy-headers` (already set in the Dockerfile's `CMD`) tells uvicorn to trust the `X-Forwarded-*` headers so OAuth redirects + cookie domains work correctly.

## 12. (Optional) Demo mode

If you want the public-demo behavior — reset every 60 minutes, pre-seeded campaign with 12 demo PCs:

```diff
# .env
- DEMO_MODE=false
+ DEMO_MODE=true
```

**Don't enable this on a production instance.** The reset wipes any data tagged with the demo emails / campaign name; you'll lose state. Used only for the public demo at `simplevtt.example`. See `docs/plans/demo-mode.md` for the full design.

## What to do next

| Task | Where to read |
|------|---------------|
| Run your first session | (future) "Running a session as GM" wiki guide |
| Add a player's character | The Characters page (topnav). For deep dives: future "The character sheet" wiki guide. |
| Build an encounter (save a battle for re-use) | (future) "Building an encounter" + the Encounters CRUD endpoints in [endpoint-catalog.md](endpoint-catalog.md). |
| Add custom monsters / spells / items | (future) "Homebrew content authoring" wiki guide. |
| Change your theme or font | User menu (top-right) → Settings. 14 themes available. |
| Pin a specific version instead of building from source | Use `docker-compose.ghcr.yml` + set `SIMPLEVTT_TAG=2.43.17` (or whatever stable tag you want). |
| Upgrade to a newer version | `git pull && docker compose up -d --build`. Schema migrations run automatically at boot. |

## Troubleshooting

**Container won't start.** `docker compose logs app`. The most common cause: `APP_SECRET_KEY` is the literal `CHANGE_ME_TO_A_LONG_RANDOM_STRING` placeholder — set it to a real value.

**Login screen forever spinning.** Browser may have a stale service worker / cached old assets. Hard-refresh (Cmd-Shift-R on macOS, Ctrl-F5 on Windows). Every static asset URL carries `?v=APP_VERSION` so version bumps invalidate caches automatically, but the *first* asset request after `up` may still be stale.

**"Login required" JSON shows in the browser instead of a page.** A WebSocket disconnected and reconnected through an expired session. The global fetch wrapper in `base.html` is supposed to redirect you to `/login?next=...` — if it doesn't, refresh the page.

**Players can't see each other's rolls.** Check `Visibility` on the Dice Roller form — it might be set to `GM only` or `GM + you`. Switch to `Public`.

**Database connection refused.** The `app` service starts before `db` is healthy if you bypass `depends_on.condition`. The default compose file already gates `app` on `db: condition: service_healthy`, so this only bites on hand-rolled setups.

**Migration failure on a version upgrade.** Capture `docker compose logs app | grep -i migration`, then open an issue with the migration block that broke. Roll back by restoring the most recent backup before the upgrade.

## Where the code lives

- **Compose files:** `docker-compose.yml`, `docker-compose.ghcr.yml`
- **Dockerfile:** `Dockerfile` (multi-arch Python 3.12 base; copies `app/` + `docs/wiki/`).
- **Boot sequence:** `app/main.py` registers routers + the global 401 handler. `app/database.py` `init_db()` runs `_apply_inline_migrations()` on every start.
- **Env-var parsing:** `app/config.py` via pydantic-settings.
- **Backup sidecar:** `scripts/backup.sh` + `scripts/entrypoint-backup.sh`.
- **Demo mode:** `app/demo_seed.py` + `app/demo_scheduler.py`. Toggled by `DEMO_MODE`.
- **Theme tokens:** `app/static/style.css` (core) + `app/static/style-fantasy-themes.css` (fantasy).

## Related guides

- **[Architecture overview](architecture-overview.md)** — for the system map this guide assumed.
- **[Endpoint catalog](endpoint-catalog.md)** — every URL you might hit.
- **[Realtime broadcasts catalog](realtime-broadcasts-catalog.md)** — what your clients sync over.
- **[Roll-log guide](roll-log-guide.html)** + **[Toast notifications guide](toast-notifications-guide.html)** — for the in-session feedback surfaces.
