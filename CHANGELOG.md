# Changelog

All notable changes to SimpleVTT are documented in this file.
Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) — Versioning: [SemVer](https://semver.org/spec/v2.0.0.html).

The current version is the topmost release section below.
Application version and database schema version are also published at runtime by `GET /version` and `GET /healthz`, and are defined as constants in [`app/version.py`](app/version.py).

---

## Instructions for AI agents updating this file

Read this section in full before modifying any version-related file. Follow it exactly.

### When to add a new entry

Add a new release section every time you make a user-visible, behavior-changing, or schema-changing edit. Pure refactors with no observable difference do **not** require an entry. If unsure, add one — extra entries are easier to live with than missing ones.

Group multiple in-flight edits under an `## [Unreleased]` section at the top until the user asks you to "cut a release", at which point you rename `[Unreleased]` → `[X.Y.Z] - YYYY-MM-DD` and create a fresh empty `[Unreleased]` block above it.

### How to bump `APP_VERSION` (semantic versioning)

The application version lives in [`app/version.py`](app/version.py) as `APP_VERSION = "MAJOR.MINOR.PATCH"`. Update it according to these rules:

- **MAJOR** — break a public contract: incompatible API changes, removed routes, removed config keys, breaking changes to the docker-compose stack, or any change requiring user action to upgrade beyond a normal redeploy.
- **MINOR** — new feature added in a backward-compatible way: new route, new optional config key, new template, new admin capability, etc.
- **PATCH** — backward-compatible bug fixes, security fixes, dependency bumps with no behavior change, copy/wording tweaks.

Bump exactly one component at a time. When MAJOR bumps, reset MINOR and PATCH to 0. When MINOR bumps, reset PATCH to 0.

### How to bump `SCHEMA_VERSION`

The schema version lives in [`app/version.py`](app/version.py) as `SCHEMA_VERSION = N` (an integer). Bump it by exactly **+1** the moment you make any change to `app/models.py` that alters the database schema:

- adding/removing a table
- adding/removing a column
- changing a column's type, default, nullable, unique, or index
- adding/removing a foreign key or constraint
- renaming any of the above

Do **not** bump `SCHEMA_VERSION` for changes that don't touch the schema (e.g., adding a method on a model class, editing a docstring). The schema version is independent of `APP_VERSION` — many app releases will leave it untouched. Every boot stamps the current value into the `schema_version` table, so the row history acts as a deployment log.

If a schema change is breaking (existing DBs need a real migration, not just `create_all`), the matching `APP_VERSION` bump must be MAJOR. For additive changes, append a new conditional ALTER block to `_apply_inline_migrations()` in `app/database.py` so existing deployments auto-upgrade on next boot.

### Required fields for every release entry

Each release section must include all five of these, in this order:

1. **Heading** — `## [X.Y.Z] - YYYY-MM-DD` (use today's date in UTC).
2. **Schema version line** — exactly `**Schema version:** N` where N is the value of `SCHEMA_VERSION` at the time of release. State this even if it didn't change.
3. **Commit summary** — one line, 10–15 words, imperative mood, no trailing period. Suitable for use as the GitHub commit subject. Prefix with `**Commit summary:**`.
4. **Description** — 2–4 sentences in plain prose explaining the user-facing impact, motivation, and any required operator action. Prefix with `**Description:**`.
5. **Categorized change list** — use any of these subsections that apply: `### Added`, `### Changed`, `### Deprecated`, `### Removed`, `### Fixed`, `### Security`, `### Schema`. Each bullet starts with a verb.

### Checklist before you finalize an entry

- [ ] `app/version.py` updated with the new `APP_VERSION` and (if changed) `SCHEMA_VERSION`.
- [ ] CHANGELOG.md has a new section at the top with all five required fields.
- [ ] If `SCHEMA_VERSION` bumped, the `### Schema` subsection lists every schema change AND `_apply_inline_migrations()` has a new conditional ALTER block.
- [ ] If the change is breaking, the description spells out the upgrade steps.
- [ ] Date is today's UTC date in `YYYY-MM-DD` format.
- [ ] Commit summary is between 10 and 15 words and reads as a verb phrase ("Add X", "Fix Y", "Refactor Z").
- [ ] You did not edit version numbers in any other file — `APP_VERSION` is the single source of truth and `app/main.py` reads it dynamically.

### Example template (copy this when adding a new entry)

````markdown
## [X.Y.Z] - YYYY-MM-DD

**Schema version:** N

**Commit summary:** Add per-campaign chat panel and persist chat history across sessions

**Description:** Players can now exchange in-character and out-of-character chat messages from the tabletop side panel. Messages are persisted to the database and replayed on reconnect. No operator action is needed beyond a redeploy; the chat table is created automatically on first boot.

### Added
- `ChatMessage` model and `/api/campaign/{id}/chat` endpoint.
- Chat panel below the dice roller with OOC/IC toggle.

### Schema
- New table `chat_messages` (id, campaign_id, user_id, body, kind, created_at).
- `SCHEMA_VERSION` bumped from N-1 to N.
````

(Replace `X.Y.Z`, `YYYY-MM-DD`, and `N` with actual values when you copy this.)

---

## [0.31.3] - 2026-05-10

**Schema version:** 21

**Commit summary:** Move Class Proficiencies below Features and cache class/race/subclass dropdown lists

**Description:** The Class Proficiencies fieldset now appears after Class, Subclass & Race Features in the character sheet sidebar. The class, subclass, and race dropdown lists are cached in `localStorage` for 24 hours so the three Open5e API calls are skipped on repeat sheet opens — only the first load (or a cache-miss after 24 h) hits the network.

### Changed
- Reordered fieldsets: Class, Subclass & Race Features now appears before Class Proficiencies
- `sheet.js`: added `fetchListCached()` wrapping `fetchList()` with a 24-hour `localStorage` cache keyed `simplevtt_classes_list`, `simplevtt_races_list`, and `simplevtt_subclasses_{slug}`
- Dropdown lists for class, race, and per-class subclasses are served from cache on subsequent opens; cache is written only when the API returns results, so a failed fetch never pollutes the cache

---

## [0.31.2] - 2026-05-10

**Schema version:** 21

**Commit summary:** Unify skill buttons and spell slot pips across full and mini character sheets

**Description:** Skill buttons on both the full D&D 5e sheet and the tabletop mini-sheet now share the same design: proficiency dot, skill name, ability abbreviation, and modifier, with a teal border for proficient skills and a gold border for expertise. Spell slot pips on both sheets now use a consistent convention — filled accent circle = available slot, hollow dim circle = spent slot — replacing the previous inconsistent and hard-to-read designs.

### Changed
- Full sheet skill buttons: border is now `2px solid accent` for proficient, `2px solid gold-mix` for expertise, default `1px solid border` otherwise
- Full sheet spell slot pips: flipped to available = filled accent, used = hollow dim (was reversed)
- Mini-sheet skills: replaced flat `mini-roll-row` layout with `mini-sk-btn` buttons matching the full sheet style (dot · name · ability · modifier); proficient and expert skills get a colored border
- Mini-sheet spell slot pips: updated to match full sheet — filled = available, hollow dim = used; pip size increased from 8px to 10px for clarity

---

## [0.31.1] - 2026-05-10

**Schema version:** 21

**Commit summary:** Merge tabletop mini-sheet HP tracker into unified four-column stat row

**Description:** The player drawer previously showed HP twice — once in a static three-column grid and again in a separate +/- control row. Both are now replaced by a single four-column row (HP | Temp | AC | Speed) where the HP and Temp cells embed the +/- step buttons inline for owners and GMs. No schema or API changes.

### Changed
- Replaced `mini-grid-3` (HP/AC/Speed) and the separate `mini-hp-row` with a single `mini-stat-row` grid (HP · Temp · AC · Speed)
- HP and Temp cells embed stacked +/− step buttons inline; buttons only render for character owners and GMs
- Removed now-unused CSS rules: `.mini-hp-row`, `.mini-hp-ctrl`, `.mini-temp-ctrl`, `.mini-hp-label`, `.mini-hp-val`
- Updated `_updateMiniHpDisplay` and `_miniHpStep` JS selectors to target `.mini-stat-row` instead of `.mini-hp-row` and `.mini-hp-display-*`

---

## [0.31.0] - 2026-05-10

**Schema version:** 21

**Commit summary:** Add Apply Healing button to spell roll-log cards with AOE charge tracking

**Description:** Spells with a healing expression now show a green **🩹 Apply Healing** button in the campaign roll-log card after casting. Any player in the campaign can click it; the server rolls the healing dice, applies the result to that player's character (capped at max HP), and broadcasts the outcome to all clients — the result row and mini-sheet HP both update live. AOE healing spells (e.g. Mass Cure Wounds) show a charge tracker `(0/6)` on the button; each user may claim once and the button locks once all charges are consumed. The spell data model gains `healing` (dice string) and `aoe_targets` (int) fields, exposed in the custom-spell form and auto-detected when importing from the Open5e browser. No schema change; no operator action needed.

### Added
- `healing` (dice string, e.g. `"3d8+5"`) and `aoe_targets` (int, default 1) fields on spell objects; preserved through the spell loader, custom-spell form, Open5e import, and the `cast_spell` broadcast payload.
- **Healing** and **AOE Targets** inputs in the custom spell panel on the character sheet.
- Auto-detection of healing dice and AOE target count from Open5e spell descriptions in `_fmt_spell()` (skips spells that already have a damage expression to avoid false matches on spells like Vampiric Touch).
- `POST /api/campaign/{id}/apply_healing` endpoint: validates campaign membership, enforces per-user claim limits, rolls dice server-side via `dice_mod.roll()`, patches `sheet.hp`, broadcasts `heal_applied`.
- In-memory `_heal_claims` dict in `tabletop_routes.py` (keyed by `cast_id`, 8-hour TTL, purged on each new healing cast).
- `_applyHealing()` and `_onHealApplied()` functions in `tabletop.js`; `heal_applied` case in the WebSocket dispatcher.
- `.spell-cast-heal-btn` (green tint), `.heal-charge-tracker`, and `.heal-result-row` CSS in `tabletop.html`.
- `window._updateMiniHpDisplay` exposed from `tabletop.html` so `tabletop.js` can update the player-drawer mini-sheet HP after healing.

---

## [0.30.4] - 2026-05-10

**Schema version:** 21

**Commit summary:** Enlarge HP numbers and move step buttons left with vertical stacking

**Description:** On both the full D&D 5e character sheet and the tabletop player-drawer mini-sheet, the current HP number is now two font sizes larger for easier reading at a glance. The +/− step buttons have been moved to the left of the HP and Temp HP values and are stacked vertically with + on top and − on the bottom. No schema change; no operator action needed.

### Changed
- `sheet_dnd5e.html`: HP input font-size increased from 30 px to 38 px (width 56 px → 70 px); Temp HP input from 15 px to 19 px (width 44 px → 52 px). +/− buttons now wrap in a `.hp-step-stack` column div placed to the left of each number.
- `tabletop.html`: `.mini-hp-val` font-size increased from 13 px to 17 px. +/− buttons wrapped in `.mini-hp-step-stack` column div placed left of the value; button font reduced slightly to 11 px to suit the compact stacked layout.

---

## [0.30.3] - 2026-05-10

**Schema version:** 21

**Commit summary:** Move AC display from header chip grid into the Inventory fieldset

**Description:** The AC chip has been removed from the top combat-stat grid on the D&D 5e character sheet. The three remaining stats (Speed, Init, Prof) are now laid out in a single row of equal-width chips. The AC value and its armor breakdown (`🛡 AC 16 = Chain Mail 16, Shield +2`) now live at the top of the Inventory fieldset, where it is directly adjacent to the equipped armor and shields that determine it. The hidden `ac` form input is preserved so the computed value continues to be saved with the sheet. No schema change; no operator action needed.

### Changed
- Top combat-stat grid reshaped from a 2×2 grid (AC / Speed / Init / Prof) to a single 3-chip row (Speed / Init / Prof).
- `#ac-breakdown-line` moved from below the character header into the Inventory fieldset header, prefixed with 🛡.
- `updateACDisplay()` format updated to `🛡 AC N = …` to match the new location.

---

## [0.30.2] - 2026-05-10

**Schema version:** 21

**Commit summary:** Enlarge mini-sheet rest controls and add HP/Temp HP step buttons

**Description:** In the tabletop player drawer, the hit dice tracker and Short/Long Rest buttons are now visually larger (bigger font, padding, and spacing) so they're easier to tap. Owners and GMs also get a new HP row below the combat stats grid with − and + step buttons for current HP and Temp HP. Clicking a step button immediately updates the display and PATCHes the character's `hp` object via the existing `/sheet-fields` endpoint (which now accepts the `hp` key). No schema change; no operator action needed.

### Added
- HP +/− and Temp HP +/− step buttons on the mini-sheet in the player drawer, visible to the character's owner and the GM.
- `"hp"` added to `_SHEET_PATCH_KEYS` so the lightweight PATCH endpoint can accept HP updates.
- `_miniHpStep()` JS function: clamps HP to `[0, max]`, temp to `≥ 0`, updates the DOM optimistically, then PATCHes the server.
- `_updateMiniHpDisplay()` helper shared between rest responses and the new step buttons — keeps the top grid readout and the +/− row in sync.

### Changed
- `.mini-rest-bar` padding increased from `5px 7px` to `7px 10px`; font-size from `11px` to `13px`.
- `.mini-rest-btn` padding increased from `2px 7px` to `4px 12px`; font-size from `10px` to `12px`; border-radius from `3px` to `4px`.

---

## [0.30.1] - 2026-05-10

**Schema version:** 21

**Commit summary:** Replace hardcoded dark-theme hex colors in D&D 5e sheet with CSS custom properties

**Description:** The D&D 5e character sheet contained roughly 200+ hardcoded hex colors in both its Jinja2 HTML and JavaScript `innerHTML` template strings, causing it to always render with dark-blue chrome regardless of the active theme. A semantic CSS variable bridge (`--s-*` properties scoped to `.sheet.dnd5e`) was added to map theme tokens, and all structural hex colors were replaced with `var(--s-*)` references. Intentional game-semantic colors (damage orange `#e8a`, attack cyan `#8cf`, spell purple `#a78bfa`, etc.) were left as-is. No operator action needed.

### Fixed
- Character sheet header, inputs, buttons, overlays, and roll-log cards now respect all eight themes (dark, midnight, dim, light, forest, bubblegum, oled, fire) instead of always rendering in dark-blue.
- Spell browser, item browser, attack rows, inventory rows, condition chips, proficiency dots, and rest buttons now use theme-aware colors.
- Remove (×) buttons, error states, and "Add to Sheet / Remove from Sheet" toggles all use CSS variable colors instead of hardcoded dark hex values.

---

## [0.30.0] - 2026-05-10

**Schema version:** 21

**Commit summary:** Add hit dice tracker plus Short and Long Rest actions to character sheet and Player drawer mini-sheet

**Description:** The HP block on the D&D 5e sheet now includes a **hit dice tracker** (current/max with ± buttons, plus the die size pulled from the class) and two action buttons — **⚡ Short Rest** and **💤 Long Rest**. Short Rest spends one hit die, rolls `1d{HD} + CON` client-side, heals up to max HP, decrements the hit-die counter, and (when in a campaign) logs the roll to the public roll log. Long Rest restores HP to max, clears Temp HP, recovers up to half max hit dice (RAW: `max(1, ⌊max/2⌋)`), and resets every spell-slot row's used pip count to 0. A matching mini version lives in the Player drawer of the tabletop: each character row now shows `🎲 HD x/y dN` and `⚡ Short` / `💤 Long` buttons that POST to a new `/api/campaign/{id}/character/{char_id}/rest` endpoint. The endpoint applies the same math server-side, persists to the DB, and broadcasts a `spell_slot_update` per restored slot level so any open sheet rerenders its pips. The mini bar also updates its own HP and HD numbers from the response without a page reload. Hit-dice state is stored under `sheet.hit_dice = {current, max}`; characters without prior values default to current=max=level. No operator action is needed beyond a redeploy.

### Added
- HP block on `sheet_dnd5e.html` gained a hit-dice row (`HD x/y dN` with ± step buttons), and two rest buttons under it. Hit-dice die size is read live from the existing `class_hit_die` field. Readonly sheets get hidden `hit_dice.current` / `hit_dice.max` inputs so non-owner viewers still serialize the values.
- Client-side Short Rest: rolls `1d{die}+CON` locally, heals (capped at max), decrements hit dice. When `CAMPAIGN_ID` is defined it also POSTs to `/roll` so the campaign log records it; on the standalone `/character/{id}/sheet` page it rolls silently.
- Client-side Long Rest: HP→max, Temp→0, hit dice +max(1, ⌊max/2⌋) capped at max, every `.ss-row`'s used pips reset via the existing `_ssSyncInputs` / `_ssRenderPips` hooks. Confirmation prompt before applying.
- `POST /api/campaign/{campaign_id}/character/{char_id}/rest` endpoint accepting `{type: "short" | "long"}`. Membership and ownership/GM checks, server-side dice roll via the existing `dice` module for short rest, returns the updated `hp` / `hit_dice` plus the rolled expression and breakdown for short rest. Long rest also broadcasts `spell_slot_update` for every level so other clients sync immediately.
- Mini hit-dice + rest bar on every Player-drawer character expansion. Owners and GMs see the buttons; spectators see only the HD readout. The mini view re-renders its HP cell and HD numbers from the API response after each rest.

### Changed
- HP block min-width raised from 155 px to 170 px to fit the HD line and rest buttons without forcing the combat-stat chips to wrap.

---

## [0.29.0] - 2026-05-10

**Schema version:** 21

**Commit summary:** Auto-derive attacks from equipped weapons and enforce equip-slot rules with conflict toasts

**Description:** Three connected sheet changes. **(1)** The Inventory fieldset moved up to sit immediately after the spells block, above Class Proficiencies and the Class/Subclass/Race Features panel — inventory is the section players touch most during play. **(2)** Weapon attacks are no longer added manually. The "+ Add as Attack" button in the Open5e item browser is gone, and the Attacks list now auto-populates from equipped weapons in the Inventory: equip a longsword and a "Longsword" attack appears with the right damage/range pulled from the item; unequip it and the attack vanishes. Auto-attacks render with a small "🛡 equipped" badge and have no remove button — to remove one you unequip the weapon. The custom-attack panel still exists for non-weapon attacks (breath weapons, monk strikes, etc.). **(3)** Equip-slot enforcement: at most one armor at a time, and the hand budget caps at 2 (1H weapon = 1 hand, shield = 1 hand, 2H weapon = 2 hands). Equipping something that exceeds the budget auto-unequips conflicts (oldest first) and shows a toast like "Unequipped Plate Armor to equip Studded Leather" — the player isn't blocked, just informed. The 2H/shield/dual-wield combinations the user requested are enforced: equipping a 2H weapon clears all hands; equipping a shield clears any 2H weapon and any second shield; equipping a third weapon when both hands are full unequips the oldest. Inventory items now carry stable `_uid` ids (lazily assigned to legacy items on next save) so attacks can reliably reference their source weapon across reorderings. No operator action beyond a redeploy.

### Added
- Weapon-specific fields on inventory items: `hands` (1 or 2), `versatile`, `damage`, `damage_type`, `range`, `properties`. The custom-add panel exposes all of these in a Weapon-row that appears only when the item type is "weapon". The Open5e import parser fills them automatically from the API's `damage_dice`, `damage_type`, `category`, and `properties` fields (parses "Two-Handed" / "Versatile" / "Ranged" / "Thrown").
- Stable `_uid` on every inventory item, generated when missing on load. Attacks created from equipped weapons carry the source `_uid` in `_from_weapon_uid` so unequip / delete / reorder doesn't break the link.
- `_enforceEquipSlots(item)` in the inventory IIFE: one armor cap; 2-hand budget; 2H weapons unequip everything else in hand; shields unequip 2H weapons and other shields; oldest 1H weapon makes room when both hands are full. Returns the list of auto-unequipped items.
- `_syncWeaponAttacks(equippedWeapons)` exposed by the attacks IIFE: adds an attack entry per equipped weapon (using its damage/range/properties/desc), removes entries whose source weapon is no longer equipped or no longer present. Called by the inventory IIFE after every equip toggle and item delete, plus once on initial render.
- Conflict toast: "Unequipped X, Y to equip Z." Uses `window.showToast` when available (campaign tabletop view) and falls back to `alert()` on the standalone sheet.

### Changed
- Inventory fieldset is now positioned above Class Proficiencies and the Class/Subclass/Race Features fieldset. The Notes fieldset stays at the bottom.
- The Open5e item browser detail panel no longer offers "+ Add as Attack". Weapons get a small italic note: "Weapons appear in your Attacks list automatically when equipped." The "+ Add to Inventory" path is unchanged.
- Auto-attack rows in the Attacks fieldset render with a tinted background, a small "🛡 equipped" pill in their header, and no × remove button. Strike still works the same. Custom attacks render exactly as before.
- Empty-state message in Attacks updated to "No attacks yet — equip a weapon in your Inventory to add one."

### Removed
- `window._addAttackFromBrowser` and `_itemToAttack()` in the item browser — both are no longer reachable now that the only way a weapon enters the Attacks list is via equip.

---

## [0.28.0] - 2026-05-10

**Schema version:** 21

**Commit summary:** Add per-user interface and font scale presets and remove HP number-input spinners

**Description:** Two ergonomics improvements. **(1)** The HP and Temp HP number inputs on the D&D 5e sheet no longer show the browser's up/down spinner arrows — the explicit ± step buttons added in 0.27.0 are now the supported way to adjust those values, and the duplicate native controls were getting in the way. **(2)** A new **Display scale** section in user settings exposes two knobs — *Interface scale* (75/85/100/110/125/150 %) which applies CSS `zoom` to scale the entire layout, and *Font scale* (85/100/110/125 %) which adjusts the root `font-size` so rem-based text grows alongside. Both default to 100 %, save to your account, and apply on every device. Phone-sized viewports (≤ 640 px) ignore both settings since the phone layout is already tuned for small screens. Two new columns (`users.ui_scale`, `users.font_scale`, both `FLOAT NOT NULL DEFAULT 1.0`) are added by the inline migration; no operator action needed beyond a redeploy.

### Added
- `users.ui_scale` and `users.font_scale` columns (Float, default 1.0) — schema v21.
- `POST /api/settings/scale` endpoint accepting `{ui_scale, font_scale}`. Server snaps incoming values to the closest allowed preset to prevent malformed sizes.
- "🔍 Display scale" section in user settings with two `<select>`s and a status line. Changes apply live (sets `--ui-scale` / `--font-scale` on `<html>`) and persist via the new API.
- Inline CSS variables stamped on `<html>` by `base.html` (`--ui-scale`, `--font-scale`) using the logged-in user's saved values; safely defaults to 1.0 when `user` is unavailable (login/register pages).
- Global CSS rules in `style.css`: `body { zoom: var(--ui-scale, 1); }` and `html { font-size: calc(100% * var(--font-scale, 1)); }`. A `@media (max-width: 640px)` block resets both to 1 so phones keep the tuned layout.

### Fixed
- Browser spinner arrows on the HP and Temp HP number inputs are now suppressed in WebKit/Chromium and Firefox via per-input `appearance: textfield` and `::-webkit-{outer,inner}-spin-button` overrides.

### Schema
- Added `users.ui_scale` and `users.font_scale` columns. Migration block in `_apply_inline_migrations()` adds them on first boot of 0.28.0.

---

## [0.27.1] - 2026-05-10

**Schema version:** 20

**Commit summary:** Fix Hide Unprepared button missing on standalone character sheet pages

**Description:** The "👁 Showing all / 🙈 Hiding unprepared" toggle on the D&D 5e Spells fieldset wasn't appearing on the standalone character page (`/character/{id}/sheet`). The button's visibility is decided by `_classVal()`, which read the class `<select>`'s `.value` — but that select is populated **asynchronously** by `sheet.js` after fetching the Open5e classes list, so when the Spells IIFE ran synchronously at page load, the select was still empty and the button stayed hidden. `_classVal()` now falls back to the `data-current` attribute (which the server stamps with the saved class slug at render time, so it's available immediately). Readonly sheets also gained a hidden `<input name="class">` so non-owner viewers can use the filter, and `_onClassLevelChange()` now also re-renders the spell list so swapping classes mid-session refreshes the button's visibility without a page reload.

### Fixed
- `_classVal()` reads the class slug from `data-current` when the dropdown's value is empty (i.e. before the async Open5e classes fetch completes). Restores the Hide Unprepared button on the standalone character sheet and any other view where the class select is async-populated.
- Readonly sheets now ship a hidden `<input name="class">` so spellcasting-aware UI (Hide Unprepared button, spell-slot pip rendering, info bar) works for viewers who don't own the character.
- Changing class via the dropdown now also re-renders the spell list, so the Hide Unprepared button appears/disappears immediately for prepared-caster swaps without needing a reload.

---

## [0.27.0] - 2026-05-10

**Schema version:** 20

**Commit summary:** Add currency tracker, surface AC breakdown on header card, add HP step buttons

**Description:** Three sheet ergonomics improvements. **(1)** A gold-biased currency tracker now lives at the top of the Inventory section — five fields (CP, SP, EP, GP, PP) with GP visually emphasized (larger, gold-tinted, prominent), plus a live "≈ N gp" total computed from standard 5e conversions (`cp/100 + sp/10 + ep/2 + gp + pp×10`). Saved as `sheet.currency.{cp,sp,ep,gp,pp}`. **(2)** The Base AC editor + AC breakdown have moved out of the Inventory bar. Base AC is now an input in the character Edit panel alongside Class/Level/Max HP/Speed, and a small italic breakdown line ("AC 20 = Plate 18 + Dex 0, Shield +2") appears directly under the HP / AC / Speed / Init / Prof header row so the calculation is always visible without opening Inventory. **(3)** The HP and Temp HP fields gained +/- step buttons; clicking adjusts by 1, holding Shift adjusts by 5 (HP can drop to 0 or below; Temp HP clamps at 0). All three are no-op for read-only sheets so non-owners still see clean numbers without controls.

### Added
- Currency tracker fieldset at the top of Inventory with per-currency input cells and a live gold-equivalent total. GP cell uses a gold gradient and bumped font for the "biased" feel.
- `Base AC` input in the existing Edit panel (replaces the inventory-section input). Readonly sheets still serialize `base_ac` via a hidden field.
- `#ac-breakdown-line` under the header HP/AC/Speed/Init/Prof row showing "AC N = …" — the breakdown updates live when Base AC, DEX, or equipped items change.
- `±` step buttons flanking the HP current and Temp HP inputs. Shift-click multiplies by 5. Buttons fire `input`/`change` events so any downstream auto-save logic sees the update.

### Changed
- Inventory header bar now contains the currency tracker + total weight. The Base AC input and the AC breakdown line that lived there in 0.24.0–0.26.0 are gone.
- `#ac-breakdown` element renamed to `#ac-breakdown-line` and moved into the character header. The inventory framework JS now references the new id.

---

## [0.26.0] - 2026-05-10

**Schema version:** 20

**Commit summary:** Add collapsible sheet sections, persist Hide Unprepared toggle, and hide the legacy Features field

**Description:** Four sections of the D&D 5e character sheet — Class Proficiencies, Class/Subclass/Race Features, Inventory, and Notes — can now be collapsed by clicking their legend (a chevron rotates to indicate state). Open/closed state is persisted per-character in `localStorage`, so opening the same sheet again restores your last layout. The legacy free-text Features field (separate from the auto-filled Class/Subclass/Race Features fieldset) is hidden from the UI but still round-trips through the form so existing data isn't lost. The Spells fieldset's "Hide Unprepared" button now uses an explicit eye-open / eye-closed (see-no-evil) icon pair, persists its state per-character in `localStorage`, and is available to readonly viewers (it's a purely visual filter).

### Added
- `fieldset.collapsible` CSS class plus a `.fs-chevron` indicator. Collapsing a section hides every child except the `<legend>`. Click handlers ignore button/anchor/input clicks inside the legend so the existing in-legend tools (`↻ Sync`, `🔍 Browse Items`, `+ Custom`) still work.
- Per-character persistence keys: `simplevtt_collapse_{char_id}_{section_key}` (collapse state) and `simplevtt_hide_unprep_{char_id}` (Hide Unprepared toggle).
- Notes is now wrapped in a proper `<fieldset>` (was a plain `<label>`) so it can collapse the same way as the others.

### Changed
- "Hide Unprepared" button: label switched to `👁 Showing all` ↔ `🙈 Hiding unprepared`, visible regardless of readonly status, and remembered across reloads. The button also moved out of the `{% if can_edit %}` block so non-owner viewers can filter their view too.
- The legacy `<label>Features</label>` block is now `display:none`. Existing values still flow through the form on save so no data is dropped; the auto-filled Class/Subclass/Race Features fieldset remains the canonical place to view that information.

---

## [0.25.2] - 2026-05-10

**Schema version:** 20

**Commit summary:** Fix imported armor showing zero AC and ignore negative DEX in heavy armor

**Description:** Two bugs in the AC modifier framework. **(1)** The `/api/open5e/items` proxy was reading `ac_base`/`ac` from Open5e armor objects, but Open5e v1's armor schema actually returns AC under the `armor_class` field (a string like "16" or "11 + Dex modifier (max 2)"). Every imported armor was therefore landing in the inventory with `ac_value: 0`, so equipping it dropped the effective AC instead of raising it. The proxy now reads `armor_class`, parses the leading integer for `ac`, and passes the original string through as `ac_string` for the detail panel. It also exposes `stealth_disadvantage` and `strength_requirement`. **(2)** The client-side AC computation was applying a negative DEX modifier inside heavy armor (e.g. DEX 8 wearing plate would lose 1 AC). Per RAW, heavy armor ignores DEX entirely — the math now floors at 0 for heavy armor regardless of DEX sign. **Note for existing characters:** items imported under 0.25.0–0.25.1 still have `ac_value: 0` saved on their sheet; remove and re-import them (or edit `ac_value` via the Custom panel) to pick up the correct value.

### Fixed
- `/api/open5e/items` proxy now reads `armor_class` from Open5e v1 armor results and parses the leading integer into the `ac` field, so imported armor lands in the inventory with the correct base AC.
- Heavy armor no longer applies a negative DEX modifier to AC; DEX is ignored entirely as the rules require. Light and medium armor still use full DEX / DEX-cap-2 respectively.

### Added
- Open5e armor results now expose `stealth_disadvantage` (bool) and `strength_requirement` (string) on the proxied response so the detail panel can grow them later.

---

## [0.25.1] - 2026-05-10

**Schema version:** 20

**Commit summary:** Filter weapons and armor in the item browser to a character's class proficiencies

**Description:** The Item Browser overlay (Browse Items on the Inventory and Attacks fieldsets) now defaults to showing only weapons and armor a character is proficient with, based on their D&D 5e class. A new "Proficient only" checkbox in the overlay header controls the filter — untick it to see the full Open5e catalog. The Magic Items tab is unaffected (magic items aren't class-restricted) and visually dims the toggle. A small italic banner above the list reports how many items were hidden so it's clear the filter is active. The proficiency map is the standard PHB list (e.g. wizards see daggers/darts/slings/quarterstaff/light crossbow even though they have no `simple/martial` proficiency; rogues see hand crossbows, longswords, rapiers, and shortswords on top of simple weapons; clerics see light + medium + shields). Unknown class slugs fall through to "no filter" so non-PHB classes still see everything. The list re-renders instantly when you toggle the checkbox or change class — no extra request to Open5e.

### Added
- `CLASS_PROFS` map and `_isProficient()` filter inside the Item Browser IIFE in `sheet_dnd5e.html`. Covers all 12 PHB classes plus artificer.
- "Proficient only" checkbox + class-name hint in the overlay header. Toggling it re-renders the list locally; changing the character's class while the overlay is open also refreshes the filter.
- "Hiding N non-proficient items" banner above the list when filtered, plus an explanatory empty-state when every result is hidden.

---

## [0.25.0] - 2026-05-10

**Schema version:** 20

**Commit summary:** Add structured Attacks framework with strike roll-log card and Open5e item browser

**Description:** This is **Part 2** of the inventory/attacks effort. The freeform "Name | bonus | damage" attacks textarea on the D&D 5e sheet is replaced with a structured Attacks fieldset modelled on the Spells fieldset: name, attack bonus, damage dice + type, range, optional save DC + ability, and description, with a custom-add panel and a per-row 🗡 Strike button. Striking posts to a new `/api/campaign/{id}/attack` endpoint that rolls the attack and damage server-side and broadcasts a `weapon_attack` WebSocket message that all clients render as a peach-bordered attack card in the roll log. Save-based attacks (e.g. Dragon's Breath) skip the d20 to-hit and instead surface a "📋 Prompt save" button that reuses the existing roll-request framework — each player rolls their own save and the result appends to the originating attack card with ✓/✗ markers, exactly like spell-cast saves. A new shared **Item Browser** overlay (a single proxy to `api.open5e.com/v1/{weapons|armor|magicitems}`) is reachable from both the Inventory and Attacks fieldsets — picking a weapon offers "+ Add to Inventory" and "+ Add as Attack" buttons; armor and magic items add only to inventory and pre-populate AC fields where applicable. The Player drawer also gains a mini Attacks section with the same Strike action. Legacy pipe-format attacks load and re-save as the structured form. No operator action is needed beyond a redeploy.

### Added
- Structured **Attacks** fieldset on `sheet_dnd5e.html` with custom-add panel: name, range, attack bonus, damage dice, damage type, save DC + save ability, description, and a 🗡 Strike button per row.
- `POST /api/campaign/{id}/attack` endpoint that validates campaign membership and character ownership, rolls the to-hit (`1d20 + attack_bonus`) and damage (the dice expression) server-side, and broadcasts a `weapon_attack` WS message. Save-based attacks skip the to-hit roll and carry `save_dc` + `save_ability` for the client to prompt.
- `appendWeaponAttack(d)` in `tabletop.js` plus matching CSS — an attack card with caster avatar, attack name, to-hit total + breakdown, damage total + type + breakdown, optional description, and (for save attacks) a 📋 Prompt save button that posts a roll-request and correlates returning saves back onto the same card with ✓/✗.
- Mini Attacks section in the tabletop Player drawer for D&D 5e characters: per-attack chip row with bonus/damage/save tags and a 🗡 Strike button hitting the same endpoint.
- New `GET /api/open5e/items?type=weapons|armor|magicitems&search=…` proxy to `api.open5e.com/v1/`. Always proxies (no local cache yet) so it works without re-running the local sync.
- Shared **Item Browser** overlay reachable from both the Inventory (`🔍 Browse Items`) and Attacks (`🔍 Browse Items`) fieldsets, with type filter chips, search, and a detail panel offering `+ Add to Inventory` (always) and `+ Add as Attack` (weapons only).
- Open5e weapon → attack parsing fills in damage dice, damage type, range (Melee vs. Ranged inferred from category/properties), and properties description. Open5e armor → inventory parsing fills in `ac_value` and `armor_type` (light/medium/heavy inferred from category) so equipping the imported armor immediately recomputes effective AC.

### Changed
- `app/static/sheet.js` form serializer now parses `attacks` as JSON when the textarea begins with `[`, falling back to the legacy pipe format (which now writes `attack_bonus` instead of `bonus` for forward compat with the new card).
- The Player-drawer mini-sheet attacks list tolerates both `attack_bonus` (new) and `bonus` (legacy) field names so existing characters render correctly without re-saving.

---

## [0.24.0] - 2026-05-10

**Schema version:** 20

**Commit summary:** Replace freeform inventory textarea with structured items list and equipment-driven AC modifier framework

**Description:** The D&D 5e character sheet's Inventory section is now a structured list mirroring the Spells fieldset. Each item has a type (gear/weapon/armor/shield/tool/consumable), quantity, weight, optional description, and — for equippable items — an equip checkbox and optional AC modifier (armor base AC, shield AC bonus, or generic AC bonus for trinkets like Ring of Protection). The AC card on the sheet header is now derived: effective AC = (best equipped armor's base + DEX capped by armor type, or `base_ac` if unarmored) + sum of equipped shield/misc AC bonuses. A new `base_ac` field stores the unarmored value separately so equipping/unequipping armor produces the right effective AC. A breakdown line under "Base AC" explains how the displayed AC was computed (e.g. `= Plate 18 + Shield +2`). Existing characters' AC values migrate seamlessly: when no items are equipped, effective AC equals the previously stored `ac`. Legacy newline-style inventory strings are still accepted on save. This is **Part 1** of a larger inventory/attacks effort — Part 2 will add a structured Attacks framework with a roll-log "strike" card, plus an Open5e weapon/armor/magic-item browser. No operator action is needed beyond a redeploy.

### Added
- Structured **Inventory** fieldset on `sheet_dnd5e.html` with: per-item type select, qty, weight, equip toggle, expand/details, and a `+ Custom` panel mirroring the Spells custom-add UX.
- **Modifier sub-framework** for AC: `ac_value` on armor (replaces base AC, with DEX capped by `armor_type` ∈ light/medium/heavy), `ac_value` on shields (additive bonus, default +2), and `ac_bonus` on miscellaneous equippable items (additive when equipped). Recomputes live as items are equipped/unequipped or DEX changes.
- New `sheet.base_ac` field — the unarmored AC the user types, persisted alongside the computed `sheet.ac`. Default migrates from existing `sheet.ac` when missing so legacy characters render unchanged.
- `#ac-breakdown` summary line under Base AC showing how the effective AC was assembled (e.g. `= Plate 18 + Shield +2`).
- Total inventory weight summary alongside the Base AC bar.

### Changed
- AC card on the sheet header is now a derived display (read-only). The user-editable knob lives in the inventory section as **Base AC** and is recomputed continuously.
- Form serialization in `app/static/sheet.js` now parses `inventory` as JSON when the textarea begins with `[`, falling back to the legacy newline format for backward compatibility.

---

## [0.23.0] - 2026-05-10

**Schema version:** 20

**Commit summary:** Hide map on phones to show only the side drawer and stop top-bar clickables from line-wrapping

**Description:** On phone-sized viewports (≤ 640 px wide) the tabletop now hides the map/canvas pane entirely and renders the side drawer at full width with its tab bar at the top, so all interaction happens through the existing tabs (Roll Log, Player, Battle, Settings, GM Tools). iPads and larger screens are unaffected. The campaign top bar also now wraps the action group as a whole instead of allowing individual button labels (e.g. "▶ Start session", "⚙ Settings") to break across lines. No operator action is needed beyond a redeploy.

### Added
- Phone-only media query (`max-width: 640px`) in `tabletop.html` that hides `.map-pane`, expands `.drawer-sidebar` to fill the viewport, drops the slide-open animation, and hides the open-arrow and pin buttons.
- Drawer init now auto-opens the first tab on phones so the panel area is never blank when the map is hidden.

### Changed
- Campaign top bar now uses dedicated CSS classes (`tt-topbar`, `tt-topbar-actions`, `tt-topbar-form`, etc.) with `flex-wrap: wrap` on the row and `white-space: nowrap` on every clickable button/link, so labels like "Start session" stay on one line and the whole action group wraps as a unit on narrow screens.

---

## [0.22.0] - 2026-05-10

**Schema version:** 20

**Commit summary:** Tighten Player tab to owned characters and add ability-labelled rolls plus mini spells panel

**Description:** The tabletop Player tab now strictly shows characters the viewing user owns — GMs no longer see every character there (the Battle drawer remains the GM-wide view). Each ability check and saving throw button on the mini-sheet now shows the ability abbreviation alongside the modifier so the roll target is unambiguous at a glance. A new miniature spells section mirrors the D&D 5e sheet's spell list (with slot pips and a 🪄 Cast button) directly inside the Player drawer, omitting the spell browser and custom-spell creator and hiding unprepared spells for prepared casters (cleric, druid, paladin, wizard, artificer). No operator action is needed beyond a redeploy.

### Added
- Mini spells section in the Player drawer for D&D 5e characters: per-level spell rows with damage/save/concentration/ritual indicators, a 🪄 Cast button posting to `/api/campaign/{id}/cast_spell`, and slot pip rows that update optimistically and stay in sync via the existing `spell_slot_update` broadcast.
- Ability label and modifier rendered inside each Check/Save button on the mini-sheet (e.g. `STR +2`).

### Changed
- Player drawer now lists only characters whose `owner_user_id` matches the viewing user, including for GMs. Use the Battle drawer for the GM-wide view.
- Prepared casters (cleric, druid, paladin, wizard, artificer) hide unprepared leveled spells in the mini spells section automatically; cantrips remain visible.

---

## [0.21.0] - 2026-05-10

**Schema version:** 20

**Commit summary:** Replace per-spell damage and save buttons with a single Cast button driving roll-log spell cards

**Description:** Each D&D 5e spell row now shows one **🪄 Cast** button instead of separate damage/save buttons. Casting consumes the matching spell slot server-side (cantrips are free) and posts a rich spell-cast card to the roll log containing the spell description plus action buttons. Anyone can press the damage button — they're shown a token picker so a GM can attribute the roll to whichever NPC/PC token they want. The save button uses the existing roll-requests framework to prompt all players for their saving throw, and incoming responses are appended to the spell card with pass/fail markers. When a slot is empty the cast is rejected with a transient toast (no roll-log spam). All schema-free; no operator action needed beyond a redeploy.

### Added
- `POST /api/campaign/{id}/cast_spell` endpoint that validates membership and slot availability, decrements the slot in the character sheet, and broadcasts a `spell_cast` WebSocket message (plus a `spell_slot_update` so other open sheets stay in sync).
- Spell-cast cards in the roll log: caster avatar/name, slot used, full spell description, optional save-prompt button, and a damage roll button visible to all clients.
- Token picker popup that lets the clicker choose which character/token rolls the spell damage. GMs see every map-placed character; players see their own.
- `showToast(msg, kind)` helper exposed on `window` for transient overlay notifications. Used for "no spell slot available" feedback among other things.
- Live `spell_slot_update` propagation: open D&D 5e sheets re-render their slot pips when the matching character casts a spell from another client.

### Changed
- D&D 5e spell rows in the character sheet replace the separate `🎲 damage` and `🎲 SAVE save` buttons with a single `🪄 Cast` button. The damage and save metadata are still shown as labels next to the button.
- Casting now decrements spell slots automatically. The pip row updates optimistically on click and reverts if the server rejects the cast.

---

## [0.20.0] - 2026-05-09

**Schema version:** 20

**Commit summary:** Add themes, fantasy fonts, roll requests, concentration tracking, and token templates

**Description:** A large batch of features accumulated since v0.10.0. Highlights include a fully theme-aware tabletop (all hardcoded dark-mode colours replaced with CSS custom properties so all eight themes work on the tabletop page), eight new themes including OLED and five fantasy parchment/tavern themes, three optional OFL-licensed fantasy display fonts with player-selectable preference and a GM-level campaign font override, a GM roll-request framework that lets the GM post prompted rolls to the log that players click to auto-resolve against their character sheet, and a concentration spell tracker integrated with the initiative turn order. Standalone characters (not tied to a campaign) are now supported. All schema changes are additive and applied automatically on first boot with no operator action needed beyond a redeploy.

### Added
- **OLED dark theme** — pure-black (`#000000`) background variant for pixel-off savings on OLED screens.
- **Five fantasy themes** — Hobbiton (warm parchment), Hearthstone (tavern dark), Mosswood (sage green parchment), Inkwell (aged manuscript), and Forge (hammered copper dark). Each theme ships with computed `--theme-*` tokens and an optional SVG paper-grain / candle-glow overlay (`sheet-fantasy.css`).
- **Display font system** — three OFL-licensed fonts loaded from Google Fonts: *Lora* (elegant serif), *Cormorant Garamond* (ornate fantasy), *IM Fell English* (old book). Players choose in Settings → Display font; GMs can override per-campaign in Campaign Settings → GM font override. Applied via `data-font` on `<html>` without a page reload.
- **Roll request framework** — GMs can post a prompted roll card to the roll log (saving throw, ability check, skill check, or custom expression). Each card shows a character dropdown; clicking Roll resolves the stat modifier server-side from the character's D&D 5e sheet, rolls, appends a pass/fail note if a DC is set, and broadcasts the result.
- **Concentration spell tracker** — GMs or character owners can set a concentration spell on any character (spell name, optional round count, notes). A 🧿 indicator appears on the character row in the Player tab and a full badge with controls shows in the expanded sheet. The GM's Next ▶ button in the battle tracker automatically ticks the round count for the current combatant; at 0 the effect ends and a WebSocket event notifies all clients.
- **Token templates** — reusable NPC/monster tokens with a pre-filled sheet that GMs can place on the map without building a full character record.
- **Standalone characters** — characters no longer require a campaign; `characters.campaign_id` is nullable so characters can exist independently.
- **Theme CSS computed variables** — `--surface-hover`, `--accent-bg`, `--accent-bg2`, `--accent-bg-hover`, `--accent-border` added to `:root` using `color-mix()` so they cascade correctly to every theme automatically.
- **Per-user theme persistence** — `users.theme` column stores the chosen theme across sessions (schema v12).
- **Roll-log colours** — `campaign_memberships.color` and `campaigns.gm_color` allow per-member highlight colours in the roll log (schema v13). Characters have their own `characters.color` column (schema v14).
- **Tab tint colours** — `campaigns.gm_tab_color` tints the GM Tools tab (schema v15); `users.battle_tab_color` and `users.player_tab_color` tint the Battle and Player tabs per-user (schema v16).
- **Token controller** — `tokens.controller_user_id` lets the GM assign a token to a specific player who can then drag it independently (schema v8, recorded here).
- **Playlist audio metadata** — `playlist_tracks` gains `track_artist`, `track_album`, `track_genre`, `track_year` columns for richer now-playing display (schema v7, recorded here).
- **Playlist categories** — `playlists.category` (music / sfx / environment) and `user_audio_category_prefs` table for per-category volume preferences (schema v9, recorded here).

### Changed
- **Tabletop page is now fully theme-aware** — every hardcoded hex colour in `tabletop.html` (panels, drawer, roll cards, initiative tracker, token tracker, music drawer, toast, etc.) replaced with CSS custom properties. Tab tint `color-mix()` fallback backgrounds also updated.
- **Drawer tab bar** minimum width corrected to 430 px so the GM Tools tab no longer wraps.
- **Roll log redesigned** as styled cards with avatar, colour-coded visibility border, large total, and monospace breakdown.

### Fixed
- `ConcentrationEffect` and `RollRequest` models were absent from `models.py` causing an `ImportError` on startup; both classes restored.
- `"oled"` removed from `VALID_THEMES` inadvertently during fantasy-theme addition; restored.

### Schema
- v11 — `characters.campaign_id` made nullable (standalone characters). SQLite requires table recreation; PostgreSQL uses `DROP NOT NULL`.
- v12 — `users.theme VARCHAR(20) NOT NULL DEFAULT 'dark'` added.
- v13 — `campaign_memberships.color VARCHAR(20)` and `campaigns.gm_color VARCHAR(20)` added.
- v14 — `characters.color VARCHAR(20)` added.
- v15 — `campaigns.gm_tab_color VARCHAR(20)` added.
- v16 — `users.battle_tab_color VARCHAR(20)` and `users.player_tab_color VARCHAR(20)` added.
- v17 — New table `roll_requests` (id, campaign_id, created_by_user_id, label, base_expression, stat_key, dc, visibility, created_at).
- v18 — New table `concentration_effects` (id, campaign_id, character_id, spell_name, rounds_remaining, notes, created_at) with unique constraint on (campaign_id, character_id).
- v19 — `users.font_preference VARCHAR(30)` added.
- v20 — `campaigns.font_override VARCHAR(30)` added.
- `SCHEMA_VERSION` bumped from 10 to 20.

---

## [0.8.0] - 2026-05-04

**Schema version:** 6

**Commit summary:** Add mini character sheets, roll toasts, proficiency highlights, and collapsible sidebar

**Description:** The Player sidebar tab has been significantly upgraded: players now see only their own characters, can favourite them (persisted in localStorage), and can expand each character inline to a compact mini sheet. The mini sheet shows HP/AC/Speed, all six abilities with Check and Save roll buttons, and all 18 skills with roll buttons — all wired into the existing roll log and WebSocket broadcast. A roll toast container at the bottom-centre of the screen shows each player their own roll results as they come in, auto-dismissing after 10 seconds. The sidebar itself now fully collapses to zero width when unpinned, giving the map the full viewport. No operator action or database migration is required.

### Added
- Roll toast popup fixed to the bottom-centre of the tabletop: shows expression, total, and breakdown for the current player's own rolls; auto-dismisses after 10 seconds; click to dismiss early.
- Expandable inline mini character sheet per character card in the Player tab: HP / AC / Speed combat stats, a 6-column ability grid with Check and Save roll buttons, and a 2-column skill grid with roll buttons for all 18 skills.
- Favourite toggle on character cards in the Player tab; favourites float to the top of the list and preference is persisted per-campaign in localStorage.
- Proficiency column highlight on ability names in the mini sheet: a teal dot and teal name colour mark abilities that have a save proficiency.
- Skill proficiency colouring in the mini sheet: teal name = proficient, gold name = expertise; linked ability abbreviation shown on each skill row.

### Changed
- "Players" sidebar tab renamed to "Player".
- Player tab now filters characters to only show those owned by the current player; GMs continue to see all characters.
- Sidebar collapses fully to zero width when an active tab is clicked while the sidebar is unpinned; a floating ☰ button re-opens it so the map can use the full viewport width.
- Mini sheet Abilities & Saves section restructured from a vertical list to a compact 6-column grid: ability name and score span the top, with Check and Save roll buttons stacked below each column.
- Mini sheet skills section changed from a single column to a two-column layout.

---

## [0.7.0] - 2026-05-02

**Schema version:** 6

**Commit summary:** Gate the tabletop behind a GM-controlled session start so players can't peek before play

**Description:** Campaigns now have an explicit Open/Closed lifecycle. The GM (or admin) hits ▶ Start session from the lobby card or the tabletop header to open the tabletop to players; ⏹ End session closes it again. While a session is closed, non-GM members who navigate to the campaign URL see a "Waiting for the GM to start the session" page that auto-redirects them in the moment the GM hits Start (via the existing per-campaign WebSocket, with a 10-second polling fallback). Players already inside the tabletop when the GM ends the session are bounced back to the lobby. GMs and admins always have access regardless — they need to set up maps, characters, and audio before opening the doors. Lobby cards now show a Live/Closed (GM view) or Live/Waiting (player view) badge so everyone knows the state at a glance. Existing campaigns auto-migrate to `session_active=False` so deploying this version doesn't suddenly expose any tabletops; GMs need to Start them.

### Added
- `Campaign.session_active` (boolean, default False) and `Campaign.session_started_at` (DateTime nullable) columns.
- `POST /campaign/{id}/session/start` and `POST /campaign/{id}/session/end` endpoints, GM-only.
- `session_waiting.html` template with auto-redirect via WebSocket + 10s polling fallback.
- `session_started` and `session_ended` WebSocket message types.
- ▶ Start session / ⏹ End session buttons in the lobby card body and the tabletop header.
- Live/Closed/Waiting status badges on lobby cards.

### Changed
- `campaign_view` returns the waiting page for non-GM members when `session_active=False` instead of letting them in.
- `tabletop.js` redirects non-GM clients to the lobby when it receives `session_ended`.

### Schema
- `campaigns.session_active BOOLEAN NOT NULL DEFAULT FALSE` — added.
- `campaigns.session_started_at TIMESTAMP NULL` — added.
- `SCHEMA_VERSION` bumped from 5 to 6.

### Notes
- GMs can re-Start an already-active session — it's idempotent and just refreshes `session_started_at`. Useful if WebSocket clients drifted out of state.
- Admins are treated as GMs for session control in any campaign, matching the existing pattern for token / sheet / audio permissions.
- Future: a per-campaign "session ends in 5 minutes" warning broadcast would be a nice polish; not included in this release.

---

## [0.6.0] - 2026-05-02

**Schema version:** 5

**Commit summary:** Add user settings page with per-track volume and synchronize audio playback across all clients

**Description:** Players and GMs now hear the same point in every track. The server records a UTC timestamp the moment the GM hits Play and broadcasts it with each `audio_play` event; clients seek their `<audio>` element to the matching offset and run a 5-second drift-correction loop so a tab that was throttled in the background snaps back to the right position. A new `/settings` page in the top navigation lists every track in every campaign the user can see, with a slider per track that persists server-side as a per-track volume override; the effective playback volume is master × per-track. The tabletop sound panel also exposes a "this track" slider that appears whenever something is playing, plus a ⟳ Resync button anyone can use if they suspect drift. Existing PostgreSQL deployments will auto-migrate on first boot via additive ALTER TABLE statements; the new `user_audio_preferences` table is created automatically.

### Added
- `Campaign.now_playing_started_at` (DateTime nullable) — server timestamp used for client-side time sync.
- `UserAudioPreference` table (user_id, track_id, volume) for per-user-per-track volume overrides.
- `app/routes/user_routes.py` + `/settings` page listing all per-track overrides grouped by campaign and playlist.
- `GET /api/audio/preferences` and `POST /api/audio/preferences/{track_id}` endpoints.
- `POST /campaign/{id}/audio/resync` endpoint that re-broadcasts the current playback state on demand.
- "This track" volume slider in the tabletop sound panel (visible only while audio is playing).
- ⟳ Resync button in the sound panel.
- "Settings" link in the top navigation.
- Drift-correction loop in `audio.js` that snaps playback to the expected position if it drifts more than 0.75 s.

### Changed
- `audio_play` WebSocket payload now includes `started_at_ms` (UTC epoch) so all clients can compute the same offset.
- Tabletop view passes `now_playing_started_at_ms` to the template so reconnecting clients sync immediately on first paint.
- Effective `<audio>` volume is now `master × per-track`. Master volume continues to live in localStorage; per-track overrides persist server-side.

### Schema
- `campaigns.now_playing_started_at TIMESTAMP NULL` — added.
- New table `user_audio_preferences` (id, user_id, track_id, volume, updated_at) with unique (user_id, track_id).
- `SCHEMA_VERSION` bumped from 4 to 5.

### Notes
- Time sync depends on the player's clock being roughly correct (no NTP drift > a few seconds). Browsers and OSes generally are; if a client's wall clock is wildly off, the resync interval will keep yanking them, which is the right behavior — just less pleasant. A future "audio_sync" handshake on connect could measure the round-trip and correct for it; for ambient music this is overkill.
- Per-track override of `null` means "use 100%". A user can reset an override from `/settings` by clicking the Reset button.

---

## [0.5.0] - 2026-05-01

**Schema version:** 4

**Commit summary:** Add per-campaign audio playlists with GM playback controls and player volume panel

**Description:** GMs can now upload mp3/ogg/wav/m4a tracks into named playlists per campaign and play them to all connected players in real time. Playback state is persisted on the Campaign row so reconnecting players resume the current track. Tracks auto-advance through the playlist when one ends, with an optional loop-at-end setting. Players get a sound panel with a volume slider, mute toggle, and "click to enable audio" prompt for browsers that block autoplay; volume and mute are persisted per-browser via localStorage. The first incoming `audio_play` for a player who hasn't interacted with the page yet may be blocked by the browser — they'll see the "click to enable" button and one click unblocks all subsequent tracks. Existing PostgreSQL deployments will auto-migrate on first boot via additive ALTER TABLEs.

### Added
- `Playlist` and `PlaylistTrack` models; `/static/uploads/audio/` storage directory.
- `Campaign.now_playing_track_id` (nullable INTEGER FK to playlist_tracks) and `Campaign.now_playing_loop` (boolean) for persisted playback state.
- `app/routes/audio_routes.py` exposing `/campaign/{id}/playlists`, `/campaign/{id}/playlists/{pid}/tracks`, `/campaign/{id}/audio/play`, `/audio/stop`, `/audio/next`, `/audio/loop`.
- Player audio panel in the tabletop sidebar (volume + mute + now-playing line + autoplay-unblock button).
- GM audio-management UI in `/campaign/{id}/settings#audio` (playlist CRUD, track upload, per-track Play, stop-everyone button).
- WebSocket message types `audio_play` and `audio_stop` broadcast through the existing per-campaign hub.
- `tabletop.js` now redispatches every WebSocket message as a `vtt:ws-message` CustomEvent so additional client modules (like `audio.js`) can react without re-opening the socket.

### Changed
- Tabletop view now passes `now_playing` (a PlaylistTrack or None) to the template so reconnecting clients immediately resume.
- Campaign settings view now passes `playlists` for GM management.
- `app/main.py` ensures `static/uploads/{maps,tokens,thumbnails,audio}/` exist on startup.

### Schema
- New table `playlists` (id, campaign_id, name, created_at).
- New table `playlist_tracks` (id, playlist_id, name, file_url, position, created_at).
- `campaigns.now_playing_track_id INTEGER NULL` — added.
- `campaigns.now_playing_loop BOOLEAN NOT NULL DEFAULT TRUE` — added.
- `SCHEMA_VERSION` bumped from 3 to 4.

### Notes
- Time-position sync across clients is intentionally not implemented in this release. When the GM hits play, every client starts the track from t=0. This is the right trade-off for ambient music loops; tight cinematic sync would need a clock-synchronization protocol that's worth its own ticket.
- Audio file URLs under `/static/uploads/audio/` are public to anyone who knows the UUID-randomized URL. Acceptable for the home-LAN use case but if you ever expose SimpleVTT to the open internet, consider proxying audio through an auth-checked endpoint.
- Per-client per-track volume control is not exposed; players can only adjust their global master volume. Could be added later if needed.

---

## [0.4.0] - 2026-05-01

**Schema version:** 3

**Commit summary:** Add per-campaign co-GM role so multiple users can run the same game

**Description:** Campaign membership now carries an `is_gm` flag, making it possible to have multiple GMs per campaign. The campaign's primary GM (owner/creator) and any user with `is_gm=True` on a membership row both get full GM powers in that campaign. GMs can promote or demote players to/from GM only for the campaigns they're a GM in. Site admins can manage GM roles in any campaign. The primary GM cannot be demoted via this UI — admins would need to transfer ownership separately. Existing PostgreSQL deployments auto-migrate on first boot.

### Schema
- `campaign_memberships.is_gm BOOLEAN NOT NULL DEFAULT FALSE` — added.
- `SCHEMA_VERSION` bumped from 2 to 3.

---

## [0.3.0] - 2026-05-01

**Schema version:** 2

**Commit summary:** Lock campaigns to a game system, add thumbnails, polish lobby with badges and cards

**Description:** Campaigns now declare a game system (generic or D&D 5e for now), and all characters in a campaign are forced to use that system's sheet template. The 5e sheet becomes rollable. Quick-die buttons in the dice tray are also system-aware. Campaigns can have an uploaded thumbnail. The lobby was redesigned as a card grid with role and system badges.

### Schema
- `campaigns.game_system VARCHAR(40) NOT NULL DEFAULT 'generic'` — added.
- `campaigns.thumbnail_url VARCHAR(500) NULL` — added.
- `SCHEMA_VERSION` bumped from 1 to 2.

---

## [0.2.0] - 2026-05-01

**Schema version:** 1

**Commit summary:** Move all configuration to environment variables and switch default port to 8013

**Description:** Configuration is now driven entirely by environment variables (loaded from `.env` in Docker), removing the separate `config.yaml` file. The default listening port changes from 8000 to 8013. This is a breaking change: existing deployments must copy their previous YAML values into `.env`.

---

## [0.1.0] - 2026-05-01

**Schema version:** 1

**Commit summary:** Initial SimpleVTT release with auth, real-time tabletop, character sheets, and Docker stack

**Description:** First working version of SimpleVTT. Provides a self-hosted virtual tabletop with local + Google SSO login, square or hex grid maps with click-and-drag tokens, a dice roller with three-tier visibility, generic and D&D 5e character sheets, an admin portal, and an automated PostgreSQL backup sidecar. The full stack ships as multi-arch Docker images.
