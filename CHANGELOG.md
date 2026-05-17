# Changelog

All notable changes to SimpleVTT are documented in this file.
Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) — Versioning: [SemVer](https://semver.org/spec/v2.0.0.html).

The current version is the topmost release section below.
Application version and database schema version are also published at runtime by `GET /version` and `GET /healthz`, and are defined as constants in [`app/version.py`](app/version.py).

> For pre-2.0.0 history, see [CHANGELOG_v1.md](CHANGELOG_v1.md).

---

## [2.4.8] - 2026-05-17

**Schema version:** 53
**Commit summary:** Init tracker now **self-heals missing portraits** at render time — walks every combatant in `battle.combatants` and fills in `image_url` from the matching live Token row when null. Solves the v2.4.6 follow-up where a demo GM with stale localStorage (combatants captured pre-v2.3.44 portrait wiring, or pre-v2.4.3 encounter load that scrubbed `image_url` off tokens) still saw color swatches in the init tracker after the seed + Load Encounter fixes shipped. No user action needed; the heal mutates the combatant in place and `saveBattle()` persists it. User-reported.
**Description:** Two coordinated edits in `app/templates/tabletop.html`. (1) New helper `_resolveCombatantImage(c)` near `combatantFromToken` (line ~3233) — returns `c.image_url` when set (fast path), otherwise tries three fallbacks in order: lookup by `c.char_id` → matching token's `image_url`, lookup by `c.token_template_id` → first matching token, lookup by `c.name` → matching token label (covers manual / hand-renamed combatants). Mutates `c.image_url` on success. Returns the resolved url or null. (2) `renderBattle` opens with an opportunistic walk over every combatant calling `_resolveCombatantImage(c)`, tracks via `_healedAny` whether any heal occurred, and at the end of the render calls `saveBattle()` only when something was healed. This keeps the localStorage-write thrash off the hot path while making the heal sticky across renders / page loads / WS pushes.
**Description (cont):** Why heal-in-place over forcing a "Clear init tracker + From Map" UX: the user expectation is "the init tracker should show entity art", not "you have a stale state — please reset". The render-time heal is invisible and idempotent: a tracker that already has all portraits skips every fallback at constant cost; a fully-stale one heals every combatant on first render and never touches the fallbacks again. The match-by-name fallback handles manual combatants whose name happens to match a token on the map (the demo's "Vex (Bandit Captain)" / "Grixxa (Goblin Captain)" / "Brother Tavik Stonebrow" all derive from token labels verbatim). Combatants whose token has since been deleted or whose name was hand-edited away from the original token label still fall back to the color swatch — the heal is best-effort, not enforced.

### Fixed
- `app/templates/tabletop.html` `renderBattle` — opportunistic portrait heal at the start of every render: walks `battle.combatants`, calls `_resolveCombatantImage` per combatant, persists any heals via `saveBattle()` at the end. Solves the stale-localStorage staleness left over from pre-v2.3.44 / pre-v2.4.3 demo flows.

### Added
- `app/templates/tabletop.html` `_resolveCombatantImage(c)` — three-step token lookup (by char_id, token_template_id, then name) returning the matching token's `image_url`. Mutates `c.image_url` on success so subsequent renders skip the resolve work.

### Notes
- The resolver scans `tokens` (the JS-side live token list, populated from initial-data and kept in sync via WS broadcasts) rather than `allTokens` — same list, same content; `tokens` is the canonical variable name in this file.
- The heal won't trigger when the token list is empty (e.g. a player viewing a campaign before the GM has staged any tokens). That's the right behavior — there's nothing to heal from.
- A future polish: the manual-add path (`doManualAdd`) could also call `_resolveCombatantImage` after pushing the new combatant so manually-entered names auto-pick up matching token art. Out of scope here.
- The `_healedAny` guard avoids touching localStorage on every render — the common steady-state case where every combatant already has `image_url` set incurs zero saves per render.

---

## [2.4.7] - 2026-05-17

**Schema version:** 53
**Commit summary:** Keep the **Player (Rogue) Fill button on the same line** as its label + email in the demo-creds box on the login page. Pre-v2.4.7 the row wrapped because `demo-alice@example.com` (22 chars) was just a few characters longer than `demo-gm@example.com` (19) / `demo-bob@example.com` (20), pushing the trailing button onto a second line and breaking visual alignment with the other two rows. User-reported.
**Description:** One styling tweak in `app/templates/login.html` — `style="white-space:nowrap;"` added to each of the three `<li>` rows in the demo-creds-box (`GM`, `Player (Rogue)`, `Player (Wizard)`). The Rogue row was the only one wrapping in practice but adding `nowrap` to all three keeps the styling consistent and guards against future label-length tweaks reopening the same bug. No CSS file change — inline style on each row matches the existing inline-style pattern the Fill buttons already use; pulling these into a class would force re-doing the existing styling decisions and isn't worth the churn for a 3-line panel.

### Fixed
- `app/templates/login.html` — `white-space:nowrap` on the three demo-creds `<li>` rows so the Fill button stays inline with its label + email regardless of email length.

### Notes
- The fix relies on the auth-card being wide enough to contain the longest row (`Player (Rogue):` + `demo-alice@example.com` + Fill button ≈ 350 px including padding). It is — the existing auth-card max-width comfortably accommodates this. If the auth-card width is ever reduced below ~380 px, the row will overflow horizontally rather than wrap. Acceptable trade-off vs. the visual inconsistency the wrap caused.
- The `Fill` buttons retain the 32-px dense-panel exception from v2.4.4 — the comment block above the `<li>` rows already documents that exception; the new v2.4.7 line was appended to the same comment so all the styling rationale lives in one place.

---

## [2.4.6] - 2026-05-17

**Schema version:** 53
**Commit summary:** When the GM clicks **Load encounter**, the init tracker now hydrates from the server's freshly-loaded battle state instead of staying frozen at whatever stale localStorage state it had. Closes the gap that left a v2.3.44-portrait demo GM with no NPC art in the init tracker even after v2.4.3 fixed the seed payload — the GM client is authoritative and ignores the `battle_update` WebSocket broadcast, so server-side state changes never propagated into their local view without this explicit hydration step. User-reported follow-up to 2.4.3.
**Description:** Two coordinated edits. (1) `app/routes/tabletop_routes.py` `_perform_encounter_load` now returns the canonical post-load `battle_state` in its JSON response (the same dict it pushed into the realtime hub via `hub.set_battle`). (2) `app/templates/tabletop.html` `loadEncounter` reads the response's `battle_state` and, when present and `map_switched` is false, assigns it to the local `battle` variable + `saveBattle()` + `renderBattle()`. The `map_switched` guard preserves the existing semantics that a map-switching load reloads the whole page (the server emits a `map_change` WS event the JS catches separately), so this branch only fires on same-map loads where the canvas surgically updates tokens in place. Players are unaffected — they were already hydrating from the `battle_update` broadcast that fires inside `_perform_encounter_load` immediately after `hub.set_battle`; this change is the GM-equivalent path.
**Description (cont):** Why the GM was being skipped in the first place: pre-v2.4.6, every battle-state update fanned out as a `battle_update` WS broadcast, and the JS hydrates from that only `if (msg.type === 'battle_update' && !IS_GM)`. The reasoning was reasonable — the GM is the source of truth for init-tracker mutations (`pushBattle` PUTs to `/api/campaign/.../battle` and broadcasts to players), and letting them auto-overwrite local state from their own broadcasts would create loops. But the Load Encounter path is a server-side decision (the server's payload becomes the new battle state), so the GM accepting that *specific* state on Load — and only on Load, only same-map, and only from the load route's response — is the right narrow exception. The change doesn't touch the broader WS broadcast filter; future server-driven state pushes that should also override GM local state will need to opt in the same way (via their own return-the-state-in-the-response pattern).

### Fixed
- `app/templates/tabletop.html` `loadEncounter` — on a successful same-map load, hydrate the local `battle` from `result.battle_state` and re-render. Resolves the v2.4.3 follow-up where a GM with stale localStorage saw no NPC portraits in the init tracker after Load even though the server hub state and broadcasts to players were correct.

### Added
- `app/routes/tabletop_routes.py` `_perform_encounter_load` — return `battle_state` in the response JSON so the GM client (which is authoritative and ignores `battle_update` broadcasts) can hydrate its local init tracker view to match the server's post-load state.

### Notes
- The new behavior only fires when `map_switched` is false. Map-switching loads trigger a full page reload via the WS `map_change` event, which re-reads localStorage on boot — so hydrating-from-response would race the reload. Keeping the existing reload semantics avoids that.
- The hub broadcast still fans the `battle_update` to all connected non-GM clients (players), so the same load operation pushes consistent state to everyone — GMs via the response body, players via WS.
- Doesn't change the `pushBattle` direction (GM → server). The GM remains the source of truth for in-session edits; Load is the one "server overwrites GM" event because the load operation IS the GM telling the server to do that.

---

## [2.4.5] - 2026-05-17

**Schema version:** 53
**Commit summary:** Rename the tabletop drawer tab labelled **Player** → **Battle**. The drawer hosts the initiative tracker as its primary content (with a small character-list section below), so "Battle" is the more accurate name; "Player" was a hold-over from when the panel was a simple player-character roster. User-requested.
**Description:** One-character-string edit in `app/templates/tabletop.html` line 777: `>Player<` → `>Battle<` on the `<button class="drawer-tab-btn player-tab" data-target="players-drawer">` element. Every internal identifier is left as-is: the `.player-tab` CSS class, the `data-target="players-drawer"` attribute, the `id="players-drawer"` on the matching panel, and the inline-JS event handlers all key off these internal names — renaming them would be a cosmetic refactor of ~dozen files for no behavioural gain, so the public-facing label change is decoupled from the internal naming.
**Description (cont):** No CSS / JS changes needed — the tab button's `.drawer-tab-btn` styling already centres any label text, so a 6-character word fits the same chip as the previous 6-character word with no layout shift. The CHANGELOG, if it had to enforce one-or-the-other consistency between display name and internal id, would also have hit base.html / settings pages / WS broadcasts that reference "player" in a different sense (player tokens, player characters, player-controlled tokens — all separate concepts). The internal-id-stays-as-is choice keeps "player" the term for "a non-GM user / their stuff" and "Battle" the term for "the in-combat tab", which is the right English-language division.

### Changed
- `app/templates/tabletop.html` line 777 — drawer tab label `Player` → `Battle`. Internal identifiers (`player-tab` CSS class, `players-drawer` target/id) unchanged.

### Notes
- The drawer panel under this tab (`#players-drawer`) contains: the initiative tracker (`renderBattle()` etc. — primary, large, drives the GM workflow), and a smaller "Player characters" list below. The init tracker is the dominant content, hence "Battle" reads as the right label.
- If a future refactor wants to also rename the internal identifiers (`#players-drawer` → `#battle-drawer`, `.player-tab` → `.battle-tab`, etc.), it would touch: this template, `app/static/style.css`, the inline event handlers in `tabletop.html`, and any pinned routes / encounter-load logic that searches by id. Not done here — the display rename was the user-requested change, and broader id renames would mix scope.

---

## [2.4.4] - 2026-05-17

**Schema version:** 53
**Commit summary:** Add a one-click **Fill** button next to each demo credential on the login page when `DEMO_MODE=true` and `DEMO_CREDENTIALS_VISIBLE=true`. Clicking writes the row's email into the form's email field, fills the shared `demopass` password, and moves focus to the Sign in button — saves the copy-paste-tab-tab-type-paste dance for the most common demo-evaluation flow. User-requested.
**Description:** Edit in `app/templates/login.html` only. Three `<button type="button" class="demo-fill-btn" data-demo-email="...">` controls appended to the existing `<li>` rows in the `demo-creds-box`. A small inline `<script>` block under the box wires every `.demo-fill-btn` to a `click` handler that targets `form[action="/login"]` and fills `input[name="email"]` + `input[name="password"]` from the button's `data-demo-email` attribute (password is hardcoded `"demopass"` to mirror `DEMO_PASSWORD` in `app/demo_seed.py`). The buttons carry inline 32-px dense-panel styling (`min-height:32px; padding:4px 12px; font-size:13px`) per the CLAUDE.md exception — the demo-creds box is an information panel where 44-px buttons would visually overpower the row text. Annotated in-template so the exception is documented next to the styling.
**Description (cont):** No backend / route changes — the form posts as before, the buttons just populate the fields client-side. Doesn't expose anything new: the credentials were already visible-in-cleartext (intentional, for demo discoverability) when both env flags are on. Hidden when either flag is off (production / staging never see them). The script is wrapped in the same `{% if DEMO_MODE and DEMO_CREDENTIALS_VISIBLE %}` block as the credentials display, so non-demo deploys ship no JS for this feature at all.

### Added
- `app/templates/login.html` — three "Fill" buttons in the demo-creds-box (one per role: GM / Player Rogue / Player Wizard) that one-click populate the sign-in form's email + password fields. Buttons render only when both demo env flags are on.
- `app/templates/login.html` — small inline `<script>` block that wires `.demo-fill-btn` `click` handlers. Reads `data-demo-email` from the clicked button; fills `name=email` + `name=password`; focuses the submit button so Enter ships the form.

### Notes
- The shared password is hardcoded into the JS rather than templated from the seed constant. The seed constant lives in `app/demo_seed.py:DEMO_PASSWORD` and currently equals `"demopass"`. If that ever changes, this template needs to follow. Risk is low (the seed has shipped this exact string since v2.3.0) and adding a Jinja round-trip would couple the template to the seed module unnecessarily; the comment in the script flags the dependency.
- The buttons carry `type="button"` explicitly so they don't accidentally submit the form when clicked (default `<button>` inside a `<form>` is `type=submit`).
- The focus-the-submit step makes the keyboard flow trivial: click Fill (or Tab + Enter to a Fill button), then Enter to submit. Better than auto-submitting the form (which would surprise the user and make it hard to switch between accounts during a single visit).

---

## [2.4.3] - 2026-05-17

**Schema version:** 53
**Commit summary:** Fix the demo "Tavern Brawl" encounter payload so loading it preserves token portraits, restores NPC monster-sheet bindings, and auto-populates the GM init tracker with pre-rolled initiative + portraits. Three pre-existing shape mismatches in `seed_encounter` — `token_template_id` (canonical key is `template_id`), missing `image_url` on every token, and a dead-code `initiative` field (canonical key is `battle_state` consumed by the runtime battle hub) — were silently no-op-ing the v2.3.44 portrait wiring whenever the encounter was loaded. User-reported: "character and monster art is not displaying in the init tracker."
**Description:** `app/demo_seed.py` `seed_encounter` rewritten to emit the canonical payload shape consumed by `_perform_encounter_load` in `app/routes/tabletop_routes.py`: `payload.tokens[]` entries now use the same field names as `_snapshot_encounter_payload` (`template_id`, `character_id`, `controller_user_id`, `label_override`, `color_override`, `image_url`, `size`, `x`, `y`, `is_hidden`), and `payload.battle_state` replaces the unread `payload.initiative` with the full battle-hub shape (`{combatants, turn_index, round, active}`). Each combatant carries `id`, `char_id`, `token_template_id`, `name`, `initiative`, `hp_current`, `hp_max`, `color`, `dex_mod`, `image_url` — sourced from the referenced Token row so the init tracker render matches the live tabletop tokens exactly. The function signature changed from `-> Encounter` to `-> tuple[Encounter, dict]`; the second value is the battle_state which `reset_and_reseed` now pushes into the realtime hub via `hub.set_battle(camp.id, battle_state)` so player WebSocket connects automatically receive the pre-rolled init tracker on first handshake (via the existing `hub.connect` `battle_update` push).
**Description (cont):** Side fix: `seed_encounter` also now sets `camp.current_encounter_id = enc.id` so the v2.3.31 "current encounter highlight" pin lights up on the demo's Tavern Brawl on first visit. The seeded encounter is the only one shipped, and the demo's narrative is built around it being "the" combat, so pinning it from boot matches user expectation. GM-client init tracker still hydrates from `localStorage` rather than the WS `battle_update` broadcast (the GM is authoritative; players hydrate from broadcasts) — so a fresh-browser demo GM still needs one "From Map" click to populate their local view, but every token they pull in now carries `image_url` and the recently-fixed encounter `template_id` keys mean a "Load encounter" click no longer strips portraits or breaks NPC monster sheets. The session_active flag stays True on the seeded campaign (the seed bypasses session-start to avoid the redundant auto-load), so the hub push from `reset_and_reseed` is the only place the demo's battle state gets seeded; subsequent resets push fresh state every hour.

### Fixed
- `app/demo_seed.py` `seed_encounter` — `payload.tokens[]` now uses canonical key `template_id` (was `token_template_id`) so `_perform_encounter_load` restores each NPC's TokenTemplate binding and the monster sheet stays clickable after Load.
- `app/demo_seed.py` `seed_encounter` — `payload.tokens[]` entries now carry `image_url` sourced from each Token row, so Load preserves the v2.3.44 portrait wiring instead of silently dropping it.
- `app/demo_seed.py` `seed_encounter` — dead-code `payload.initiative` field replaced with canonical `payload.battle_state` ({combatants, turn_index, round, active}). Each combatant carries `image_url`, `char_id`, `token_template_id`, `dex_mod`, full HP, and the pre-rolled initiative.

### Added
- `app/demo_seed.py` `reset_and_reseed` — `hub.set_battle(camp.id, battle_state)` push after the SQL commit so fresh player WS connects auto-receive the populated init tracker via the existing `hub.connect`'s `battle_update` push.
- `app/demo_seed.py` `seed_encounter` — `camp.current_encounter_id = enc.id` so the v2.3.31 currently-running encounter pin highlights Tavern Brawl from demo boot.

### Notes
- The `seed_encounter` return-type change (`Encounter` → `tuple[Encounter, dict]`) is internal — the demo seed's only caller is `reset_and_reseed` in the same file, updated alongside.
- The fix doesn't affect users whose stale `localStorage` carries pre-v2.3.44 combatants with `image_url=null`. They need to either (a) click "Clear combatants" then "From Map" once, or (b) wait for the next demo reset and reload the browser to pull a fresh state. Documenting in the next demo-page hint.
- All canonical token-payload fields match `_snapshot_encounter_payload` in `app/routes/tabletop_routes.py` line-for-line — verified by `grep -n "tokens_out.append"`. If the canonical shape changes again, this seed should change in lockstep.

---

## [2.4.2] - 2026-05-17

**Schema version:** 53
**Commit summary:** Re-grid the six NPC token positions in `seed_tokens` for the 1254×1254 tavern map — three NPCs (Thug at `x=1200`, Grixxa at `x=1250`, Bandit Beta at `x=1150`) were clipping off the right edge after the v2.4.1 map resize. New 2-column / 3-row formation snaps every NPC to the 70-px grid and centres them around `x=910–1120`, all comfortably within the 1184-px max for a 1×1 token. Preserves the v2.3.22 spatial layout (Vex up front, Thug back-right, Grixxa bottom-right). User-requested.
**Description:** Single edit in `app/demo_seed.py` `seed_tokens`'s `npc_placements` tuple: every NPC's `(x, y)` repositioned to a grid-snapped slot inside the new square room. Vex (980, 420), Bandit Alpha (910, 490), Bandit Beta (1050, 490), Bandit Gamma (980, 560), Thug (1120, 420), Grixxa (1120, 560). The Thug/Grixxa right-edge overflow flagged in the v2.4.1 release notes is fixed — `1120 + 70 = 1190 < 1254` with 64 px margin to spare. Vex is still the leftmost (forward-most) NPC matching the encounter narrative ("Vex barks orders"). Three bandits form a triangle in the middle, Grixxa sits in the bottom-right "tabletop" corner. Tactically the PC cluster around `x=350–420` and NPC cluster around `x=910–1120` leaves a ~490-px gap (≈ 7 grid squares) between the parties — far enough that turn-1 movement matters, close enough that ranged attacks (Bandit Light Crossbow, Bandit Captain Dagger thrown, Wizard Fire Bolt) all fire on first contact.

### Changed
- `app/demo_seed.py` `seed_tokens` `npc_placements` — six NPC positions regridded for the v2.4.1 1254×1254 map. Two-column / three-row formation centred around `x=910–1120`. Fixes the Thug / Grixxa / Bandit Beta right-edge clipping reported after v2.4.1.

### Notes
- All six NPCs now snap cleanly to the 70-px grid (multiples of 70). PC positions from v2.4.1 (`350,490` / `420,560` / `420,420`) are user-supplied and not all on-grid; left as-is per user request.
- The encounter snapshot in `seed_encounter` doesn't store `(x, y)` for each combatant beyond what's in the `Token` rows (the `initiative_order` payload uses `token_idx` to point at tokens, not coordinates). So this position change propagates to the "Tavern Brawl" encounter automatically — no further edits needed in `seed_encounter`.
- If the user wants a more spread-out / asymmetric arrangement (e.g. Grixxa actually standing on a specific drawn-on tabletop in the new map image), call out the desired coordinates and they go in as a single-line tuple swap.

---

## [2.4.1] - 2026-05-17

**Schema version:** 53
**Commit summary:** Update `app/demo_seed.py` to match the new 1254×1254 `tavern.png` (replaced the original 1400×900 Pillow placeholder) and reposition the three PC tokens for the new room layout: Pip at (350,490), Thalindra at (420,560), Brother Tavik at (420,420). `show_grid=True` asserted explicitly on the seeded Map so a future re-author of this file sees the intent rather than relying on the column default. User-supplied coordinates.
**Description:** Two coordinated edits, both in `app/demo_seed.py`. (1) `seed_map`: `width_px=1400` → `1254`, `height_px=900` → `1254`, plus `show_grid=True` added to the `Map(...)` constructor (defaults to True from the v2.4.0 column default, but explicit here so the next demo cycle isn't a silent regression if the default ever changes). (2) `seed_tokens` PC rows: chars[0] (Pip Quickfingers) `x=200,y=500` → `x=350,y=490`, chars[1] (Thalindra Moonwhisper) `x=200,y=600` → `x=420,y=560`, chars[2] (Brother Tavik Stonebrow) `x=200,y=700` → `x=420,y=420`. NPC placements (six bandits/thug/goblin captain on the right side of the map) are unchanged — the user only specified PC positions, and the right-side NPCs were already positioned 1050–1250 px in `x`, which sits inside the new map's 1254 px width modulo a small overhang on the two rightmost tokens (Thug at 1200 and Grixxa at 1250 — both extend ~16–66 px past the right edge with 70-px token size). Flagged for follow-up if the user wants those nudged in as well.

### Changed
- `app/demo_seed.py` `seed_map` — map dimensions `1400×900` → `1254×1254` to match the v2.4.0-followup `tavern.png` replacement (commit `2f549ab` "Update tavern.png"). `show_grid=True` asserted explicitly on the `Map(...)` constructor.
- `app/demo_seed.py` `seed_tokens` — PC token spawn positions repositioned for the new square room: Pip Quickfingers `(350, 490)`, Thalindra Moonwhisper `(420, 560)`, Brother Tavik Stonebrow `(420, 420)`. User-supplied coordinates.

### Notes
- The fresh demo cycle runs `reset_and_reseed` on container boot when `DEMO_RESET_ON_BOOT=true` (it is, on the live deploy), so the new positions appear automatically once the container restarts. The hourly scheduler then keeps replanting them on every reset cycle.
- NPC positions intentionally left untouched. The two rightmost (Thug at `x=1200`, Grixxa at `x=1250`) overflow the 1254-wide map by a small amount; bringing them in is a one-line per-token tweak whenever the user wants to layout-pass the right side of the room.
- The `show_grid=True` kwarg is technically a no-op against the v2.4.0 column default, but kept for clarity — it's the kind of latent bug that bites two years later when someone changes the default and the seed silently flips to overlay-off.

---

## [2.4.0] - 2026-05-17

**Schema version:** 53
**Commit summary:** Per-map **show grid overlay** toggle in Campaign settings → World → Maps. Lets GMs use maps whose background image already contains a hand-drawn grid (Dyson Logos, Patreon battlemaps, photographed minis-grid mats, etc.) without doubling it up with the client-drawn overlay, while keeping snap-to-grid token placement intact. MINOR bump for the additive schema column. User-requested.
**Description:** Five-piece change. (1) `Map.show_grid: Mapped[bool]` added in `app/models.py` (default True, `server_default="true"` to match the existing `users.animate_gifs` pattern). (2) Schema v53 migration in `app/database.py`'s `_apply_inline_migrations()` — single `ALTER TABLE maps ADD COLUMN show_grid BOOLEAN NOT NULL DEFAULT TRUE` guarded by the standard `_column_names` idempotency check, so every existing map gets the overlay-on default and pre-v53 installs upgrade in place on first boot. SCHEMA_VERSION bumped 52 → 53 in `app/version.py`. (3) Template wiring in `app/templates/tabletop.html`: the `<canvas id="vtt-canvas">` element gains `data-show-grid="{{ '1' if active_map.show_grid else '0' }}"` so the tabletop client reads the per-map flag without an extra fetch. (4) `app/static/tabletop.js` reads `canvas.dataset.showGrid !== '0'` into a `showGrid` constant alongside the existing `gridType` / `gridSize` reads, and the `render()` loop guards `drawSquareGrid()` / `drawHexGrid()` behind it. Crucially, `snapToGrid()` keeps deriving from `gridType` alone, so a GM can render a hex-grid-baked-into-the-image map with `grid_type=hex, show_grid=false` and token movement still snaps to the correct hex centres. (5) Campaign-settings UI in `app/templates/campaign_settings.html`: a small "overlay" checkbox is added to each map's row (right of the grid-size input), and a "Show grid overlay" checkbox is added to the upload-new-map form (default checked). The row checkbox POSTs to a new `POST /campaign/{cid}/settings/maps/{mid}/show_grid` endpoint that mirrors the existing `/grid_size` handler (GM-only, JSON body `{show_grid: bool}`).
**Description (cont):** This is the first schema bump since v52 (2.0.0). The migration is non-destructive and the new column has a safe default, so existing demo / production databases pick up the column transparently on first boot — operators don't need to manually `ALTER` anything. The new field is orthogonal to `grid_type`: `grid_type=none` already disabled both overlay and snapping (and continues to), while `grid_type=square|hex` × `show_grid=true|false` now gives four combinations covering all the practical map shipping conventions (client-drawn grid on a blank background, no grid at all, grid baked into the background image with snap-only client behaviour, and rare cases where the GM wants the client overlay on top of a baked-in grid for testing).

### Added
- `app/models.py` `Map.show_grid` — Boolean column, default True, `server_default="true"`. Per-map "show grid overlay" toggle; orthogonal to `grid_type`.
- `app/database.py` Schema v53 migration block — `ALTER TABLE maps ADD COLUMN show_grid BOOLEAN NOT NULL DEFAULT TRUE` with the standard `_column_names`-guarded idempotency check. SCHEMA_VERSION bumped to 53.
- `app/templates/tabletop.html` — `data-show-grid="{{ '1' if active_map.show_grid else '0' }}"` attribute on `<canvas id="vtt-canvas">`. Tabletop client reads it on init; no extra fetch.
- `app/static/tabletop.js` — `const showGrid = canvas.dataset.showGrid !== '0'` near the existing `gridType` / `gridSize` reads. `render()` now guards the grid-draw calls behind `showGrid`.
- `app/templates/campaign_settings.html` — per-row "overlay" checkbox in the Maps table (class `map-show-grid-input`, `data-map-id`-keyed); inline JS handler POSTs to the new `/show_grid` endpoint and rolls back the checkbox on failure.
- `app/templates/campaign_settings.html` — "Show grid overlay" checkbox in the upload-new-map form (default checked).
- `app/routes/tabletop_routes.py` `settings_map_show_grid` — `POST /campaign/{campaign_id}/settings/maps/{map_id}/show_grid`, GM-only, JSON body `{show_grid: bool}`. Mirrors the existing `settings_map_grid_size` handler.
- `app/routes/tabletop_routes.py` `settings_upload_map` — accepts `show_grid: bool = Form(False)` (HTML-checkbox idiom: unchecked → field omitted → False; default-shipped-checked → 1 → True) and passes it through to the new `Map(..., show_grid=show_grid)` constructor.

### Schema
- `maps.show_grid` (`BOOLEAN NOT NULL DEFAULT TRUE`) added. SCHEMA_VERSION → 53.

### Notes
- `grid_type=none` was already a valid way to disable both the overlay AND snapping for one specific use case (free-form maps without any grid math). The new flag adds the missing fourth quadrant: snap yes, overlay no.
- The per-row checkbox sits inside the dense Maps table (per the CLAUDE.md 32-px dense-panel exception) — width/height 14px with a tight gap to the "overlay" label. Inline annotation on the element explains the exception. The upload-form checkbox uses the standard 16-px target since that form is in a comfortable layout.
- The migration is forward-compatible: legacy maps with `show_grid IS NULL` cannot exist (the column is `NOT NULL`), and the `DEFAULT TRUE` backfills every pre-v53 row on the ALTER, so the new template attribute renders `'1'` for every legacy map and tabletop rendering is identical to v2.3.45 until the GM explicitly toggles a map off.
- The first schema bump in the 2.x line — operators should still back up Postgres before upgrading (defensive habit), but the change is non-destructive (additive column with a safe default).

---

## [2.3.45] - 2026-05-17

**Schema version:** 52
**Commit summary:** HiDPI-sharpen the tabletop canvas — multiply the backing-store resolution by `devicePixelRatio` and enable `imageSmoothingQuality = 'high'` so the v2.3.44 demo token portraits render crisp on Retina / 4K displays instead of being bilinearly upscaled 2-3× by the browser. User-reported: tokens looked soft after the v2.3.44 portrait wiring.
**Description:** The HTML template (`app/templates/tabletop.html`) sets `width="{{ map.width_px }}"` / `height="…"` on `<canvas id="vtt-canvas">`, which sized both the CSS display *and* the backing store identically. On a 2× display the browser had to upscale the rasterized canvas content per-paint, smearing every drawn pixel — invisible on the old letter-on-a-color-circle tokens but obvious on the new ~1000 px source photographic portraits being downscaled to ~70 px on canvas. Fix in `app/static/tabletop.js`: right after `canvas.getContext('2d')`, capture the logical map dimensions into `MAP_W` / `MAP_H` constants (the HTML-attribute values), then multiply `canvas.width` / `canvas.height` by `DPR = window.devicePixelRatio || 1`, pin the CSS display size to the original logical map size via `canvas.style.width / height`, and call `ctx.scale(DPR, DPR)` so all subsequent draw calls keep using logical CSS coordinates. Also set `ctx.imageSmoothingQuality = 'high'` — the default `'low'` made the 1000 px → 70 px source-to-canvas downscale unnecessarily mushy. Every former `canvas.width` / `canvas.height` reference in the file (grid line loops, hex tiling extent, `clearRect`, pan clamping) is replaced with `MAP_W` / `MAP_H` because the canvas-property accessors now return the DPR-multiplied backing-store size, not the logical size the rest of the code assumes.
**Description (cont):** The fix is one-time at module init; no per-frame DPR computation. Save/restore preserves the initial `ctx.scale(DPR, DPR)` transform across all draw functions (which use `save()`/`restore()` pairs but never `setTransform` / `resetTransform`). Hit testing is unaffected because every event handler uses `canvas.getBoundingClientRect()` which returns the CSS display size — and the CSS display size is now pinned to the original logical map size via `canvas.style.width / height`, so click/drag/zoom math sees the same coordinate space as v2.3.44. Zoom-induced blur (CSS `transform: scale(...)` on the canvas element on top of the higher-DPR rasterization) is improved proportionally but not eliminated — at 5× zoom on a 2× display the token still upscales 5× past its rasterized resolution. Eliminating that residual blur would require moving the zoom transform into the draw loop (`ctx.setTransform(scale*DPR, …)`), which is a larger refactor and stays out of scope here. The 2× DPR fix alone makes the demo's seated portraits visibly crisper on every modern display.

### Changed
- `app/static/tabletop.js` — module init now captures `MAP_W` / `MAP_H` before resizing the canvas backing-store by `devicePixelRatio`, pins CSS display size, calls `ctx.scale(DPR, DPR)`, and sets `imageSmoothingEnabled = true` / `imageSmoothingQuality = 'high'`.
- `app/static/tabletop.js` `drawSquareGrid` / `drawHexGrid` / `render` / `clampPan` — every former `canvas.width` / `canvas.height` reference now uses `MAP_W` / `MAP_H` so the grid lines / hex tiling / `clearRect` / pan clamping continue to operate in logical CSS coordinates rather than the new DPR-multiplied backing-store coordinates.

### Notes
- The fix is non-functional on a `DPR === 1` display (legacy 1080p, pre-Retina) — the multiplications collapse to no-op and the canvas behaves exactly like v2.3.44 did. The `Math.max(1, ...)` clamp guards against weird browsers that report `DPR < 1`.
- `MAP_W` / `MAP_H` are captured once at init and don't recalculate if the active map changes mid-session (a fresh map load reloads the whole page, so this is fine in practice). If a future change adds in-page map swapping without a reload, the canvas resize logic would need to move into a `resizeCanvas(w, h)` helper.
- The fix also applies retroactively to GIF / video / fallback-circle tokens, monster sheet thumbnails (the v2.3.0 `sheet_dnd5e.html` canvas — separate code path, still uses default DPR=1, fix-eligible but not changed here since the user's report was specifically about the tabletop), and the grid lines themselves (which now anti-alias at backing-store resolution and look noticeably finer at low zoom levels).

---

## [2.3.44] - 2026-05-16

**Schema version:** 52
**Commit summary:** Wire the nine new demo token portraits (`rogue.jpg`, `wizard.jpg`, `cleric.jpg`, `bandit-captain.jpg`, `bandit-alpha.jpg`, `bandit-beta.jpg`, `bandit-gamma.jpg`, `thug.jpg`, `goblin-captain.jpg`) into `seed_tokens` so a fresh demo cycle renders illustrated combatants instead of color-swatch placeholders. Files were dropped into `app/static/demo/tokens/` in the prior `demo-tokens` commit (`7164ab4`); this change updates `app/demo_seed.py` to set `image_url` on every PC and every NPC. User-requested.
**Description:** Three coordinated edits. (1) `seed_tokens` PC rows: `rogue.png` → `rogue.jpg` and `wizard.png` → `wizard.jpg` (extension changed to match the shipped files), plus a brand-new `image_url="/static/demo/tokens/cleric.jpg"` on Brother Tavik (added v2.3.25 without a portrait). (2) `seed_tokens` NPC loop: the `npc_placements` tuple gained a sixth element — the per-token image filename — so each of the six NPCs gets a distinct portrait. The three identical bandit templates share one template id (still `bandit`) but render with three different illustrations (alpha / beta / gamma) so the GM can tell them apart at a glance in the init tracker. (3) `docs/demo/image-prompts.md` token-path table refreshed: every "needs token wire" row is now "shipped + wired", paths updated to `.jpg`, and the post-generation instructions trimmed to a short "drop the file at the same path" note since the wiring is no longer the missing piece.

### Changed
- `app/demo_seed.py` `seed_tokens` — PC tokens switch from `rogue.png` / `wizard.png` to `rogue.jpg` / `wizard.jpg`; Brother Tavik (chars[2]) gains `image_url="/static/demo/tokens/cleric.jpg"`.
- `app/demo_seed.py` `seed_tokens` — `npc_placements` extended from a 5-tuple `(slug, label, x, y, color)` to a 6-tuple with the per-token image filename appended; the loop now sets `image_url=f"/static/demo/tokens/{image}"` on each Token. The three bandit rows reference `bandit-alpha.jpg` / `bandit-beta.jpg` / `bandit-gamma.jpg` so identical-template combatants get distinguishable art.
- `docs/demo/image-prompts.md` — token-path table refreshed to reflect all nine character portraits being shipped + wired; the post-generation wiring checklist trimmed.

### Notes
- The demo color swatches (Alice `#6cb4ff`, Bob `#4ade80`, GM `#f5b75c`, bandits `#c84a4a`, Grixxa `#7c9c54`) stay set on each token — they continue to drive the ring-around-the-portrait + the per-combatant initiative chip color, just no longer the whole token face.
- No new files were added in this commit; the jpgs themselves shipped with `7164ab4` ("demo-tokens"). This is purely the code-side wiring.
- Once the demo scheduler runs its next reset (`DEMO_RESET_INTERVAL_MINUTES`), the new portraits appear on the public demo URL without operator intervention.

---

## [2.3.43] - 2026-05-16

**Schema version:** 52
**Commit summary:** Append `?v={{ APP_VERSION }}` to every static JS/CSS reference in the template tree so a release bump automatically invalidates Cloudflare's edge cache (and any other CDN / browser disk cache that keys on full URL). Caught after shipping v2.3.41 — the deployed `features_editor.js` had the new Charges column but Cloudflare was serving the pre-2.3.41 file from edge cache for ~4 hours (`cf-cache-status: HIT`, `max-age=14400`), and a browser hard-refresh wasn't enough to bust it. User-reported.
**Description:** Every release going forward changes the query string on every static asset URL (`/static/features_editor.js?v=2.3.43` vs `…?v=2.3.42`), which Cloudflare treats as a different cache key — so the first visitor after a deploy gets a fresh fetch, and every subsequent visitor for that release version gets the warm edge cache. No CDN config change needed (the existing `max-age=14400` is fine — it just keys on URL+query now). Touched files: `app/templates/base.html` (3 CSS), `app/templates/sheet_dnd5e.html` (8 JS), `app/templates/sheet_generic.html` (1 JS), `app/templates/tabletop.html` (5 JS), `app/templates/campaign_settings.html` (3 JS). 20 references total. `APP_VERSION` was already a Jinja global via `app/templates.py` so no Python-side wiring was needed.

### Changed
- `app/templates/base.html` — `/static/style.css`, `/static/style-fantasy-themes.css`, `/static/sheet-fantasy.css` each get `?v={{ APP_VERSION }}`.
- `app/templates/sheet_dnd5e.html` — eight `<script src="/static/...">` references all version-stamped.
- `app/templates/sheet_generic.html` — `/static/sheet.js` version-stamped.
- `app/templates/tabletop.html` — five `<script src="/static/...">` references (`action_buttons`, `roll_toast`, `beast_picker`, `tabletop`, `audio`) all version-stamped.
- `app/templates/campaign_settings.html` — three `<script src="/static/...">` references (`features_editor`, `spell_picker`, `resources_editor`) all version-stamped.

### Notes
- htmx (loaded from `unpkg.com`) and Google Fonts (loaded from `fonts.googleapis.com` / `fonts.gstatic.com`) are not version-stamped — those are third-party CDN URLs with their own caching, and pinning to `htmx.org@1.9.12` already provides URL-level invalidation when we bump the htmx pin.
- The favicon at `/static/favicon.svg` is left unstamped — it's served separately by the browser tab UI, and our brand mark doesn't change per release. Adding `?v=…` to it would force a re-fetch on every release with no user-visible benefit.
- Static data files fetched via `fetch()` at runtime (e.g. the spell list JSON, the homebrew content endpoints) go through the dynamic `/api/...` and `/local/...` routes and are not cached aggressively by Cloudflare, so they don't need this treatment.
- This is a non-functional change for v2.3.41 / v2.3.42 users on first load — they'll fetch the fresh files anyway because the URL has changed. The only behavioural difference is "no more days of stale-asset confusion after a deploy."

---

## [2.3.42] - 2026-05-16

**Schema version:** 52
**Commit summary:** **✏️ Edit** breadcrumb button on every monster sheet — when the underlying TokenTemplate resolves to a `local-homebrew` monster, the GM gets a one-click bounce to the campaign-settings homebrew editor anchored to that specific monster's `<details>` panel (auto-opens + scrolls into view + lazy-inits the features editor inside). Closes the gap between "look at the stat block" and "edit the stat block" — previously the GM had to navigate to settings → Homebrew tab → Monsters sub-tab → scroll → expand the right card by hand. User-requested.
**Description:** Three coordinated pieces. (1) `monster_template_sheet_page` in `app/routes/tabletop_routes.py` now reads `tmpl.sheet["monster_slug"]` and runs it through `local_content.resolve`; only when the resolver tags the source as `local-homebrew` does it pass `edit_homebrew_slug=<slug>` into the template context. SRD and Open5e-cached monsters (where editing through the homebrew form would silently fork the source) get None instead — those stay read-only, matching the existing "📋 Clone" button's intentionally explicit fork flow. (2) `monster_page.html` renders the `✏️ Edit` button in the breadcrumb when `edit_homebrew_slug` is set, with `href="/campaign/{cid}/settings#custom-monster-{slug}"` and `target="_top"` so the click breaks out of the v2.3.15 iframe drawer (otherwise the settings page would render inside the drawer with no way back). (3) `campaign_settings.html` adds `id="custom-monster-{slug}"` to each homebrew monster's `<details>` element, extends `_resolveFromHash()` to map `custom-monster-*` / `custom-class-*` / `custom-subclass-*` / `custom-race-*` / `custom-background-*` / `custom-feat-*` prefixes to the matching homebrew sub-tab, and adds `_maybeOpenAnchorDetails()` which opens the matching `<details>` element and `scrollIntoView`s it on initial load and on hashchange. The `<details>` `toggle` event then drives the existing `features_editor.js` / `spell_picker.js` / `resources_editor.js` lazy-init hooks, so the GM lands on a fully-initialised editor with no extra click.

### Added
- `app/routes/tabletop_routes.py` `monster_template_sheet_page` — `edit_homebrew_slug` template variable, set to `tmpl.sheet["monster_slug"]` when the resolver returns source `local-homebrew`, None otherwise.
- `app/templates/monster_page.html` — `✏️ Edit` breadcrumb link, gated on `edit_homebrew_slug`. `target="_top"` so the click escapes the v2.3.15 drawer iframe.
- `app/templates/campaign_settings.html` — `id="custom-monster-{slug}"` on every per-monster `<details>` in the homebrew Monsters sub-tab so the v2.3.42 edit link can deep-link to a single entry.
- `app/templates/campaign_settings.html` — `_resolveFromHash` recognises the six `custom-{type}-*` per-entry hash prefixes and routes them to the correct sub-tab. Future per-entry deep links to homebrew classes / subclasses / races / backgrounds / feats already work without further template changes (just add the `id="..."` to those `<details>` and a 📋 link in the relevant read-only view).
- `app/templates/campaign_settings.html` — `_maybeOpenAnchorDetails()` opens the matching `<details>` element on initial load and on hashchange, then `scrollIntoView` so the GM lands on the form they wanted. The existing `toggle`-event lazy-init in `features_editor.js` picks up the open and initialises the row-based editor.

### Notes
- The edit button does not appear on SRD-imported monsters (e.g. a TokenTemplate created via the Open5e search) — those have no `monster_slug` pointer to a `local-homebrew` source, and editing the TokenTemplate's frozen-copy sheet would diverge from the SRD source rather than create a proper homebrew override. The Clone button on the homebrew tab is the right tool there (creates a homebrew copy first, then editable).
- The button is GM-only because the entire monster sheet page is GM-only — the route check at the top of `monster_template_sheet_page` rejects non-GMs with 403 before any rendering happens.
- The new `_maybeOpenAnchorDetails` only opens `<details>` elements (not the older `.settings-section` sections, which already auto-show via `_applySelection`). This keeps the section-name CRUD redirect behaviour (`…/settings#custom-monsters` → opens the Monsters sub-tab) unchanged.
- The demo's four NPC monsters (Bandit Captain, Bandit, Thug, Goblin Captain Grixxa) are all homebrew — clicking 📋 Sheet on any of them in the init tracker, then ✏️ Edit, lands the GM directly on the form for that monster.

---

## [2.3.41] - 2026-05-16

**Schema version:** 52
**Commit summary:** Surface the v2.3.40 `Action.charges_max` field in the homebrew Actions editor — every action row now carries a **Charges** number input alongside the existing Attack / Damage / Save fields, so GMs can mark an action as limited-use without hand-editing JSON. Blank or 0 = unlimited (the default); a positive integer (1, 2, 3…) drives the GM init tracker's per-combatant `cur/max` pill + ↻ recharge button + button-disabled-when-spent behaviour shipped in v2.3.40. User-reported gap.
**Description:** v2.3.40 added the `charges_max` field to `Action` and wired the full init-tracker rendering / decrement / reset flow, but did not extend `features_editor.js` to surface it — GMs creating new homebrew monsters had to drop into the raw JSON tier (or wait for a hand-edit like the `app/demo_seed.py` Grixxa entry) to set the field, which the user (correctly) called out as a missing piece. This commit adds a seventh column to the action-row grid (now `auto 80px 110px 130px 90px 70px 80px`), an `_mkLabeledInput("Charges", "0", …)` widget with `type=number`, `min=0`, `max=99`, and a `title` tooltip explaining the semantics ("Uses per encounter (e.g. 1 for 'Recharge 5-6' or '1/day'). Blank or 0 = unlimited."). The serializer in `_serialize` emits `charges_max: N` only when N > 0, keeping the JSON terse for the unlimited-use majority (every existing action without an explicit cap stays unchanged on round-trip). No backend changes — the existing Pydantic `Action.charges_max: int = 0` default already handles blanks/missing keys.

### Added
- `app/static/features_editor.js` — Charges number input on every action-mode row. Surfaces in: monster Actions / Special Abilities / Reactions / Legendary Actions editors (campaign settings → 📋 Homebrew Monsters → expand an entry → any of the four action lists). Initial value reads from `initial.charges_max` so re-opening an entry shows the stored value.
- `app/static/features_editor.js` `_serialize` — `charges_max: N` emitted only when N > 0 so unmodified rows stay JSON-clean.

### Notes
- Demo's Grixxa Frightful Howl (`charges_max: 1`) now round-trips through the UI — opening the homebrew editor for the Goblin Captain shows "1" in the Charges column for that action; saving without changes leaves the JSON identical.
- The numeric input takes the same 32px dense-panel minimum as the surrounding inputs per CLAUDE.md.
- Existing JSON sources (homebrew files, demo seeds) without the field stay valid — the Pydantic default makes `charges_max` absent ⇄ `0` interchangeable.

---

## [2.3.40] - 2026-05-16

**Schema version:** 52
**Commit summary:** Per-combatant **charge tracking** for monster limited-use actions in the GM init tracker — actions with `charges_max > 0` (e.g. Frightful Howl 1/day, Recharge 5–6 breath weapons, X/short-rest specials) now render a `cur/max` pill next to the action name, decrement on every roll-button click (🎯 / 🎲 / 📋), and disable the strike buttons when spent. A `↻` recharge button per row resets the count back to max. User-requested.
**Description:** Adds `charges_max: int = 0` to the shared `Action` schema in `app/action_schema.py` — zero means unlimited (the existing default; all prior actions stay usable indefinitely). The homebrew monster sheet adapter (`_monster_template_to_sheet` in `app/routes/tabletop_routes.py`) now passes `id` and `charges_max` through into the per-attack dict so the inline init view sees them alongside the existing attack_bonus / damage / save_dc fields. `buildMonsterInitSheet` in `app/templates/tabletop.html` initializes `combatant.action_charges[action.id] = charges_max` lazily on first render, renders the pill + ↻ button when `charges_max > 0`, and disables the strike-button trio when `charges_cur <= 0`. The `.monster-strike-btn` document-level click handler now decrements `combatant.action_charges[action_id]` (clamped at zero) on every successful POST `/roll`, calls `saveBattle()` + `renderBattle()` so the new count persists across re-renders and survives a localStorage round-trip. A sibling `.monster-charge-reset` handler `delete`s the per-action key so the next render reseeds it back to max (also `saveBattle()` + `renderBattle()`). State lives entirely client-side per combatant — the same Action instance shared across multiple combatants (e.g. three Bandits with "Heavy Crossbow Reload 1/round") gets separate per-row counts. The demo update on Grixxa's Frightful Howl (`charges_max: 1`) lets a fresh demo session prove the flow: roll the howl once, watch the buttons disable and the pill flip to amber `0/1`, click ↻ to recharge.
**Description (cont):** Click-counter semantics: every click on a strike button decrements once, not once per combat round, since the GM is the one driving the cadence and a hit-and-damage flow uses two separate UI clicks. If the GM wants the howl to fire only when an attack actually lands, they click 🎯 first (decrements), see the d20 in the log, decide it hit, then click 🎲 — which decrements again. This is by design; the rare "I want to roll attack and damage but only consume one charge" case can be resolved by a single ↻ click between the two rolls.

### Added
- `app/action_schema.py` `Action.charges_max: int = 0` — declarative limited-use field on the shared Action schema. Zero (default) means unlimited; positive integer renders the cur/max pill + ↻ recharge button + button-disabled-when-spent semantics in the GM init tracker.
- `app/templates/tabletop.html` `buildMonsterInitSheet` per-action `combatant.action_charges` initialization, `cur/max` pill rendering, `↻` recharge button rendering, button disabled-when-spent rendering. Per-combatant counts persist via the existing `saveBattle()` localStorage path.
- `app/templates/tabletop.html` `.monster-strike-btn` click-handler decrement branch — on a successful `/roll` response, decrements `comb.action_charges[action_id]` (clamped at zero) and re-renders so the disabled state appears immediately.
- `app/templates/tabletop.html` `.monster-charge-reset` click-handler — `delete`s the per-action key so the next render reseeds the count from `charges_max`. Resets are unbounded (no rate limit) — the GM is trusted to recharge correctly per short / long rest.
- `app/templates/tabletop.html` CSS for `.monster-action-charges` (green pill, amber `.spent` variant) and `.monster-charge-reset` (32×32 dense-panel button per CLAUDE.md).
- `app/demo_seed.py` Grixxa's Frightful Howl gets `charges_max: 1` so a fresh demo proves the flow end-to-end.

### Changed
- `app/routes/tabletop_routes.py` `_monster_template_to_sheet` `atk_entry` — added `id` and `charges_max` pass-through so the inline init view can key per-action charge state and the rendered counter / disabled-button logic can read it.

### Notes
- The shared `Action.charges_max` field is editor-ready but the homebrew monster Actions editor (`app/templates/_features_editor.html`) does not yet surface a numeric input for it — homebrew authors will hit it via the JSON-edit panel for now. Adding a "Charges/use" number input is a follow-up; the demo entry is hand-edited in `seed_homebrew_files`.
- The full standalone monster sheet (`app/templates/sheet_dnd5e.html` with `is_monster_sheet=True`) does not yet render charges. The init-tracker view is the primary in-combat surface; the static sheet is a read-only reference and can stay un-counted for now.
- The decrement key uses `action.id` (from the structured `actions` array) or falls back to a slugified name when missing (`"frightful howl"` → `"frightful-howl"`). Slugs are stable across re-renders so the per-combatant count survives template edits that leave the name intact.
- The reset is by-delete-key rather than by-set-to-max so the renderer's `?? a.charges_max` fallback drives the value — keeps the source of truth (max) at the template level rather than duplicating it into per-combatant state.

---

## [2.3.39] - 2026-05-16

**Schema version:** 52
**Commit summary:** Fix bare NPC monster sheets in the GM init tracker when the combatant's stored `token_template_id` no longer matches any current template. Adds a name-substring fallback in `buildMonsterInitSheet` that finds the right template by combatant label (e.g. "Vex (Bandit Captain)" → template "Bandit Captain") and heals the combatant in place so the per-row "📋 Sheet" link also routes correctly. User-reported.
**Description:** Reported symptom: expanding a monster row in the init tracker shows nothing (no AC chips, no ability grid, no per-action buttons), despite the inline view working in earlier sessions. Most likely root cause: stale `localStorage` battle.combatants — the GM had combatants saved from before a demo reseed cycle, and after the reseed the template's id had been reassigned. `allTemplates.find(t => t.id === combatant.token_template_id)` returned undefined → `buildMonsterInitSheet` early-returned `''` → bare row. Fix walks `allTemplates` a second time looking for a template whose name appears as a substring of the combatant's name, which works for the demo's "Vex (Bandit Captain)" / "Grixxa (Goblin Captain)" / "Bandit Alpha" / "Thug" labels (they all derive from a template name) and any encounter where the GM kept the template-name suffix. On a successful fallback the helper writes the correct `token_template_id` back onto the combatant in place and calls `saveBattle()` so the next render skips the search AND the 2.3.33 "📋 Sheet" button URL gets corrected too. If neither lookup works (e.g. a manually-named combatant with no template association), the helper still early-returns and the GM sees the static edit row only — same behavior as before.

### Fixed
- `app/templates/tabletop.html` `buildMonsterInitSheet` — added a name-substring fallback over `allTemplates` when the by-id lookup misses, with in-place id-healing + `saveBattle()` so the fix persists across re-renders.

### Notes
- The name-match is case-insensitive `String#indexOf` (not a regex), so it tolerates the common "Boss Name (Template Name)" label pattern without surprises. Multiple template-name matches collapse to the first hit — fine in practice (a "Bandit Captain Bandit" combatant would still resolve to one of them).
- Does not invalidate the underlying localStorage scheme — the GM can still reset the init tracker with the existing "Remove" button per combatant if a wrong template gets healed onto a combatant after a manual rename. Long-term: the encounter-load endpoint should translate the encounter's `initiative` field to `battle_state` so a freshly-loaded encounter doesn't depend on the GM's localStorage at all. Filed as a follow-up.

---

## [2.3.38] - 2026-05-16

**Schema version:** 52
**Commit summary:** Docs-only: add `docs/demo/image-prompts.md` with ready-to-paste image-generator prompts for every PC, every NPC type, and the Tavern Brawl battle map in the demo dataset. Model-agnostic (Midjourney / DALL-E / Stable Diffusion). Includes a "how to wire the generated PNG back into `seed_tokens`" checklist so the demo can grow from color-swatch tokens to fully-illustrated ones over time. No code change.
**Description:** User-requested follow-up to the v2.3.32 README demo description. The seed already references shipped PNGs for the two original PCs (`rogue.png` / `wizard.png`) but every other entity — the GM's Brother Tavik (added v2.3.25), all six NPCs (Bandit Captain / Bandit ×3 / Thug / Goblin Captain), and the tavern map — currently render as color swatches because no token art exists. This doc carries character descriptions that match the seeded sheets verbatim (race, class, alignment, weapons, signature spells) so the rendered token has the right visual identity to slot into the demo's narrative. Each prompt is annotated with framing notes (3-quarter view, 1:1 aspect, isolated against transparent background, suitable for a 256-pixel circular token) and matched negative-prompt suggestions. A model-specific notes section at the bottom calls out Midjourney's `--ar 1:1 --style raw` flags, DALL-E's transparent-background limitation, and Stable Diffusion checkpoint suggestions. Closing section is a 6-step "after generation" checklist (background-remove, crop, downscale to 256×256, drop in `app/static/demo/tokens/`, wire `image_url` into the `Token(...)` row in `seed_tokens`, bump and ship) that mirrors the conventions the two shipped tokens already follow.

### Added
- `docs/demo/image-prompts.md` — character + map prompts for every demo entity. Organized as: token-file path table, style baseline, three PC sub-sections, four NPC sub-sections (Vex / Grixxa / Thug / Bandit ×3 variants), tavern battle-map prompt, model-specific notes, post-generation checklist.

### Notes
- The two shipped tokens (`rogue.png` for Pip, `wizard.png` for Thalindra) are referenced as the style baseline. New generations should match their painterly fantasy look.
- The bandit trio (Alpha / Beta / Gamma) gets three minor-variation prompts rather than three independent prompts — the encounter places them as stat-identical mooks but the GM needs to tell them apart visually on the map. The prompt suggests Stable Diffusion's ControlNet OpenPose to share a pose across the trio if the operator wants consistency.
- No version bumps for adding generated art alone — the docstring + checklist note that an art-drop commit is its own PATCH bump per CLAUDE.md.

---

## [2.3.37] - 2026-05-16

**Schema version:** 52
**Commit summary:** Homebrew **📋 Clone** button on every entry in campaign settings — feats, backgrounds, races, monsters, classes, and subclasses. Closes [`TODO.md`](TODO.md) → GM Tools → Homebrew Clone. Lets GMs spin off variants ("Grixxa" → "Veteran Goblin Captain", "Bandit" → "Wounded Bandit") without retyping every field.
**Description:** One generic helper `_clone_homebrew_record(*, src_slug, content_type, target_slug=None)` in `app/routes/tabletop_routes.py`: GM-permission-check, resolve source via `local_content.resolve`, guard that source is `local-homebrew` (not shipped SRD), `_unique_clone_slug` to pick a `copy-of-{slug}` that doesn't collide, build new record with `name = "Copy of {original}"`, write via `local_content.write_homebrew`. Six thin POST endpoints — `/campaign/{cid}/custom-{feats|backgrounds|races|monsters|classes|subclasses}/{slug}/clone` — call the helper and redirect to the relevant `#custom-{type}` anchor on the settings page so the new entry shows in the list ready to edit. Subclasses get special handling because their slug is `{class_slug}-{subclass_slug}`: a dedicated route extracts the class prefix from the source slug and re-prefixes the clone as `{class_slug}-copy-of-{bare_sub}` so the clone stays a sibling under the same parent class instead of becoming a flat `copy-of-{combined}` root entry that the resolver couldn't route correctly. Template gets a 📋 Clone form alongside each existing Delete form (one per type, six places), styled inline-block + side-by-side so the row layout stays tight. No clone for shipped SRD content — `_clone_homebrew_record` rejects with 404 unless the resolver returned `source == "local-homebrew"`.

### Added
- `app/routes/tabletop_routes.py` `_unique_clone_slug(base, content_type, campaign_id)` — collision-safe `copy-of-{slug}` generator, appends `-2`/`-3`/… up to 50 attempts before giving up with a 500.
- `app/routes/tabletop_routes.py` `_clone_homebrew_record(*, …)` — generic helper used by all six clone routes. GM-only via `_require_gm_for_campaign`; SRD source rejected via the resolver's source label check.
- Six new POST routes: `clone_custom_feat` / `clone_custom_background` / `clone_custom_race` / `clone_custom_monster` / `clone_custom_class` / `clone_custom_subclass` (subclass route handles the namespaced-slug case before delegating).
- Six 📋 Clone forms in `app/templates/campaign_settings.html`, one per homebrew type, rendered inline-block next to the existing Delete form. Tooltip on each clarifies the destination scope.

### Notes
- Demo usage: a GM exploring the demo can clone Grixxa (Goblin Captain) → "Copy of Goblin Captain" with slug `copy-of-goblin-captain`, then edit name + HP + actions to make a Veteran variant — proves the editor + clone end-to-end with no SRD lookup needed.
- The clone preserves all source fields verbatim (`{**source, slug: new, name: new}`) so structured action lists, custom stat blocks, prerequisites, descs, etc. all carry over. Only `slug`, `name`, `scope`, and `source` are rewritten.
- The collision-safe slug starts at `copy-of-{slug}` and bumps to `copy-of-{slug}-2`, `copy-of-{slug}-3`, … on conflict; this lets the GM clone the same source multiple times without manual disambiguation.
- Shipped SRD content (e.g. `app/data/local/dnd5e/monsters/bandit-captain.json`) can't be cloned through this flow — by design. To fork SRD into homebrew, the GM uses the existing "Import" flow which creates a fresh homebrew record from an Open5e search. A "Fork SRD" button is a separate follow-up if there's demand.

---

## [2.3.36] - 2026-05-16

**Schema version:** 52
**Commit summary:** Fix the 2.3.35 ship — restoring the outer `{% if not is_monster_sheet %}` that the previous edit accidentally dropped. 2.3.35's intent (gate Spells fieldset on caster status) was correct but its diff replaced the outer monster-hide opener instead of nesting inside it, orphaning the matching `{% endif %}` near the Notes fieldset and crashing every full-sheet render with `TemplateSyntaxError: Encountered unknown tag 'endif'`. Verified by Jinja-block-balance count (`ifs == endifs == 83`) and a clean HTTP 200 on all three demo PC sheets.
**Description:** 2.3.35's Edit replaced the line `{% if not is_monster_sheet %}` with `{% if _is_caster %}` rather than INSERTING the new opener as a nested block. The 2.3.13 monster-hide endif at line 1479 then matched against... nothing, since the outer if was gone. Every full sheet render 500'd at template-parse time. Fix is a one-line re-insertion of `{% if not is_monster_sheet %}` above the new `{% set _is_caster %}` line so the structure is: outer 2.3.13 `if not is_monster_sheet` → inner 2.3.35 `if _is_caster` → Spells fieldset → inner endif → ...other fieldsets... → outer endif. Both the broken 2.3.35 commit and this fix kept in history; rolling back 2.3.35 alone would have lost the mini-sheet partial change too.

### Fixed
- `app/templates/sheet_dnd5e.html` — restored the `{% if not is_monster_sheet %}` opener at line 951 (was inadvertently overwritten in 2.3.35). The new 2.3.35 `{% set _is_caster %}` + `{% if _is_caster %}` now sit nested inside it.

### Notes
- Caught by HTTP smoke-test (`curl /campaign/1/character/2/sheet → 500`) after rebuild. Lesson for the file: when adding a nested if inside a long-spanning if block, double-check both the opener and the existing-block endif location.

---

## [2.3.35] - 2026-05-16

**Schema version:** 52
**Commit summary:** Hide the Spells section on non-caster character sheets — Rogue / Barbarian / Fighter (sans Eldritch Knight) / Monk PCs no longer carry an empty Spells fieldset on the full sheet or a vestigial Spells tab on the mini-sheet. Closes [`TODO.md`](TODO.md) → Character Sheet → "Hide Spells from Non-Casters".
**Description:** `_is_caster` gate added to both `sheet_dnd5e.html` (full sheet) and `_mini_sheet_card.html` (mini-sheet) — caster status is true if any of: (1) `sheet.class_spellcasting` is non-empty (the standard single-class caster signal — Wizard "INT", Cleric "WIS", etc.), (2) `sheet.spell_slots` is a non-empty dict (multiclass rolls up across classes via the spell-slot calculator, so a Fighter 5 / Wizard 3 still surfaces slots even if `class_spellcasting` reads the primary class), or (3) `sheet.spells` list is non-empty (defensive — if a player has manually added a spell entry, the player evidently wants it visible). Full sheet: Spells fieldset (lines 956–1059) wrapped in `{% if _is_caster %}`, nested inside the existing 2.3.13 `{% if not is_monster_sheet %}` block so the broader monster gate stays balanced. Mini-sheet: `_is_caster` is AND-ed with the existing `_spell_vis.any` check that gates both the Spells tab button and the panel body, so non-casters skip rendering even if a spell snuck into the list.

### Added
- `app/templates/sheet_dnd5e.html` — `_is_caster` Jinja `{% set %}` right before the Spells fieldset, plus an inner `{% if _is_caster %}` ... `{% endif %}` that scopes the gate to just the Spells fieldset (not the broader 2.3.13 monster-hide block which also covers Class Resources / Inventory / etc.).
- `app/templates/_mini_sheet_card.html` — `_is_caster` `{% set %}` right after the existing `_PREPARED_CASTERS` / `_primary_slug` lines. Used in the Spells tab button + Spells panel conditionals.

### Notes
- Demo PCs: Pip (Rogue) is non-caster — full sheet Spells fieldset hides, mini-sheet has no Spells tab. Thalindra (Wizard, INT) and Brother Tavik (Cleric, WIS) are unchanged (both have `class_spellcasting` set).
- The Spell Browser overlay (`#spell-browser-overlay` in the full sheet, used by the "Browse Spells" button) is left in the DOM at `display:none`. It can only be triggered by the in-fieldset button which now doesn't render on non-casters, so it's unreachable as expected. Trimming the overlay markup is a follow-up if DOM weight becomes a concern.
- Multiclass detection edge case: a hypothetical character with no spell_slots configured yet but `classes` containing a caster class wouldn't be detected. Mitigation: the spell-slot calc in `app/static/sheet.js` populates `spell_slots` automatically on multiclass setup; this commit relies on that to keep the heuristic simple.

---

## [2.3.34] - 2026-05-16

**Schema version:** 52
**Commit summary:** Revert the v2.3.17 monster mini-sheet swap and restore the v2.3.9 inline stat-block view in the GM initiative tracker — user preferred the denser inline AC/Spd chips + 6-cell ability mod grid + per-action 🎯/🎲/📋 buttons over the heavier PC-style mini-sheet. The v2.3.33 per-row "📋 Sheet" button stays so the full PC-style sheet is still one click away in the drawer when the GM wants it. User-reported.
**Description:** v2.3.17 rendered every monster TokenTemplate into a hidden `#monster-mini-sheet-pool` div using the same partial PCs use, then stole the mini-body into the init-card-sheet on expand. The result was a tab-rich, multi-section card that obscured the at-a-glance combat info (HP, AC, all six ability mods, the per-action attack/damage/save buttons) under a Skills/Attacks/Spells tab gate. Reverts the pool render + the partial-based monster path; restores the v2.3.9 `buildMonsterInitSheet` that builds an inline AC/Spd + ability grid + per-action row layout directly into the init-card-sheet. The `.monster-strike-btn` CSS rule and the document-level click handler that POSTs the three roll kinds (attack / damage / save) to `/api/campaign/{cid}/roll` come back with it. The v2.3.33 "📋 Sheet" button on each init-entry header is unchanged — it still opens the v2.3.10 read-only standalone monster sheet in the v2.3.15 drawer for deeper inspection. Critical detail: the v2.3.9 inline render reads `tmpl.sheet` directly, which at the time the demo's `_npc_sheet` was minimal (`abilities: {STR:10, ...}` placeholder). New change in `tabletop_routes.py` runs every TokenTemplate's sheet through `_monster_template_to_sheet` server-side before serializing into `tmpl_data`, so the inline view now sees the real projected stats (Bandit Captain's STR 15 / DEX 16 etc., Goblin Captain's full structured action set, etc.) without any client-side resolve call.

### Changed
- `app/routes/tabletop_routes.py` tabletop route — `tmpl_data` build replaces each template's raw `sheet` with `_monster_template_to_sheet(t, campaign.id)` so the client sees the resolved stat block. For non-monster templates the adapter returns the input unchanged. Removes the v2.3.17 `monster_templates` context (no longer needed without the pool render).
- `app/templates/tabletop.html` `buildMonsterInitSheet` — restored to the v2.3.9 inline layout (AC/Spd chips + 6-cell ability mod grid + per-action row with 🎯 Attack / 🎲 Dmg / 📋 Save buttons sourced from `sh.actions` or `sh.attacks`).
- `app/templates/tabletop.html` `.monster-strike-btn` CSS — restored.
- `app/templates/tabletop.html` `#initiative-list` document-level click handler — restored. Builds the appropriate `/roll` expression per `data-kind` (attack assembles `1d20+bonus`; damage sends the dice expression; save sends `expression: 0` + DC X SAVE note); all three POST with `skip_roll_state: true` so the GM's own char's adv/dis pill doesn't bleed in.

### Removed
- `#monster-mini-sheet-pool` div in `app/templates/tabletop.html` — the v2.3.17 hidden pool that fed monster mini-bodies into the init tracker via the body-steal logic. The init tracker now goes straight to `buildMonsterInitSheet` for combatants without a `char_id`.

### Notes
- `_SyntheticMonsterChar`, `_monster_template_to_sheet`, and the standalone `/campaign/{cid}/monster-template/{tid}/sheet` route all stay. The drawer still opens the read-only PC-style sheet for monsters when the GM clicks the v2.3.33 📋 Sheet button — that path is unchanged.
- PCs continue to use the v2.3.16 `_mini_sheet_card.html` partial unchanged; only the monster path is reverted.
- All four homebrew monsters (Bandit Captain / Bandit / Thug / Goblin Captain) seeded by `seed_homebrew_files` now render with real stats inline because the server pre-resolves the template sheet. The original v2.3.9 + minimal `_npc_sheet` combination would have shown 10/10/10 placeholders — fixed as a side effect of the `tmpl_data` resolve.

---

## [2.3.33] - 2026-05-16

**Schema version:** 52
**Commit summary:** Init tracker: every combatant row now has a **📋 Sheet** button in its header that opens the relevant sheet (PC's full character sheet for player combatants, monster stat block for NPCs) in the 2.3.15 slide-out drawer. Completes the "GM never has to leave the init tracker" arc — every kind of mid-combat lookup (HP edit, attack roll, sheet read, expand mini-body) is reachable from the init tracker entry without finding a token on the map first. Closes the [`TODO.md`](TODO.md) → GM Tools → "Initiative Tracker — Open Sheet for Active Combatant" item.
**Description:** The 2.3.15 drawer interceptor only matched `a.monster-sheet-link`; this commit generalizes the selector to `a.monster-sheet-link, a.character-sheet-link` and extends the label fallback to read either `data-monster-name` or `data-character-name`. `renderBattle` now stamps an Open Sheet anchor between the header info column and the expand chevron — PCs get the new `.character-sheet-link` class pointing at `/campaign/{cid}/character/{id}/sheet`; monsters get the existing `.monster-sheet-link` class pointing at `/campaign/{cid}/monster-template/{tid}/sheet`. Manual init entries (no `char_id` and no `token_template_id`) skip the button. The mini-header click handler that toggles the row's expand/collapse now also ignores clicks inside `a` elements (was only `input, button`) so the new anchor doesn't double-fire as both "open sheet" AND "expand row". Active-turn entries get a subtly stronger purple tint on the button to draw the GM's eye to whose turn it is.

### Added
- `app/templates/tabletop.html` `renderBattle` — Open Sheet anchor per init entry. PC link uses `.character-sheet-link` + `data-character-name`; monster link uses `.monster-sheet-link` + `data-monster-name`. `target="_blank" rel="noopener"` so Cmd/Ctrl-click pops the sheet in a new tab (the 2.3.15 drawer interceptor skips modifier-clicks for exactly this reason).
- `app/templates/tabletop.html` `.init-sheet-btn` CSS rule — 32 px min-height (dense-panel floor per CLAUDE.md), purple palette matching the 2.3.14 monster-sheet link affordance, slightly stronger tint on `.init-entry.active-turn`.

### Changed
- `app/templates/tabletop.html` drawer link interceptor — selector generalized from `a.monster-sheet-link` to `a.monster-sheet-link, a.character-sheet-link`; label resolution falls back through `data-monster-name` → `data-character-name` → text content.
- `app/templates/tabletop.html` mini-header expand/collapse handler — guard widened from `input, button` to `input, button, a` so the new Open Sheet anchor doesn't ALSO toggle the row.

### Notes
- Active-turn highlighting is the existing `.init-entry.active-turn` CSS plus the new heavier purple on the button; the TODO suggested "most prominent on the currently-active turn entry", which is already true visually.
- PC sheets opened in the drawer iframe are fully interactive (not read-only) — the GM can roll abilities/skills/saves/attacks from inside the iframe and the rolls land in the campaign roll log on the parent tabletop via the existing WebSocket fanout. Same path the 2.3.10 monster sheet uses.
- Sheet-button-click is deliberately separate from row-expand-click. Both work side-by-side: click the chevron area → expand the mini-body inline; click the Sheet button → open the full sheet in the drawer.

---

## [2.3.32] - 2026-05-16

**Schema version:** 52
**Commit summary:** Docs-only: add a "Demo" section to the README that describes the setting (Tavern Brawl), the three PCs (Pip / Thalindra / Brother Tavik), all six NPCs (Vex / Grixxa / Thug / 3 Bandits), the pre-rolled initiative order, the three sign-in credentials, the reset behavior, and the env-var snippet for enabling demo mode on a self-hosted deploy. User-requested alongside 2.3.31. No code change.
**Description:** Before this commit the README listed "Features" and went straight to "Architecture" — a reader exploring the project had no way to know what they'd see if they visited a demo URL beyond `docs/plans/demo-mode.md`'s design-doc-level "Demo: The Sundered Vault" reference. New section between Features and Architecture documents the demo end-to-end: sign-in table with the three accounts + shared password, opening-scene paragraph, three tables (PCs / NPCs / pre-rolled initiative), a "what gets wiped on reset" pointer, and an `.env` snippet for operators enabling demo mode on their own deploy. Pulls forward the demo's existing flavor (Vex Vance, Brother Tavik Stonebrow, Grixxa) and the 2.3.31 detail that all six NPCs are homebrew-authored so the demo shows the homebrew tier flow end-to-end. Links to `docs/plans/demo-mode.md` for design depth and `.env.example` for the full var list.

### Added
- `README.md` new `## Demo` section between `## Features` and `## Architecture`. Sub-sections: Sign in, The setting, Player characters (3-row table), NPCs in the Tavern Brawl (6-row table), Pre-rolled initiative (numbered list), What gets wiped on reset, Enabling demo mode on your own deploy (env snippet).

### Notes
- The PC + NPC tables are intentionally compact (name / class+level / race / owner | name / stat block / CR / role) rather than rendering full stats — readers who want the numbers can click through on a running demo. The README is the elevator pitch, not the stat block.

---

## [2.3.31] - 2026-05-16

**Schema version:** 52
**Commit summary:** Demo: bring the remaining three NPC stat blocks (Bandit Captain / Bandit / Thug) into the homebrew tier alongside the Goblin Captain. All four demo combatants now resolve through `local_content.resolve` → homebrew JSON instead of the SRD tier, demonstrating the homebrew authoring path end-to-end and giving each NPC explicit `attack_bonus` fields (no longer relying on the 2.3.11 desc-text regex fallback). User-requested.
**Description:** Before this commit Grixxa (Goblin Captain) was the only demo NPC that resolved through the homebrew tier — the others resolved through the shipped SRD JSONs in `app/data/local/dnd5e/monsters/`. Functionally identical mini-sheets (same HP/AC/abilities/attacks), but the demo only showcased the homebrew flow for one of four NPCs. Adds three more `write_homebrew(..., type="monsters", ...)` calls in `seed_homebrew_files` for `bandit-captain` / `bandit` / `thug`, each shadowing the shipped slug via the resolve's homebrew-first priority. Stats match the SRD baseline so the rendered values don't change; what changes is the data shape on disk (action `attack_bonus` is now an explicit string like `"+5"` instead of `null` + regex-extracted from desc), and the demo's homebrew JSON file count goes from 2 to 5 (1 feat + 4 monsters). Each NPC also gets special abilities surfaced as `category: "special_ability"` entries on the unified actions list — Pack Tactics for the Thug, Leadership + Parry for the Bandit Captain (the SRD files had these in the Multiattack desc only).

### Added
- `app/demo_seed.py` `seed_homebrew_files` — three new `write_homebrew` calls for the bandit-captain / bandit / thug slugs. Each ships full structured actions (`attack_roll: true`, explicit `attack_bonus`, `damage`, `damage_type`) and category-tagged special abilities where applicable.

### Notes
- The `_attribution` field on each new monster credits the SRD baseline ("Stats from D&D 5e SRD 5.1; authored as homebrew so the demo exercises the homebrew tier end-to-end") so the homebrew tier override doesn't accidentally claim the SRD's mechanics as demo-original work.
- All four demo monster TokenTemplates keep their `monster_slug` pointer shape — what changes is which tier the resolver hits. Stops, swaps, and tweaks remain a simple JSON edit per monster.
- Module docstring updated: "one richly-authored monster" → "four richly-authored monsters".

---

## [2.3.30] - 2026-05-16

**Schema version:** 52
**Commit summary:** Fix the 2.3.29 logged-in 404 redirect not actually firing — registered the handler on FastAPI's `HTTPException` subclass instead of Starlette's base class, which Starlette's routing layer uses when raising 404s for unmatched paths. Re-registered on `starlette.exceptions.HTTPException` (which FastAPI's subclass inherits from) so the handler catches both routing-layer 404s and explicit `raise HTTPException(...)` calls. The 2.3.28 401 "Login required" redirect kept working because that's an explicit FastAPI subclass raise.
**Description:** Ship-broke 2.3.29 because the exception handler decorator was scoped to FastAPI's `HTTPException` only. FastAPI's class is `fastapi.HTTPException` which inherits from `starlette.exceptions.HTTPException`. When a route handler does `raise HTTPException(...)`, it raises the FastAPI subclass; when Starlette's routing layer can't match a path, it raises the BASE class. A handler registered on the subclass catches only the former, not the latter. Re-registering on `StarletteHTTPException` catches both. Verified locally: anonymous `/does-not-exist` → 404 (unchanged); logged-in `/does-not-exist` → 303 → `/`; anonymous `/campaign/99999` → 303 → `/login?next=/campaign/99999` (2.3.28 401 path unaffected).

### Fixed
- `app/main.py` `_auth_redirect_handler` — now decorated with `@app.exception_handler(StarletteHTTPException)` and typed against `StarletteHTTPException`. Removed the unused `from fastapi import HTTPException` import. Behavior change: routing-layer 404s now reach the handler.

---

## [2.3.29] - 2026-05-16

**Schema version:** 52
**Commit summary:** Two user-requested UX tweaks. (1) Logged-in users who hit a non-existent page now get a `303 → /` instead of the JSON `{"detail":"Not Found"}` or browser-default 404. Anonymous 404s stay as-is so they don't leak page existence by branching per auth state. (2) Small muted version chip (`· v2.3.29`) rendered next to the SimpleVTT brand in the topnav so the tabletop view — which blanks the footer to reclaim vertical space — still surfaces the running version.
**Description:** Extends the 2.3.28 `_auth_redirect_handler` in `app/main.py` to also catch 404 when the caller wants HTML AND the session carries a `user_id` (peeked from `request.session.get("user_id")` directly — no DB round-trip needed, since we only need "is anyone logged in" not the full User row). Returns `RedirectResponse("/", 303)`. 401 handling for `"Login required"` is unchanged. JSON / fetch callers (which always send `Accept: application/json`) and anonymous HTML callers fall through to Starlette's default handler. Version chip is a `<span class="brand-version">· v{APP_VERSION}</span>` appended inside the brand `<a>` so it inherits the link semantics; CSS rule in `style.css` sets it to 11px / `--fg-mute` so it doesn't compete visually with the brand. `title` attribute carries the schema version so hovering the brand surfaces both pieces.

### Added
- `app/main.py` `_auth_redirect_handler` — 404 branch. Logged-in HTML callers redirect to `/`; everything else delegates to `http_exception_handler` (Starlette's default).
- `app/templates/base.html` — `<span class="brand-version">· v{{ APP_VERSION }}</span>` inside the brand `<a>` in the topnav. Title attribute exposes app version + schema version on hover.
- `app/static/style.css` — `.topnav .brand-version` rule (11px, muted, 6px left margin) so the version chip sits compactly next to the brand without competing for visual weight.

### Notes
- Anonymous 404s deliberately keep the default behavior so the app doesn't leak page existence: an anonymous request to `/campaign/999` and `/some-truly-bad-url` both return the same generic 404, regardless of whether the campaign exists.
- The chip lives in the global topnav (every page), not just the tabletop. The tabletop is the one place that *needed* it because it blanks the footer, but adding it globally is consistent and cheap. The footer still shows the long-form version line on every other page.

---

## [2.3.28] - 2026-05-16

**Schema version:** 52
**Commit summary:** Auto-redirect expired-session users to `/login` instead of showing raw `{"detail":"Login required"}` JSON in the browser. Server-side handler covers HTML page loads; client-side fetch wrapper covers in-app AJAX calls (rolls, HP edits, attacks). Login form round-trips a `?next=` param so the user bounces back to the page they were on after re-auth. User-reported.
**Description:** When a session expired mid-action (most often: the demo's hourly reset wipes the user's session row), any `require_user`-guarded request would 401 with a JSON body. Browsers happily displayed the raw `{"detail":"Login required"}` for HTML page loads, and in-app fetches would fail silently or pop a JSON-content alert. Three-piece fix: (1) FastAPI exception handler in `app/main.py` catches `HTTPException(401, "Login required")`, sniffs the `Accept` header, and returns a 303 redirect to `/login?next=<original-path>` when the caller wants HTML; JSON callers (with `Accept: application/json`) still get the 401 unchanged so JS can detect it. (2) Global fetch wrapper in `base.html` monkey-patches `window.fetch` to clone the response, look for `{"detail":"Login required"}` on a 401, and `window.location.href = '/login?next=…'` when found (returning a never-resolving promise so the caller doesn't see the error). (3) Login route accepts `next` as both a query param (GET) and a form field (POST), validated through `_safe_next_path` (rejects absolute URLs, protocol-relative URLs, and path-as-scheme smuggling to prevent open redirects), and bounces to that path on success. Hidden `<input name="next">` carries the value through the form.

### Added
- `app/main.py` `_auth_redirect_handler` — global `@app.exception_handler(HTTPException)` that converts `401 "Login required"` to a `303 RedirectResponse('/login?next=…')` for HTML callers, delegating to `fastapi.exception_handlers.http_exception_handler` for everything else.
- `app/templates/base.html` inline `<script>` that wraps `window.fetch` before any page-level script runs. Catches `401 + {"detail":"Login required"}` and navigates to `/login?next=…`. Non-deferred + at the top of `<body>` so it patches before any other JS captures the original `fetch`.
- `app/routes/auth_routes.py` `_safe_next_path(raw)` — validates a return-to path is same-origin (starts with `/` but not `//`, no scheme smuggled in the first segment) before returning it. Falls back to `/`.

### Changed
- `app/routes/auth_routes.py` `login_page` (GET) — accepts `next: Optional[str]` query, passes the safe-validated value as `next_path` to the template.
- `app/routes/auth_routes.py` `login_submit` (POST) — accepts `next: str = Form("/")`, redirects to the safe-validated value on success.
- `app/templates/login.html` — `<form method="post" action="/login">` now carries a hidden `<input name="next" value="{{ next_path or '/' }}">`.

### Notes
- Open-redirect guard is intentional — without it, `?next=https://evil.example/` could phish a user after a real login. `_safe_next_path` rejects anything that doesn't start with a single `/` and doesn't smuggle a scheme like `/javascript:alert(1)`.
- Google SSO doesn't yet round-trip `next` — successful Google logins bounce to `/`. Wiring `next` through the OAuth state param is a follow-up.
- The fetch wrapper specifically targets `body.detail === 'Login required'` so it doesn't intercept other 401s (e.g. login-form bad password, which is a 401 with a different detail and lives on `/login` already).

---

## [2.3.27] - 2026-05-16

**Schema version:** 52
**Commit summary:** Demo: reset Postgres auto-increment sequences after each wipe so the URL-keyed tables (campaigns / characters / token_templates) hand out stable ids cycle-over-cycle instead of drifting upward. After this commit a visitor opening the demo URL gets `/campaign/1/...` every time instead of `/campaign/4`, then `/campaign/5`, then `/campaign/6`, ... User-reported.
**Description:** Postgres `SERIAL` / `IDENTITY` deliberately doesn't reuse deleted ids — when the demo wipe drops the campaign row and the reseed inserts a new one, the sequence hands out the next value rather than rolling back. The user noticed this in URLs (`/campaign/4` → `/campaign/5` → ...) after a few reset cycles; same drift was happening invisibly to character ids and token template ids. New `_reset_sequences(db)` helper runs after `wipe(db)` (which commits the deletes) and before `seed_users(db)`, calling `setval('<table>_id_seq', COALESCE(MAX(id), 0) + 1, false)` for each URL-keyed table. The `MAX(id) + 1` shape is safe even when a real admin has populated the table with non-demo rows — the sequence catches up to existing data instead of conflicting. SQLite path is a no-op because the project's `Integer primary_key=True` maps to plain `INTEGER PRIMARY KEY` (no AUTOINCREMENT), and SQLite's "next id = max(rowid) + 1" already gives stable demo ids after the wipe.

### Added
- `app/demo_seed.py` `_reset_sequences(db)` — Postgres-only helper that resets `campaigns_id_seq` / `characters_id_seq` / `token_templates_id_seq` to `MAX(id) + 1`. Logs a warning on failure but doesn't raise (so a sequence-rename or schema drift can't break the reset loop). Calls `db.commit()` so the next seed's INSERT sees the new sequence value.

### Changed
- `app/demo_seed.py` `reset_and_reseed` — calls `_reset_sequences(db)` between the wipe and the first `seed_*` so the reseed inserts pick up at id 1 (or `existing_max + 1` if a real admin has populated the table).

### Notes
- Only the three URL-keyed tables get the reset. Tokens / maps / encounters / users / dice rolls / memberships keep creeping upward but their ids aren't bookmarked so it doesn't matter (and resetting users would risk colliding with a real admin who's logged in at id 1).
- On a fresh demo deploy with no real admin data, post-reseed ids are exactly `campaigns.id=1`, `characters.id={1, 2, 3}` (Pip / Thalindra / Tavik), `token_templates.id={1, 2, 3, 4}` (bandit-captain / bandit / thug / goblin-captain).

---

## [2.3.26] - 2026-05-16

**Schema version:** 52
**Commit summary:** Docs-only: annotate the three design plans in `docs/plans/` with implementation status so future readers can see at a glance which phases shipped and which are still deferred. No code change.
**Description:** All three plan docs (`death-saves.md`, `advantage-disadvantage.md`, `demo-mode.md`) opened with "Status: Planned. Not yet implemented." even though every Phase 1 has shipped (some over a year ago in this fictional timeline). Updates each plan's top-of-file Status block to reflect the actual shipped versions, adds a new "Implementation status" section right under the Status block that itemises each phase / deliverable with ✅ / ⏸ / ❌ markers and the version where it landed, and annotates the inline Phase headers in the body with the same markers. The original design content (architectural decisions, file lists, verification steps, scope boundaries) is preserved unchanged — those remain useful historical reference for anyone wanting to understand why the implementation chose the shape it did.

### Changed
- `docs/plans/death-saves.md` — Status: Phase 1 shipped v2.1.0; refinements v2.1.1 (always-on tracker visibility, healing also clears `dead`); adv/dis interaction v2.2.0; cross-character rollover fix v2.2.2 / v2.3.18. Phase 2 reserved-but-never-populated. Phases 3 + 4 deferred (depend on session-time concept and per-NPC stat-block death save toggle that haven't shipped).
- `docs/plans/advantage-disadvantage.md` — Status: Phase 1 shipped v2.2.0; refined v2.2.2 / v2.2.3 (full-width pill row); cross-character regression re-fixed v2.3.18. Phase 2 (condition automation) deferred — depends on a conditions system. Phase 3 (positional rolls) deferred — depends on Maps 2.0 grid distance.
- `docs/plans/demo-mode.md` — Status: shipped v2.3.0 (originally targeted v2.1.0 in this plan); fix train v2.3.1 / v2.3.2 / v2.3.5 (Starlette compat, env-var forwarding, FK ordering bug); enrichment v2.3.22 (Goblin Captain) and v2.3.25 (GM Cleric). Per-visitor accounts, edge rate-limiting, and demo-only feature flags remain explicitly out of scope.

### Notes
- The annotation pass leaves all original plan content intact so the architectural rationale, verification matrices, and out-of-scope lists remain useful future reference. Only the headers + a new Implementation status section are new.
- Future plan docs added under `docs/plans/` should follow the same convention: top-of-file Status header that's updated as implementation lands, plus inline phase annotations.

---

## [2.3.25] - 2026-05-16

**Schema version:** 52
**Commit summary:** Demo: give the GM a Cleric 5 ("Brother Tavik Stonebrow") so the demo party has a divine healer + the GM has a PC mini-sheet to demo alongside the players. Placed on the map next to Pip and Thalindra, inserted into the Tavern Brawl initiative at init 14 (between Pip and Thalindra).
**Description:** Direct user request after the 2.3.22 demo enrichment. The previous demo party was Rogue + Wizard with no healing — the GM watching a demo session had no PC to drive the mini-sheet flow from the GM perspective. This commit adds `_cleric_sheet(name)` (Life Domain, Hill Dwarf, Folk Hero — 18 AC chain+shield, 43 HP w/ Dwarven Toughness, WIS spellcasting with healing-focused spell list incl. Cure Wounds / Healing Word / Mass Healing Word / Spirit Guardians + a save-based Sacred Flame cantrip that exercises the 2.3.18 save-roll button path). `seed_characters` returns three characters now (`[alice_pc, bob_pc, gm_pc]`) and the new token is placed at (200, 700) under the GM's controller. `seed_tokens` inserts Tavik's token at index 2 (right after the two PCs), which means every NPC token_idx in the Tavern Brawl initiative_order shifts by +1 — Grixxa 7→8, Vex 2→3, Thug 6→7, Bandits 3/4/5 → 4/5/6. The encounter description gets a Tavik mention.

### Added
- `app/demo_seed.py` `_cleric_sheet(name)` — minimal D&D 5e Cleric 5 (Life Domain) sheet. Includes a save-based Sacred Flame attack that exercises the 2.3.18 monster/save click path (PCs use it too — DC 14 DEX save renders the same way in the mini-sheet Attacks tab).
- `app/demo_seed.py` `seed_characters` — third Character row (`gm_pc`) owned by `users["gm"]`. Returned list is now 3-long.
- `app/demo_seed.py` `seed_tokens` — Tavik token at (200, 700) with `controller_user_id=users["gm"].id`, character_id linking to `gm_pc`. Color `#f5b75c` (warm amber) so the GM character is visually distinct from the blue (rogue) / green (wizard) PC swatches and the red bandits.
- Tavik entry in the Tavern Brawl `initiative_order` at init 14 between Pip (15) and Thalindra (13).

### Changed
- `app/demo_seed.py` Tavern Brawl `initiative_order` — every NPC `token_idx` shifted +1 because the Tavik token is inserted at index 2 in `seed_tokens`. Verified by hand: Grixxa 7→8, Vex 2→3, Thug 6→7, Bandit Alpha 3→4, Bandit Beta 4→5, Bandit Gamma 5→6. The two PC entries (Pip, Thalindra) stay at token_idx 0/1.
- Encounter description gets a Tavik mention ("Brother Tavik unslings his warhammer behind you").
- Module docstring updated: "two D&D 5e characters" → "three D&D 5e characters", "eight tokens" → "nine tokens".

### Notes
- No portrait image for Tavik — the demo assets directory ships `rogue.png` and `wizard.png` only. The color swatch (`#f5b75c`) carries the visual identity. A cleric token PNG is a follow-up if the demo gets more polish.
- The GM's character isn't a "Character" in the membership sense (the GM is the campaign owner, not a member); the existing `gm_user_id` on the Campaign row already grants control. The `owner_user_id=users["gm"].id` on the Character row is what makes the GM the owner.

---

## [2.3.24] - 2026-05-16

**Schema version:** 52
**Commit summary:** Revert the 2.3.23 debug overlay — collapsibles started working again after the 2.3.23 deploy (most likely a stale browser-cached version of an older JS asset; the new build invalidated the cache). Removes the production noise.
**Description:** User reported the collapsibles regression fixed itself after the 2.3.23 debug deploy went out. The diagnostic overlay never reported a bad call site (because there wasn't one to catch) — the symptom was almost certainly a half-loaded asset bundle from the cache where, e.g., the partial-extracted markup was new but the consuming JS was old (or vice versa) and event handlers didn't bind to the right elements. A hard reload after the cache update fixed it; the same fix would have applied without the debug commit, but the debug deploy forced an asset rotation that cleared the issue.

### Removed
- `app/templates/tabletop.html` — TEMP diagnostic IIFE (monkey-patched `DOMTokenList` + `Element.prototype.classList`, fixed bottom-right overlay logging `.open` mutations and click targets). The patching added small overhead to every `.classList` access; reverting restores native performance.

### Notes
- The previous monster-sheet work (2.3.7–2.3.22) stays intact. The unified monster mini-sheet, drawer, structured attack rolls, and enriched demo Goblin Captain all keep functioning.
- If the regression returns in the future, re-deploy the 2.3.23 commit (or cherry-pick the diagnostic IIFE back in) and the call-site overlay will surface the bad call.

---

## [2.3.23] - 2026-05-16

**Schema version:** 52
**Commit summary:** **TEMP DEBUG** — adds a fixed bottom-right overlay on the tabletop that captures clicks on mini-headers / init-entries and every add/remove/toggle of the `open` class on any element, with the calling stack frame, so we can diagnose a regression reported by the user where "all collapsibles briefly expand then instantly close." Static-code analysis isolated nothing — every handler returns early on non-matching targets and the partial extraction was verified byte-equivalent — so this commit moves diagnosis to runtime.
**Description:** The user reports that opening any PC mini-sheet or monster mini-sheet in the tabletop (Characters drawer header click, init-tracker row expand) starts to expand and then instantly collapses. Static analysis of every document-level click handler I added in 2.3.18 / 2.3.20 / 2.3.21 confirms each early-returns on non-matching selectors. The partial extraction in 2.3.16 was confirmed byte-equivalent. So the cause must be a runtime interaction not visible in source. This commit installs a temp diagnostic: monkey-patches `DOMTokenList.prototype.{add,remove,toggle}` so any `'open'` class mutation logs `{element-token, caller}` to a fixed overlay; a capture-phase click listener also logs the click target. The user can click the offending header and screenshot the overlay; the sequence will identify which call site is removing `.open` mid-click. Self-removes via the ⊗ button when no longer needed.

### Added
- `app/templates/tabletop.html` top-of-script TEMP diagnostic IIFE. Patches `Element.prototype.classList` to back-reference the owning element so the patched `DOMTokenList` methods can identify which element is being mutated. Logs into a fixed overlay (`#__open_class_debug`-style) with caller stack-line truncation. To be removed in the next commit once the bug is diagnosed.

### Notes
- This commit deliberately ships a debug script to production. The monkey-patching of `Element.prototype.classList` and `DOMTokenList.prototype` has measurable overhead — every `.classList.add('whatever')` call goes through the wrapper — but the cost is small on a single page-load and the alternative (asking a non-technical user to navigate browser devtools) was worse. Revert in the next commit once the bug is fixed.

---

## [2.3.22] - 2026-05-16

**Schema version:** 52
**Commit summary:** Enrich the demo dataset so the v2.3.7–v2.3.21 monster-sheet work is visible end-to-end on a fresh `DEMO_MODE` deploy without any GM setup. Goblin Captain ("Grixxa") is now a fully-authored homebrew monster — four actions (multiattack + scimitar + javelin + Frightful Howl save) + two passive special abilities — placed as a token on the demo map and inserted at the top of the Tavern Brawl initiative order. The on-boot reseed regenerates the demo, so the demo URL picks it up automatically.
**Description:** Before this commit, the demo's homebrew Goblin Captain had a single Scimitar action and no TokenTemplate / token / encounter slot, so the only way to see the new monster mini-sheet flow was to manually author a monster + place a token + add to init — too many steps for a "open the demo URL and see the feature" experience. This commit expands the homebrew JSON in `seed_homebrew_files` from one action to a six-entry actions list that exercises every roll path the 2.3.18 / 2.3.21 handlers can fire: a descriptive Multiattack (no buttons — proves narrative entries pass through cleanly), a melee attack-roll Scimitar ("+5" / 1d6+3 slashing), a ranged attack-roll Javelin (same to-hit / damage type piercing), a save-based Frightful Howl (DC 12 WIS save, no damage — proves the save-announce path), plus Pack Tactics + Nimble Escape special abilities so the GM sees the special-ability category render too. `seed_token_templates` now creates a TokenTemplate pointer for `goblin-captain` (resolved through `_monster_template_to_sheet` at view time — the homebrew tier overlays the structured stat block onto the minimal template sheet). `seed_tokens` places Grixxa on the right side of the bar at the corresponding map position. `seed_encounter` inserts Grixxa as the first initiative entry (rolled 18 — highest in the order, so when the GM expands the encounter the FIRST row to see is the new monster mini-sheet). Encounter description updated to mention Grixxa.

### Changed
- `app/demo_seed.py` `seed_homebrew_files` — Goblin Captain expanded from one Scimitar action to four actions (Multiattack + Scimitar + Javelin + Frightful Howl) + two special abilities (Pack Tactics, Nimble Escape). HP 24 → 36, hit dice `7d6` → `8d6+8`, abilities tuned upward (DEX 14 → 16, WIS 10 → 12, CHA 10 → 13), senses + languages populated. `attack_bonus` set explicitly to "+5" on attack entries (no longer relies on the 2.3.11 desc-regex fallback).
- `app/demo_seed.py` `seed_token_templates` — added `("goblin-captain", "Goblin Captain")` to the specs list. The template carries the standard `_npc_sheet` pointer shape; the structured stat block resolves through the homebrew tier at view time.
- `app/demo_seed.py` `seed_tokens` — added a Grixxa token at (1250, 550) using the new goblin-captain template. Goblin-green color (#7c9c54) to visually distinguish from the red-coded bandits.
- `app/demo_seed.py` `seed_encounter` — Grixxa inserted at the top of the initiative_order (init 18, token_idx 7). Encounter description mentions her.
- Module docstring — token count updated (7 → 8), Goblin Captain call-out added.

### Notes
- Reset cadence: the `DEMO_RESET_ON_BOOT=true` startup hook reseeds on every container start; the running `demo_scheduler` reseeds every `DEMO_RESET_INTERVAL_MINUTES` (default 60). So the enrichment is visible to any visitor within the next reset window after deploy.
- What the new demo exercises end-to-end:
  - **v2.3.8** structured-action editor — Grixxa's actions are stored with `attack_roll`/`attack_bonus`/`damage`/`damage_type`/`save_ability`/`save_dc` first-class fields that the editor produces.
  - **v2.3.10/11** monster sheet adapter — opening Grixxa's "Open full sheet" link projects the homebrew stat block into `sheet_dnd5e.html` with the structured attacks folded into `sheet.attacks`.
  - **v2.3.13** PC-only section hiding — the sheet shows abilities/saves/skills/attacks and nothing else.
  - **v2.3.15/20** drawer with postMessage close — clicking the link opens the drawer; Close inside the iframe dismisses it cleanly.
  - **v2.3.17** monster mini-sheet in the init tracker — Grixxa expands inline with the full PC-style mini-sheet.
  - **v2.3.18** click-to-roll — Scimitar / Javelin / Frightful Howl buttons all fire to `/roll` from the mini-sheet's Attacks tab.

---

## [2.3.21] - 2026-05-16

**Schema version:** 52
**Commit summary:** Branch the `.mini-cast-btn` (Spells-tab Cast button) handler for monsters — mirrors the 2.3.18 strike-handler pattern. Today demo monsters don't have `sheet.spell_slots` so the button doesn't render, but a future homebrew NPC caster (Bandit Mage, Veteran Cultist, etc.) would surface the gap: `/api/campaign/{cid}/cast_spell` requires a real Character row and would 404 on a TokenTemplate-backed mini-sheet. Closes out the polish items the user authorized after 2.3.19.
**Description:** Two pieces. (1) Cast button stamps spell roll fields as data attrs (`data-spell-damage`, `data-spell-damage-type`, `data-spell-save-ability`, `data-spell-save-dc`, `data-spell-attack-roll`, `data-spell-attack-bonus`, `data-spell-healing`) so the monster branch can rebuild rolls without a /cast_spell round-trip. Redundant for PCs (they use the index+slot endpoint) but harmless. (2) Click handler moved from `#players-drawer` to `document` so it fires for mini-sheets wherever they live (Characters drawer, init-tracker after the body steal, monster pool when expanded). Monster branch posts up to four sequential `/roll` entries — attack roll, damage, healing, save announcement — same pattern as the strike handler. If a monster spell has none of the structured fields, a bare announcement (`expression: 0` + note "Monster casts SpellName") fires so the table at least sees something happened. PC path unchanged: still optimistically decrements the slot pip, still POSTs `/cast_spell`, still reverts the pip on error.

### Added
- `app/templates/_mini_sheet_card.html` — `data-spell-*` attributes stamped on every `.mini-cast-btn`. Mirrors the 2.3.18 attack-field stash pattern.

### Changed
- `app/templates/tabletop.html` — `.mini-cast-btn` click handler moved from `#players-drawer` to `document`. Added the monster branch that posts attack/damage/healing/save rolls to `/roll` instead of `/cast_spell`. PC behavior unchanged including the slot-pip optimistic decrement.

### Notes
- Closes the gap I flagged in the 2.3.18 changelog notes ("Cast Spell handler still posts to character-specific `/cast_spell`. ... A future homebrew monster with structured spell-slot data would surface that gap").
- The monster path skips slot-pip mutation entirely — monster mini-sheets don't render the `_pre_caster_spell_slot_rows` section in the partial (gated on `_is_owner` / spell-slot data the monster's projected sheet doesn't carry), so there's no pip to decrement.

---

## [2.3.20] - 2026-05-16

**Schema version:** 52
**Commit summary:** Wire the monster sheet's in-iframe Close button to dismiss the 2.3.15 drawer via `postMessage` instead of navigating the iframe to the campaign page. Flagged as a known limitation in the 2.3.15 changelog notes; user authorized the follow-up after the 2.3.19 fix.
**Description:** `monster_page.html` exposes `window.closeSheet()` which `sheet_dnd5e.html` calls from its Close button (and the breadcrumb up-arrow). Prior to this commit, `closeSheet` just did `window.location.href = '/campaign/{cid}'` — when the sheet was loaded inside the 2.3.15 drawer iframe, that navigated the IFRAME to the campaign page (the drawer stayed open and now displayed the entire campaign tabletop nested inside itself, which was both ugly and broke the WebSocket connection in the iframe). Fix detects iframe context (`window.parent !== window`) and `postMessage`s the parent with a known message type (`simplevtt:monster-sheet-close`); the parent drawer listens for that exact type + same-origin and calls its own `closeDrawer()`. Standalone-tab opens still work — when `closeSheet` is called outside an iframe (or when `postMessage` throws), it falls back to the original navigation behavior.

### Added
- `app/templates/tabletop.html` drawer JS — new `message` event listener that calls `closeDrawer()` when receiving a `{type: 'simplevtt:monster-sheet-close'}` postMessage from a same-origin frame. Origin check rejects messages from other sources.

### Changed
- `app/templates/monster_page.html` `window.closeSheet` — detects iframe context first; postMessages the parent with the close type when iframed, falls back to `window.location.href` navigation when standalone (or when postMessage throws).

### Notes
- Same-origin policy guards the message handler — the iframe always loads from the same SimpleVTT origin, so a strict `ev.origin !== window.location.origin` check is the right gate.
- The postMessage type is namespaced (`simplevtt:`) so it won't conflict with random other postMessages a browser extension or third-party widget might emit.

---

## [2.3.19] - 2026-05-16

**Schema version:** 52
**Commit summary:** Fix pre-existing bug where the init-tracker "From Map" button only saw tokens that existed at page load — tokens placed after load (Library, Open5e, Players-tab) silently failed to roll up unless the GM reloaded first. Reported by the user while testing the 2.3.16/17/18 monster mini-sheet work: "I added the Bandit Captain from the library, they will not appear in the init order."
**Description:** The init-tracker IIFE keeps its own `allTokens` array that's initialized from `initData.tokens` at page load. The tabletop.js IIFE maintains a separate `tokens` array that IS reactive to the `token_add` / `token_delete` / `token_update` WebSocket messages, but the two IIFEs don't share state — `allTokens` was a frozen snapshot. So after placing a Bandit Captain from the Library tab post-load, clicking the init tracker's "From Map" button iterated the snapshot (which didn't include the new token) and the new bandit was silently skipped. Fix subscribes the init tracker's WS handler (which already exists for `battle_update` syncing) to the three token messages and updates `allTokens` in place. No `renderBattle` re-run on token events — already-added combatants don't change shape when their source token mutates — but the next "From Map" click sees the fresh list. Bug pre-dates 1.1.0; user encountered it now because they were testing the new monster mini-sheet flow against a fresh-placed bandit.

### Fixed
- `app/templates/tabletop.html` init-tracker WS handler — now handles `token_add` / `token_delete` / `token_update` in addition to the existing `battle_update` sync, keeping `allTokens` in sync with live token state so "From Map" sees post-load placements.

### Notes
- The fix is GM-side only as a side effect (only GMs interact with the init tracker's add controls), but the handler runs for all clients without harm. Player clients also benefit because their cached `allTokens` stays current if they ever need it.
- Verified via grep that the three message types are the ones tabletop.js's own `tokens` array already responds to (line 880-902 of `app/static/tabletop.js`); mirroring the same set keeps the two arrays in sync indefinitely.

---

## [2.3.18] - 2026-05-16

**Schema version:** 52
**Commit summary:** Wire the monster mini-sheet (2.3.17) click handlers so Strike + ability/skill clicks fire correctly. Strike branches by `data-char-id` format — PCs keep using `/attack`, monsters POST the attack/damage/save rolls to `/roll` with expressions built from the new data-attack-* attributes stashed on the button. Ability/skill listener moved to document so it fires regardless of which container the mini-sheet body lives in (Characters drawer, init tracker, or monster pool).
**Description:** Closes out the user's "make monster init-tracker use the PC mini-sheet" request. 2.3.17 rendered the markup but the strike handler was bound to `#players-drawer` (monsters live in `#monster-mini-sheet-pool`, then move into `.init-card-sheet` on init expand — neither inside the players drawer) and called `/api/campaign/{cid}/attack` which requires a real `Character` row. This commit (1) moves both the strike handler and the ability/skill click handler to `document` so they fire wherever the mini-sheet currently lives, and (2) adds a monster branch on the strike handler that builds the attack expression client-side from data attributes (mirroring the 2.3.9 inline-button approach, but using the mini-sheet's own attack data). The monster path emits up to three separate `/roll` POSTs in sequence — attack-roll, damage, save-announcement — each landing in the campaign roll log as its own entry, so the GM and players see the full chain. Ability/skill clicks on monsters drop the `character_id` from the body (parseInt of "monster-22" → NaN → omitted) and add `skip_roll_state: true` so the GM's own PC's adv/dis pill doesn't bleed into monster checks.

### Added
- `_mini_sheet_card.html` — `data-attack-bonus` / `data-attack-damage` / `data-attack-damage-type` / `data-attack-save-ability` / `data-attack-save-dc` stamped on every `.mini-strike-btn` so the strike handler can rebuild the attack expression client-side without DOM-walking. Redundant for PCs (they still use the `/attack` endpoint via `attack_index`) but harmless.

### Changed
- `app/templates/tabletop.html` — strike handler moved from `#players-drawer` to `document`. Added the monster branch that POSTs `1d20+bonus`, the damage expression, and a save-announcement (when present) to `/roll` instead of `/attack`. PC behavior unchanged.
- `app/templates/tabletop.html` — ability/skill handler (`.mini-roll-btn, .mini-sk-btn`) moved from `#players-drawer` to `document`. Added `skip_roll_state: true` for monster click sources so the GM's own character's adv/dis state doesn't apply to monster checks. `character_id` is omitted when the closest `[data-char-id]` is a monster-string id (parseInt → NaN → falsy).

### Notes
- Cast Spell (`.mini-cast-btn`) handler still posts to character-specific `/cast_spell`. Monsters typically don't have spell slots in `sheet.spell_slots` so the Cast button wouldn't render for them anyway — but a future homebrew monster with structured spell-slot data would surface that gap. Filed as a follow-up.
- HP step PATCH and short/long rest POSTs are already suppressed for monsters by the 2.3.17 `_is_owner = ... and not is_monster` gate — the buttons don't render so the handlers can't fire.

---

## [2.3.17] - 2026-05-16

**Schema version:** 52
**Commit summary:** Render mini-sheet cards for every GM-accessible monster `TokenTemplate` (using the 2.3.16 partial) into a hidden pool div, and extend the init-tracker mini-body steal logic to find them. When the GM expands a monster combatant row, they now see the same compact PC-style mini-sheet (HP/AC/Speed/abilities/skills/attacks tabs) instead of the prior one-line "Open full sheet" link. Click handlers are scoped to safe operations in this commit; 2.3.18 wires the remaining attack/strike paths.
**Description:** Direct response to the user's request after seeing 2.3.15: "make the sheets in the GM initiative use this sheet" (showed the existing PC mini-sheet). The 2.3.16 partial extraction made this tractable — this commit synthesizes a character-like object for each monster `TokenTemplate` (id `"monster-{tid}"` so DOM ids don't collide with real Character primary keys) via the 2.3.10/11 sheet projection adapter, then renders the partial into a `#monster-mini-sheet-pool` hidden div. The init tracker's render now computes a unified `slotId` per combatant (`c.char_id` for PCs, `"monster-{token_template_id}"` for monsters) and the existing `#char-detail-{slotId}` lookup + mini-body steal logic just works for both. PC-only sections (HP step buttons, short/long rest buttons, wild-shape/polymorph transform bar, death saves, roll-state pill `can_edit`) suppress on monster mini-sheets via an `is_monster` flag passed through `{% with %}` — those endpoints expect a real `Character` row and would 404 for monsters. The "Open full sheet" link in the mini-footer routes to the 2.3.10 monster sheet URL for monsters and carries the 2.3.15 `monster-sheet-link` class so a click opens the sheet in the slide-out drawer.

### Added
- `app/routes/tabletop_routes.py` — builds a `monster_templates` list in the tabletop route (GM-only), filtering to dnd5e templates that carry combat data (`abilities` or `attacks` or `actions` keys). Each becomes a `_SyntheticMonsterChar` with `id="monster-{tid}"` + a new `template_id` slot so the partial can emit the `/monster-template/{tid}/sheet` URL without parsing the id prefix.
- `app/templates/tabletop.html` — `#monster-mini-sheet-pool` hidden `display:none` div that renders `_mini_sheet_card.html` for each monster template with `{% with is_monster=true %}`. The init tracker steals from this pool exactly like it does from the visible Characters panel today.

### Changed
- `app/templates/_mini_sheet_card.html` — `_is_owner` now also requires `not is_monster`, which gates off HP step buttons, short/long rest buttons, the roll-state pill `can_edit`, and the death-saves tracker for monsters in one place. Wild-shape/polymorph bar wrapped with `and not is_monster`. "Open full sheet" link branches to the monster URL + `monster-sheet-link` class when rendering a monster.
- `app/templates/tabletop.html` `renderBattle` — unified `slotId` per combatant (PC `char_id` or `monster-{token_template_id}`) so `hasCharDetail` + the steal selector + the open/close handler all key off the same identifier for both PCs and monsters.
- `app/routes/tabletop_routes.py` `_SyntheticMonsterChar` — `id` accepts both int (2.3.10 route) and str (2.3.17 mini-sheet pool); added `template_id` slot for the monster-sheet URL.

### Notes
- Skills, ability checks, ability/save toggle, and tab switching all work on monster mini-sheets in this commit — those handlers either don't hit a backend endpoint or hit `/roll` which already tolerates a missing/invalid `character_id` (falls back to the rolling user's first character).
- The Strike (weapon attack) and Cast Spell handlers POST to character-specific endpoints (`/attack`, `/cast_spell`) that require a real `Character` row — those would fail silently or error toast for monster mini-sheets in this commit. 2.3.18 wires them to `/roll` with a built expression instead, mirroring the 2.3.9 inline-button approach but using the mini-sheet's own attack data.

---

## [2.3.16] - 2026-05-16

**Schema version:** 52
**Commit summary:** Pure refactor — extract the per-character mini-sheet card (lines 984–1365 of `app/templates/tabletop.html`, ~382 lines covering the dnd5e mini-sheet + the generic-template fallback + the mini-footer) into a new `_mini_sheet_card.html` partial so a follow-up commit can reuse the same UI for monster TokenTemplates in the GM init tracker. No behavior change for PCs.
**Description:** Setup commit for the "make monster init-tracker rows look like the PC mini-sheet" feature (user request after seeing 2.3.15 land). The mini-sheet had been inlined inside the `{% for c in characters %}` loop, which made it impossible to render for any source other than a `Character` ORM row. The partial takes `c` (character-like object) and reads `user` / `is_gm` / `campaign` from the caller scope; renders identical HTML to the previous inline version. The outer loop's `{% if c.owner_user_id == user.id or is_gm %}` visibility gate stays in the parent template, not the partial. Verified post-extraction: HTTP 200 page render, 32 mini-sheet markers in the rendered HTML (same count as pre-refactor), no Jinja errors in the app logs.

### Added
- `app/templates/_mini_sheet_card.html` — verbatim extraction of the per-character mini-sheet markup, with a header comment documenting the expected inputs (`c`, `is_monster`) and the caller-scope dependencies (`user`, `is_gm`, `campaign`). `is_monster` is reserved for 2.3.17 — this commit doesn't consume it yet.

### Changed
- `app/templates/tabletop.html` — replaced the inline mini-sheet block (lines 984–1365) with `{% include "_mini_sheet_card.html" %}`. Net diff is a 379-line reduction in the parent template.

### Notes
- This is a refactor, not a feature. The visible UI is identical; 2.3.17 will start consuming the partial from a second loop (over monster TokenTemplates) so the GM init tracker can steal monster mini-bodies the same way it steals PC ones today.
- The partial intentionally does NOT contain the `{% if c.owner_user_id == user.id or is_gm %}` visibility gate from the original site — that's the caller's responsibility because monster mini-sheets will use a different gate (`{% if is_gm %}` unconditionally).

---

## [2.3.15] - 2026-05-16

**Schema version:** 52
**Commit summary:** Open the monster sheet in a slide-out drawer over the tabletop instead of a new tab — keeps the GM oriented in the campaign view while running combat. Iframe-based so the sheet's own JS stays isolated and doesn't double-init against the tabletop's globals. Cmd/Ctrl-click on the link still falls through to the new-tab default for power users who want to pop it out permanently.
**Description:** Final UX polish on the Unified Monster Sheet pivot. The 2.3.12 link opened the sheet in a new tab, which on most setups means tab-switching mid-combat — fine for prep, jarring during a turn. This commit adds a right-edge drawer (max 820 px / 92 vw wide) with a backdrop dim. A delegated click handler on `document` intercepts any `<a class="monster-sheet-link">` click and loads the link's `href` into an `<iframe>` inside the drawer; the iframe isolates the sheet's `wireDnd5eRollButtons` wiring from the parent tabletop's `CAMPAIGN_ID` / `ME` / `CHAR_ID` globals (no naming conflicts, no double-init). Rolls fired from inside the iframe still POST to `/api/campaign/{cid}/roll` and the server broadcasts the result over WebSocket to the parent tabletop's roll log — same wiring, no extra glue. Close via the × button, the backdrop, or Esc. The header has a small "↗ New tab" affordance for the GM who decides mid-session they want to keep the sheet open in a separate window.

### Added
- `app/templates/tabletop.html` `#monster-sheet-drawer` + `#monster-sheet-backdrop` markup (GM-only, gated on `{% if is_gm %}` so player clients never carry the DOM). 220 ms slide-in from the right via CSS `transform` transition.
- `app/templates/tabletop.html` inline IIFE that wires the delegated click handler, drawer open/close, Esc-key dismissal, and backdrop-click dismissal. Cmd/Ctrl/Shift/middle-click bypasses the interception so the browser's default new-tab behavior wins for the power-user path.

### Changed
- `app/templates/tabletop.html` `buildMonsterInitSheet` — the "📋 Open full sheet" anchor now carries `class="monster-sheet-link"` + `data-monster-name="..."` so the drawer handler can intercept and label the drawer header. Removed the trailing "↗" arrow from the link text since the drawer slides in rather than navigating.

### Notes
- The sheet's in-iframe Close button (`closeSheet()` in `monster_page.html`) still does `window.location.href = '/campaign/{cid}'` which, inside the iframe, just navigates the iframe to the campaign page (the parent tabletop is unaffected). A `postMessage` to the parent to dismiss the drawer would be cleaner — filed as a follow-up.
- Player-only clients never load the drawer markup or handler — monsters are GM-only data and the surface stays GM-only too.

---

## [2.3.14] - 2026-05-16

**Schema version:** 52
**Commit summary:** Retire the 2.3.9 inline monster stat-block + 🎯/🎲/📋 strike buttons in the init tracker now that the 2.3.10–2.3.13 full-sheet view is the canonical path. The init-tracker monster row now collapses to an AC/Speed quick-glance chip plus the existing "📋 Open full sheet ↗" link.
**Description:** After 2.3.12 wired up the full-sheet link and 2.3.13 tightened the sheet to monster-relevant sections, the 2.3.9 inline ability grid + per-action strike buttons duplicated the full sheet's affordances with a less-polished UI (no adv/dis support, no proper roll log card, "save" was an announcement-only line). Removing them avoids two UIs drifting and reclaims vertical space in the init panel. `buildMonsterInitSheet` collapses to a one-line layout: any AC/Speed chips on the left, the full-sheet link button on the right. The delegated `.monster-strike-btn` click handler (~60 LoC) and its CSS class come out with it.

### Changed
- `app/templates/tabletop.html` `buildMonsterInitSheet` — now returns a single-row "AC / Spd chips · Open full sheet" layout. Removed the ability-mod grid and per-action button strip.

### Removed
- `app/templates/tabletop.html` — the GM-only `#initiative-list` delegated click handler that fired `.monster-strike-btn` POSTs to `/api/campaign/{cid}/roll` (kind=attack/damage/save). Same rolls now happen via the full sheet's existing roll-button wiring.
- `.monster-strike-btn` CSS class.

### Notes
- The full-sheet link still uses the purple palette so the affordance keeps the same visual identity it had as a button group.
- The 2.3.8 structured-attack editor + the 2.3.10/11 monster sheet adapter both remain — this commit only strips a duplicate UI surface.

---

## [2.3.13] - 2026-05-16

**Schema version:** 52
**Commit summary:** Hide the PC-only sections (Spells / Class Resources / Inventory / Class+Subclass+Race Features / Class Proficiencies / Notes + the two slide-in overlays for the Spell and Item browsers) when rendering `sheet_dnd5e.html` for a monster, by gating the whole block on a new `is_monster_sheet` flag the route now passes. The character-details edit panel + multiclass picker + per-level HP rolls editor were already hidden because they sit behind `{% if can_edit %}` and the monster route renders read-only — so no extra wrapping needed there.
**Description:** After 2.3.10/2.3.11/2.3.12 a GM clicking "Open full sheet" on a monster row got the full PC sheet, but the half of the sheet that has no meaning for an NPC (spell slots with "no spell slots configured" placeholders, an empty inventory, currency boxes, empty class-feature accordions, etc.) still rendered as scroll-padding clutter. One Jinja gate around the contiguous block from the Spells fieldset (line 952) through the Notes fieldset (line 1461) — also covers the Spell Browser overlay, Beast Picker overlay, and the inline spell-slot pip renderer that the gated sections own. The route sets `is_monster_sheet: True`; for the PC sheet route the variable is undefined, which evaluates falsy under the project's `ChainableUndefined` setup, so `{% if not is_monster_sheet %}` returns True and the sections render exactly as before. Verified locally: PC sheet renders unchanged; Bandit Captain monster sheet now shows only the header / roll-state pill / ability scores / saves / skills / defenses / conditions / attacks — the bits that actually have data.

### Added
- `is_monster_sheet: True` in the context dict passed by `monster_template_sheet_page` to `monster_page.html` (which forwards everything to `sheet_dnd5e.html`).

### Changed
- `app/templates/sheet_dnd5e.html` — wrapped lines 952–1461 (Spells fieldset, Spell Browser overlay, Beast Picker overlay, spell-slot pip renderer, Class Resources fieldset, Inventory fieldset, Class+Subclass+Race Features fieldset, Class Proficiencies fieldset, hidden Features textarea, Notes fieldset) in `{% if not is_monster_sheet %}` ... `{% endif %}`. Single contiguous gate so reviewers only have to verify two edit boundaries.

### Notes
- The edit panel (Character Details / multiclass / HP rolls / Background / Feats) sits behind `{% if can_edit %}` at line 251 and is already hidden on the monster sheet (`can_edit=False`).
- If a future feature wants to add a section that *is* relevant for monsters (e.g. lair actions, legendary actions surfaced as buttons), it should go OUTSIDE the gate — between the Attacks fieldset and the Spells fieldset is a natural insertion point.

---

## [2.3.12] - 2026-05-16

**Schema version:** 52
**Commit summary:** Wire the GM init-tracker monster row to the new full monster sheet — adds a "📋 Open full sheet ↗" link at the top of the inline monster stat-block panel that opens `/campaign/{cid}/monster-template/{tid}/sheet` in a new tab. Completes the Unified Monster Sheet first slice.
**Description:** Smallest possible UI hook — the 2.3.10/2.3.11 sheet already works as a standalone URL; this commit just makes it reachable from where the GM already is. The inline stat-block + strike buttons added in 2.3.9 stay below the new link as a quick-glance reference (no need to leave the tabletop just to see HP/AC/ability mods or fire a single attack). The link uses the same `.monster-strike-btn` purple palette so it looks like a related affordance. `target="_blank" rel="noopener"` so opening the sheet doesn't yank the GM off the tabletop mid-combat.

### Added
- `app/templates/tabletop.html` `buildMonsterInitSheet` — prepends a "📋 Open full sheet ↗" anchor pointing at the 2.3.10 monster-sheet URL. 32 px min-height per the CLAUDE.md dense-panel rule.

### Notes
- Wired as a link (not a modal) for the first iteration so the GM can keep the sheet open in a second tab while running combat. A modal/drawer variant that pops the sheet over the tabletop is a follow-up if the tab-management workflow feels heavy.
- The 2.3.9 inline strike buttons (🎯 Attack / 🎲 Dmg / 📋 Save) stay in place as a quick-action fallback. If the full-sheet workflow turns out to dominate, those can be retired in a later commit.

---

## [2.3.11] - 2026-05-16

**Schema version:** 52
**Commit summary:** Fix the 2.3.10 monster-sheet route returning an essentially-empty sheet for the demo-style "pointer" TokenTemplate shape (the `_npc_sheet` seed in `app/demo_seed.py` stores only `{class:"NPC", monster_slug, level, abilities:{baseline 10s}}` and expects the stat block to resolve at view time). Adds slug resolution + a desc-text regex fallback so shipped SRD monsters get real to-hit bonuses on their attack buttons.
**Description:** Two adapter improvements landed together because both are required to make a stock-deploy demo monster sheet useful: (1) `_monster_template_to_sheet` now reads `tmpl.sheet["monster_slug"]` and, if set, calls `local_content.resolve(slug, type="monsters", campaign_id=cid)` to load the full Monster Pydantic record (homebrew tier first, shipped SRD fallback) and overlays it onto the template's sheet via a new `_monster_dict_to_sheet(m, base=)` helper that projects HP / AC / abilities / speed / size+type header / damage-and-condition lists from the Monster shape into the character sheet's dict shape. The TokenTemplate's sheet then keeps any custom overrides (notes, slug, etc.) while picking up the real stat block. (2) Shipped SRD monster JSON files set `actions[].attack_roll = true` but leave `attack_bonus = null` — the to-hit lives only in the desc text ("Melee Weapon Attack: +5 to hit, ..."). The fold-into-attacks step now regex-extracts `([+-]\d+) to hit` from the desc when `attack_bonus` is empty, so the resulting `atk_bonus` populates "+5" and the attack button rolls `1d20+5` instead of a raw `1d20`. Verified locally: Bandit Captain template now renders STR 15 / DEX 16 / CON 14 / WIS 11 with two structured attacks (Scimitar +5 / 1d6+3 slashing, Dagger +5 / 1d4+3 piercing) on the new monster-sheet URL.

### Added
- `app/routes/tabletop_routes.py` `_monster_dict_to_sheet(m, *, base=None)` — projects a Monster Pydantic dict into the character sheet dict shape. Pass-through of any keys not derivable from the monster (notes, monster_slug, etc.) so the TokenTemplate's custom fields survive the overlay.

### Changed
- `app/routes/tabletop_routes.py` `_monster_template_to_sheet` — now takes `campaign_id` and, when `tmpl.sheet["monster_slug"]` is set, resolves the slug via `local_content.resolve(..., type="monsters", campaign_id=cid)` and overlays the full Monster stat block onto the template's sheet before the fold-into-attacks step. Also regex-extracts to-hit from the action desc when `attack_bonus` is null, covering the shipped SRD monster case where the to-hit is only in the desc text.
- `monster_template_sheet_page` — passes `campaign_id` through to the adapter so homebrew-tier slugs resolve in the right scope.

### Notes
- Demo Bandit Captain TokenTemplate (`_npc_sheet("bandit-captain", "Bandit Captain")`) was the smoking-gun test case — before this commit the new monster-sheet route rendered a 10/10/10/10/10/10 Captain with no attacks. After this commit it renders the full Bandit Captain stat block with both attacks clickable.
- The desc-text regex assumes the "+N to hit" convention used by SRD content. Homebrew monsters authored via the 2.3.8 editor already populate `attack_bonus` first-class so the regex never fires for them.

---

## [2.3.10] - 2026-05-16

**Schema version:** 52
**Commit summary:** First slice of the "Unified Monster Sheet" TODO — adds a server-side adapter + new GET route that renders the existing `sheet_dnd5e.html` for any monster `TokenTemplate`, giving GMs PC-parity click-to-roll for ability checks, saves, skills, and structured attacks without rebuilding a parallel UI. Replaces the in-tracker minimal stat-block (2.3.9) wiring in the next commit.
**Description:** Pivot decision after testing 2.3.9 — building bespoke monster-row buttons in the init tracker means reinventing roll wiring, advantage/disadvantage application, breakdown rendering, roll-log integration, and the click-to-toggle skill/save UI that the PC sheet already does end-to-end. Cheaper to reuse the PC sheet against a synthesized "monster character" projection. This commit lands the plumbing: (1) `_SyntheticMonsterChar` — a SQLAlchemy-free stand-in exposing only the attributes `sheet_dnd5e.html` actually reads (id, name, sheet, template, owner_user_id, campaign_id, color, portrait_url, ring_style); (2) `_monster_template_to_sheet(tmpl)` — projects `TokenTemplate.sheet + sheet.actions` into the dict shape the character template consumes, folding any homebrew 2.3.8 structured-action entries (`attack_roll` / `attack_bonus` / `damage_type` / `save_ability` / `save_dc`) into the character-style `sheet.attacks` list and de-duping by name so a homebrew override shadows an SRD-imported same-name attack; (3) new GET `/campaign/{cid}/monster-template/{tid}/sheet` (GM-only, read-only — `can_edit=False`) that renders a new slim `monster_page.html` wrapper which mirrors `character_page.html` minus the delete affordance and with a monster breadcrumb. The wrapper still `{% include sheet_template %}`s `sheet_dnd5e.html`, so all the existing roll-button wiring, adv/dis pill, skill toggles, and damage rolls work for free — they read state via `form.querySelector('[name="..."]').value` against the populated (but read-only) form fields. Init-tracker hookup lands in 2.3.11.

### Added
- `app/templates/monster_page.html` — slim wrapper around `sheet_dnd5e.html` with a monster-appropriate breadcrumb and no delete-character button. Defines `CAMPAIGN_ID` / `CHAR_ID` / `ME` and a `closeSheet()` that returns to the campaign tabletop.
- `app/routes/tabletop_routes.py` `_SyntheticMonsterChar` — `__slots__` stand-in for the Character ORM object. Intentionally not a SQLAlchemy model; the underlying entity is a TokenTemplate, not a Character row.
- `app/routes/tabletop_routes.py` `_monster_template_to_sheet(tmpl)` — pure-function projection of TokenTemplate.sheet + structured actions into the character-sheet dict shape. Pass-through for everything except actions; folds structured `attack_roll` / `save_ability` action entries into `sheet.attacks` with the character key conventions (`atk_bonus`, not `attack_bonus`; UPPER-case `save_ability`).
- `app/routes/tabletop_routes.py` new GET route `/campaign/{cid}/monster-template/{tid}/sheet` rendering `monster_page.html` with the synthesized context.

### Notes
- The next commit (2.3.11) swaps the in-tracker monster-row buttons (added in 2.3.9) for an "Open monster sheet" button that opens this new URL. The 2.3.9 inline buttons stay as fallback until the new sheet experience is validated.
- Spell / multiclass / class-feature sections in `sheet_dnd5e.html` are gated by `{% if %}` guards on `sheet.classes` / `sheet.spells` / `sheet.spell_slots` — monsters that don't populate those just don't render those sections. No template fork required for this slice.
- Edit-monster flow still happens through the existing homebrew editor in campaign settings (not the new sheet view). The new sheet is read-only by design — it's a play-time tool, not an authoring tool.

---

## [2.3.9] - 2026-05-15

**Schema version:** 52
**Commit summary:** Render click-to-roll attack/damage/save buttons in the GM initiative-tracker monster card. Phase 3 of the "homebrew monster attacks → rollable buttons" TODO — completes the editor (2.3.8) → in-play rendering loop the user asked for.
**Description:** Before this commit, expanding a monster row in the GM initiative tracker showed only the HP/initiative edit strip — `buildInitSheet(c.char_id)` returned empty for non-character combatants (no `char_id`). Now `combatantFromToken` stashes `token_template_id` on each combatant so a new `buildMonsterInitSheet(combatant)` helper can look up the source TokenTemplate and render a compact stat-block (AC / Speed chips, ability-mod grid) plus a per-action row with 🎯 Attack / 🎲 Dmg / 📋 Save buttons. The buttons POST to `/api/campaign/{cid}/roll` with the appropriate expression (`1d20+bonus` for attacks; the dice expression for damage; a `0` + note announcement for saves) so results land in the shared roll log alongside PC rolls. Action data comes from `tmpl.sheet.actions` (homebrew structured shape, populated by the 2.3.8 editor) when present, falling back to `tmpl.sheet.attacks` (SRD regex-derived shape from `_open5e_to_dnd5e_sheet`). Both populate the same per-row shape so the renderer doesn't fork. `skip_roll_state: true` on the POST so the GM's own character's adv/dis pill doesn't bleed into monster attacks.

### Added
- `buildMonsterInitSheet(combatant)` in `app/templates/tabletop.html` — renders the compact monster stat-block panel inside the init-tracker GM card. Reads from `tmpl.sheet.actions` (preferred) or `tmpl.sheet.attacks` (fallback) on the source TokenTemplate.
- `token_template_id` field on the combatant object returned by `combatantFromToken` — kept on the in-memory battle state so the monster-sheet renderer can look up the source template even after the original token is removed from the map.
- Delegated `.monster-strike-btn` click handler on the initiative list — GM-only, fires the three roll kinds (attack / damage / save) to `/api/campaign/{cid}/roll`.
- `.monster-strike-btn` CSS (32 px min-height per CLAUDE.md dense-panel rule).

### Notes
- Saves render as an "announcement-only" log entry (`expression: "0"` + a descriptive `note`) — the GM still has to use the regular roll-request panel to push a per-player save prompt. A proper "Prompt save" button that hooks into the existing roll-request flow is a follow-up.
- Existing SRD-imported monster TokenTemplates get the regex-derived `sheet.attacks` shape, which loses save info and damage type. Homebrew monsters authored through the 2.3.8 editor carry the full structured shape on `sheet.actions` and get richer buttons. Bringing SRD imports up to parity (parse the desc text into structured fields at import time) is a follow-up.
- Player view unchanged — only GM combatant cards get the new sheet (consistent with current monster-data visibility rules).

---

## [2.3.8] - 2026-05-15

**Schema version:** 52
**Commit summary:** Add structured attack fields to the homebrew-monster Actions editor — `attack_roll` toggle, to-hit bonus, damage / damage type, save ability / save DC. Round-trips through the monster POST handler and the actions-split read path so a re-save no longer drops the fields. Phase 1 of the "homebrew monster attacks → rollable buttons" TODO; rendering the buttons in the stat-block view lands in 2.3.9.
**Description:** Extends `features_editor.js` with an opt-in `data-row-mode="action"` mode. When set, each row gets a secondary input strip below the existing name/level/desc with: an "Attack" checkbox (gates the 🎯 Attack Roll button on the stat block), a To-hit text input ("+5"), a Damage dice expression input ("1d8+3"), a Damage type dropdown (the standard 5e list), a Save ability dropdown (STR/DEX/CON/INT/WIS/CHA), and a Save DC number input. The two monster Actions fieldsets in `campaign_settings.html` (create + edit forms) now declare the mode; the three sibling fieldsets (Special Abilities / Reactions / Legendary) stay name+desc-only by design — those are mostly narrative. The `Action` Pydantic model gained two new optional fields (`attack_bonus: str = ""` and `save_dc: int = 0`) to match the character-sheet attack schema and so the existing server-side `1d20 + attack_bonus` expression builder at `tabletop_routes._resolve_attack` works unchanged. `_coalesce_monster_actions` now passes the new fields through into the unified `actions: list[Action]` array on the Monster model, and the actions_split read path (which feeds the editor's initial data) now includes them too — without that, a re-save would silently wipe any fields the GM set on a prior save. Editor serialization omits empty/default values so the on-disk JSON stays clean.

### Added
- `attack_bonus: str` and `save_dc: int` on `app.action_schema.Action`. Both default to empty/0 so existing JSON files (and existing Action records in flight) validate unchanged.
- `data-row-mode="action"` on the two monster Actions fieldsets in `app/templates/campaign_settings.html` (the existing-monster edit form and the new-monster create form).
- `_mkLabeledInput` / `_mkLabeledSelect` helpers in `app/static/features_editor.js` for the labelled column inputs used by the attack strip.

### Changed
- `app/static/features_editor.js` — `_createRow` and `_serialize` are now mode-aware. Action rows render the attack strip; serialization omits empty/default attack fields so the JSON stays compact. Inputs are stashed on `row._inputs` instead of pulled by DOM index, which was fragile.
- `app/routes/tabletop_routes.py` `_coalesce_monster_actions` — preserves the six attack fields when folding the four split JSON lists into the unified `actions` array.
- `app/routes/tabletop_routes.py` campaign-settings render path — when splitting `actions` back into the four buckets for the editor, also includes the attack fields so a re-load shows them populated.

### Notes
- Special abilities / reactions / legendary actions deliberately stay name+desc-only. The TODO scope notes this — adding the strip to all four fieldsets would be visual noise for entries that rarely involve a rollable attack.
- The Pydantic model defaults mean existing SRD monster JSON files (which lack `attack_bonus` / `save_dc`) validate unchanged. The renderer in 2.3.9 will fall back to a raw 1d20 when `attack_bonus` is empty.

---

## [2.3.7] - 2026-05-15

**Schema version:** 52
**Commit summary:** Fix `features_editor.js` silently dropping edits made in any editor instance whose hidden input is not named `features_json` — specifically the race editor (`traits_json`) and all four monster sub-fieldsets (`actions_json`, `special_abilities_json`, `reactions_json`, `legendary_actions_json`). Resolved while scoping the "homebrew monster attack fields → rollable buttons" TODO, which is unbuildable on a broken sync layer.
**Description:** Pre-existing bug: `_findHiddenInput(root)` did a form-wide query for `input[type="hidden"][name="features_json"]` regardless of which editor instance called it. On forms that don't have a `features_json` input — every race form and every monster form, both create and edit variants — the lookup returned `null` and the submit handler silently skipped the sync. Any GM edit to a homebrew monster's actions / special abilities / reactions / legendary actions, or a homebrew race's racial traits, was lost on save (the existing on-disk JSON was re-rendered on the next page load, so the UI looked like nothing happened). Fix replaces the hardcoded form-wide lookup with: (1) optional `data-target="<input-name>"` on the editor root, (2) fall back to the editor's `nextElementSibling` if that's a hidden input — which every current template already lays out that way (editor div followed immediately by the matching `<input type="hidden" name="..._json">`), (3) legacy form-wide `features_json` fallback so class/subclass editors keep working unchanged. Zero template changes required.

### Fixed
- `app/static/features_editor.js` — `_findHiddenInput` now resolves per-instance via data-target → next sibling → legacy features_json. Race traits and monster action edits now persist instead of being silently dropped on form submit.

### Notes
- Found while scoping the homebrew-monster rollable-attacks TODO (which is unbuildable until the sync layer works). Shipping this as its own commit so the bugfix is independently reviewable and revertable.
- Discovered preexisting bug: docstring at the top of the file was also updated to describe the new resolution order.

---

## [2.3.6] - 2026-05-15

**Schema version:** 52
**Commit summary:** Doc-only: add two related homebrew-monster TODOs to `TODO.md` under GM Tools.
**Description:** No behaviour change. Captures two backlog items raised in conversation, both about making monster combat as click-to-roll as PC combat: (1) expand the homebrew-monster Actions editor to include structured attack fields (`attack_roll`, `attack_bonus`, `damage`, `damage_type`, save fields) so homebrew action entries can be rendered as roll-buttons the way shipped SRD monsters' actions already could; (2) replace the initiative-tracker monster stat-block popover with a reuse of the D&D 5e character sheet shell so checks, saves, and attacks become clickable with the same `/roll` wiring and adv/dis state propagation that PCs already get. The two items are sequenced — (1) is the data prerequisite for (2)'s attack-button wiring against homebrew monsters.

### Changed
- `TODO.md` — added `### Homebrew Monster Attack Fields → Rollable Attack Buttons` and `### Unified Monster Sheet in Initiative Tracker (reuse character sheet UI)` under the existing GM Tools section, both after `### Homebrew Clone`.

---

## [2.3.5] - 2026-05-15

**Schema version:** 52
**Commit summary:** Fix the demo wipe failing with `ForeignKeyViolation` on `fk_campaign_active_map` — the demo campaign's `active_map_id` pointed at a map the wipe was trying to delete, the constraint has no `ondelete` clause, so every on-boot reseed (and every scheduled reset) failed with `IntegrityError` and the demo dataset never got refreshed.
**Description:** Surfaced while verifying the 2.3.4 user-theme fix on the local stack. App-startup logs showed `demo seed (boot) failed: (psycopg2.errors.ForeignKeyViolation) update or delete on table "maps" violates foreign key constraint "fk_campaign_active_map" on table "campaigns"` — the wipe tried `DELETE FROM maps WHERE campaign_id = 1` while `campaigns.active_map_id = 1` still referenced it. The constraint at `app/models.py:99-101` is declared with `use_alter=True` to break the campaigns↔maps circular FK, and has no `ondelete`, so a delete of any referenced map raises. Fix is one extra statement in `wipe()`: before deleting maps, run an `UPDATE campaigns SET active_map_id = NULL WHERE id IN (...)` for the demo campaigns. This unblocks the existing delete and also makes the wipe re-runnable (the existing version left the DB stuck because the failed transaction rolled back and the next boot would hit the same error).

### Fixed
- `app/demo_seed.py` — `wipe()` now NULLs each demo campaign's `active_map_id` before deleting its maps. Without this, every on-boot reseed and every scheduled reset raised `IntegrityError` and left the demo dataset stale.

### Notes
- Side effect: combined with the 2.3.4 user-theme default change, the next successful reseed will recreate the three demo users with `theme = APP_DEFAULT_THEME` (i.e. `sepia` for any operator using the recommended config). Existing demo-user rows from a pre-2.3.4 deploy are deleted-and-recreated by the wipe.
- Redeploy with `docker compose up -d --build app`. The on-boot reseed will now succeed.

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
