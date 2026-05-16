# Changelog

All notable changes to SimpleVTT are documented in this file.
Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) — Versioning: [SemVer](https://semver.org/spec/v2.0.0.html).

The current version is the topmost release section below.
Application version and database schema version are also published at runtime by `GET /version` and `GET /healthz`, and are defined as constants in [`app/version.py`](app/version.py).

> For pre-2.0.0 history, see [CHANGELOG_v1.md](CHANGELOG_v1.md).

---

## [2.3.4] - 2026-05-15

**Schema version:** 52
**Commit summary:** Fix `APP_DEFAULT_THEME` being ignored for newly created users — the `User.theme` column had a hardcoded Python-side `default="dark"`, so every new user (registration, Google SSO, demo seed) was inserted with `theme="dark"` regardless of the operator's `APP_DEFAULT_THEME`, and the login-as-demo-user case fell through to the per-user value instead of the configured default.
**Description:** Follow-up to 2.3.3. Symptom: after setting `APP_DEFAULT_THEME=sepia` and confirming logged-out pages render `data-theme="sepia"`, signing in as a demo user (or any newly created user) still rendered `data-theme="dark"`. Root cause: `app/models.py:56` set `default="dark"` on the `User.theme` column — a literal Python default — so every `User()` insert without an explicit `theme=` argument got `"dark"`. Template at `app/templates/base.html:3` then resolves `user.theme if user and user.theme else APP_DEFAULT_THEME`, picking the stored `"dark"` over the configured default. Fix swaps the Python-side `default=` to a callable `_default_user_theme` that lazily reads `get_settings().default_theme` at INSERT time (not import time, to avoid circular imports). `server_default="dark"` stays a static literal because it's rendered into `CREATE TABLE` — it's only a safety net for raw inserts, which the app does not perform. The next demo reset (or on-boot reseed) deletes and recreates the demo users, so they'll come back with the configured theme.

### Fixed
- `app/models.py` — `User.theme` Python-side default is now a callable that returns `get_settings().default_theme`. Affects every new user creation path (local register, Google SSO callback, demo seed). Existing users are unchanged.

### Notes
- Existing users in production keep whatever theme is already stored on their row. Only new inserts pick up the configured default.
- Redeploy with `docker compose up -d --build app` to pick up the model change; on the demo deployment the on-boot reseed (when `DEMO_RESET_ON_BOOT=true`) will recreate the three demo users with the configured theme.

---

## [2.3.3] - 2026-05-15

**Schema version:** 52
**Commit summary:** Fix `APP_DEFAULT_THEME` never reaching the `app` container (same root cause as the 2.3.2 demo-var fix) and change the in-code default from `dark` to `sepia` so a stock deploy lands on the project's preferred fantasy theme.
**Description:** Follow-up to 2.3.2: `APP_DEFAULT_THEME` is consumed in `app/config.py` and exposed as a Jinja global at `app/templates.py:29` (used by `base.html` to set `data-theme` for logged-out and brand-new users), but it was missing from the `app` service's `environment:` allow-list in both `docker-compose.yml` and `docker-compose.ghcr.yml`. So `APP_DEFAULT_THEME=sepia` in `.env` had no effect — every logged-out page rendered `data-theme="dark"`. Fix forwards the var with `${APP_DEFAULT_THEME:-sepia}` (matching `.env.example`) and bumps the Python-side fallback from `"dark"` to `"sepia"` in both spots in `app/config.py` so a deploy with no `.env` value at all agrees with the compose default.

### Fixed
- `docker-compose.yml` — forward `APP_DEFAULT_THEME` from `.env` into the `app` container with a `sepia` fallback.
- `docker-compose.ghcr.yml` — same, for the GHCR-image variant.

### Changed
- `app/config.py` — `default_theme` field default and `get_settings()` env fallback both updated from `"dark"` to `"sepia"`. Users who explicitly set their theme in `/settings` are unaffected (`base.html` uses `user.theme` when present); only logged-out pages and brand-new users without a theme choice see the change.

### Notes
- Redeploy with `docker compose up -d --build app` — env-var changes only take effect on container recreation.

---

## [2.3.2] - 2026-05-15

**Schema version:** 52
**Commit summary:** Fix demo-mode env vars never reaching the `app` container — `docker-compose.yml` and `docker-compose.ghcr.yml` enumerate the env vars they forward, and the four `DEMO_*` vars added in 2.3.0 were omitted from that list, so `DEMO_MODE=true` in `.env` had no effect inside the container.
**Description:** Reported on https://vtt-demo.iptater.net: `DEMO_MODE=true` and `DEMO_CREDENTIALS_VISIBLE=true` in `.env`, but the login page renders no banner and no credentials box. Both compose files declare `environment:` as an explicit allow-list rather than `env_file:`, so any var not listed there is simply not visible to the container. `app/config.py` then reads `os.environ.get("DEMO_MODE")`, gets `None`, falls back to `False`, and the Jinja globals (`DEMO_MODE`, `DEMO_CREDENTIALS_VISIBLE`) wired in `app/templates.py` evaluate to `False` for every render — gating off both the `_demo_banner.html` include in `base.html` and the `{% if DEMO_MODE and DEMO_CREDENTIALS_VISIBLE %}` block in `login.html`. Fix is mechanical: add the four `DEMO_*` keys to the `app` service's `environment:` block in both compose files, with `${VAR:-default}` fallbacks matching `.env.example`.

### Fixed
- `docker-compose.yml` — forward `DEMO_MODE`, `DEMO_RESET_INTERVAL_MINUTES`, `DEMO_RESET_ON_BOOT`, `DEMO_CREDENTIALS_VISIBLE` from `.env` into the `app` container.
- `docker-compose.ghcr.yml` — same four `DEMO_*` vars added to the `app` service.

### Notes
- After pulling this fix, redeploy with `docker compose up -d --force-recreate app` (or the `ghcr.yml` equivalent) — env-var changes only take effect on container recreation, not a plain `restart`.
- `APP_DEFAULT_THEME` is similarly missing from both compose files (a separate pre-existing bug — the live site renders `data-theme="dark"` regardless of the value in `.env`). Not fixed here to keep this commit scoped to the reported demo issue; tracked as a follow-up.

---

## [2.3.1] - 2026-05-16

**Schema version:** 52
**Commit summary:** Fix two pre-existing Starlette 1.0 incompatibilities that broke *every* page render (not specific to demo mode but surfaced when demo mode was tested). One — Starlette 1.0 removed the legacy `TemplateResponse(name, context)` signature in favor of `TemplateResponse(request, name, context)`. Two — Starlette 1.0's `Jinja2Templates` no longer wires `ChainableUndefined` by default, so `{{ user.foo or '' }}` on the logged-out login page now raises `UndefinedError`.
**Description:** When this codebase's environment upgraded to Starlette 1.0 (released 2026), every `TemplateResponse(name, context)` call site started passing the *context dict* as the template *name* parameter, which crashed inside Jinja's template cache lookup with `TypeError: unhashable type: 'dict'`. The 21 affected call sites are all in `app/routes/*.py`. Rather than touch every one (and risk missing one), this fix wraps `templates.TemplateResponse` in a thin shim that detects the legacy signature (first arg is a `str`), extracts `context["request"]`, and forwards to the new signature. Separately, Starlette 1.0 also drops the default `ChainableUndefined` setup, so `{{ user.theme }}` etc. on the login/register pages crashed with `UndefinedError`. Set `templates.env.undefined = ChainableUndefined` to restore the chain-friendly behavior every template here was written against.

### Fixed
- `app/templates.py` — wraps `templates.TemplateResponse` with `_compat_template_response` that accepts both the legacy `(name, context, ...)` and the new `(request, name, context, ...)` signatures. Lets us upgrade Starlette without sweeping every call site immediately; the shim is a stable forward-compatible layer.
- `app/templates.py` — sets `templates.env.undefined = ChainableUndefined` so `{{ user.foo or '' }}` on logged-out pages evaluates to `''` instead of raising.

### Notes
- Both bugs existed before demo mode but only surfaced when demo mode was tested because demo mode is the first scenario that lands an unauthenticated visitor on the login page from a fresh install.
- Long-term: sweep the 21 `TemplateResponse(name, context)` call sites to the new `(request, name, context)` form and drop the shim. Filed as a follow-up.

---

## [2.3.0] - 2026-05-15

**Schema version:** 52
**Commit summary:** Phase 1 of Demo Mode — `DEMO_MODE=true` env var enables a public-demo deployment with an hourly auto-reset, a pre-seeded sample campaign (3 users / 1 map / 2 PCs with full D&D 5e sheets / 7 tokens for a tavern-brawl encounter / 8-roll history / 2 homebrew records), an admin on-demand `POST /admin/demo/reset` endpoint, a non-dismissible top banner with countdown to next reset, and a credentials box on the login page.
**Description:** Implements `docs/plans/demo-mode.md` so a single public URL can hand out clean demo instances without operator intervention. Architectural choices from the plan: (1) in-process asyncio reset loop registered on the FastAPI lifespan, (2) surgical wipe by deterministic emails (`demo-gm@example.com`, `demo-alice@example.com`, `demo-bob@example.com`) + campaign-name sentinel — never a full-DB wipe, so an accidental `DEMO_MODE=true` on a production deploy touches no real data, (3) bundled placeholder assets under `app/static/demo/` so resets never need to clean the upload volume, (4) seed module is one file (`app/demo_seed.py`) with explicit per-section functions for easy extension. Banner is non-dismissible by design — it's the only safeguard against an operator forgetting `DEMO_MODE` is on.

### Added
- `DEMO_MODE`, `DEMO_RESET_INTERVAL_MINUTES`, `DEMO_RESET_ON_BOOT`, `DEMO_CREDENTIALS_VISIBLE` settings in `app/config.py` (all clamped / defaulted; reset interval clamped to [5, 1440]).
- `app/demo_seed.py` (~370 LoC) — `wipe(db)` deletes by demo email/campaign-name tags including the homebrew JSON directory; eight `seed_*` helpers (users, campaign, map, characters, token templates, tokens, roll history, encounter) plus `seed_homebrew_files`; `reset_and_reseed(db)` orchestration with per-section counts logged. Idempotent end-to-end (verified by running twice).
- `app/demo_scheduler.py` — `start_demo_scheduler(app)` registers an asyncio background task that runs `reset_and_reseed` every `DEMO_RESET_INTERVAL_MINUTES`. Errors caught + logged so a single failure doesn't kill the loop. `stop_demo_scheduler(app)` for the shutdown hook.
- `POST /admin/demo/reset` in `app/routes/admin_routes.py` — admin-only on-demand reset. 503 if `DEMO_MODE=false`. Returns the per-section count dict for scripting.
- `app/templates/_demo_banner.html` — non-dismissible top banner with a JS countdown that reloads the page when it hits 0:00. Included unconditionally in `base.html`; the `{% if DEMO_MODE %}` inside makes it a no-op when demo mode is off.
- Login credentials box in `app/templates/login.html` — gated on `DEMO_MODE and DEMO_CREDENTIALS_VISIBLE`. Lists the three demo accounts + shared password.
- Bundled placeholder assets at `app/static/demo/`: `maps/tavern.png` (1400×900 with grid + bar + tables), `tokens/rogue.png` / `tokens/wizard.png` (256×256 colored circles with letter ID). Generated programmatically with Pillow, CC0. `app/static/demo/README.md` documents the assets and notes how to replace.
- `DEMO_*` env vars added to `.env.example` with safety warnings.
- `DEMO_MODE`, `DEMO_RESET_INTERVAL_MINUTES`, `DEMO_CREDENTIALS_VISIBLE` exposed as Jinja globals so templates can render the banner / login box without each route passing them in its context.

### Changed
- `app/main.py` startup hook is now async, performs the on-boot reset (when `DEMO_RESET_ON_BOOT=true`, default), and spawns the scheduler when `DEMO_MODE` is on. New shutdown hook cancels the scheduler task cleanly.

### Notes
- Plan deviation: assets at `app/static/demo/` instead of `app/data/demo/` so they're served by the existing static-files mount without adding a new mount. Documented in the `app/static/demo/README.md`.
- Slight scope deviation from the plan: skipped seeding placeholder audio tracks (CC0 audio is harder to source than CC0 images, and the demo works fine without). Adding two short placeholder OGGs is a follow-up.
- Safety guards on destructive admin endpoints (the plan's "demo users can't be deleted" behavior) deferred. The hourly reset is the dominant safety mechanism; if a demo visitor manages to delete a user from the admin panel, the next reset restores it within at most `DEMO_RESET_INTERVAL_MINUTES` minutes.

---

## [2.2.6] - 2026-05-15

**Schema version:** 52
**Commit summary:** Fix the full-sheet skill click resolving to the *wrong* character's roll_state when the user has multiple characters in the campaign — same root cause as the 2.2.2 fix for the tabletop mini-sheet, just applied to the full sheet path. Also adds `roll_state` to `update_sheet`'s carry-forward list so a full sheet Save can't accidentally clobber the pill state.
**Description:** Reported symptom: "log says (auto advantage) even when I select Dis on the full sheet." Server-side end-to-end DB trace confirmed the state machine works correctly when the right character is read — so the bug had to be in *which* character `/roll` was reading. The full sheet's skill click handler in `app/static/sheet.js` (wireDnd5eRollButtons) wasn't passing `character_id`, so the server fell back to "the rolling user's first character in this campaign" (the same fallback the mini-sheet had before 2.2.2). If the user has a second test character in the campaign with a stale `roll_state.value = "advantage"`, the fallback found that one and applied advantage instead of the dis the user just set on the open sheet's pill. Fix: thread `character_id` through the skill click using `form.dataset.charId` (or the global `CHAR_ID` const as fallback), mirroring the 2.2.2 pattern. Defensive: add `roll_state` to the carry-forward list in `update_sheet` so a full sheet Save can't clear the pill state by omission.

### Fixed
- `app/static/sheet.js` `wireDnd5eRollButtons` — skill / ability / save click now sends `character_id` (resolved from `form.dataset.charId` or the global `CHAR_ID`) in the `/roll` payload, so the server reads *this* character's `roll_state`, not a stale sibling's.

### Changed (defensive)
- `app/routes/tabletop_routes.py` `update_sheet` — added `roll_state` to the carry-forward list alongside `death_saves`, `hp_rolls`, etc. A full sheet Save no longer drops the pill state when the client's `buildSheet()` payload omits `roll_state` (which it always does — no form field).

---

## [2.2.5] - 2026-05-15

**Schema version:** 52
**Commit summary:** Fix the 2.2.1 adv/dis dice-toast animation not firing on full-sheet rolls (skill checks, ability checks, attacks) — `_detectAdvDis` was only checking the client-supplied expression, which is the *original* (`1d20+5`) not the server-upgraded one (`2d20kh1+5`). Added a breakdown-only fallback so the toast detects the upgrade from the dice.py output marker.
**Description:** When the server auto-upgrades a single-d20 expression to `2d20kh1` / `2d20kl1`, the new expression isn't echoed back in the `/roll` response — the sheet's `showRollToast(...)` call passes the *original* expression. That broke the 2.2.1 detection logic which scanned the expression for adv/dis markers (`2dNkh1`, `1dNa`, etc.); the original `1d20+5` doesn't match. The breakdown always carries the `]kh1` / `]kl1` marker from `dice.py`, so a breakdown-only scan is a reliable fallback. The fix adds that fallback inside `_detectAdvDis` after the two expression-pattern attempts fail: if the breakdown contains `NdM<mod>[v1,v2]kh1` or `...kl1`, we treat the roll as auto-upgraded adv/dis, infer sides from the breakdown's leading `NdM`, and surface kept/discarded dice the same way the 2.2.1 expression-driven path did. The new fallback covers all four toast invocation sites on the full sheet (skill / ability click, action-button damage, weapon attack, manual roll) since they all pass the original expression to `showRollToast`.

### Fixed
- `app/static/roll_toast.js` — `_detectAdvDis(expression, breakdown)` now scans the breakdown when the expression doesn't carry adv/dis markers. 10 unit tests cover the new server-upgraded path (`expr="1d20+5"` with `brk` containing `2d20kh1[…]kh1`), existing expression-driven paths (long form, shorthand), and the negative cases that must continue to return null (plain rolls, damage rolls, ability gen).

---

## [2.2.4] - 2026-05-15

**Schema version:** 52
**Commit summary:** Fix roll-state pill buttons being unresponsive on the full D&D 5e character sheet — the click handler lived in `tabletop.js`, which doesn't load on the standalone sheet page.
**Description:** 2.2.0 added the click delegation for `[data-action="set-roll-state"]` to `app/static/tabletop.js`. That file only loads on the tabletop page (`tabletop.html`); the full sheet (`character_page.html` → `sheet_dnd5e.html`) doesn't include it. So the pill rendered correctly on the sheet (since 2.2.3 promoted it to a full-width row), but clicks did nothing — there was no handler listening. Adds a duplicate delegated handler inside `sheet_dnd5e.html`'s inline script block, matching the pattern already used for the Roll Death Save / Stabilize buttons (which suffered the same context separation when they were added in 2.1.0).

### Fixed
- `app/templates/sheet_dnd5e.html` — inline script now delegates `[data-action="set-roll-state"]` clicks to a fetch against `/api/campaign/{id}/character/{id}/roll-state`, with optimistic local pill update via a new `_updateRollStatePill(charId, value)` helper. Buttons on the full sheet are now responsive whether the page is opened standalone or inside the campaign tabletop.

---

## [2.2.3] - 2026-05-15

**Schema version:** 52
**Commit summary:** Move the adv/dis roll-state pill (and the death-saves tracker, kept paired for layout consistency) out of the cramped HP card on the D&D 5e full sheet into a dedicated full-width row below the HP / Hit-Dice / Combat-stat chips header. They were already rendered there since 2.2.0 but tucked inside the narrow HP card next to Temp HP where they were easy to overlook.
**Description:** The full sheet's vitals header is a three-column flex row (HP | Hit Dice | AC/Speed/Init/Prof chips). The roll-state pill was being included inside the HP card after the Temp HP stepper, which gave it a ~150px width and visually buried the three Adv/Normal/Dis buttons. Promotes the pill (and the paired death-saves tracker) to a full-width styled card directly below the header — visible at the same prominence as the HP block itself. Adds a CSS `:first-child` rule that suppresses the pill / tracker's top-border separator when they're the first element inside their container (they were designed to stack with a divider, which looks like a stray line as the first thing in a card).

### Changed
- `app/templates/sheet_dnd5e.html`: roll-state pill + death-saves tracker moved from inside the HP `.s-card` to a new dedicated full-width `.s-card` row sitting between the vitals header and the edit panel.
- `app/static/style.css`: `.roll-state-pill:first-child` and `.death-saves-tracker:first-child` now drop their top margin / padding / border so they sit flush against the card top edge.

---

## [2.2.2] - 2026-05-15

**Schema version:** 52
**Commit summary:** Fix mini-sheet skill / ability click on the tabletop sidebar so it respects the *target character's* roll_state (advantage/disadvantage pill), not the rolling user's. Particularly affected GMs clicking a player's skill: the server was falling back to the GM's own character lookup and silently dropping the player's pill state.
**Description:** 2.2.0's server-side adv/dis upgrade resolves the rolling character via the optional `character_id` body field, falling back to the rolling user's first character in the campaign when omitted. The mini-sheet click handler in `tabletop.html` (skill buttons and ability roll buttons) wasn't passing `character_id`, so for a GM clicking a player's mini-sheet, the lookup found the GM's own character (or nothing) and used *that* roll_state — making the player's pill appear broken. Threads `character_id` through the payload by walking up the DOM to the nearest `[data-char-id]` ancestor (works in both the Characters panel `.char-detail` wrappers and the Initiative Tracker's stolen `.mini-body` where the parent becomes `.init-entry`).

### Fixed
- `app/templates/tabletop.html` — the `players-drawer` click delegation for `.mini-roll-btn` / `.mini-sk-btn` now includes `character_id` in the `/roll` POST payload. Resolves the character by walking up to the nearest `[data-char-id]` ancestor so the rolled character's roll_state pill is honoured regardless of whether the GM or the player is doing the rolling.

---

## [2.2.1] - 2026-05-15

**Schema version:** 52
**Commit summary:** Roll-toast popup now shows BOTH dice for advantage / disadvantage rolls with the kept die highlighted (green for adv, red for dis) and the discarded die dimmed + strike-through. Covers both the long form (`2d20kh1` / `2d20kl1`) and the shorthand (`1d20a` / `1d20d`).
**Description:** Before this change, the toast for `2d20kh1` rendered both dice but treated them identically — players couldn't tell at a glance which one "won." The shorthand `1d20a` was worse: the expression-parsing regex saw only `1d20` so the toast rendered a single die showing the kept total, hiding the discarded value entirely. Now `_detectAdvDis(expression, breakdown)` parses both inputs to identify the two-die pair, the kind (adv vs dis), each die's value, and which index was kept (max for adv, min for dis). The toast forces a second die into the render for shorthand cases, applies the `rt-die-kept rt-die-kept-adv` / `rt-die-kept-dis` class to the kept die (color tint + glow), and applies `rt-die-discarded` to the other (opacity 0.35 + strikethrough). Animation behavior unchanged — the spin still cycles random values until landing, then the classes apply.

### Added
- `_detectAdvDis(expression, breakdown)` helper in `app/static/roll_toast.js`. 10 unit tests cover long form (`2d20kh1`, `2d20kl1`, with and without modifiers), shorthand (`1d20a`, `1d20d`, `d20a` no-count), tie cases, and non-adv/dis expressions (`1d20`, `1d8+3`, `4d6kh3`) which return null.
- `.rt-die-kept` / `.rt-die-kept-adv` / `.rt-die-kept-dis` / `.rt-die-discarded` CSS classes in `app/static/style.css`.

### Changed
- `showRollToast` now detects adv/dis early and pushes a second die into the render array when the shorthand form leaves it underpopulated. After the spin lands, both dice are assigned their breakdown values explicitly (overriding any earlier `_parseDieVals` result) and the kept/discarded classes are applied.

---

## [2.2.0] - 2026-05-15

**Schema version:** 52
**Commit summary:** Phase 1 of the Advantage & Disadvantage tracking feature — server-side `_apply_roll_state` upgrade for single-d20 expressions, tri-state Adv/Normal/Dis pill on the mini-sheet + full sheet, live WebSocket sync, manual `2d20kh1` / `2d20kl1` / `1d20a` / `1d20d` buttons preserved as one-shot overrides.
**Description:** Implements the design plan in `docs/plans/advantage-disadvantage.md`. A character with `roll_state.value = "advantage"` or `"disadvantage"` set on their sheet has every single-d20 ability check, save, attack, or skill check auto-upgraded server-side to `2d20kh1` / `2d20kl1` before rolling. The upgrade happens inside `/api/campaign/{id}/roll` and `/api/campaign/{id}/attack` so all roll surfaces (mini-sheet ability/skill buttons, action-button payloads, sheet-side weapon attacks, roll-request prompts) benefit without per-handler wiring. Manual `adv` / `dis` dice buttons keep working unchanged — the regex contract only matches single-d20 expressions, so `2d20kh1` / `2d20kl1` / `1d20a` / `1d20d` submissions are detected and tagged `(manual …)` in the log without server modification. Initiative is automatically exempt: it's rolled client-side via `Math.random()` and never reaches the server. Roll log notes get `(auto advantage)` / `(auto disadvantage)` / `(manual advantage)` / `(manual disadvantage)` suffixes appended server-side so players see clearly *why* the dice doubled.

### Added
- `_apply_roll_state(expression, roll_state) -> (new_expression, applied)` helper in `app/routes/tabletop_routes.py`. Pure function — 17 unit tests cover auto-upgrade (1d20, 1d20+5, 1d20+5-2), manual detection (2d20kh1, 2d20kl1, 1d20a, 1d20d shorthand), non-d20 expression passthrough (4d6kh3, 3d8+5), multi-dice passthrough (1d20+1d4), and edge cases (empty string, whitespace, null state).
- `_roll_state_note_suffix(applied)` helper that returns the human-readable parenthetical for each `applied` value.
- `POST /api/campaign/{id}/character/{char_id}/roll-state` — sets / clears the character's roll_state. Body: `{value: "advantage" | "disadvantage" | null}`. GM or character owner only. Broadcasts a `character_roll_state` WebSocket event.
- `app/templates/_roll_state_pill.html` — reusable Jinja partial. Tri-state pill with three buttons (Adv / Normal / Dis); the active state is color-coded (green / neutral / red) and the click handler posts to the new endpoint.
- Roll-state pill rendered in:
  - The sidebar `.mini-sheet` (rendered in `tabletop.html` per character)
  - The full character sheet header (in `sheet_dnd5e.html`, next to the death-saves tracker)
- WebSocket handler `_onCharacterRollState(d)` in `app/static/tabletop.js` updates every pill on the page for the matching `character_id`. Click delegation on `[data-action="set-roll-state"]` posts to the endpoint and optimistically updates the pill before the broadcast lands.
- CSS in `app/static/style.css` — `.roll-state-pill` family: tri-state button styling with active-state colour for advantage (green tint) / disadvantage (red tint) / normal (accent border).

### Changed
- `/api/campaign/{id}/roll` now accepts optional `character_id` and `skip_roll_state` body fields. The character lookup that already attributes the roll log entry is performed before rolling so the helper can inspect `roll_state`. If no `character_id` is supplied, falls back to the rolling user's first character in the campaign (matches the pre-existing behaviour). The broadcast `roll` event and the JSON response now include `roll_state_applied: "auto_advantage" | "auto_disadvantage" | "manual_advantage" | "manual_disadvantage" | null`.
- `/api/campaign/{id}/attack` routes its `1d20+bonus` (and bare `1d20`) attack expression through the helper before rolling. The `weapon_attack` WS broadcast and the JSON response carry `roll_state_applied`.
- Roll-log `note` field is suffixed server-side with `(auto advantage)` / `(auto disadvantage)` / `(manual advantage)` / `(manual disadvantage)` so the rolling player and the GM both see why a 2d20kh1/kl1 showed up. Length still capped at 200 chars.

### Not in Phase 1 (per the plan)
- Elven Accuracy (3d20 keep highest) — deferred.
- Auto-clear on long rest — deferred.
- Roll-request prompts pre-marking adv/dis on the request itself — each player's own roll_state still applies; the prompt is transparent.
- NPC / monster tokens — Phase 1 only applies to player characters with a sheet. Adding adv/dis to NPC tokens requires Token-level state and is deferred to a later phase.

---

## [2.1.8] - 2026-05-15

**Schema version:** 52
**Commit summary:** Add a "Lighting" entry to the TODO backlog under Maps & Map Editor — GM-placed light sources with flicker, integrated with fog-of-war and player vision.
**Description:** Captures the lighting feature for future implementation: torches / lanterns / campfires / magical lights with per-source radius, colour, and flicker behaviour. Player vision is constrained by attached lights (tokens illuminate what their light reaches, plus revealed fog); GM sees all. Depends on the Maps 2.0 / Map Editor Framework groundwork (fog-of-war LOS + wall segments) landing first so shadows compute correctly.

### Changed
- `TODO.md`: new "Lighting" entry under Maps & Map Editor.

**Schema version:** 52
**Commit summary:** Add a "Homebrew Clone" entry to the TODO backlog under GM Tools — a Clone button on every homebrew record (feats / backgrounds / races / subclasses / monsters / classes) that duplicates the source JSON as "Copy of \<name\>" and opens the new entry in the editor.
**Description:** Captures a small but high-value GM-quality-of-life feature for future implementation: spin off homebrew variants without retyping every field. Lives in TODO.md under the GM Tools section.

### Changed
- `TODO.md`: new "Homebrew Clone" entry under GM Tools.

**Schema version:** 52
**Commit summary:** Remove the redundant standalone `#player-dice-panel` from the tabletop sidebar; the Dice Roller card attached to the roll log is now the single dice UI.
**Description:** Two dice rollers had coexisted on the tabletop: the styled "Dice Roller" card pinned to the bottom of the roll log (`#roll-form` with input / clear / visibility / Roll button / quick dice + the GM Roll Request sub-panel) and a separate "Dice" details panel in the sidebar above the Characters panel (`#player-dice-panel` with mirror controls using `-p` suffixed IDs). The two were functionally identical — same endpoint, same payload shape — so the sidebar one was pure duplication and visual clutter. Removed both the HTML block and the JavaScript handlers that powered the duplicate.

### Removed
- `<details id="player-dice-panel">` block in `app/templates/tabletop.html` (lines ~940-966): the 🎲 Dice details, roll form (`#roll-form-p`), clear button (`#roll-expr-clear-btn-p`), visibility select (`#roll-vis-p`), and `.quick-die-p` quick-roll buttons.
- The matching JavaScript handlers in `app/static/tabletop.js`: submit handler for `#roll-form-p`, clear handler for `#roll-expr-clear-btn-p`, and the `.quick-die-p` quick-roll click handler.

### Notes
- The roll-log Dice Roller (`#roll-form`) is unchanged and continues to be the single dice UI on the tabletop. GM Roll Request sub-panel is also unaffected.

**Schema version:** 52
**Commit summary:** Initiative tracker shows the rich Jinja `.mini-sheet` for every PC the GM expands, instead of the simpler `buildInitSheet()` fallback view. One-line Jinja filter change.
**Description:** When a GM expanded a combatant entry in the initiative tracker, characters owned by *other* players rendered with a stripped-down static stat block (header → "Init 0 · HP 14/10", chip-style AC/Spd/Init/PP, single-line Saving Throws, simple two-column skills — no rest buttons, no death-saves tracker, no Check/Save toggle, no class features, no spells panel). The cause: the init tracker only "steals" the rich `.mini-body` from the Characters panel when an `#char-detail-<id>` element exists in the DOM, and the Characters panel's Jinja filter (`{% if c.owner_user_id == user.id %}`) hid every PC the GM didn't own. Extending the filter to `or is_gm` puts `#char-detail` blocks for every PC into the DOM (server-rendered, only paid once per page load), so the init tracker can use the rich mini-sheet for any player character. Players still see only their own characters in the Characters panel.

### Changed
- `app/templates/tabletop.html`: Characters panel filter `{% if c.owner_user_id == user.id %}` → `{% if c.owner_user_id == user.id or is_gm %}`. GMs now see every PC's mini-sheet in the sidebar Characters panel. Side effect: the init tracker's `hasCharDetail` lookup succeeds for every PC combatant, so expanding any player's initiative entry now renders the full Jinja mini-sheet (HP stepper / AC chip / hit dice / Short+Long Rest / death-saves tracker / Check-Save toggle / two-column skills+attacks / Set Concentration).
- `buildInitSheet()` is still called for combatants without a matching PC (token-template NPCs, deleted character ids) — those don't have a full character sheet to render anyway.

---

## [2.1.4] - 2026-05-15

**Schema version:** 52
**Commit summary:** Decommission the GM-side 📋 expandable mini-sheet on the token tracker; the Jinja-rendered Characters-panel mini-sheet is now the sole mini-sheet UI on the tabletop.
**Description:** Two parallel mini-sheet renderers had grown up on the tabletop — a Jinja-rendered always-visible block in the Characters panel (rich: HP stepper, AC/Spd/Tmp chips, hit dice, Short/Long rest buttons, abilities with Check/Save toggle, skills + attacks two-column, Set Concentration button, death-saves tracker) and a separate JavaScript-built `buildMiniSheetEl()` mini-sheet that the GM expanded inline via a 📋 button on each token tracker row (simpler: HP/AC/Spd grid, abilities, saves, attacks, skills). The duplication was confusing and the JS variant lacked many of the affordances the Jinja one had grown. This release removes the 📋 expand path entirely. GMs who need to inspect a player's full stats use the existing full character sheet page; the Characters panel still lists only the viewer's own characters (per the existing Jinja filter).

### Removed
- `buildMiniSheetEl(name, tmpl, sheet, character)` in `app/static/tabletop.js` (~233 lines of D&D 5e mini-sheet rendering: tags, stats grid, abilities, saving throws, attacks, skills, the 2.1.0 death-saves tracker block, plus the 2.1.2 character-arg plumbing).
- The 📋 "Show sheet" button in the token tracker row template.
- The click handler + dynamic `sheetRow` element + sheetData lookup that expanded the inline mini-sheet on click.

### Changed
- Token tracker rows now show name + visibility + image-upload + controller dropdown + 🗑 delete only. Visually cleaner; one fewer button per row.

---

## [2.1.3] - 2026-05-15

**Schema version:** 52
**Commit summary:** Add the death-saves tracker to the always-visible Jinja `mini-statblock` (the sidebar mini-sheet that shows by default for every character). 2.1.0-2.1.2 only added it to the GM-side expandable mini-sheet rendered by `buildMiniSheetEl` (click 📋 on a token row), so most users couldn't see it at all.
**Description:** There are two distinct "mini-sheets" on the tabletop: (1) the always-visible sidebar block rendered server-side via the Jinja `mini-statblock` partial in `tabletop.html` (HP / AC / Speed / Tmp / HD / Rest buttons — what most users mean by "the mini-sheet"), and (2) the GM-side expandable mini-sheet built client-side in `buildMiniSheetEl` and shown when the GM clicks 📋 on a token tracker row. The 2.1.0 implementation wired (2) but missed (1). Includes the `_death_saves_tracker.html` partial inside the sidebar `.mini-body`, right below the HP / Rest row, using a `{% with %}` block to alias the local Jinja variables (`c` → `char`, `sh` → `sheet`, `_is_owner` → `can_edit`) to match the partial's expected names.

### Fixed
- `app/templates/tabletop.html`: include `_death_saves_tracker.html` inside the per-character `mini-body` block so the always-visible sidebar mini-sheet shows the tracker for every PC. The Jinja partial sets `data-character-id`, which the existing `character_death_save` WebSocket handler in `tabletop.js` already targets — live updates work without further changes.

---

## [2.1.2] - 2026-05-15

**Schema version:** 52
**Commit summary:** Fix mini-sheet death-saves tracker missing on the tabletop — `buildMiniSheetEl` lacked a `character` argument, so the tracker render code threw a `ReferenceError: char is not defined` and aborted before reaching `wrap.appendChild`.
**Description:** 2.1.0 added the death-saves tracker to the mini-sheet but referenced a `char` variable that wasn't in scope inside `buildMiniSheetEl(name, tmpl, sheet)`. The thrown ReferenceError silently aborted the renderer, leaving the mini-sheet without the tracker (and without any abilities/saves/skills rendering after the crash point — though most users only noticed the missing tracker). Threads the character object through the function signature and guards the tracker block on `character && character.id` so NPC token-template mini-sheets cleanly skip it (Phase 1 death saves are PC-only).

### Fixed
- `app/static/tabletop.js` `buildMiniSheetEl(name, tmpl, sheet)` → `buildMiniSheetEl(name, tmpl, sheet, character)`. The death-saves tracker block now reads `character.id` / `character.owner_user_id` instead of an undefined `char` reference, and is wrapped in `if (character && character.id)` so token-template mini-sheets skip it.
- Single call site in the GM token tracker (line ~2438) now passes the matched character object (`sheetChar`) when the token is character-backed, `null` for token-template tokens.

---

## [2.1.1] - 2026-05-15

**Schema version:** 52
**Commit summary:** Death-save tracker UX fixes from real-world 2.1.0 testing — healing a dead character now revives them to alive (was: required GM override), and the tracker is permanently visible on both the full sheet and the mini-sheet (was: auto-hidden when status was alive).
**Description:** Two UX adjustments after testing 2.1.0. (1) A character who had reached 3 failures and gone to `dead` would not auto-revive when healed via any path (heal endpoint, rest, sheet HP edit) — the original plan reserved that transition for the GM-override endpoint to mimic strict revivify-spell semantics. In practice the user healing the character is usually the GM, so the override step was redundant; healing now simply brings them back to `alive` with cleared counters. Tables that want strict semantics can still leave HP at 0 and use the override to mark alive at 1 HP. (2) The tracker partial hid itself with `display:none` when status was `alive`, which made the feature invisible until a character actually started dying. The tracker is now permanently visible — players see "ALIVE 0/3 ✓ 0/3 ✗" as a baseline so the system is discoverable. The Roll Death Save / Stabilize buttons still only render when status is `dying`, so the resting state stays uncluttered.

### Fixed
- `_apply_hp_change` now transitions `dead` → `alive` on any positive HP change (heal, rest, sheet HP edit, full sheet save). Counters cleared in the same step. `status_changed: True` is reported so the WebSocket broadcast fires and every open sheet/mini-sheet refreshes.

### Changed
- `app/templates/_death_saves_tracker.html` — removed the inline `style="display:none"` block that hid the tracker when status was `alive`.
- `app/templates/sheet_dnd5e.html` — removed the `el.style.display = (status === 'alive') ? 'none' : ''` toggle inside the WebSocket update handler.
- `app/static/tabletop.js` — same: removed the display toggle in both the mini-sheet renderer and the `character_death_save` WebSocket handler.
- `docs/plans/death-saves.md` — updated decision #3 to reflect "any HP > 0 clears dead too" and decision #7 to note the always-visible tracker.

---

## [2.1.0] - 2026-05-15

**Schema version:** 52
**Commit summary:** Phase 1 of the Death Saving Throws feature — server-driven `_apply_hp_change` state machine, three new endpoints, success/failure tracker in the full sheet and the mini-sheet, live WebSocket sync, RAW-correct massive-damage instant-kill and damage-at-0 auto-failures from day one.
**Description:** Implements the design plan in `docs/plans/death-saves.md`. When a character's HP drops to 0 they automatically enter the "dying" state; a 🎲 "Roll Death Save" button appears on their sheet (full and mini) and rolls a 1d20 through the existing roll pipeline (so death saves land in the campaign log just like any other roll). 10+ counts as a success, <10 a failure, natural 20 wakes the character at 1 HP, natural 1 counts as two failures, 3 successes → stable, 3 failures → dead. The state machine lives in a single `_apply_hp_change` helper that every HP-mutating endpoint now routes through; transitions (alive → dying, dying → dead via failures or massive damage, stable → dying on a damage hit, healing → alive) are computed server-side so stale clients can't desync the state. Three new endpoints: roll a death save (player or GM for their own / GM's character), GM-only override (manual status set for narrative beats), GM-only stabilize. State changes broadcast over WebSocket as `character_death_save` so every open mini-sheet and full-sheet on the campaign updates without a refresh.

### Added
- `_apply_hp_change(char, new_current, *, is_damage, is_crit, damage_amount)` in `app/routes/tabletop_routes.py` — single source of truth for character HP transitions. Implements the full Phase 1 state machine: alive→dying on HP=0 (with massive-damage check for instant death when remaining damage ≥ max HP), dying→dying with auto-failure tick on damage (+2 on crit), dying→dead on 3 failures or massive damage, stable→dying on damage with failure tick, healing wakes the character from dying/stable, and `dead` stays dead until a GM override. Pure dict-shape mutation on `Character.sheet`, returns a result dict for the caller to echo / broadcast. 11 unit tests + 5 DB-round-trip tests pass.
- `_set_death_save_state(char, *, status, successes, failures)` helper for the GM override + stabilize paths (mutates state without touching HP).
- `POST /api/campaign/{id}/character/{char_id}/death-save` — rolls a 1d20, applies the result per RAW, persists a `DiceRoll` row so the roll log sees it, broadcasts both the `roll` event (with `kind: "death_save"`) and the `character_death_save` event.
- `POST /api/campaign/{id}/character/{char_id}/death-save/override` — GM-only manual override of `{status, successes, failures}`. Used by the token context menu and for misclick recovery. When transitioning to `alive` from a 0-HP state, bumps HP to 1 so the state stays internally consistent.
- `POST /api/campaign/{id}/character/{char_id}/stabilize` — GM-only. Sets status to `stable`, clears counters. Phase 3 will add the Medicine-check auto-resolution; Phase 1 ships a manual GM-clickable affordance.
- `app/templates/_death_saves_tracker.html` — reusable Jinja partial rendering the tri-color status badge (DYING/STABLE/DEAD/ALIVE), three success pips, three failure pips, and conditional Roll/Stabilize buttons. Auto-hidden when status is `alive`.
- Inline JS in `app/templates/sheet_dnd5e.html` wires the Roll Death Save and Stabilize buttons on the full sheet, exposes `window.updateDeathSavesTracker(charId, data)` for live updates, integrates with the existing `window.showRollToast()` roll popup so death save results animate the same as any other d20.
- Mini-sheet rendering in `app/static/tabletop.js` injects the tracker into every character's mini-sheet, listens for the new `character_death_save` WebSocket event, and delegates Roll/Stabilize button clicks to the same endpoints.
- CSS in `app/static/style.css` — `.death-saves-tracker` family: tri-state status badges (color-coded), success/failure pips that fill when accumulating, subtle pulse animation on the dying status to draw the player's eye, compact 32px buttons (HIG-exempt panel comment included).

### Changed
- `/api/campaign/{id}/apply_healing` now routes the HP write through `_apply_hp_change` so healing a dying character wakes them. Broadcasts a `character_death_save` follow-up event when the status transitions.
- `/api/campaign/{id}/character/{char_id}/rest` (long and short) route through `_apply_hp_change` for the same reason. Fixes a pre-existing bug where rest endpoints failed to broadcast HP changes — they now broadcast the death-save state change when relevant, and the rest of the rest payload is unchanged.
- `PATCH /api/campaign/{id}/character/{char_id}/sheet-fields` — when the patch includes `hp`, routes the current HP through `_apply_hp_change`. Accepts an optional `hp_change_reason: "damage" | "set"` body field plus `is_crit` and `damage_amount` for damage sources. The default (`"set"`) does not apply auto-failure ticks, so manual sheet edits won't unexpectedly bump death save counters.
- `POST /api/campaign/{id}/character/{char_id}` (full sheet save) detects HP transitions across the save and fires the state machine when the new HP differs from the old. Adds `death_saves` to the carry-forward list so a full sheet POST that doesn't include it preserves the server-side state.
- The sheet route handlers (`get_sheet`, `character_sheet_page`, standalone sheet) now pass `is_gm: bool` to the template context so the partial can render the GM-only Stabilize button.

### Not changed (deferred to Phase 2-4)
- Auto-prompt on initiative turn (Phase 3, gated on combat-tracker integration).
- Medicine-check auto-stabilize (Phase 3).
- Stable countdown / 1-HP-after-1d4-hours rule (Phase 3, gated on session-time concept).
- NPC death saves on tokens with no character row (Phase 4, opt-in per-token).
- Wild-shape apply/revert HP paths still mutate HP directly; out of scope for Phase 1 because a character can't be in beast form while dying.

---

## [2.0.6] - 2026-05-15

**Schema version:** 52
**Commit summary:** Document the Death Saving Throws design in `docs/plans/death-saves.md`; add a one-line entry under Combat in the TODO.
**Description:** Captures the design for 5e death saving throws — auto-triggered when a character's HP hits 0, success/failure pips, "Roll Death Save" button routed through the existing roll pipeline (so it honors the adv/dis roll-state toggle), and automatic state machine for healing / damage-while-dying / massive-damage rules. Phase 1 includes RAW-correct massive-damage instant-kill and damage-at-0 auto-failure from day one. Healing always clears the dying state. GM-only "Stabilize" button (stabilize is something done to a character, not by them in standard 5e). Phases 2-4 cover richer broadcasts, initiative auto-prompt, Medicine-check stabilize, and an optional per-token "NPCs use death saves" GM toggle.

### Added
- `docs/plans/death-saves.md` — full design plan: server-driven state machine in `_apply_hp_change`, three new endpoints (roll, override, stabilize), three UI surfaces (mini-sheet, full sheet, GM token-context menu), color-coded status badges, verification covering nat-20 wake / nat-1 double-fail / damage-at-0 / crit-at-0 / massive-damage / adv-dis interaction / GM permission guards.
- `TODO.md`: new "Death Saving Throws" entry under Combat, pointing to the plan.

---

## [2.0.5] - 2026-05-15

**Schema version:** 52
**Commit summary:** Document the Advantage & Disadvantage Tracking design in `docs/plans/advantage-disadvantage.md`; trim the TODO entry to a one-line pointer.
**Description:** Captures the design for a per-character roll-state toggle that the server applies to d20 rolls automatically. The plan preserves the existing manual `adv` / `dis` dice buttons as one-shot overrides for edge cases (Bless, Reckless Attack, Help, GM judgment calls). Phase 1 is manual-toggle-only and self-contained; Phases 2-3 layer on the conditions system and Maps 2.0 movement tracking respectively. Defaults baked in: initiative rolls are exempt from auto-upgrade (5e RAW has no general rule that initiative honors conditions), and the toggle persists until manually cleared (no auto-reset on long rest in Phase 1).

### Added
- `docs/plans/advantage-disadvantage.md` — full design plan for the planned MINOR Advantage & Disadvantage Tracking feature: server-side d20 expression upgrade, regex contract (only single-d20 expressions are eligible), manual-button coexistence rule, initiative exemption, three UI surfaces (mini-sheet pill, full sheet pill, GM token-context menu), verification covering both auto and manual paths.

### Changed
- `TODO.md`: Advantage & Disadvantage Tracking entry trimmed from ~8 lines to one sentence + a link to the plan file.

---

## [2.0.4] - 2026-05-15

**Schema version:** 52
**Commit summary:** Move the Demo Mode design into a dedicated planning file; trim the TODO entry to a one-line pointer.
**Description:** The Demo Mode TODO entry had grown to a multi-paragraph brief and would have grown further as design decisions accumulated (hourly auto-reset, surgical wipe strategy, NPC tokens in the seeded encounter, safety guards, verification). Detailed plans don't fit the TODO format — it's meant to be scannable. Moves the full plan to a new `docs/plans/` directory and shrinks the TODO entry to one sentence plus a link. Establishes the convention: any feature whose plan exceeds a paragraph gets its own file under `docs/plans/`.

### Added
- `docs/plans/demo-mode.md` — full design plan for the planned v2.1.0 Demo Mode feature: in-process asyncio reset loop, tag-based surgical wipe, seed module with NPC-populated tavern encounter, bundled-asset strategy, safety guards, and verification steps.
- `docs/plans/` directory for future feature design docs.

### Changed
- `TODO.md`: Demo Mode entry trimmed from ~12 lines to one sentence + a link to the plan file.

**Schema version:** 52
**Commit summary:** Credit Open5e in the per-file `_attribution` of every shipped SRD JSON record; regenerate all 984 files from the live Open5e API with the new credit chain.
**Description:** The per-file `_attribution` previously cited only "the D&D 5e SRD (CC BY 4.0 / OGL 1.0a)" without naming Open5e, the intermediate CC BY 4.0 source the JSON shape was derived from. CC BY 4.0's attribution clause flows downstream — Open5e itself must be credited in works that redistribute its data. Updates the `ATTRIBUTION` constant in `scripts/build_srd_content.py` to name Wizards of the Coast AND Open5e (with the URL) AND point to `CREDITS.md` for the full chain, then re-runs the builder against `https://api.open5e.com/v1/` to refresh every file. The script's `wotc-srd` document filter still gates the redistribution perimeter; the rebuild was a no-op on the file-list dimension (same 984 files, same slugs) but every record now carries the corrected credit string.

### Changed
- `scripts/build_srd_content.py`: `ATTRIBUTION` constant rewritten to credit both Wizards of the Coast (the upstream work) and Open5e (the intermediate distributor), with a pointer to `CREDITS.md`.
- Every JSON file under `app/data/local/dnd5e/` regenerated with the new `_attribution` string. Counts unchanged: 319 spells / 322 monsters / 292 items / 15 conditions / 13 subclass_features / 12 class_features / 9 races / 1 feat / 1 background. All 984 files still validate against their Pydantic models.

---

## [2.0.2] - 2026-05-15

**Schema version:** 52
**Commit summary:** Add `CREDITS.md` with the full third-party attribution chain (D&D 5e SRD via Open5e, htmx, Google Fonts, Python deps).
**Description:** SimpleVTT redistributes the ~984 SRD-derived JSON files generated in 1.7.0; CC BY 4.0 requires reasonable attribution at the work level, not just per-record. Adds a `CREDITS.md` at the repo root listing Wizards of the Coast (SRD 5.1, CC BY 4.0 / OGL 1.0a), Open5e (the intermediate source, CC BY 4.0), htmx (BSD), Google Fonts (SIL OFL 1.1), and every Python dependency from `requirements.txt` with its license. The `LICENSE` file's trailing notice already points here for the content credit chain.

### Added
- `CREDITS.md` at repo root. Three sections: game-rules content (SRD via Open5e), frontend dependencies (CDN-loaded htmx + Google Fonts), Python dependencies (everything in `requirements.txt`). Each entry links to the upstream project and names the SPDX license.

---

## [2.0.1] - 2026-05-15

**Schema version:** 52
**Commit summary:** Add MIT LICENSE at the repo root.
**Description:** SimpleVTT had no project-level license file. Without one, the project defaults to "all rights reserved" — contributors can't legally contribute, forkers can't legally fork, and registries flag the project as unlicensed. Adds an MIT LICENSE plus a short third-party content notice pointing to `CREDITS.md` (added in 2.0.2) for the SRD attribution.

### Added
- `LICENSE` at repo root — MIT for the project itself, with a trailing notice that the shipped SRD JSON content is separately licensed (CC BY 4.0 / OGL 1.0a) via the Open5e project.

---

## [2.0.0] - 2026-05-15

**Schema version:** 52
**Commit summary:** Destructive cutover from DB-backed `custom_*` tables to file-based homebrew. Six tables exported then DROPPED at boot; ~150 ORM references in routes / admin / resolver replaced with `local_content.*`; Custom* SQLAlchemy models deleted; URL contracts for every GM-authored homebrew type changed from `{type_id: int}` to `{type_slug: str}`.
**Description:** Completes the file-based content framework introduced in 1.7.0. Homebrew classes, subclasses, races, feats, monsters, and backgrounds no longer live in SQL — every record is now a per-slug JSON file under the `homebrew_data` Docker volume, validated through the Pydantic schemas in `content_schemas.py`. **Operator action required before upgrading: back up your Postgres database AND verify the `homebrew_data` volume exists.** On first v2.0.0 boot the inline migration framework (schema v52) calls `app/_migrate_v52.py`, which exports every row in the six `custom_*` tables to JSON files, then DROPs all six tables in a single transaction. Both export and drop happen inside one SQLAlchemy `engine.begin()` block, so any export error aborts the migration before any table is destroyed. After the migration, the GM authoring forms on the campaign settings page write JSON files directly via `local_content.write_homebrew`; the admin `/admin/stubs` audit page walks the homebrew volume rather than joining six SQL tables; and `app/local_features.py` retains only the shipped-FS providers — its DB providers (`_db_class_provider`, `_db_subclass_provider`, …) are removed in lockstep with the model classes.

### Added
- `app/_migrate_v52.py` runner — `run_v52_migration(engine)` — wired into `_apply_inline_migrations` at the v52 step. Idempotent: no-op when the legacy tables are already gone. Single transaction wraps both the per-table exports and the `DROP TABLE` statements; partial JSON writes from a failed export are overwritten on the next attempt (writes are atomic + deterministic).
- `_enumerate_homebrew(type_dir)` helper in `app/routes/admin_routes.py` — walks every scope directory under the homebrew volume for a given content type and yields each loaded record with `_campaign_id` / `_scope` / `_mtime` synthetic keys. Replaces the six per-table SQL joins on the `/admin/stubs` audit page; the JSON twin at `/admin/stubs.json` reads from the same helper.
- Pre-flight + post-flight row counts logged at INFO level so the boot log shows `"v52 migration: N Custom* rows to export across M table(s)"` followed by per-table `"exported K rows from <table>"` and `"dropped <table>"` lines.

### Changed
- **`ClassFeature.features` is now `Any`** (was `str`). Matches the existing `SubclassFeature.features: Any` pattern so shipped SRD class files (markdown blob) and homebrew records (structured `[{name, level, desc}, ...]` list from the campaign-settings editor) both load through the same schema. The migration dumper preserves the structured list verbatim — no flattening to markdown on the export path — so the GM-side feature editor round-trips after migration.
- `_dump_custom_class` in the v52 migration no longer flattens features through `features_to_markdown`; the helper itself stays in `local_content.py` for ad-hoc use but the migration writes structured data directly.
- Every Custom* CRUD endpoint in `app/routes/tabletop_routes.py` (classes, subclasses, races, feats, monsters, backgrounds) refactored to file-based: `db.query(Custom*)` calls replaced with `local_content.resolve` / `local_content.search`; inserts/updates replaced with `local_content.write_homebrew`; deletes replaced with `local_content.delete_homebrew`. URL contracts changed from `{type_id: int}` to `{type_slug: str}` (CustomSubclass uses combined `<class>__<sub>` slug). The matching `campaign_settings.html` form `action=` URLs and visible `<code>` slug labels updated to match.
- `app/routes/tabletop_routes.py`: import / export endpoints (`/api/campaign/{id}/homebrew/{import,export}`) projects the file records back to the legacy field-name shape (`feat_slug`, `background_slug`, `race_slug`, `monster_slug`, `class_slug`, `sub_slug`) for the import payload's bulk-create shape. Round-trips a v1 export pack into a v2.0.0 campaign without edits.
- `app/routes/tabletop_routes.py`: search proxies (`/api/open5e/{feats,backgrounds,races,subclasses,monsters,classes}`) now consult `local_content.search(...)` for the homebrew tier; Open5e mirror / live API only fires on shipped-SRD + homebrew miss.
- `app/routes/tabletop_routes.py`: `_custom_monster_lite(row)` signature changed from `CustomMonster` ORM row to a plain `dict` (file record).
- `app/routes/tabletop_routes.py`: monster bulk-import collapses the four legacy parallel action lists (`actions`, `reactions`, `special_abilities`, `legendary_actions`) into a single `actions: list[Action]` array via the new `_coalesce_monster_actions` helper; the matching `_monster_record_to_export(r)` projects the unified array back to the four split lists for the export endpoint.
- `app/routes/admin_routes.py` `/admin/stubs` HTML view + `/admin/stubs.json` audit endpoint rewritten to walk the homebrew volume; campaign + creator names resolved in-process via a single Campaign / User lookup map per request rather than per-record SQL joins.
- `app/local_features.py` chain lists (`_CLASS_PROVIDERS`, `_SUBCLASS_PROVIDERS`, `_RACE_PROVIDERS`, `_MONSTER_PROVIDERS`, `_BACKGROUND_PROVIDERS`, `_FEAT_PROVIDERS`) collapsed to a single-entry list containing only the shipped-FS provider. The DB-backed providers no longer exist; resolver call sites that need homebrew should use `app/local_content.py` directly.

### Removed
- **SQLAlchemy models (and their tables):** `CustomClass`, `CustomSubclass`, `CustomRace`, `CustomFeat`, `CustomMonster`, `CustomBackground` in `app/models.py`. The corresponding tables — `custom_classes` / `custom_subclasses` / `custom_races` / `custom_feats` / `custom_monsters` / `custom_backgrounds` — are dropped by the v52 boot migration after their rows export to the homebrew Docker volume.
- DB-backed provider functions in `app/local_features.py`: `_db_class_provider`, `_db_subclass_provider`, `_db_race_provider`, `_db_monster_provider`, `_db_background_provider`, `_db_feat_provider`.
- `_class_to_dict(c)` and the other Custom* `_*_to_dict` helpers in `tabletop_routes.py` — the export endpoint inlines each projection from file records.
- Schema v22-v30 `CREATE TABLE` calls in `app/database.py`'s `_apply_inline_migrations`. The version stamps are kept for upgrade-path bookkeeping; the actual `CREATE` is now a no-op since v52 drops the tables anyway. Databases initialised at v2.0.0+ never have the tables.
- Imports of `Custom*` model classes from `app/routes/admin_routes.py` and `app/routes/tabletop_routes.py`.

### Schema
- **v52 (destructive, forward-only).** The six legacy `custom_*` tables are exported to JSON files in the `homebrew_data` Docker volume, then DROPped in one SQL transaction. Idempotent on subsequent boots (no Custom* tables present → no-op).
- **Operator action required:**
  1. **Back up Postgres before upgrading.** A standard `pg_dump` is sufficient. The migration is destructive; if you discover after the fact that an export failed silently, your only recovery is from the SQL dump.
  2. Pull the v2.0.0 image and `docker compose up`. Watch the boot log for `"v52 migration: N Custom* rows to export across M table(s)"` followed by `"exported K rows from <table>"` for each table that had data. The final per-table count should equal the pre-flight count; mismatch logs as `ERROR` and recommends a manual review of the homebrew volume.
  3. Verify the `homebrew_data` named volume exists and contains files: `docker compose run --rm app ls /app/app/data/homebrew/dnd5e/`. You should see one or more `campaign-<id>` (or `global`) subdirectories, each with per-content-type folders.
  4. Recommended: take a `tar` snapshot of the populated `homebrew_data` volume as a second backup line.
- After successful upgrade, the `custom_*` tables no longer exist. Subsequent boots see no Custom* tables and the v52 migration is a no-op.

### Migration notes
- **Partial-failure recovery.** If the SQL transaction rolls back mid-export, the JSON files written before the failure are harmless and overwritten deterministically on the next attempt. Identify the offending row from the error message, fix or delete the row, then reboot — the migration completes idempotently.
- **Operators on a brand-new database** (no v1.x data to migrate) see `"v52 migration: no Custom* tables present; nothing to do."` and proceed to start.
- The `app/data/homebrew/` directory in the Docker image is created empty so the named volume mounts cleanly even before any file has been authored.
