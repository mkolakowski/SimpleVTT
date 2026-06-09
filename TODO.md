# SimpleVTT — Planned Features

Backlog of features to implement.

> Completed items live in [`TODONE.md`](TODONE.md). When an item ships, move it there (preserving the version reference) rather than leaving a strikethrough or ✅ stub here.

**Priority legend (Manually Added section only; other sections are time-ordered by header):**

| Tag | Meaning |
|-----|---------|
| `🔥 IN PROGRESS` | Actively being shipped (a plan doc + ongoing commits exist). |
| `🔴 P1` | High priority — bugs, regressions, top-of-the-list features the user has explicitly asked for. |
| `🟡 P2` | Medium priority — substantial features that are planned but not blocking anyone. |
| `🟢 P3` | Low priority — polish / cosmetic / nice-to-have UX tweaks. |

When the assistant offers a single-option "what's next?" via `AskUserQuestion` after a commit, the **top-priority** item (highest P-level, or the IN PROGRESS phase) should be the **(Recommended)** option per the rule in [`CLAUDE.md`](CLAUDE.md#offer-whats-next-as-multiple-choice-questions).

**Quick map of where to look:**

- **Active class-feature automation backlog** → see [Full Class-Feature Automation — remaining backlog](#full-class-feature-automation--remaining-backlog) (just Phase 8 + a few per-feature Phase-2 finishers remain after v2.149.1).
- **Design plans with deferred phases** → see [Design Plans Backlog](#design-plans-backlog) (every `docs/plans/*.md` indexed with a priority tag).
- **One-off bugs + UI polish that don't have a design plan** → see [Manually Added](#manually-added).
- **Big feature buckets that aren't tracked by a plan** → see the topic sections below (Character Sheet, GM Tools, Combat, Maps, Media, Player Features, UI/Mobile, Rules Reference, Legal & Compliance, Test Infrastructure, Integrations, Visual, Class Features (next cycle)). The priority legend doesn't apply to these — they're topic-grouped, not P-tagged.

---

## Manually Added

- 🟢 **P3** — Feature: More pills in the roll log for spells
    - Move spell type, range, action type and details to pills
        - details should be an expanding pill
        - pills should be different color than damage pills
- 🟢 **P3** — Allow the map and roll log (when on the left) to move over the tt-topbar but not over the title of the campaign or the ruler, roll log, battle, characters, tools buttons
- 🟢 **P3** — Change the logout button under tools > quick links to reverse how its animated (better for backgrounds)
- 🟢 **P3** — Update all of roll log to look like spells

---

## Character Sheet

### Ability Score Generation
Two methods for players to generate ability scores during character creation:
- **Point buy** — players spend a fixed pool of points (standard D&D 5e: 27 points, scores 8–15 before racial bonuses) with an interactive cost table shown in the sheet UI. Should enforce the budget in real time and show remaining points.
- **Dice rolling** — roll 4d6 drop lowest for each attribute, with an in-sheet button per score and a "Re-roll all" option. Should show the individual dice results before committing. Optionally allow the GM to lock or unlock rerolls per campaign.

### Class Resource Tracking in Mini-Sheet
Review every D&D 5e class and subclass resource and surface the most commonly used ones in the mini-sheet panel. Current mini-sheet only shows HP and basic rolls. Resources to audit and add:
- **Rage** (Barbarian) — uses per long rest; toggle button to mark active (grants resistance, damage bonus) with a use counter
- **Ki points** (Monk), **Sorcery points** (Sorcerer), **Superiority dice** (Battle Master Fighter), **Bardic Inspiration** — numeric trackers with per-rest reset
- **Channel Divinity**, **Second Wind**, **Action Surge**, **Lay on Hands** pool — binary or pool trackers
- **Wild Shape** uses (Druid), **Arcane Recovery** (Wizard) — per-rest binary toggles

Goal: a compact resource row below HP in the mini-sheet that auto-populates based on the character's class(es). Resources should persist server-side (stored in the character JSON) and broadcast updates via WebSocket so the GM can see resource consumption in real time.

### Dynamic Character Art Updates
When a player updates their character portrait on their sheet, the change should propagate in real time to the tabletop — updating the token image, the player list, and any other places the portrait is displayed — without requiring a page reload. Should use the existing WebSocket broadcast infrastructure so all connected clients (GM and other players) see the new art immediately.

---

## GM Tools

### GM Access to All Character Sheets
GMs should be able to open and read any player's character sheet in the campaign directly from the tabletop or campaign settings, without needing to be assigned as the character's owner. Read-only access is the minimum; optionally allow the GM to make edits (e.g. to update HP after a session or correct a mistake). Needs a clear UI entry point — likely a "View Sheet" button next to each character in the GM's player list.

### Reporting Page
Admin/GM dashboard showing campaign activity: session count, token move history, roll statistics, active players over time. Useful for GMs who want a post-session summary.

### Initiative Tracker Roll Prompt
When a combatant is added to the initiative order without a roll (e.g. added mid-combat from the token sheet or manually), show the GM a "Prompt Roll" button next to that entry. Clicking it sends a WebSocket message to the relevant player's client asking them to roll initiative. The button disappears automatically once the player's initiative is recorded (either via self-roll or GM entry).

### Homebrew Clone
Add a "Clone" button on every homebrew entry in the campaign settings homebrew menu — feats, backgrounds, races, subclasses, monsters, and classes (the six file-based homebrew types as of v2.0.0). Clicking it duplicates the source record as a new homebrew JSON file with a name pre-populated to "Copy of \<original\>" and a fresh auto-generated slug, then opens the new entry in the editor for the GM to tweak. Makes it trivial to spin off variants (e.g. clone "Bandit" → tweak HP / abilities → save as "Veteran Bandit") without retyping every field. Behaviour: server-side endpoint reads the source JSON, mutates the `slug`/`name` fields, writes a new file in the same campaign scope, redirects to the edit form. Existing-slug guard already applies (the existing `_existing_*` check in `homebrew/import` rejects duplicates). No clone for shipped SRD content — that lives in `app/data/local/dnd5e/` and is read-only; cloning shipped → homebrew would be a separate feature.

### Homebrew Monster Attack Fields → Rollable Attack Buttons
Expand the homebrew-monster Actions editor (`app/templates/campaign_settings.html` ~line 2188-2192, currently a generic `data-features-editor` exposing only `name` + `desc`) so each action carries the same structured fields the shipped SRD stat blocks already use — `attack_roll: bool`, `attack_bonus: int` (or derived "+to_hit"), `damage: "1d8"`, `damage_type`, optional `save_ability` / save DC for save-based attacks. With those fields populated, the stat-block view can render each attack as a clickable button that pipes through the existing `/roll` endpoint (mirroring the character sheet's weapon attack flow at `app/static/sheet.js`) so GMs running a homebrew "Veteran Bandit" don't have to manually retype `1d20+5` and `1d8+3 slashing` into chat for every swing. Scope: (1) extend the features-editor JS to render the extra attack fields when the parent fieldset is the Actions list (Special Abilities / Reactions / Legendary can stay name+desc-only — those are mostly narrative), (2) update the homebrew monster POST handler to persist the structured fields into the JSON file, (3) extend the monster stat-block read-view to render attack buttons when `attack_roll: true` is set, with hover/click semantics matching the character-sheet attack buttons. Bonus follow-up: a "Parse from description" button that regex-extracts `+N to hit` / `NdM damage type` from a pasted SRD-style description so importing a homebrew monster doesn't require filling every field manually.

### Unified Monster Sheet in Initiative Tracker (reuse character sheet UI)
Today the initiative tracker opens a read-only stat-block popover for monster entries, while character entries open the full interactive D&D 5e sheet (`app/templates/sheet_dnd5e.html`) with clickable ability checks, skill checks, saves, and weapon-attack buttons that pipe through `/roll`. Goal: replace the monster popover with the same sheet shell so the GM can click an attack on "Bandit Captain" the same way a player clicks an attack on their PC — one-click roll, auto-applied advantage/disadvantage from `roll_state`, breakdown lands in the shared roll log. Pairs naturally with the "Homebrew Monster Attack Fields" TODO above (the structured `attack_roll` / `damage` fields are the data the buttons bind to). Scope sketch: (1) backend — extend the sheet route or add a "monster sheet" sibling that reads a stat block (SRD JSON or homebrew JSON) and projects it into the same context shape `sheet_dnd5e.html` expects (abilities, modifiers, skills, attacks, spells). Most fields map cleanly; HP/AC/speed/CR have direct equivalents, skills need to be derived from the monster's `skills` list + ability modifiers, attacks come from the Actions list. (2) frontend — reuse `sheet.js`'s `wireDnd5eRollButtons` against the monster sheet so ability/skill/save/attack clicks all hit `/roll` and respect roll-state. (3) initiative tracker — open the new sheet (full-screen or large modal) instead of the popover, keyed by token's stat-block reference (slug or homebrew slug). (4) ownership/scope — monsters are GM-only; the sheet should hide the "edit" affordances available to a PC owner (or route them to the homebrew editor for homebrew monsters). Open question: do legendary actions and lair actions get first-class buttons too, or stay as narrative text? Probably first-class buttons since they're the rolling-heavy content. Builds on the structured-attack-fields TODO above; can ship the read-mostly version first and incrementally add roll wiring per field category.

---

## Combat

### Advantage & Disadvantage Tracking
Per-character roll-state toggle (adv / normal / dis) that the server applies to d20 rolls automatically, with the existing manual `adv` / `dis` dice buttons preserved as one-shot overrides. Three phases: manual toggle, condition automation, context-aware rolls. See [`docs/plans/advantage-disadvantage.md`](docs/plans/advantage-disadvantage.md) for the full design.

### Death Saving Throws
Triggered automatically when a character hits 0 HP. Mini-sheet + full sheet show success/failure pips; "Roll Death Save" button rolls a 1d20 through the regular roll pipeline (so it honors the adv/dis roll-state toggle). Healing wakes the character up; damage at 0 HP ticks failures (with crit and massive-damage rules per 5e RAW). GM gets override + stabilize controls. See [`docs/plans/death-saves.md`](docs/plans/death-saves.md) for the full design.

### Combat 2.0 — Action Economy Tracking
Full per-turn action economy tracker surfaced in the initiative tracker and each player's mini-sheet. Tracks the four action types defined by D&D 5e:

- **Action** — one per turn; used for attacks, casting most spells, Dash/Disengage/Dodge/Help/Hide/Ready
- **Bonus action** — one per turn; class features, certain spells, off-hand attacks
- **Movement** — up to the character's speed (in feet); partially consumed by moving between tokens (requires Maps 2.0 grid distance awareness)
- **Free action / Reaction** — one reaction per round; tracked separately, auto-resets at the start of the character's next turn

UI: a compact row of four icons in the initiative tracker entry and mini-sheet. Clicking an icon marks it spent (greyed out). At the start of a character's turn the GM can click "New Turn" to reset all four. The GM can also manually mark/unmark any action for any combatant. State is broadcast over WebSocket so all clients stay in sync.

---

## Maps & Map Editor

### Bulk Map Upload
Allow GMs and admins to upload multiple map images at once (e.g. a zip or multi-file picker) rather than one at a time. Should probably show a progress indicator and let the user assign names/grid settings to each before committing.

### Map Generator
Procedural in-browser map generation — produce a playable battle map without any external upload. Minimum viable output: a dungeon room layout (walls, corridors, door placements) rendered to a canvas the GM can place tokens on immediately. Stretch goals: biome presets (dungeon, wilderness, tavern interior), adjustable density/size parameters, and one-click export as a PNG that feeds into the existing map upload flow.

### Bundled Art Assets (Maps, Player Tokens, Monster Tokens)
Source and bundle a starter set of free-to-use art so new campaigns have something to work with out of the box. Three separate asset packs:
- **Battle maps** — a handful of generic scenes (dungeon room, tavern, forest clearing, city street) usable as starting maps
- **Player tokens** — a set of generic adventurer portraits (warrior, rogue, mage, cleric, ranger, etc.)
- **Monster tokens** — common encounter creatures (goblin, skeleton, orc, wolf, spider, etc.)

Licensing requirements: CC0 or CC BY with attribution in a bundled `CREDITS.md`. Consider AI-generated art (e.g. Stable Diffusion with a permissive licence) as a practical source for a consistent style across all three packs. Assets should ship inside the Docker image under `app/static/bundled/` so they are available without any upload step.

### Maps 2.0 — Advanced Map Features
Extends the existing battle map canvas with GM-controlled environmental features. Builds on the Map Editor Framework groundwork below; these items represent the prioritised feature set for a Maps 2.0 milestone.

- **Combat movement locking** — when a combat encounter is active, token movement is capped at the character's speed (in feet). Each move broadcasts the distance consumed; the token becomes unmovable once the movement budget is exhausted for that turn. Requires grid scale (ft per square/hex) to be set on the map. Integrates with Combat 2.0 action economy tracking.
- **Fog of war** — GM-controlled per-cell reveal overlay. Players see black/obscured cells until the GM reveals them. Two modes: manual brush reveal (GM paints explored areas) and auto-reveal based on token line-of-sight. GM always sees the full map.
- **Walls & doors** — the GM places wall segments (line tools) directly on the battle map. Wall data is saved at the map level (not per-encounter) so the same map always loads with its walls intact. Doors are interactive wall segments: players and GMs can toggle them open/closed, which updates the fog-of-war LOS calculation in real time.
- **Dedicated wall editor** — a separate editing mode (toggle in the GM toolbar) for placing, moving, and deleting wall segments. Should be distinct from normal token-interaction mode to prevent accidental edits during play. Wall data stored as a JSON array of line segments on the `BattleMap` record.
- **Clickable map items** — hotspots placed by the GM that trigger a description popup or roll prompt when a token moves onto or a player clicks them.

### Map Editor Framework
Groundwork for in-browser map authoring tools. Planned capabilities:
- **Fog of war** — GM-controlled reveal of map regions; players see only explored areas
- **Walls** — line segments that block token line-of-sight
- **Doors** — interactive wall segments that players/GMs can open or close
- **Clickable items** — hotspots on the map that trigger a description popup or roll prompt
- **Multi-map encounters** — link multiple maps into a single encounter (e.g. interior/exterior transitions) without switching the active map for the whole campaign

### Lighting
GM can place different kinds of light sources on the map — torches, lanterns, campfires, magical lights — each with their own radius, colour, and behaviour. Flicker animation for fire-based sources (gentle brightness/radius oscillation), steady glow for magical lights, etc. Integrates with fog of war and player vision: tokens illuminate the area around them based on attached lights, and players only see what their token's light source(s) cover (plus any GM-revealed fog area). The GM has full visibility regardless. Stretch goals: ambient map-wide lighting (day/night/dim), per-token vision types (darkvision out to N ft as dim light, blindsight ignoring lighting entirely), and "extinguish" interaction on placed lights. Builds on the Maps 2.0 / Map Editor Framework groundwork above — both fog-of-war LOS and wall segments need to land first so lighting can compute shadows correctly.

---

## Media & Content

### Resources
A dedicated section for GMs and admins to upload documents (PDFs, images, handouts) that players can view directly in the browser — inline PDF rendering, no download required. Needs access control so GMs can choose whether a resource is visible to all players or GM-only.

### Playlist Builder with Existing Songs
Allow GMs to create playlists from tracks already uploaded to the campaign rather than re-uploading. UI: a picker listing existing campaign audio tracks, drag-to-reorder, save as a named playlist. Backend: new playlist model + endpoints; guard file deletion to prevent removing audio that is still referenced by a playlist.

---

## Player Features

### User Presence on the Tabletop
Show who is currently connected to the session in real time. All connected users (GM and players) should be able to see at a glance which other players are online, idle, or have disconnected. Planned scope:

- **Presence indicators** — a small online/offline dot (or avatar badge) next to each player's name in the player list and/or initiative tracker. Green = connected, grey = disconnected. Optional: amber = connected but idle (no interaction for N minutes).
- **WebSocket lifecycle hooks** — on connect, broadcast a `presence_join` message to all clients; on disconnect (or WebSocket close), broadcast `presence_leave`. Clients maintain a local presence map and update the UI reactively.
- **Cursor / active-token highlight** (stretch) — show a faint coloured ring or name label on the token currently being hovered or dragged by another user, similar to Google Docs cursor presence.
- **GM view** — the GM's player list should show presence state for every campaign member, including those who haven't joined the current session yet (shown as offline).

Backend: presence state is ephemeral (in-memory in `realtime.py`, not persisted to the database) — it resets when the server restarts, which is acceptable.

### Player Notes
Per-player scratchpad (rich text or markdown) scoped to a campaign. Notes should be private to the player by default, with an optional "share with GM" toggle. Persisted server-side so they survive page refreshes.

---

## UI / Mobile

### Slide-Out Menu for Mobile
On small screens, replace the current sidebar with a proper slide-out drawer triggered by a hamburger button. The map should fill the full viewport and the drawer overlays it rather than pushing it. Needs gesture support (swipe to open/close).

### Darker Sepia Themes
Add a few darker sepia/warm-brown colour themes as alternatives to the existing dark theme. Candidates: a deep parchment (dark tan background, inked-brown text), a candlelit tavern (very dark brown with amber accents), and a burnt manuscript (near-black with faded sepia highlights). Should slot into the existing theme system with new CSS variable sets — no structural changes needed.

---

## Rules Reference

### SRD Rules in Full Text
Surface the complete D&D 5e Systems Reference Document (SRD 5.1, CC BY 4.0) as searchable in-app reference text. Players and GMs should be able to look up rules without leaving the VTT. Planned scope:
- Full SRD text indexed and searchable by keyword (conditions, actions, spells, equipment, etc.)
- Contextual links from the character sheet and encounter panels (e.g. clicking a condition name opens its SRD entry)
- Offline-capable: content bundled in the Docker image rather than fetched at runtime
- GM can pin a rule snippet to the tabletop panel for the whole table to see during play

Content source: the official SRD 5.1 PDF / markdown release from Wizards of the Coast, licensed CC BY 4.0. Attribution required in-app.

### Page Number References in Official Content
Where SimpleVTT surfaces content from official published sourcebooks (e.g. PHB, MM, DMG) — in spell descriptions, class features, item entries — investigate whether page numbers can be shown alongside the source citation (e.g. "PHB p.218").

**Licensing review required before implementing:** displaying page numbers from non-SRD sourcebooks may constitute a reference to copyrighted content even if the page number itself is a fact. Consult the D&D 5e SRD licence terms and any Fan Content Policy. If page numbers are only shown for SRD-sourced content (which is CC BY 4.0), no additional licensing concern applies — SRD content should be safe. Non-SRD sourcebook page numbers should be gated on legal sign-off.

---

## Legal & Compliance

### Full Audit for Licensed Material
Systematic review of all content bundled in or served by SimpleVTT to ensure nothing included exceeds its licence terms. Scope:

- **SRD content (spells, monsters, items, classes, races)** — confirm all data served via the Open5e mirror or shipped FS files is SRD 5.1 / CC BY 4.0 material only; flag any non-SRD entries (e.g. setting-specific content, post-SRD sourcebook expansions)
- **Images and art** — audit every image in `app/static/` (including any bundled token/map art) against its licence; ensure CC0 or CC BY assets have attribution in `CREDITS.md`
- **Fonts** — verify Google Fonts licences (currently all SIL OFL 1.1 — should be clean)
- **Third-party JS/CSS libraries** — list all vendored or CDN-loaded libraries and confirm licences are compatible with self-hosting
- **Any AI-generated art** — confirm the generation tool's output licence (some tools claim copyright on outputs; others release CC0); document the tool and settings used for each asset

Output: a `CREDITS.md` file at the repo root listing every third-party asset, its licence, and its source URL, plus a checklist of items that need further review or replacement.

---

## Test Infrastructure

### Install emoji font in CI for the skull-overlay test (or rework the assertion)
**Filed 2026-05-25 (v2.49.241).** `tests/encounter_sim/level_3_edge_cases/death_saves/test_skull_overlay_at_zero_hp.py::test_skull_overlay_renders_on_zero_hp_token` is skipped pending font diagnosis. CI's Playwright Chromium consistently samples `[66, 66, 66, 255]` (gray tofu) at the token center — the ☠ emoji isn't rendering because the runner image lacks an emoji font. Locally (macOS) the skull renders fine.

**Fix paths:**
1. Add `fonts-noto-color-emoji` (or equivalent) install step to the Playwright job in `.github/workflows/test-harness.yml` before `playwright install --with-deps chromium`. Quick win — just a `sudo apt-get install -y fonts-noto-color-emoji` line.
2. Change the test's assertion from "sample a canvas pixel" to "check window.battle + a draw-fired flag." Decouples the test from font availability entirely.
3. Rewrite the skull overlay itself to use an SVG/HTML element on top of the canvas. Most invasive but easiest to test against.

Path (1) is the smallest commit; path (2) is the most resilient long-term. The v2.49.4 regression class this test catches IS still covered locally (where macOS has the font).

### Re-tokenize Garrik Ironside (or change tokenized-six lineup to include a Fighter)
**Filed 2026-05-25 (v2.49.236 CI cleanup).** Two encounter-sim Playwright tests are skipped pending this fix:
- `tests/encounter_sim/level_2_encounter/test_tavern_brawl_baseline.py::test_tavern_brawl_3_pcs_3_npcs_round_cycle`
- `tests/encounter_sim/level_3_edge_cases/action_economy/test_action_surge_refunds_chip.py::test_action_surge_refunds_action_chip`

Both seed Garrik (Fighter) into the init tracker via direct localStorage / `seed_battle_into_page`, but the tabletop's orphan-cleanup at `tabletop.html:4807` drops any combatant whose `char_id` isn't tokenized in the demo seed. v2.49.172's demo slim from 12 → 6 tokenized PCs removed Garrik (and Sir Caelan / Lyra / Mira / Kael / Rowan) from `seed_tokens()`, but didn't update these tests.

**Fix paths:**
1. Add Garrik back to `seed_tokens()` (one `tokens.append(Token(...))` block; needs a map position + image_url). Cascades: maybe also need to add him to the pre-rolled initiative in `seed_battle_state`. Cheapest if no other tokenized PC is a Fighter.
2. Swap the test fixtures to use a currently-tokenized PC (Krieger = Barbarian, Pip = Rogue, etc.). Works for the tavern brawl test (just init-tracker rendering) but NOT for the Action Surge test (needs a tokenized Fighter — none exist in the tokenized six today).
3. Change the demo's tokenized-six lineup to swap one of Pip/Thalindra/Tavik/Zara/Krieger/Magnus for Garrik. Plan-doc impact: `class-content-status.md` Phase-A demo-roster notes.

Backbone Kristen (`tests/harness/test_use_action_surge.py`) still covers the Action Surge chip-refund contract via direct PUT `/battle`; only the Playwright UI assertion is gated on the missing token.

---

## Integrations

### Philips Hue Integration
Allow GMs to sync Philips Hue smart lights with tabletop events — e.g. dim lights on combat start, flash red on a critical hit, restore brightness when combat ends. Should connect to the local Hue Bridge (mDNS or manual IP) and allow the GM to map VTT events to Hue scenes or brightness/colour changes in campaign settings.

---

## Visual

### Frosted-glass treatment across the whole tabletop interface
v2.49.139 applied the iOS-style frosted-glass look (semi-transparent background + `backdrop-filter: blur(10px) saturate(140%)`) to roll-log cards only. Extend to every drawer card on the tabletop so the canvas behind reads through everywhere — init-tracker cards (`.init-row` / `.init-entry`), GM panel cards (`.gm-panel`), the sound panel, the AoE picker hint, the ruler hint, the targeting chip, etc. Each surface needs:
- A theme-coherent `color-mix(in srgb, var(--bg) 78%, transparent)` background (or the appropriate variant for accent / panel-tinted surfaces)
- `backdrop-filter: blur(10px) saturate(140%)` + `-webkit-backdrop-filter` for Safari/iPad
- Verification that text remains readable on a busy map across all 9 themes (dark, midnight, dim, light, forest, bubblegum, oled, fire, sepia)

Performance note from v2.49.139: each `backdrop-filter` element triggers a compositor layer. Audit the total composite layer count once applied — if it gets heavy on long sessions, gate the blur behind a "low-detail" theme toggle.

---

## Class Features (next cycle)

### Paladin Aura of Courage (Lv 10)
Same shape as Aura of Protection (v2.53.0) and Aura of Devotion (v2.55.0) — `_ally_has_aura_of_courage(db, campaign_id, saving_char_id)` walks init for any Paladin Lv 10+ in any oath. RAW: "you and friendly creatures within 10 feet of you can't be frightened while you are conscious." This is a **condition-install immunity** gate matching the Aura of Devotion pattern, just with "frightened" as the blocked condition key (instead of "charmed"). Wire the same way: gate at `/roll_request/{id}/respond`'s PC-failed-save condition-install block, skip install + broadcast `feature_used(source=aura-of-courage)` when `cond.key == "frightened"` and a Paladin Lv 10+ is in init.

**Caelan bump**: 7 → 10. **Three levels** of cascading changes — prof bonus +3 → +4 (changes at Lv 9), HP +24, Lay on Hands pool 35 → 50, spell slots gain L3 (4/3/2 instead of 4/3/0). The prof bump breaks existing attack-bonus assertions in `test_attack.py::test_attack_divine_smite_spends_slot` (Longsword +6 → +7 because STR +3 + prof +4 = +7) — needs an audit-and-fix pass. **Recommended scope**: bundle Aura of Courage with the Caelan bump so the slot-pool / damage-die scaling lands once. Defer Aura of Devotion's Lv 18 30-ft radius expansion — same helper, larger gate, different commit.

Filed by v2.55.0 when the user picked Indomitable as the next implementation target. Pick this up after Indomitable ships.

### Fighter Indomitable (Lv 9+) — IN PROGRESS as v2.56.0 "Iron Will"
Garrik bump 7 → 9 (prof +3 → +4, HP +14, Second Wind 1d10+9). New `/use_indomitable` endpoint installs a single-use `indomitable-armed` self-buff; the save-roll construction hook reads the buff, swaps `1d20 → 2d20kh1`, and removes the buff from the combatant so the consumption is per-save (RAW: one specific reroll). RAW-bent v1: advantage on the next save rather than reroll-on-failure, since the post-roll reroll flow needs an undo-and-reapply path for installed conditions which is its own substantial commit. Filed for follow-up: the precise post-roll reroll with consequence-undo.

---

## Full Class-Feature Automation — remaining backlog

🔥 **IN PROGRESS** — plan: [`docs/plans/full-feature-automation.md`](docs/plans/full-feature-automation.md); live audit: [`docs/automation-coverage.md`](docs/automation-coverage.md). **Phases 0–7 ✅ done** + the entire v2.128.2–v2.149.1 retrofit batch landed (see CHANGELOG). Only Phase 8 (higher-level subclass features Lv 6/10/14/17/20) and a few Phase-1.5 / Phase-2 follow-ups on individual features remain.

**Status by archetype (re-evaluated 2026-06-08):**

Shipped archetypes (Phase 7 reactions, auras E, on-hit B, buff/temp-HP D/F, movement G) live in [`TODONE.md`](TODONE.md#full-class-feature-automation--archetype-bullets-shipped).

- 🟢 **P3 — Phase 8: higher-level subclass features (Lv 6/10/14/17/20).** Mostly composition on the now-built primitives; batch by class. The long tail. **Now the primary remaining work for the parent plan.**
- 🟢 **P3 — Per-feature Phase-2 finishers (deferred from this session):**
    - **Blade Flourish Phase 2** — Defensive AC self-buff + Mobile push + Slashing secondary-target routing.
    - **Fancy Footwork Phase 2** — OA-flow gate reads the `fancy-footwork-blocked` buff and skips OAs against the named char_id.
    - **Relentless Avenger Phase 2** — `/token/move` consumes `free_movement_remaining_ft` budget + skips OA prompts while `oa_immune_during_move` is set.
    - **Supreme Healing Phase 1.5** — `/apply_healing` chat-card path (legacy `_heal_claims` flow) also substitutes max dice.
    - **Combat Inspiration Phase 3** — Integrate the AC half into the reactions framework so the prompt fires automatically on `attack_targeted` for any combatant carrying a BI die buff.
    - **AP Phase 3 / UM Phase 1b** — Auto-install via `/attack` post-hit hook (currently both require player-driven trigger via the `target_surprised` / endpoint call).
- 🟢 **P3 — Classifier rerun for `docs/automation-coverage.md`.** Auto-generated row counts in the "Full classification" table still pin v2.99.460; rerun the classifier after the v2.128.2–v2.149.1 batch so the per-endpoint table reflects reality. Curated bullets + the "Recent retrofits" table are aligned per v2.142.1 + v2.149.1.

The remaining ~30 announce-only rows are **archetype J** (narration-only-by-design: passive senses, language grants, passive damage-boosters that already ride other paths) — leave as-is; see the audit doc's "Notable announce-only backlog" section for the full split.

---

## Design Plans Backlog

Every design doc under [`docs/plans/`](docs/plans/) + the two repo-root planning docs (`docs/encounters-plan.md` + `docs/multi-system-refactor.md`). Priorities reflect the post-v2.149.1 state of each plan — **🔥 IN PROGRESS** = a plan with ongoing commits this session; **🔴 P1** = next-up substantial work; **🟡 P2** = substantial deferred phases or proposed work; **🟢 P3** = lower-priority or living-doc style.

### 🔥 IN PROGRESS

- [`full-feature-automation.md`](docs/plans/full-feature-automation.md) — see the section above; Phase 8 is the next slice.

### ✅ Shipped end-to-end

Now lives in [`TODONE.md`](TODONE.md#design-plans-backlog--shipped-end-to-end) — 12 plans (auras, death-saves, demo-mode, feature-saves, movement-and-summons, movement-oa-flow, on-hit-riders, ruler-and-range, spell-upcasting, temp-hp-and-bonuses, test-harness, wild-magic).

### 🔴 P1 — Next substantial work

- [`advantage-disadvantage.md`](docs/plans/advantage-disadvantage.md) — Phase 1 ✅ shipped; **Phase 2–3 deferred** (condition automation, context-aware rolls). Pairs well with Combat 2.0 action economy. **Now the only P1 design plan with substantial open work.**

### 🟡 P2 — Substantial deferred phases

- [`paladin-oaths.md`](docs/plans/paladin-oaths.md) — Phase 1 ✅ v2.99.245; this session shipped Aura of Warding (Ancients) v2.133.0–v2.135.1 + Scornful Rebuke (Conquest) v2.142.0 + Relentless Avenger (Vengeance) v2.149.0 + Aura of the Guardian (Redemption) per v2.99.281; **Phase 2–6 + 2 oaths (Crown, Treachery) deferred**.
- [`battle-master.md`](docs/plans/battle-master.md) — Phase 1 ✅ v2.99.233; **Phase 2–5 + 15 maneuvers deferred**.
- [`eldritch-knight.md`](docs/plans/eldritch-knight.md) — Phase 1 ✅ v2.99.232; **Phase 2–4 deferred**.
- [`warlock-pact-boon.md`](docs/plans/warlock-pact-boon.md) — **Phase 0–5 unstarted** (this session partially touched the Warlock surface via Ascendant Step v2.147.0 but the pact-boon plan itself is unshipped).
- [`sorcery-points-and-metamagic.md`](docs/plans/sorcery-points-and-metamagic.md) — Phase 0 ✅ v2.49.120; **Phase 1–5 unstarted**.
- [`spell-validation-suite.md`](docs/plans/spell-validation-suite.md) — **Phase 0–5 unstarted**. Would close the spell-upcasting backfill audit gap.
- [`reactions-automation.md`](docs/plans/reactions-automation.md) — Phase 1a + 1b + 2a-partial ✅ v2.67.0–.2 + Phase 7 ✅ v2.118.0–.122.0; **Phase 2b–6 + the proactive-prompt machinery deferred**.
- [`encounter-sim-test-suite.md`](docs/plans/encounter-sim-test-suite.md) — design finalized; **Phase 1 PoC pending**.
- [`unified-mini-sheet.md`](docs/plans/unified-mini-sheet.md) — 3 mockups landed; **Phase 1–3 unstarted**. Pairs naturally with Class Resource Tracking + Combat 2.0.
- [`docs/encounters-plan.md`](docs/encounters-plan.md) — **proposed, not started**.
- [`docs/multi-system-refactor.md`](docs/multi-system-refactor.md) — **proposed, not started**. Big architectural lift.

### 🟢 P3 — Lower-priority / living docs

- [`player-simulacrum.md`](docs/plans/player-simulacrum.md) — **design only, all phases unstarted**. Speculative.
- [`wiki-expansion.md`](docs/plans/wiki-expansion.md) — living roadmap of how-to guides + reference cards still to write. Doc-style work, lots of small slices.
- [`class-content-status.md`](docs/plans/class-content-status.md) — living inventory; updates as features ship.
