# Demo Mode — Design Plan

**Status:** Shipped in **v2.3.0** (originally targeted at v2.1.0 in this plan but landed later as part of the v2.3 train).
Subsequent fixes + enrichments: **v2.3.1** (Starlette 1.0 compat), **v2.3.2** (`DEMO_*` env vars forwarded to compose container), **v2.3.5** (demo wipe FK ordering fix), **v2.3.22** (homebrew Goblin Captain authored end-to-end via the new structured editor), **v2.3.25** (GM gets a Cleric character).
**Tracked in:** [`TODO.md`](../../TODO.md) → Development & Testing → Demo Mode.

---

## Implementation status

(Annotation pass v2.3.26 — audited against CHANGELOG / code.)

- ✅ **Reset mechanism** — done in v2.3.0. `app/demo_scheduler.py` registers a FastAPI startup hook that runs `reset_and_reseed()` in-process every `DEMO_RESET_INTERVAL_MINUTES` minutes (clamped 5–1440, default 60). `DEMO_RESET_ON_BOOT=true` seeds on container start.
- ✅ **Surgical tag-based wipe strategy** — done in v2.3.0. Delete-by-email / delete-by-slug; no `is_demo` column needed. Fixed FK ordering bug at v2.3.5 (`campaigns.active_map_id` had to be nulled before deleting maps).
- ✅ **Seed module** — done in v2.3.0. `app/demo_seed.py` with all `seed_*` helpers + `reset_and_reseed(db)` orchestration. Enriched in v2.3.22 (Goblin Captain) and v2.3.25 (GM Cleric); now seeds 3 characters / 9 tokens / 4 token templates.
- ✅ **Bundled demo assets** — done in v2.3.0. `app/static/demo/maps/tavern.png`, `tokens/rogue.png`, `tokens/wizard.png` (no audio shipped — `tavern.ogg`/`battle.ogg` were skipped at the original landing per the v2.3.0 release notes). Goblin Captain and Cleric use color swatches; no PNGs yet.
- ✅ **Demo banner with countdown** — done in v2.3.0. `app/templates/_demo_banner.html` non-dismissible top banner with JS countdown that reloads the page at T+0.
- ✅ **Demo credentials box on login** — done in v2.3.0. Gated on `DEMO_CREDENTIALS_VISIBLE=true`.
- ✅ **`POST /admin/demo/reset`** — done in v2.3.0. Admin-only on-demand reset endpoint in `app/routes/admin_routes.py`.
- ✅ **Config vars** — done in v2.3.0. `DEMO_MODE`, `DEMO_RESET_INTERVAL_MINUTES`, `DEMO_RESET_ON_BOOT`, `DEMO_CREDENTIALS_VISIBLE` in `app/config.py` + `.env.example`. Compose forwarding fixed in v2.3.2 (the original landing forgot to forward the env vars from `.env` into the `app` container, so `DEMO_MODE=true` had no effect inside Docker).
- ✅ **Safety guards** — done in v2.3.0. Documented in the changelog as part of the lifespan handler safeguards.
- ⏸ **Per-visitor ephemeral accounts** — explicitly deferred from day one. Three shared demo accounts; multiple simultaneous visitors share session state.
- ⏸ **Rate limiting at the demo URL** — explicitly deferred from day one. Cloudflare or equivalent at the edge if traffic becomes a problem.
- ⏸ **Demo-specific feature flags** — explicitly out of scope from day one. Still out of scope.

---

---

## Goal

A `DEMO_MODE=true` deployment that ships with a complete sample campaign and **automatically resets every hour**, so the public can try SimpleVTT at a stable URL without standing up their own instance.

The hourly reset is the load-bearing constraint — it informs the safety model (anything a demo user touches must be reversible), the seed data shape (small enough to re-seed in <2 seconds), and the persistence model (no demo content writes to the upload volume).

---

## Architectural decisions

### 1. Reset mechanism — in-process asyncio task

A FastAPI lifespan handler spawns a background task that loops `await asyncio.sleep(interval); reset()` for the lifetime of the app process.

**Why over alternatives:**

- **Cron sidecar container** — works but doubles the deploy surface (`docker compose up` now needs two services). Wins only if resets must survive an app crash, which doesn't matter for a demo.
- **Per-request lazy reset** — every request checks `now - last_reset > interval`. Free for idle servers but adds a DB hit to every request and races under concurrency.
- **APScheduler** — overkill for one job.

**Tradeoff:** if the app crashes mid-hour, the next reset is delayed until startup + interval. Acceptable for a demo. Mitigated by `DEMO_RESET_ON_BOOT=true` (default), which resets on startup so the first visitor after a restart sees a clean slate.

**Configurable:** `DEMO_RESET_INTERVAL_MINUTES=60` (default 60, min 5, max 1440) so operators can tune.

### 2. Wipe strategy — surgical (tag-based), not full-DB

Reset deletes only records tagged as demo (deterministic emails like `demo-gm@example.com`, campaign slug `demo-campaign`, character slugs `demo-*`, homebrew scope `campaign-<demo_id>`), then re-seeds.

**Why over full-DB wipe:** safety. If `DEMO_MODE=true` is accidentally set on a production deploy, surgical wipe touches only demo-tagged rows (none exist in prod → no-op). Full wipe would nuke real campaigns.

**Implementation:** rather than adding `is_demo` to every model, use the deterministic naming patterns above and delete by slug/email pattern. Less schema churn.

### 3. Seed data — single idempotent module

`app/demo_seed.py` exposes:

- `seed_users(db) -> dict[str, User]` — returns dict keyed by role: `gm`, `alice`, `bob`
- `seed_campaign(db, gm, players) -> Campaign`
- `seed_maps(db, campaign) -> list[Map]` — references bundled images at `app/data/demo/maps/`
- `seed_characters(db, campaign, players) -> list[Character]` — one full D&D 5e sheet per player
- `seed_tokens(db, campaign, map_, characters)` — player tokens
- `seed_npc_tokens(db, campaign, map_) -> list[Token]` — monster tokens, no `character_id`, HP from the shipped SRD JSON
- `seed_homebrew_files(campaign)` — writes a couple of homebrew JSON files to the homebrew Docker volume
- `seed_encounter(db, campaign, map_, tokens, npc_tokens)` — bundles all 7 tokens + pre-rolled initiative
- `seed_roll_history(db, campaign, characters)` — 8-10 sample rolls for the log
- `reset_and_reseed(db)` — orchestration: wipe → call each `seed_*`

Single SQL transaction wraps the wipe + reseed; homebrew file writes happen after commit (best-effort; the next reset overwrites any partial write).

### 4. Bundled demo assets — read-only, image-baked

Demo images ship at `app/data/demo/` (inside the image, **not** in the upload volume). Demo records reference these paths directly. The upload-volume code path is never hit by demo data, so resets don't have to touch the volume.

If demo users upload files mid-session, those uploads go to the normal upload volume tagged with their user id. Reset deletes the demo users → uploaded files orphan → an optional cleanup pass after reset can sweep them.

This sidesteps the broader bundled-art-assets license question (separate TODO item). The demo ships with one or two placeholders you have rights to; the bundled-art project remains unblocked.

---

## Seed data scope

| Entity | Count | Notes |
|---|---:|---|
| Users | 3 | `demo-gm@example.com` / `demo-alice@example.com` / `demo-bob@example.com`. All password `demopass`. |
| Campaign | 1 | "Demo: The Sundered Vault" — GM owns, both players are members |
| Maps | 1 | "Tavern" (bundled placeholder PNG) |
| Characters | 2 | Alice = Rogue 5, Bob = Wizard 5. Full D&D 5e sheets (abilities, skills, spells/cantrips, inventory, weapon attacks) |
| Player tokens | 2 | One per character, placed near the tavern door |
| NPC tokens | 5 | See table below — placed near the bar opposite the PCs |
| Audio tracks | 2 | "Tavern Ambient" + "Battle Music" (short placeholder OGGs) |
| Homebrew | 2 files | One custom feat ("Lucky Strike"), one custom monster ("Goblin Captain") — JSON files in the homebrew volume under `campaign-<demo_id>/` |
| Roll history | 8 rolls | Mix of attack rolls, saves, and skill checks across the last hour |
| Encounters | 1 | "Tavern Brawl" — references the map, all 7 tokens, pre-rolled initiative |

Total seed time target: **<2 seconds** on a cold DB.

### NPCs in the Tavern Brawl encounter

All five NPCs reference monsters already shipped under `app/data/local/dnd5e/monsters/` — no new content authoring is needed. Difficulty is "Medium" by 5e XP budget against Rogue 5 + Wizard 5: survivable but engaging.

| Token name | Source slug | CR | Role |
|---|---|---:|---|
| Bandit Captain "Vex" | `bandit-captain` | 2 | Leader — gives the GM something interactive to RP |
| Bandit (Alpha) | `bandit` | 1/8 | Mook |
| Bandit (Beta) | `bandit` | 1/8 | Mook |
| Bandit (Gamma) | `bandit` | 1/8 | Mook |
| Thug | `thug` | 1/2 | Heavy backup |

NPC tokens render with the existing fallback monogram avatar — no bundled NPC art needed. If art lands later, drop PNGs into `app/data/demo/tokens/` and update the seed.

---

## Files to add

- **`app/demo_seed.py`** (~400 LoC) — constants for demo emails / slugs / password hash, `wipe(db)`, all `seed_*` functions, `reset_and_reseed(db)`.
- **`app/demo_scheduler.py`** (~80 LoC) — `start_demo_scheduler(app)` registered in the lifespan handler when `DEMO_MODE=true`. `_reset_loop` wraps each reset in `try/except` so a single failure doesn't kill the loop. Logs row counts at INFO.
- **`app/data/demo/`** — bundled assets:
  - `maps/tavern.png`
  - `tokens/rogue.png`, `tokens/wizard.png`
  - `audio/tavern.ogg`, `audio/battle.ogg`
  - `README.md` naming each asset's source and license
- **`app/templates/_demo_banner.html`** — persistent banner with a JS countdown that reloads the page at T+0 so users see fresh state immediately.

---

## Files to modify

### `app/config.py` (`Settings`)
```python
demo_mode: bool = False
demo_reset_interval_minutes: int = 60  # clamped to [5, 1440]
demo_reset_on_boot: bool = True
demo_credentials_visible: bool = True  # show pw on login page when demo_mode
```

### `app/main.py` (lifespan handler)
```python
if settings.demo_mode:
    if settings.demo_reset_on_boot:
        with SessionLocal() as db:
            reset_and_reseed(db)
    start_demo_scheduler(app)
```

### `app/templates/base.html`
Include the demo banner partial when `demo_mode` is true. Wire `demo_mode` through the global template context via `app/templates.py`.

### `app/templates/login.html`
When `demo_credentials_visible` is true, render a small box below the login form listing the three accounts and the shared password.

### `app/routes/admin_routes.py`
Add `POST /admin/demo/reset` — admin-only endpoint that triggers `reset_and_reseed(db)` immediately. Returns a redirect with a flash message. Lets ops trigger an on-demand reset without restarting the container.

### `.env.example`
Add the four `DEMO_*` vars with `false` / `60` defaults and comments.

### `README.md`
New "Demo Mode" section: how to enable, what's seeded, reset cadence + how to override, manual reset endpoint, safety notes.

### `docker-compose.yml`
Add a commented-out demo block in the `app` service env so operators can flip it on.

### `app/version.py` + `CHANGELOG.md`
MINOR bump to **2.1.0**.

---

## Safety guards

1. **Demo-aware destructive endpoints.** When `DEMO_MODE=true`, admin-side deletes of demo users / the demo campaign redirect with "Demo records restore on next reset; not deleting now." Non-demo records are unaffected (in case real admins exist).
2. **Banner is non-dismissible.** No `localStorage` opt-out. The banner is the only safeguard against an operator forgetting `DEMO_MODE` is on in production.
3. **Reset is transactional.** Wipe + reseed run in a single SQL transaction; a failed reseed rolls back the wipe. Homebrew JSON writes happen after commit — partial writes are harmless because the next reset overwrites them.
4. **Concurrency is documented, not prevented.** A user mid-action when reset fires sees their next request 404 (their session row is gone) and gets redirected to login. Acceptable for a demo; documented in the banner.

---

## Verification

1. **Fresh boot** — `DEMO_MODE=true DEMO_RESET_ON_BOOT=true docker compose up`. Logs show `"demo reset complete: 3 users, 1 campaign, 7 tokens, ..."`. Login as `demo-gm` works.
2. **Banner visible** — every page shows the demo banner with a ticking countdown.
3. **Reset cycle** — set `DEMO_RESET_INTERVAL_MINUTES=2`, modify the demo campaign (add a token, delete a character), wait 2 minutes, refresh. Campaign returns to seed state.
3a. **Encounter contains all combatants** — load "Tavern Brawl" as GM. 7 tokens render: 2 PCs near the door, 5 NPCs near the bar. Initiative tracker shows 7 pre-rolled entries.
3b. **NPC stat blocks resolve** — click the Bandit Captain token. Stat block popup pulls live data (HP 65, AC 15, Multiattack) from `app/data/local/dnd5e/monsters/bandit-captain.json`.
3c. **Reset restores NPCs** — kill a Bandit (set HP to 0), wait for reset, confirm the Bandit is back at full HP in its starting position.
4. **Manual reset endpoint** — `POST /admin/demo/reset` triggers immediate reset; banner countdown resets.
5. **Non-demo deploy unaffected** — leave `DEMO_MODE` unset, boot the app, confirm no scheduler runs, no banner, no demo records exist.
6. **Safety guard** — as admin, try to delete `demo-gm@example.com`. Confirm redirect with the "restores on reset" message; user still exists.
7. **Reset under load** — log in as `demo-alice`, start a roll, fire reset mid-flight via `/admin/demo/reset`. Alice's next request redirects to login; logging back in shows seed state.
8. **Homebrew survives reset boundary** — seeded homebrew JSON files reappear after reset (not just DB rows).

---

## Out of scope (deferred)

- **Per-visitor ephemeral accounts.** Multiple simultaneous demo visitors share the three accounts → session contention. Acceptable for v1; a future enhancement could mint one-time-use credentials per visitor.
- **Rate limiting at the demo URL.** Bots will discover it. Add Cloudflare/equivalent at the edge if traffic becomes a problem; not in this plan.
- **Demo-specific feature flags.** No "this feature only in demo mode" plumbing. Demo just shows the full product.
- **Bundled art audit.** Demo ships with one or two placeholders the operator has rights to; the broader bundled-art-assets TODO item is unchanged.

---

## Commit strategy

Single MINOR bump to **2.1.0** because all pieces are one coherent feature (~600 LoC + a few placeholder assets). The diff is large but reviewable as one feature.

If you'd prefer to split:
- **2.1.0** — scheduler + seed module + reset endpoint (no UI changes)
- **2.2.0** — demo banner + login credentials UI
- **2.3.0** — safety guards on admin destructive endpoints

Three smaller commits would be easier to review but ship the feature in stages, leaving the banner + safety guards missing between commits.
