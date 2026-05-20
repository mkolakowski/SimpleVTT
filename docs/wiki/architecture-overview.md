# Architecture overview

**Audience:** new contributors needing the system map before diving into a specific area.
**Version stamp:** v2.43.16.

SimpleVTT is a self-hosted, single-deployment web app for running tabletop RPG sessions. The stack is deliberately small: one FastAPI process behind a Postgres database, with all clients on the same WebSocket hub. There is **no SPA framework, no build step for the frontend** — every page is a Jinja2 template + a script tag that pulls vanilla JS modules from `/static/`.

This page is the system map. Each subsystem has its own deep-dive guide (filed in the wiki TODO); this doc explains how they connect.

## The stack at a glance

```
┌─────────────────────────────────────────────────────────────────┐
│                      Browser (every client)                      │
│  Jinja2-rendered HTML  +  /static/*.js (vanilla)  +  HTMX        │
│   ↑ HTTP                                            ↑ WebSocket  │
│   │ /campaign/{id}, /api/campaign/{id}/...          │            │
│   │                                                 │            │
└───┼─────────────────────────────────────────────────┼────────────┘
    │                                                 │
┌───┴─────────────────────────────────────────────────┴────────────┐
│                       FastAPI process                            │
│  app/routes/*.py   +   app/realtime.py (CampaignHub)             │
│   ↑ ORM                                                          │
│   │                                                              │
└───┼──────────────────────────────────────────────────────────────┘
    │
┌───┴──────────────────────────────────────────────────────────────┐
│                       Postgres 16                                │
│  Campaign, Character, Token, Map, Encounter, …                   │
└──────────────────────────────────────────────────────────────────┘
```

All three layers ship in a single `docker compose up` — the `app` service runs FastAPI, the `db` service runs Postgres, the `backup` service runs `pg_dump` on a cron. No external dependencies at runtime (the SRD content is bundled into the image at `app/data/local/dnd5e/`).

## The tech stack

| Layer | Tech | Why |
|-------|------|-----|
| **HTTP + WebSocket** | FastAPI 0.115 + uvicorn (with `--proxy-headers`) | Async-native, type-checked, OpenAPI for free, easy WebSocket support, one-process deploy. |
| **HTML rendering** | Jinja2 templates (`app/templates/`) | Server-side render, no client build step, every page hydrates with the user's theme + font + version-stamped static URLs. |
| **HTMX** | `unpkg.com/htmx.org@1.9.12` (CDN, loaded with `defer`) | Used sparingly for the homebrew CRUD + the GM tools panel. Lets us swap fragments without writing per-form JS. |
| **Frontend JS** | Vanilla, no build step. Modules in `app/static/*.js`. | Keeps the deploy artifact = one Python image; no node_modules; debuggable in-browser with Sources tab. |
| **Realtime** | Native `WebSocket` + per-campaign hub (`app/realtime.py`) | One process per campaign-set; fan-out via Python sets. No Redis pubsub, no clustering. |
| **DB** | Postgres 16 via SQLAlchemy 2.0 | Single-writer, one process talking to it. JSONB columns for sheet data (`Character.sheet`), JSON columns for token data. |
| **Migrations** | Inline `_apply_inline_migrations()` in `app/database.py` (`SCHEMA_VERSION` bump per change) | Alembic is in `requirements.txt` for future use; today we run a forward-only inline migrator at boot. |
| **Auth** | Session cookies via `SessionMiddleware`, bcrypt-hashed passwords, optional Google SSO via Authlib | One simple model; no JWT, no refresh tokens. |
| **Audio** | Per-campaign playlist with mutagen for tag metadata | Audio routes upload to a volume, then the WS hub broadcasts play commands. |
| **Dice** | Custom `app/dice.py` (no library) | Custom because we need bracketed-die breakdowns (`1d20[14]+5 = 19`) that no off-the-shelf parser produces cleanly. |

## The request lifecycle

A typical "Krieger swings a Greataxe at a bandit" turn:

```
1. Sheet page         GET  /campaign/1/character/4/sheet
                       → Jinja render with the v={{APP_VERSION}} cache-busted assets

2. Player clicks Strike
                      POST /api/campaign/1/attack
                       body: {character_id: 4, attack_index: 0,
                              target_combatant_id: "tok_bandit_1",
                              target_name: "Bandit"}

3. Server in /attack
   a. Validate auth (owner of char OR GM)
   b. Roll the d20 + damage via app/dice.py
   c. Look up target's AC, decide hit/miss
   d. If auto_apply_damage is on: _apply_damage_to_combatant
      → write Character.sheet.hp.current via SQLAlchemy
      → record entry in _attack_damage_log (8h TTL for Undo)
   e. Mark the action chip via _mark_battle_economy
      → mutates hub._battle[1].combatants[i].economy.action = True
   f. hub.broadcast(1, {"type": "weapon_attack", "data": {...}})

4. Hub fan-out
   - Every connected WebSocket for campaign 1 receives the JSON
   - The bandit's owner (GM client) re-renders the token HP bar
   - Krieger's client renders the weapon-attack card in the roll log
   - All clients re-render the chip strip on Krieger's sheet
   - The dice toast fires on every client (visibility filter is "public")
```

The HTTP request returns ~50-200 ms in. The WS fan-out happens in the same Python coroutine — by the time the response goes back to the player, every other client has already received the broadcast.

## State: three locations, three lifetimes

| Location | Lifetime | What lives there | When to use it |
|----------|----------|------------------|---------------|
| **Postgres DB** | Forever (until campaign delete) | Character.sheet, HP, slots, resources, tokens, maps, encounters, campaign config | All persistent state. The source of truth. |
| **In-memory hub** (`app/realtime.py`) | Until process restart | Battle state (combatants, turn_index, round, economy chips), `_attack_damage_log` (Undo TTL), `_heal_claims`, `_save_request_context`, in-progress targeting picker state | Ephemeral table state — restart loses chip flips, in-progress Undos. Acceptable: restart is rare; chip flips reset on next round anyway. |
| **Browser `localStorage`** | Per-browser, per-campaign | Roll-log card replay buffer (`simplevtt:rolllog:${CAMPAIGN_ID}`, last 100 entries), targeting state (`simplevtt:targeting:${CAMPAIGN_ID}`), per-user theme / font / scale | Display-only state. Survives page refresh; lost on browser data clear. |

When in doubt: persistent state goes in the DB. Ephemeral table-state (chips, Undo logs) goes in the hub. UI preferences go in localStorage.

## The realtime hub

`CampaignHub` (`app/realtime.py`) keys on `campaign_id`. Each campaign has:

- A set of connected `WebSocket` objects (`_channels[cid]`).
- A per-connection identity table (`_identities[ws]` → `{user_id, display_name, color, is_gm}`) for the presence indicator.
- A snapshot of the current battle state (`_battle[cid]`) so the GM's chip flips + initiative changes can be re-read by other endpoints (e.g. the over-budget gate in `_mark_battle_economy`).

The hub is **single-process** — there's no Redis pubsub, no inter-worker fan-out. Run more than one uvicorn worker and the WS hub fragments. Today we deploy one worker per campaign-set; if you need horizontal scaling, file an architecture follow-up (Redis pubsub for hub fan-out is the standard answer).

For the catalog of broadcast types, see the [realtime broadcasts catalog](realtime-broadcasts-catalog.md).

## Directory layout

```
app/
├── main.py              ← FastAPI app + router registration + 401-redirect handler
├── realtime.py          ← CampaignHub (the WS fan-out)
├── database.py          ← SQLAlchemy engine + init_db + _apply_inline_migrations
├── models.py            ← All SQLAlchemy models (Campaign, Character, Token, Map, …)
├── auth.py              ← session cookie auth, password hashing, Google SSO
├── config.py            ← env var parsing via pydantic-settings
├── templates.py         ← Jinja2 Templates instance + bold_dice filter
├── version.py           ← APP_VERSION, SCHEMA_VERSION (the single source of truth)
├── dice.py              ← custom parser/roller with bracketed die breakdowns
├── action_schema.py     ← typed schema for "actions" lists on spells / features
├── content_schemas.py   ← class / subclass / race / feat schemas
├── local_content.py     ← SRD content resolver (looks up app/data/local/dnd5e/)
├── local_features.py    ← class-feature definitions for the curated table
├── character_presets.py ← demo PC factory + class preset builders
├── open5e_local.py      ← local fallback for the Open5e API (offline support)
├── demo_seed.py         ← demo campaign seeder
├── demo_scheduler.py    ← background task that periodically resets demo mode
├── game_systems.py      ← multi-system registry (d&d5e is the main one)
├── sheet_templates.py   ← per-system sheet template registry
├── routes/
│   ├── tabletop_routes.py   ← 139+ endpoints; the bulk of the app
│   ├── auth_routes.py        ← /login, /register, /logout, Google SSO
│   ├── user_routes.py        ← /characters, /settings, per-user prefs
│   ├── audio_routes.py       ← playlists + tracks
│   ├── admin_routes.py       ← /admin
│   ├── homebrew_routes.py    ← homebrew JSON import/export
│   └── wiki_routes.py        ← this wiki you're reading
├── static/
│   ├── style.css                 ← global styles + theme tokens
│   ├── style-fantasy-themes.css  ← hobbiton, hearthstone, sepia, etc.
│   ├── sheet-fantasy.css         ← character sheet styling
│   ├── tabletop.js               ← the main client bundle (~8000 LOC)
│   ├── roll_toast.js             ← dice toast popup (decoupled WS listener)
│   ├── action_buttons.js         ← shared action-button renderer
│   ├── dnd5e_class_resources.js  ← class-feature registry
│   ├── dnd5e_feature_economy.js  ← per-feature slot table
│   └── …                         ← ~30 other small modules
├── templates/
│   ├── base.html                ← topnav + footer + theme + version
│   ├── tabletop.html            ← the main GM/player view (extends base)
│   ├── sheet_dnd5e.html         ← D&D 5e character sheet
│   ├── campaign_settings.html
│   ├── wiki.html                ← /wiki landing
│   ├── wiki_md.html             ← markdown-rendered wiki guide wrapper
│   └── …                         ← ~20 partials
└── data/
    ├── local/dnd5e/             ← bundled SRD content (spells, monsters, items, classes, …)
    └── homebrew/                ← Docker volume — per-campaign custom content
```

Plus at the repo root: `Dockerfile`, `docker-compose.yml`, `requirements.txt`, `CHANGELOG.md`, `CLAUDE.md`, `README.md`, `tests/harness/` (the click-through harness), `docs/` (this wiki + plan docs).

## Schema migrations

Migrations are **inline + forward-only**, applied at process start (`init_db()` in `app/database.py`). Each migration block in `_apply_inline_migrations()`:

1. Reads `SchemaInfo.version` from the DB.
2. If lower than the target block's version, runs the ALTER / data-fixup statements.
3. Updates `SchemaInfo.version` to the new value.

`SCHEMA_VERSION` in `app/version.py` is the single source of truth. Bump by **+1** for every migration block added. The boot-time scan handles fresh DBs (init from blank) AND existing ones (apply only the missing migrations) — same code path either way.

Alembic is in `requirements.txt` but unused today. A future refactor can switch to Alembic when the schema is large enough that inline blocks become unwieldy.

For details + how to write a forward-only step, see the future "Schema migrations" wiki guide (filed in `docs/wiki/README.md`).

## Frontend: vanilla JS + Jinja2

No SPA framework. The reasoning:

1. **Server-side state.** The roll-log card is served by Jinja on page load (so a refreshed page already shows recent rolls). The WS hub fills in real-time updates after that. A SPA framework would re-fetch + re-render the same data the server just sent.
2. **One artifact.** The Docker image carries one Python process. A separate Node build step + a static-asset CDN would double the deployment footprint.
3. **Debuggable.** Chrome devtools' Sources tab opens `/static/tabletop.js` as plain JS. No source maps, no transpiled output, no React fiber trees to scroll through.
4. **Versioned cache-busting.** Every static asset URL carries `?v={{APP_VERSION}}` (v2.3.43 onwards). When we bump the version, the cache invalidates automatically for every visitor — no SW dance, no localStorage versioning, no hard-refresh request.

The trade-off: there's a lot of vanilla JS in `tabletop.js` (~8000 LOC). The discipline that keeps it readable: every section opens with a comment header tagged to the feature commit (`v2.34.0 Phase T.4b: auto-attack-roll …`), and the file is grep-able along those tags.

For the major frontend modules: see [the toast notifications guide](toast-notifications-guide.html) (`roll_toast.js`), the [roll-log guide](roll-log-guide.html) (the card renderers in `tabletop.js`), and the future "The character sheet" wiki guide for `sheet_dnd5e.html` + its companion JS.

## Auth model

- **Sessions:** `SessionMiddleware` from Starlette stores a signed session cookie. `APP_SECRET_KEY` env var signs it. No JWT — sessions live server-side in the cookie.
- **Passwords:** bcrypt via passlib. Configurable rounds; default fine.
- **Google SSO:** optional, via Authlib + the `GOOGLE_SSO_*` env vars.
- **The 401 → /login redirect:** a global `fetch` wrapper in `base.html` intercepts `401 {"detail": "Login required"}` responses and bounces the user to `/login?next=...`. Server-side, `app/main.py` registers an exception handler that does the same for HTML page loads. Together: an expired session never leaves the user with a blank page or raw JSON — they always land on the login page with a return-to URL.
- **Auth scopes:** `gm` (campaign GM), `member` (any campaign member), `owner` (character's owner OR GM), `none` (public). See the [endpoint catalog](endpoint-catalog.md) for per-endpoint scope.

## Demo mode

`DEMO_MODE=true` (env var) enables:
- A seeded campaign with 12 demo PCs (one per PHB class, all at Lv 5).
- Pre-baked accounts (`demo-gm@example.com`, `demo-alice@example.com`, `demo-bob@example.com`).
- A periodic reset (default 60 min, configurable via `DEMO_RESET_INTERVAL_MINUTES`) that wipes the campaign + re-seeds.
- A "Use demo credentials" auto-fill button on the login form (v2.4.4).

Used for the public demo deployment + the click-through test harness. For details, see the future "Demo mode" wiki guide (planned per `docs/plans/wiki-expansion.md`).

## Docker Compose model

`docker-compose.yml` ships three services:

| Service | Image | Purpose |
|---------|-------|---------|
| `app` | `simplevtt-app:latest` (built from `Dockerfile`) | The FastAPI process. Volumes: `uploads_data` (maps + tokens + audio) + `homebrew_data` (per-campaign custom content). |
| `db` | `postgres:16-alpine` | Postgres. Volume: `db_data`. Health-checked. |
| `backup` | `postgres:16-alpine` (re-used) | Cron loop that runs `pg_dump` to the `backup_data` volume daily. |

Network: internal Docker bridge. The `app` service talks to `db:5432` via the DSN in `DATABASE_URL`. No external API calls at runtime — the open5e proxy in `app/open5e_local.py` falls back to bundled data when the public API is unreachable.

Third-party APIs (per CLAUDE.md): when adding one, ship it as a named docker-compose service with a healthcheck. Don't hit public endpoints at request time.

## Testing

Two harnesses, both in `tests/harness/`:

- **Click-through harness** (the bulk): `httpx` clients hit the live `localhost:8013` container, assert HTTP response shapes + WS broadcast shapes. 205 tests as of v2.43.14. Per CLAUDE.md, every new endpoint commit ships at least one happy-path harness test. See `docs/test-harness-coverage.md` for the full catalog + `docs/plans/test-harness.md` for the design rationale.
- **Playwright UI layer** (Phase 4): browser-level smoke tests for the most critical click paths. Lower-coverage than the click-through harness; intentionally narrow.

CI runs both on every push to `main`/`dev` and every PR (`.github/workflows/test-harness.yml`).

## Versioning

Every commit ships a version bump (see `CLAUDE.md`). The `app/version.py` constants are the single source of truth; `CHANGELOG.md` carries the per-release narrative + bump rationale + a required entry format. Static assets cache-bust on the version; the `/version` and `/healthz` endpoints expose it for deploy scripts.

## Where to go from here

- **A specific subsystem** → its wiki guide (when written): action-economy, targeting, buff slots, damage flow, auto-resolution, etc.
- **A specific endpoint** → [endpoint catalog](endpoint-catalog.md).
- **A specific broadcast** → [realtime broadcasts catalog](realtime-broadcasts-catalog.md).
- **The harness** → `docs/plans/test-harness.md` + `docs/test-harness-coverage.md`.
- **A specific design decision** → `docs/plans/*.md`.
- **Operational concerns** (deploy, backups, theming) → the Tier 1+3 wiki guides listed in `docs/wiki/README.md`.
