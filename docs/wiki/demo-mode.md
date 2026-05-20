# Demo mode

**Audience:** operators standing up the public demo deployment OR debugging the seeded campaign.
**Version stamp:** v2.43.21.

Demo mode is the operational toggle that turns a SimpleVTT instance into a self-resetting public sandbox. With `DEMO_MODE=true`, the lifespan handler periodically wipes a known set of demo-tagged records and re-seeds a complete sample campaign — three users, twelve PCs (one per PHB class at Lv 5), a tavern map, a few monsters, a pre-built encounter, and a smattering of roll-log history.

The goal: anyone can visit the demo URL, log in as `demo-gm@example.com / demopass`, click around for an hour, and never break the next visitor's experience.

**Do not enable on a production instance.** The reset is *surgical* (deletes only records matching demo emails / slugs) so it won't nuke real campaigns by accident — but it WILL erase the demo accounts' state every hour. If a real GM happened to claim the email `demo-gm@example.com`, their work would be wiped. Reserve demo mode for instances that exist purely to show off the app.

## Quick start

Edit `.env`:

```diff
- DEMO_MODE=false
+ DEMO_MODE=true
- DEMO_RESET_INTERVAL_MINUTES=60
+ DEMO_RESET_INTERVAL_MINUTES=60    # keep default, or tune (clamped 5–1440)
- DEMO_RESET_ON_BOOT=true
+ DEMO_RESET_ON_BOOT=true            # seed on container start so first visitor sees clean state
- DEMO_CREDENTIALS_VISIBLE=true
+ DEMO_CREDENTIALS_VISIBLE=true      # show the three logins on the login page
```

Then rebuild + restart:

```bash
docker compose up -d --build app
```

Watch the logs:

```bash
docker compose logs -f app
# → "Demo mode enabled — interval 60 min, reset_on_boot=true"
# → "Demo wipe + reseed completed in 1.2s — 3 users, 1 campaign, 12 characters, 9 tokens"
```

Open `http://localhost:8013/` — the top of every page now shows a non-dismissible **🧪 Demo Mode** banner with a live countdown to the next reset. The login page shows the three pre-baked credentials.

## What's seeded

The exact contents of the seeded demo (as of v2.43.21):

| Entity | Count | What's in it |
|--------|------:|--------------|
| **Users** | 3 | `demo-gm@example.com` (the GM), `demo-alice@example.com`, `demo-bob@example.com`. All password `demopass`. |
| **Campaign** | 1 | "Demo Campaign". GM owns; Alice + Bob are members. |
| **Maps** | 1 | "Tavern" (bundled placeholder PNG at `app/static/demo/maps/`). Set as the active map. |
| **Characters** | 12 | One demo PC per PHB class at Lv 5: Pip Quickfingers (Rogue), Thalindra Moonwhisper (Wizard), Brother Tavik Stonebrow (Cleric), Sir Caelan Lightbringer (Paladin), Lyra Sunstrider (Bard), Mira Greenleaf (Druid), Garrik Ironside (Fighter), Kael Brightleaf (Ranger), Zara Emberfire (Sorcerer), Krieger Stonefist (Barbarian), Rowan Quickbow (Ranger variant), Magnus Hexbinder (Warlock). Full D&D 5e sheets (abilities, skills, spells, inventory, attacks). |
| **Tokens** | 9 | Player PCs + some monster tokens. Pre-placed on the tavern map. |
| **Token templates** | 4 | Bandit + Goblin Captain + a couple of placeholder monsters. Goblin Captain is a homebrew template (authored end-to-end via the v2.3.22 structured editor). |
| **Encounter** | 1 | Pre-built encounter with the 9 tokens + pre-rolled initiative — load it for the first session. |
| **Homebrew** | 2 files | One custom feat ("Lucky Strike"), one custom monster ("Goblin Captain"). JSON files in the homebrew volume at `homebrew_data/campaign-<demo_id>/`. |
| **Roll-log history** | 8–10 | Sample rolls so the right drawer isn't empty on first load. |

Total seed time on a typical host: ~1–2 seconds. The reset wraps a single SQL transaction around the wipe + reseed; homebrew JSON file writes happen after commit (best-effort).

## How the reset works

`app/demo_scheduler.py` registers a FastAPI lifespan handler that spawns a background asyncio task. The task loops:

```
while True:
    await asyncio.sleep(DEMO_RESET_INTERVAL_MINUTES * 60)
    await reset_and_reseed(db)
```

`reset_and_reseed(db)` in `app/demo_seed.py`:

1. **Wipe** — deletes all records matching deterministic demo patterns:
   - Users with email matching `demo-*@example.com`
   - Campaign with slug `demo-campaign` (and cascading: tokens, characters, encounters, audio playlists, roll history)
   - Homebrew files under `campaign-<demo_id>/`
   - `campaigns.active_map_id` is nulled BEFORE deleting maps (the v2.3.5 FK ordering fix)
2. **Re-seed** — calls each `seed_*` helper in order: `seed_users` → `seed_campaign` → `seed_maps` → `seed_token_templates` → `seed_characters` → `seed_tokens` → `seed_npc_tokens` → `seed_encounter` → `seed_roll_history` → `seed_homebrew_files`.

The whole wipe + reseed runs inside one SQL transaction (homebrew file writes happen after commit, so a half-completed file write doesn't roll the DB back).

Why surgical wipe instead of `TRUNCATE everything`? Safety. If `DEMO_MODE=true` is accidentally set on a production deploy, the surgical wipe touches only demo-tagged rows — no real campaigns are affected (none of them match the demo patterns). A `TRUNCATE` would have nuked everything.

## Env vars

| Var | Default | Range | What it does |
|-----|---------|-------|--------------|
| `DEMO_MODE` | `false` | bool | Master switch. `false` → all other demo vars ignored. |
| `DEMO_RESET_INTERVAL_MINUTES` | `60` | 5–1440 | How often the lifespan handler runs the wipe + reseed. Clamped server-side. |
| `DEMO_RESET_ON_BOOT` | `true` | bool | Run the wipe + reseed once at process start so the first visitor after a restart sees clean state. Set `false` for development if you want your manual edits to survive restart. |
| `DEMO_CREDENTIALS_VISIBLE` | `true` | bool | Show the three demo logins on the login page (`/login` shows a "Use demo credentials" auto-fill box). Set `false` to keep the demo URL public but require visitors to know the password. |

All four vars live in `.env`. The compose file forwards them into the `app` container (v2.3.2 fix — original v2.3.0 forgot the forwards, so `DEMO_MODE=true` had no effect inside Docker).

## What demo users can do (and can't)

The three demo accounts have full access to the demo campaign:

- ✅ Roll dice, cast spells, attack monsters
- ✅ Move tokens, save snapshots, load encounters
- ✅ Edit characters, change themes / fonts / portraits
- ✅ Upload custom token images (goes to the normal upload volume, orphans on next reset)
- ✅ Author homebrew content (writes to `homebrew_data/campaign-<demo_id>/`, wiped on next reset)

They **can't**:

- ❌ See or affect non-demo campaigns (none exist on a pure demo instance, but the auth model still applies)
- ❌ Promote themselves to admin (no `ADMINS=` match)
- ❌ Persist anything past the next reset

## On-demand reset

There's an admin endpoint to force a reset between scheduled cycles:

```bash
# Logged in as an admin (any user whose email is in ADMINS=)
curl -X POST http://localhost:8013/admin/demo/reset \
     -H "Cookie: session=<your session cookie>"
# → {"ok": true, "reset_at": "2026-05-20T19:42:10Z", "next_reset_at": "2026-05-20T20:42:10Z"}
```

The countdown banner updates on the next page load.

Use cases: a demo user broke something visible to the next visitor, or you want to test a fresh-seed scenario without waiting an hour.

## Safety guards

Several checks protect against accidental demo-mode-on-production deployments:

1. **The surgical wipe.** Even if `DEMO_MODE=true` is set on a production instance, the wipe only deletes records matching demo patterns. Real campaigns aren't tagged with `demo-*` emails or the `demo-campaign` slug, so they're untouched.
2. **The non-dismissible banner.** Every page on a demo-mode instance carries a 🧪 Demo Mode banner with the countdown. Anyone visiting the site sees it immediately — they won't mistake it for a production instance.
3. **The login page warning.** If `DEMO_CREDENTIALS_VISIBLE=true`, the login page literally shows the credentials. Operators reflexively turn this off on anything that isn't the demo.
4. **The log line at startup.** Every container start logs "Demo mode enabled — interval N min, reset_on_boot=true/false". A grep in your logs catches accidentally-promoted environments.

## Bundled assets

Demo images ship at `app/static/demo/`:

- `app/static/demo/maps/tavern.png` — the demo tavern map
- `app/static/demo/tokens/rogue.png` — Pip's portrait
- `app/static/demo/tokens/wizard.png` — Thalindra's portrait

These are baked into the Docker image, **not** in the upload volume. Demo records reference them by relative path. Reset doesn't touch the upload volume (demo users' uploads orphan there until a manual cleanup pass).

Other demo characters use color-swatch portraits (no PNG) — the v2.3.22 / v2.3.25 enrichments added more characters but didn't ship per-character PNGs.

## Per-visitor ephemeral accounts (deferred)

Today, multiple simultaneous visitors share the same three demo accounts. If two people are logged in as `demo-gm@example.com` from different browsers, they'll see each other's actions in real time.

Per-visitor ephemeral accounts (each visitor gets a unique cookie-bound session with their own copies of the demo PCs) was explicitly deferred from day one. The trade-off: simpler implementation + shared-state surprises. The current model is "two people demoing at the same time will see each other" — sometimes a feature (multiplayer demo!), sometimes confusion. Filed for future enhancement.

## Rate limiting (deferred)

Also explicitly deferred. The expectation: if the public demo URL ever attracts enough traffic to need rate limiting, put Cloudflare or equivalent at the edge. The app itself doesn't ship a built-in rate limiter.

## Troubleshooting

**Demo mode doesn't seem active.** Check `docker compose logs app | grep -i demo` — you should see "Demo mode enabled" at startup. If not, the env var didn't reach the container. Verify `docker compose exec app env | grep DEMO_MODE` shows `DEMO_MODE=true`. The v2.3.2 fix forwards the env vars from `.env` to the `app` container — if you're on a pre-v2.3.2 build, upgrade.

**Reset didn't fire at the scheduled time.** Check the lifespan task is still alive: `docker compose logs app | grep -i "demo wipe"` should show a "completed in Xs" line every interval. If not, the task may have died on an exception — restart the container.

**Demo users' actions persist past the reset.** They shouldn't — every demo character is tagged with the demo emails / slugs. If you see persistence: (a) check that the user's email matches the demo pattern (`demo-*@example.com`), (b) check that the campaign slug is `demo-campaign`, (c) file an issue with the exact data that survived.

**I want to extend the seed.** Edit `app/demo_seed.py`. Each `seed_*` helper is idempotent (running it twice produces the same result), so you can iterate by calling individual helpers from a Python shell against the demo DB. Re-deploys pick up the new seed.

**Multiple visitors are colliding.** Expected — per the design note above. If it becomes a real problem, the per-visitor-ephemeral-accounts work was explicitly deferred but the design is sketched in `docs/plans/demo-mode.md`.

## Where the code lives

- **Scheduler:** `app/demo_scheduler.py` — registers the lifespan handler that spawns the reset task.
- **Seeder:** `app/demo_seed.py` — `reset_and_reseed(db)` orchestration + the eight `seed_*` helpers.
- **Demo-credentials box on login:** `app/templates/login.html` — gated on `DEMO_CREDENTIALS_VISIBLE`.
- **Countdown banner:** `app/templates/_demo_banner.html` — non-dismissible, JS countdown that reloads at T+0.
- **Admin reset endpoint:** `app/routes/admin_routes.py` — `POST /admin/demo/reset`, admin-only.
- **Env-var parsing:** `app/config.py` — pydantic settings + clamping for `DEMO_RESET_INTERVAL_MINUTES`.
- **Bundled assets:** `app/static/demo/` — maps, token PNGs.
- **Design rationale:** `docs/plans/demo-mode.md` — the original implementation plan + tradeoffs.

## Related guides

- **[First-run setup](first-run-setup.md)** — the standard (non-demo) deploy walkthrough.
- **[Architecture overview](architecture-overview.md)** — for the lifespan-handler + asyncio-task context.
- **[Endpoint catalog](endpoint-catalog.md)** — `/admin/demo/reset` lives there.
- **`docs/plans/demo-mode.md`** — the design doc with the deferred-features section + the tradeoff narrative.
