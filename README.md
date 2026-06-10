# SimpleVTT

> Current version: **2.158.22** · Schema: **v69** · See [CHANGELOG.md](CHANGELOG.md) for release history and the rules for bumping versions (pre-2.0.0 history archived in [CHANGELOG_v1.md](CHANGELOG_v1.md)).

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
| **Sir Caelan Lightbringer** | Paladin 5 (Oath of Devotion) | Human | GM | Front-line martial; Longsword + Javelin; Lay on Hands pool 25 HP, Divine Sense 4/long rest, Channel Divinity 1/short rest, Defense Fighting Style (+1 AC). Added v2.14.0 to unlock the Lay on Hands picker (v2.10.0) end-to-end in the demo. |
| **Lyra Sunstrider** | Bard 6 (College of Lore) | Half-Elf | GM | Charisma face + support caster; Rapier + Hand Crossbow + Vicious Mockery cantrip; Healing Word / Faerie Fire / Suggestion / Hypnotic Pattern / Dispel Magic. Bardic Inspiration 3/short rest at d8 (CHA mod uses, Font of Inspiration short-rest refresh from Lv 5). Added v2.14.1 to unlock the Bardic Inspiration picker (v2.11.0) end-to-end. **Magical Secrets** (v2.15.1 Lore Bard Lv 6 picks): **Fireball** (8d6 fire, DC 14 DEX save, AoE damage Bards don't normally get) + **Counterspell** (reaction-counter — both marked 🪄 on her sheet). |
| **Mira Greenleaf** | Druid 5 (Circle of the Moon) | Wood Elf | GM | Nature caster + Wild Shape combat-druid; Scimitar + Sling + Produce Flame cantrip; Healing Word / Faerie Fire / Moonbeam / Call Lightning / Conjure Animals. Wild Shape 2/short rest with CR-1 cap and bonus-action transform (Circle of the Moon). Added v2.14.2 to set up Wild Shape transform UI work (priority #4 in the class-content roadmap). |
| **Garrik Ironside** | Fighter 5 (Champion) | Variant Human | GM | Two-handed front-line martial; Greatsword (+7 / 2d6+4 slashing) + Handaxe (thrown). STR 18 / CON 16, AC 16 (chain mail, no shield). Great Weapon Fighting style (reroll 1s and 2s on damage). Second Wind 1/short rest, Action Surge 1/short rest, Improved Critical (Champion Lv 3: crit on 19-20, passive — needs roll-time intercept to wire fully). Added v2.17.0 to unlock Phase B work for Second Wind / Action Surge / Brutal Critical-shape uplifts. |
| **Kael Brightleaf** | Monk 5 (Way of the Open Hand) | Wood Elf | GM | Speed-45 melee disruptor (Wood Elf Fleet of Foot + Monk Unarmored Movement). DEX 18 / WIS 15. AC 16 (Unarmored Defense: 10 + DEX + WIS). Unarmed Strike + Quarterstaff both +7 / 1d6+4 bludgeoning (Martial Arts: DEX replaces STR; Lv 5 die is 1d6). Ki 5/short rest. Class abilities buttons for Flurry of Blows / Patient Defense / Step of the Wind (Open Hand Technique + Stunning Strike are deferred follow-ups). Added v2.18.0 to unlock Phase B work for the Ki spend-picker. |
| **Zara Emberfire** | Sorcerer 5 (Draconic Bloodline) | Tiefling | GM | Red-Dragon-ancestor blaster caster; Dagger + Fire Bolt (2d10 fire, 120 ft, +6 attack); 6 leveled spells including Burning Hands / Scorching Ray / Fireball plus the racial Hellish Rebuke + Darkness 1/long each. CHA 17, AC 15 (Draconic Resilience: 13 + DEX), HP 37 (incl. +5 Draconic Resilience). Sorcery Points 5/long rest. Metamagic options known: Quickened Spell + Twinned Spell (Quickened ships its curated button; Twinned is filed). Added v2.18.1 to unlock Phase B work for Font of Magic SP↔slot conversion. |
| **Krieger Stonefist** | Barbarian 5 (Path of the Berserker) | Half-Orc | GM | Front-line raging tank; Greataxe (+7 / 1d12+4 slashing) + Javelin (+7 / 1d6+4 piercing, thrown 30/120). STR 18 / CON 16, AC 15 (Unarmored Defense: 10 + DEX + CON), HP 55 (highest in the party), Speed 40 (Fast Movement at Lv 5). Rage 3/long rest, Reckless Attack on demand. Half-Orc Savage Attacks + Relentless Endurance. Frenzy + Brutal Critical are deferred follow-ups (needs (C) buff slot + crit-detection hook). Added v2.18.2 to unlock Phase B work for the rage state machine. |
| **Rowan Quickbow** | Ranger 5 (Hunter) | Variant Human | GM | Back-line archer; Longbow (+9 / 1d8+4 piercing, range 150 ft — Archery Fighting Style baked into +9) + Shortsword (+7 / 1d6+4 piercing). DEX 18 / WIS 15, AC 16 (studded leather + DEX), HP 44. Hunter's Mark (concentration buff, +1d6 on weapon hits), Colossus Slayer (Lv 3 Hunter pick — +1d6 on below-max-HP targets, passive). Favored Enemy: Humanoids (every bandit in the Tavern Brawl). Natural Explorer: Forest. Variant Human bonus feat: Sharpshooter (-5/+10 trade, ignore cover). 4 known Ranger spells across L1-L2 slots (4/2). Added v2.18.3 to unlock Phase B work for the Hunter's Mark concentration buff + Sharpshooter per-attack uplift. |
| **Magnus Hexbinder** | Warlock 5 (The Fiend) | Bronze Dragonborn | GM | Eldritch-blaster caster; Eldritch Blast cantrip (+6 / 2 beams of 1d10+3 force at 120 ft, Agonizing Blast adds CHA mod) + Quarterstaff (+4 / 1d6+1) as a melee fallback. CHA 17, AC 14 (studded leather + DEX), HP 38. **Pact Magic**: 2/2 L3 slots **short-rest** refresh (the unique-to-Warlock spell-slot table — distinct from every other class). Iconic spells: Hex (concentration, +1d6 necrotic on weapon/spell hits) + Counterspell + Fireball (subclass-granted from The Fiend). Three Eldritch Invocations at Lv 5: Agonizing Blast / Devil's Sight / Mask of Many Faces. Dark One's Blessing (passive: temp HP on kill = CHA mod + Warlock level = 8). Bronze Dragonborn lightning breath weapon 2d6 1/short. Added v2.18.4 to **wrap Phase A** (12/12 PHB classes) and unblock Phase B work for Pact Magic short-rest slot refresh + Hex concentration buff + Dark One's Blessing temp-HP-on-kill trigger. |

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

1. Kael Brightleaf — **init 20**
2. Garrik Ironside — init 19
3. Grixxa (Goblin Captain) — init 18
4. Vex (Bandit Captain) — init 17
5. Lyra Sunstrider — init 16
6. Pip Quickfingers — init 15
7. Brother Tavik — init 14
8. Thalindra Moonwhisper — init 13
9. Sir Caelan Lightbringer — init 12
10. Thug — init 11
11. Zara Emberfire — init 10
12. Bandit Alpha — init 9
13. Mira Greenleaf — init 8
14. Bandit Beta — init 7
15. Krieger Stonefist — init 6
16. Bandit Gamma — init 5
17. Rowan Quickbow — init 4
18. Magnus Hexbinder — init 3

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

## Testing

The repo ships an HTTP + WebSocket click-through harness under
`tests/harness/` that exercises every interactive endpoint on the
character sheet + mini-sheet and asserts on the resulting WS
broadcasts. See `docs/plans/test-harness.md` for the design.

To run against a live demo stack:

```bash
# One-time: install dev deps (pytest + plugins + httpx + websockets)
pip install -r requirements-dev.txt

# Run the harness (requires the demo stack at localhost:8013):
make test-harness
# or:
pytest tests/harness/ -v
```

Override the target stack via env vars (defaults shown):

- `HARNESS_BASE_URL=http://localhost:8013`
- `HARNESS_WS_TIMEOUT=2.0` (per-test WS receive timeout)

Phase 1 + 1.5 cover every action-bearing endpoint (`/attack`,
`/cast_spell`, `/use_feature`, `/use_item`, `/use_lay_on_hands`,
`/use_bardic_inspiration`, `/move`, `/roll`) + smoke (42 tests,
~20 s). Phase 2 (v2.12.2) wires this into GitHub Actions on every
PR + push to main/dev via `.github/workflows/test-harness.yml` —
the workflow boots a clean docker compose stack with `DEMO_MODE=true`,
waits for `/healthz`, runs pytest, and uploads JUnit XML + HTML
reports as artifacts. Phase 4 (v2.13.0) adds a Playwright UI
harness under `tests/harness_ui/` that drives a real headless
chromium to catch DOM-level regressions (the canonical case: v2.7.3
weapon-attack-toast miss). One-time setup:

```bash
pip install -r requirements-dev.txt
playwright install chromium       # ~250 MB; one-time
make test-harness-ui
```

The UI harness is kept separate from the HTTP+WS one (`make test-
harness`) because the browser overhead means each test takes
seconds instead of milliseconds. Phase 4.5 (v2.13.1) wires this
into CI as a parallel `harness-ui` job alongside the existing
`harness` job in `.github/workflows/test-harness.yml` — both run
on every PR + push to main/dev; the Playwright binaries are cached
between runs so cache-hit cost is ~5 s extra per run vs. ~30-45 s
on a cold cache. See the plan doc for the roadmap.

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
