# SimpleVTT

> Current version: **2.11.0** · Schema: **v55** · See [CHANGELOG.md](CHANGELOG.md) for release history and the rules for bumping versions (pre-2.0.0 history archived in [CHANGELOG_v1.md](CHANGELOG_v1.md)).

A self-hosted virtual tabletop for online TTRPG sessions. Python (FastAPI) backend with a Jinja2 + HTMX + vanilla JS frontend, PostgreSQL for storage, real-time sync over WebSockets, and Docker Compose deployment that works on both `linux/amd64` and `linux/arm64` (Raspberry Pi, Apple Silicon, etc.).

## Features

- **Auth**: local email/password login + optional Google SSO. Self-service registration can be toggled via env var.
- **Tabletop canvas**: square or hex grids on top of GM-uploaded battle maps. Click and drag to move tokens you're assigned to. Double-click a token to open its character sheet.
- **Dice roller**: full `XdY±Z` notation including `kh3`/`kl3` (keep highest/lowest) and `1d20a`/`1d20d` (advantage/disadvantage). Per-roll visibility: GM-only, GM + roller, or all players.
- **Roll log**: every roll is persisted. Pop-out window with live updates via WebSocket. Players only see rolls they're allowed to see.
- **Character sheets**: free-form generic template, or D&D 5e (stats, skills, AC/HP, attacks, spells, inventory).
- **Admin portal**: manage users, campaigns, memberships, characters, and battle maps. Admins are defined by the `ADMINS` env var.
- **Automated backups**: a sidecar container runs `pg_dump` on cron with daily + weekly retention.

## Demo

A `DEMO_MODE=true` deploy ships with a fully-staged sample session that resets every 60 minutes (see [`docs/plans/demo-mode.md`](docs/plans/demo-mode.md) for the full design). The reset cadence and credentials are configurable in `.env`; see the **Demo mode** section of [`.env.example`](.env.example).

### Sign in

Three accounts, all with the password **`demopass`** (also surfaced on the login page when `DEMO_CREDENTIALS_VISIBLE=true`):

| Email | Role |
|---|---|
| `demo-gm@example.com` | Game Master (also owns Brother Tavik below) |
| `demo-alice@example.com` | Player — controls Pip Quickfingers |
| `demo-bob@example.com` | Player — controls Thalindra Moonwhisper |

### The setting

**Demo: The Sundered Vault**, opening scene — **The Tavern Brawl**. The party have cornered a band of brigands inside a roadside tavern; the brigands turn nasty. The bar is to the east, the door to the west, and the floor is about to get loud.

### Player characters

| Name | Class & level | Race | Owner | Notes |
|---|---|---|---|---|
| **Pip Quickfingers** | Rogue 5 (Thief) | Halfling | Alice | DEX-focused melee + thrown daggers; high Stealth / Sleight of Hand expertise |
| **Thalindra Moonwhisper** | Wizard 5 (Evocation) | Elf | Bob | Fireball / Magic Missile / Misty Step / Counterspell — INT-focused ranged caster |
| **Brother Tavik Stonebrow** | Cleric 5 (Life Domain) | Hill Dwarf | GM | Heavy-armour healer; Warhammer + Sacred Flame; Bless / Cure Wounds / Spirit Guardians (added v2.3.25 to round out the party with divine healing and give the GM a PC mini-sheet to demo from) |

### NPCs in the Tavern Brawl

All six are authored as homebrew monster JSON in the campaign's homebrew scope (v2.3.31), exercising the homebrew tier → mini-sheet → click-to-roll flow end-to-end. Click a row in the GM initiative tracker to open the unified monster mini-sheet; click **📋 Open full sheet** to open the read-only standalone sheet in the drawer.

| Name | Stat block | CR | Role |
|---|---|---:|---|
| **Vex Vance** | Bandit Captain | 2 | Leader — Scimitar / Dagger / Parry reaction / Leadership 1/short rest |
| **Grixxa** | Goblin Captain (homebrew, v2.3.22) | 1 | Top of the init order — Scimitar / Javelin / Frightful Howl save DC 12 / Pack Tactics / Nimble Escape |
| **Thug** | Thug | 1/2 | Heavy backup — Multiattack Mace + Heavy Crossbow / Pack Tactics |
| **Bandit Alpha** | Bandit | 1/8 | Mook — Scimitar / Light Crossbow |
| **Bandit Beta** | Bandit | 1/8 | Mook — same loadout |
| **Bandit Gamma** | Bandit | 1/8 | Mook — same loadout |

### Pre-rolled initiative

The encounter ships with a deterministic initiative order so you can hit "Load encounter" and immediately start playing:

1. Grixxa (Goblin Captain) — **init 18**
2. Vex (Bandit Captain) — init 17
3. Pip Quickfingers — init 15
4. Brother Tavik — init 14
5. Thalindra Moonwhisper — init 13
6. Thug — init 11
7. Bandit Alpha — init 9
8. Bandit Beta — init 7
9. Bandit Gamma — init 5

### What gets wiped on reset

The hourly reset surgically deletes everything tagged with the three demo emails or the demo campaign name — no other rows are touched. Token positions, HP edits, custom rolls, and any extra characters / homebrew anyone created are reverted to the seed dataset. See `app/demo_seed.py` `wipe()` for the full list and `_reset_sequences()` (v2.3.27) for why the campaign URL stays at `/campaign/1` across cycles.

### Enabling demo mode on your own deploy

In `.env`:

```bash
DEMO_MODE=true
DEMO_RESET_INTERVAL_MINUTES=60   # clamped to [5, 1440]
DEMO_RESET_ON_BOOT=true          # seed on container start
DEMO_CREDENTIALS_VISIBLE=true    # show creds on /login
```

Then `docker compose up -d --build`. A non-dismissible banner appears on every page warning visitors that data resets on the configured cadence.

## Architecture

```
docker-compose stack
 ├── db        postgres:16-alpine
 ├── app       FastAPI + Uvicorn (this repo's Dockerfile)
 └── backup    postgres:16-alpine running cron + pg_dump → ./backups/
```

All images are multi-arch.

## Setup

1. **Clone and configure**
   ```bash
   cp .env.example .env
   ```
   Edit `.env` and set, at minimum:
   - `APP_SECRET_KEY` — generate with `python -c "import secrets; print(secrets.token_urlsafe(48))"`.
   - `POSTGRES_PASSWORD` — pick a strong value for production.
   - `ADMINS` — comma-separated list of admin emails (matching accounts get auto-promoted on login).
   - `APP_BASE_URL` — the public URL you'll access SimpleVTT at, port included.

2. **(Optional) Google SSO**
   In Google Cloud Console → APIs & Services → Credentials → Create OAuth 2.0 Client (Web). Add an authorized redirect URI matching `${APP_BASE_URL}/auth/google/callback`. Set `GOOGLE_SSO_ENABLED=true` and paste the client ID/secret into `.env`.

3. **Build and run**
   ```bash
   docker compose up -d --build
   ```
   The app will be available at `http://localhost:8013` (or whatever `APP_PORT` you set). Tables are created automatically on first boot.

4. **First login**
   - If `APP_ALLOW_LOCAL_REGISTRATION=true`, click *Create one* on the login page and register with one of the emails listed in `ADMINS`. You'll be promoted to admin automatically.
   - Or, if you've enabled Google SSO, click *Sign in with Google*.

## Backups

The `backup` container writes to `./backups/daily/` (and `./backups/weekly/` on Sundays). Defaults: 7 daily snapshots, 4 weekly. Schedule and retention are configurable via env vars (`BACKUP_CRON`, `KEEP_DAILY`, `KEEP_WEEKLY`). To restore:

```bash
gunzip -c backups/daily/simplevtt-YYYYMMDDTHHMMSSZ.sql.gz \
  | docker compose exec -T db psql -U simplevtt simplevtt
```

## Architecture decisions

- **FastAPI + Jinja2 + HTMX + vanilla JS canvas**: backend logic stays Python. The canvas needs imperative pixel control (token dragging, hex math) so it's a small vanilla JS file rather than a heavier framework. WebSocket broadcasting is built into FastAPI.
- **PostgreSQL**: relational data (users, campaigns, memberships, rolls) plus JSON columns for character sheets.
- **Sessions over JWT**: simpler for a server-rendered app. Session cookies are signed with `APP_SECRET_KEY`.
- **Admins by email in env**: easy to bootstrap, plays well with both local and SSO accounts.
- **All config via env vars**: no separate YAML config file — everything lives in `.env`. Simpler to template, easier to inject through orchestrators (Compose, Kubernetes, Nomad).

## Project layout

```
.
├── docker-compose.yml
├── Dockerfile
├── requirements.txt
├── .env.example                # copy to .env — all config lives here
├── scripts/
│   ├── backup.sh               # pg_dump + retention
│   └── entrypoint-backup.sh    # cron wrapper for the backup sidecar
└── app/
    ├── main.py                 # FastAPI app + startup
    ├── version.py              # APP_VERSION + SCHEMA_VERSION constants
    ├── config.py               # env-var settings loader
    ├── database.py             # SQLAlchemy engine/session
    ├── models.py               # ORM models
    ├── auth.py                 # local + Google SSO helpers
    ├── dice.py                 # dice expression parser
    ├── sheet_templates.py      # generic + D&D 5e templates
    ├── realtime.py             # WebSocket hub
    ├── templates.py            # Jinja2 instance
    ├── routes/
    │   ├── auth_routes.py
    │   ├── tabletop_routes.py
    │   └── admin_routes.py
    ├── templates/              # Jinja2 HTML templates
    └── static/                 # CSS/JS + uploaded maps & tokens
```

## Development (without Docker)

If you want to run the app directly against a local Postgres or SQLite:

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
# Load env vars (any tool will do — direnv, dotenv, or just `export`).
export $(grep -v '^#' .env.example | xargs)
# DATABASE_URL defaults to sqlite:///./simplevtt.db when not set.
uvicorn app.main:app --reload --port 8013
```

## Third-party fonts

The following free/open-source fonts are loaded from Google Fonts and available as optional display fonts in **Settings → Display font**:

| Font | Designer | Licence | Source |
|------|----------|---------|--------|
| **Lora** | Cyreal | [SIL OFL 1.1](https://scripts.sil.org/OFL) | [Google Fonts](https://fonts.google.com/specimen/Lora) |
| **Cormorant Garamond** | Christian Thalmann | [SIL OFL 1.1](https://scripts.sil.org/OFL) | [Google Fonts](https://fonts.google.com/specimen/Cormorant+Garamond) |
| **IM Fell English** | Igino Marini | [SIL OFL 1.1](https://scripts.sil.org/OFL) | [Google Fonts](https://fonts.google.com/specimen/IM+Fell+English) |

All three fonts are served by the Google Fonts CDN and are used only as optional UI preferences — the default UI uses the system sans-serif stack. No fonts are bundled in the repository.

Players pick a font in **Settings → Display font**. GMs can override this for all players on the tabletop page via **Campaign Settings → GM font override**.

## Notes / future work

- Schema migrations use `Base.metadata.create_all` for simplicity. For production schema changes, switch to Alembic (already in requirements).
- WebSocket auth uses session cookies. If you serve over HTTPS, set `https_only=True` in `app/main.py` (and run behind a TLS-terminating proxy).
- Rate limiting on the dice roller would be a sensible production hardening (currently only protected by the `MAX_DICE` parser cap).
