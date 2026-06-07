# SimpleVTT — Planned Features

Backlog of features to implement.

**Priority legend (Manually Added section only; other sections are time-ordered by header):**

| Tag | Meaning |
|-----|---------|
| `🔥 IN PROGRESS` | Actively being shipped (a plan doc + ongoing commits exist). |
| `🔴 P1` | High priority — bugs, regressions, top-of-the-list features the user has explicitly asked for. |
| `🟡 P2` | Medium priority — substantial features that are planned but not blocking anyone. |
| `🟢 P3` | Low priority — polish / cosmetic / nice-to-have UX tweaks. |

When the assistant offers a single-option "what's next?" via `AskUserQuestion` after a commit, the **top-priority** item (highest P-level, or the IN PROGRESS phase) should be the **(Recommended)** option per the rule in [`CLAUDE.md`](CLAUDE.md#offer-whats-next-as-multiple-choice-questions).

---

## Touch Target Remediation

Apple's HIG minimum of 44×44 px was applied globally in v1.2.7 via the base `button`, `input`, and `select` CSS rules, and class-level overrides were added for the tabletop panel elements. The following inline-styled elements were not covered by that pass and still need updating. Grouped into three phases ordered by effort.

### ~~Phase 1 — Campaign Settings~~ ✓ Done (v1.2.8)

`app/templates/campaign_settings.html`

| Line | Element | Current style | Fix |
|------|---------|---------------|-----|
| ~83 | `.track-actions button` (rename / save / cancel / play / delete audio track) | `padding:2px 7px; font-size:12px` | Add CSS class `.track-action-btn` with `min-height:44px` and replace inline style |
| ~624 | `select.pl-category-select` (playlist category dropdown) | `font-size:11px; padding:2px 4px` | Increase to `padding:6px 8px` or remove inline style and rely on global `select` rule |
| ~1071 | `select#enc-lib-sort` (encounter library sort) | `font-size:12px; padding:2px 6px` | Same — remove inline padding override so global rule applies |

**Approach:** Remove the inline `padding` overrides from the two selects (they will then inherit the global `min-height:44px` rule). For `.track-actions button`, add a named CSS class at the top of the template so it can be shared across all track action buttons.

---

### ~~Phase 2 — Tabletop JS-created buttons~~ ✓ Done (v1.2.9)

`app/templates/tabletop.html` · `app/static/tabletop.js`

Defined `.enc-action-btn` (32 px), `.enc-modal-btn` (44 px), and `.enc-spawn-btn` (32 px) CSS classes. Replaced `style.cssText` assignments on encounter action buttons, save/cancel, and spawn set/clear with `className` assignments. Removed padding overrides from encounter edit form inputs/selects, roll-request panel controls, audio-enable button, and Import & Place button.

---

### ~~Phase 3 — D&D 5e Character Sheet~~ ✓ Done (v1.2.10)

`app/templates/sheet_dnd5e.html`

Nearly all 24 buttons share the same inline style (`font-size:11px; padding:2px 8px`). The fix is to introduce a single shared CSS class and replace every occurrence.

**New class to add** (at the top of the template's `<style>` block):
```css
.sheet-section-btn { font-size: 11px; min-height: 44px; padding: 0 10px; }
```

**Buttons to update** (replace `style="font-size:11px;padding:2px 8px"` with `class="sheet-section-btn"`):

| Line | Button ID | Purpose |
|------|-----------|---------|
| ~109 | `#char-edit-btn` | Edit character details |
| ~255 | `#bg-sync-btn` | Re-fetch background |
| ~268 | `#feats-add-btn` | Add feat |
| ~282 | `#mc-add-class-btn` | Add multiclass |
| ~522 | `#ab-edit-btn` | Edit ability scores |
| ~523 | `#ab-done-btn` | Save ability scores |
| ~568 | `#st-edit-btn` | Edit saving throws |
| ~569 | `#st-done-btn` | Save saving throws |
| ~618 | `#sk-edit-btn` | Edit skills |
| ~619 | `#sk-done-btn` | Save skills |
| ~819 | `#browse-weapons-btn` | Browse weapons |
| ~820 | `#add-custom-attack-btn` | Add custom attack |
| ~905 | `#spell-browser-btn` | Browse spells |
| ~906 | `#add-custom-spell-btn` | Add custom spell |
| ~909 | `#hide-unprepared-btn` | Toggle unprepared spells |
| ~911 | `#sc-autofill-btn` | Autofill spell slots |
| ~1125 | `#resources-sync-btn` | Sync resources |
| ~1126 | `#resources-add-btn` | Add resource |
| ~1127 | `#wild-shape-btn` | Wild Shape (Druid) |
| ~1128 | `#polymorph-btn` | Polymorph |
| ~1165 | `#browse-items-btn` | Browse items |
| ~1166 | `#add-custom-item-btn` | Add custom item |
| ~1306 | `#sync-race-btn` | Sync racial traits |
| ~1320 | `#sync-class-btn` | Sync class details |

Two additional buttons use slightly different padding and may need individual review:
- `#short-rest-btn` / `#long-rest-btn` (~line 167–168): `padding:4px 8px` — closer to compliant, verify with `.mini-rest-btn` class already applied.
---

## Manually Added

- ✅ **DONE** — GM and player do not get popup notification that opportunity attack can be used. **Design doc: [`docs/plans/movement-oa-flow.md`](docs/plans/movement-oa-flow.md)** (added v2.99.50). All 6 phases shipped v2.99.52–v2.99.57:
    - Phase 1 ✅ v2.99.52 — Team data model + same-team filter
    - Phase 2 ✅ v2.99.53 — Token Management UI overhaul (edit button, pills, remove upload art)
    - Phase 3 ✅ v2.99.54 — "would-this-trigger-OA?" preview endpoint
    - Phase 4 ✅ v2.99.55 — Pre-move "Continue or Stop?" modal (the headline)
    - Phase 5 ✅ v2.99.56 — Per-watcher serial resolution + attack picker + skip
    - Phase 6 ✅ v2.99.57 — Multi-token-per-owner sub-queue (parallel across owners)
    - Notification flow (covered by Phase 4 + 5):
        - Pause movement and popup notification
        - User moving token gets popup asking if they want to continue movement as they will trigger an attack of opportunity
            - player chooses to stop → token stops + doesn't move out of the spot that leaving would trigger the OA + end flow
            - player chooses to move → owner of the token(s) receives a notification per token, if they have a reaction, to either roll the attack or skip
                - Attacking choice lists eligible attacks (some feats will let spells be used) and if the player chooses an attack, executes it as the OA
                    - if player survives → allow movement until next OA contest, as range allows
                - If skip chosen → allow movement until next OA contest, as range allows
    - if multiple tokens would get OAs they will need to all be resolved before the player can continue movement (Phase 5)
    - if one owner has multiple tokens that would need to make OAs, finish one flow before showing the next (Phase 6)
    - Do not prompt for OAs for tokens on the same "team" (Phase 1)
        - GM to specify using a toggle inside token management to assign "hero" or "villain" team groups vs the existing players and GM/NPC (Phase 1 + 2)
        - add edit button next to refresh and expose dropdown to change ownership and team per line item (Phase 2)
            - when not editing, show these new fields as pills before the buttons (Phase 2)
            - when not editing do not show player assignment dropdown (Phase 2)
        - remove upload art from token management (Phase 2)
- ✅ **DONE (spell slots) — v2.99.462–.464** — Bug: Un-do button does not refund spell slot
    - ✅ All spell-slot consumers now refund on Undo: the 10 dedicated `cast_*` endpoints (cast_sleep / cast_slow / cast_polymorph / cast_compulsion / cast_bestow_curse / cast_bane / cast_hold_person / cast_flesh_to_stone / cast_hold_monster / cast_web) via the new `_log_spell_slot_spend` helper (v2.99.462–.463), plus `/attack` Divine Smite + `/use_primeval_awareness` (v2.99.464).
    - **Remaining (lower-priority audit follow-up):** a coverage pass over feature/item resource consumes — the `/undo_attack_damage` machinery already handles `resource_spend` / `inventory_consume` kinds; audit which `use_*` endpoints actually log them on consume (most do, e.g. lay_on_hands / second_wind). Not a spell-slot issue.
- 🔴 **P1** — Bug investigation: NPCs unable to use action buttons, IE strike button on Dagger for vex
    - Players seem to work as expected
- 🟡 **P2** — Feature: plan three ways that we can allow users to up-cast spells
    - IE, Magic missile at level 3
    - Note: will need an audit of spells to see how up-casting them will affect how the spell is handled
- 🟡 **P2** — Feature: Framework that will allow then to use features like luck by clicking a button inside the roll log card they want to re-roll
    - button to only be visible to GM and PC owner
    - Add confirmation to confirm usage
    - Should "grey out" if the PC/NPC does not have use of the feature and should not be visible if no features available
- 🟡 **P2** — when roll log is on left, do not make disappear when gm requests roll and gm rolls for player
    - example: GM uses gm roller to push a INT Save with the DC of 20 for both demo characters, GM rolls as Pip, roll log collapses after the roll animation completes
- 🟡 **P2** — GM does not get movement popup when moving tokens past range
- 🟡 **P2** — AoE updates
    - AoE spells that are concentration or have a duration, place a visual indicator of the spell
        - notable complications,
            - Spirit Guardians: aoe will need to be bound to player token and tokens on the same team should not be targeted
            - Moonbeam: after placement, is concentration, as long as there is duration and the caster has not lost concentration, display the moonbeam and allow the player to move it per the range in the spell, once per turn
    - AoE spells that are a single turn, like Fireball, leave a pulse to indicate the AoE to the players, should happen for a few seconds
- 🟡 **P2** — Add feature to lock player and NPC movement
    - add toggle in encounter
    - add option in campaign settings to make the toggle default on or off in the encounter interface
    - player and GM to get popup notifying that movement is locked
        - Player can request from GM to allow movement
            - GM can approve or deny
        - GM popup will ask to confirm movement
- 🟢 **P3** — Feature: More pills in the roll log for spells
    - Move spell type, range, action type and details to pills
        - details should be an expanding pill
        - pills should be different color than damage pills
- 🟢 **P3** — Move the Title of the campaign, to the center of the window and please place it in a "pill" that has the "glass effects"
- 🟢 **P3** — Remove badge system tt-topbar-badge and "muted tt-topbar-gm" from the tt-topbar
- 🟢 **P3** — Allow the map and roll log (when on the left) to move over the tt-topbar but not over the title of the campaign or the ruler, roll log, battle, characters, tools buttons
- 🟢 **P3** — Change the logout button under tools > quick links to reverse how its animated (better for backgrounds)
- 🟢 **P3** — Update the Dice roller to have the same glass effects
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

### ~~Targeting Button on the Attack Flow~~ ✓ Done (v2.49.85 → v2.49.87)
Shipped in three commits: v2.49.85 (server) added `target_combatant_ids` list support on `/attack` with per-target fresh attack + damage rolls and a new `auto_attack_targets` response/broadcast array. v2.49.86 (client wiring) extended `_targetBodyFields` on the sheet to emit the list when the canvas has 2+ targets currently selected. v2.49.87 (mobile picker) added multi-select via checkbox rows + a Confirm button to `_promptTargetPicker`, opt-out via `{allowMulti: false}` — the same modal handles desktop multi-target without canvas-double-clicks. Filed follow-ups: chat-card multi-target rendering, per-target uplift detection (Hex / Hunter's Mark / Colossus Slayer), per-target range check.

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

🔥 **IN PROGRESS** — plan: [`docs/plans/full-feature-automation.md`](docs/plans/full-feature-automation.md); live audit: [`docs/automation-coverage.md`](docs/automation-coverage.md). **Phases 0–6 ✅ done** (feature-use registry, on-hit riders, feature saves, temp-HP + roll bonuses, auras, movement + summons + the Phase 0 audit). **Coverage: 182 tracked / 55 announce-only of 239** (was ~60/156 at baseline). The engine primitives all exist; what's left is routing the announce-only tail through them + the two unstarted phases.

**Concrete next-session tasks** (each one PATCH-bump + harness test that asserts the *state change*, then refresh the audit doc's counts via the classifier):

- 🟡 **P2 — Phase 7: reactions breadth.** New reaction kinds on the existing reactions framework ([`docs/plans/reactions-automation.md`](docs/plans/reactions-automation.md)): Riposte (attack after a miss), Protective Field (reduce damage), Chronal Shift (reroll), make Restore Balance a real adv/disadv-cancel reaction. ~5 commits.
- 🟡 **P2 — Auras backlog (E).** `aura_of_warding` (resistance to *spell* damage — needs a "spell-damage resistance" concept the engine doesn't model yet, the bigger lift), `ancestral_protectors`, `unwavering_mark`, `scornful_rebuke` — fold into `_tick_auras` (the v2.99.448 `requires_condition` gate + v2.99.449 `buff` payload are the tools).
- 🟡 **P2 — On-hit / attack-roll backlog (B).** `assassinate` (advantage + auto-crit vs surprised — a new attack-roll-modifier mechanic, distinct from the damage riders done). The flat/dice once-per-turn rider shape (Genie's Wrath v2.99.450) and the server-resolved extra attack (Horde Breaker v2.99.451 / Dread Ambusher v2.99.452) are already proven for the rest.
- 🟢 **P3 — Buff / temp-HP tail (D/F).** `combat_inspiration`, `rallying_cry`, `blade_flourish`, `protective_spirit`, `grim_harvest`, `supreme_healing` — `_install_buff` / `_grant_temp_hp` retrofits.
- 🟢 **P3 — Movement tail (G).** `ascendant_step` / `stormborn` (fly via a speed/fly buff), `relentless_avenger`, `fancy_footwork`.
- 🟢 **P3 — Phase 8: higher-level subclass features (Lv 6/10/14/17/20).** Mostly composition on the now-built primitives; batch by class. The long tail.

The remaining ~30 announce-only rows are **archetype J** (narration-only-by-design: passive senses, language grants, passive damage-boosters that already ride other paths) — leave as-is; see the audit doc's "Notable announce-only backlog" section for the full split.
