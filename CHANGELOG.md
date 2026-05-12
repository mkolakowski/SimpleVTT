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

## [0.57.1] - 2026-05-12

**Schema version:** 31

**Commit summary:** Make the Bonus Cantrip dropdown self-diagnose when Open5e returns empty + add local-to-live fallback in the spells proxy

**Description:** The "Bonus Cantrip" cantrip-picker dropdown that appears for Druid Circle of the Land (and for Light Cleric, Nature Cleric, etc.) was rendering as a permanently-blank select when `/api/open5e/spells?spell_list=druid&level=0&limit=80` returned nothing — which can happen if Open5e is unreachable, if the local mirror is stale, or if the v1 spell-list filter ever changes shape. The dropdown silently ate the failure and the player just saw an unclickable widget. Two fixes: (1) the dropdown now visibly shows the failure with the underlying reason (HTTP status, "empty-result", network message) and a small ↻ Retry button that drops the failed cache entry and re-hits the server without a page reload; (2) the spells proxy now falls back to the live Open5e API when `LOCAL_OPEN5E=true` is set but the local mirror returns zero results for the given filter — so a partial/stale local sync no longer silently breaks pickers. Also logs the empty-local case so deployments running the mirror can spot which filters are missing data.

### Fixed
- Bonus Cantrip dropdown (and any other curated `type: 'choose'` grant on a subclass) no longer renders as an empty widget on Open5e failure. The select now shows the underlying error message, and a small ↻ Retry button sits next to it to re-try without reloading the page.
- `_fetchCantripsForClass` only caches successful, non-empty responses. A transient failure used to be cached for the rest of the session, leaving the dropdown broken until reload.
- `/api/open5e/spells` falls back to the live API when the local mirror returns zero results — previously a stale mirror would lock the picker empty even when Open5e would have returned data. Also logs an `INFO` line when the fallback fires.

### Added
- `[bonus-cantrip]` console warnings in the cantrip fetcher pinpointing the failed URL and the underlying reason, so the developer console immediately shows why a dropdown is empty.

## [0.57.0] - 2026-05-11

**Schema version:** 31

**Commit summary:** Add Halfling auto-defenses and an Open5eCoverage diagnostic for curated-table gaps

**Description:** Adds the Halfling family to the innate-defenses curated table — Halfling, Lightfoot Halfling, Ghostwise Halfling get Frightened condition immunity (Brave, modelled the same flexible-reading way as Fey Ancestry), and Stout / Strongheart Halflings additionally get Poison damage resistance (Stout Resilience — a RAW-accurate Dwarven Resilience analog). Also introduces a small developer framework for spotting "Open5e item with no local curated coverage" gaps. Three curated tables ship alongside the sheet — `_INNATE_DEFENSES` (race/class/subclass → auto-applied damage and condition immunities), `_CLASS_RESOURCES` (class/subclass → trackable feature counters), `_SUBCLASS_SPELLS` (subclass → always-prepared spell grants). The new `window.Open5eCoverage` queries all three uniformly and reports which selected items have local entries vs. which don't. Intended as a dev tool, not a user-facing UI: open the JS console on any D&D 5e sheet and run `Open5eCoverage.summarize()` to see the report, or set `localStorage.setItem('simplevtt_coverage_debug', '1')` once to auto-print on every sheet load until cleared. As we add more curated entries the report will get shorter — it's the to-do list of "Open5e content we know about but haven't taught the rules engine yet."

### Added
- Halfling race entries in `app/static/dnd5e_innate_defenses.js`: `halfling`, `lightfoot-halfling`, `ghostwise-halfling`, `stout-halfling`, `strongheart-halfling`. All share the Brave → Frightened immunity reading; Stout / Strongheart additionally include Poison damage resistance.
- New `app/static/open5e_coverage.js` module exposing `window.Open5eCoverage` with three methods:
  - `inspect(sheet?)` — returns a structured report of curated/missing coverage for the live sheet (or any sheet-shaped object).
  - `summarize(sheet?)` — prints a one-screen console report (race + class/subclass coverage tags + missing list).
  - `isCurated(kind, slug)` — single boolean for one item; `kind` is one of `race-defenses`, `class-defenses`, `subclass-defenses`, `class-resources`, `subclass-resources`, `subclass-spells`.
- Opt-in auto-print on sheet load when `localStorage.simplevtt_coverage_debug === '1'`. Wraps the output in a `console.groupCollapsed` so it doesn't dominate the console.
- Coverage script loaded alongside the other curated tables on the D&D 5e sheet.

## [0.56.1] - 2026-05-11

**Schema version:** 31

**Commit summary:** Add Elf Fey Ancestry to the innate-defenses curated table for all elf subraces

**Description:** The Defenses fieldset wasn't auto-flagging Charmed immunity for Elves because no Elf entries were in the curated `dnd5e_innate_defenses.js` table. Fixed by adding all PHB Elf subraces — Elf, High Elf, Wood Elf, Drow, Eladrin — pointing at a shared `_FEY_ANCESTRY` constant that lights the Charmed condition chip. The two existing elf subraces with extra resistances (Shadar-kai, Sea Elf) now combine both grants under a single tooltip label so the player sees their full racial defense package on one row. Note on the rules: RAW Fey Ancestry is "advantage on saves against being charmed, and magic can't put you to sleep" — i.e. a save-side advantage, not flat Charmed immunity. We model it as a Charmed chip because (a) the chip is a useful visible reminder of the trait, and (b) many tables already play Fey Ancestry as effective charm immunity; the chip's hover tooltip names the trait explicitly so players whose tables play it stricter can read it as "advantage" instead. Sleep-magic immunity isn't a chip type in the standard list and is omitted.

### Added
- Elf race entries in `app/static/dnd5e_innate_defenses.js`: `elf`, `high-elf`, `wood-elf`, `drow`, `eladrin`. All share Fey Ancestry → Charmed condition immunity chip.
- Updated Shadar-kai and Sea Elf entries to also carry Fey Ancestry on top of their existing Necrotic / Cold resistance — they're elf subraces too.

## [0.56.0] - 2026-05-11

**Schema version:** 31

**Commit summary:** Auto-apply race and class defenses on the D&D 5e sheet via a curated lookup

**Description:** The D&D 5e Defenses fieldset now auto-applies defenses granted by the character's race and class. A Tiefling automatically shows Fire Resistance, a Mountain Dwarf shows Poison Resistance, an Aasimar shows Necrotic + Radiant Resistance, and a Monk crossing level 10 picks up Poison Damage Immunity + Poisoned Condition Immunity from Purity of Body. Auto-applied chips render with a ✨ badge and a locked appearance — hovering shows the source ("Auto-applied from Dwarven Resilience"), clicking surfaces the same hint via toast rather than toggling. The player's manual chip selections remain editable and independent. When race / class level / subclass changes the auto chips refresh immediately (no save needed). Coverage is conservative on purpose: only always-on defenses from sources I can verify (PHB races, Aasimar, Genasi, Triton, Yuan-ti, Shadar-kai, Sea Elf, Monk Lv 10). Conditional features (Rage's BPS resistance, Aura of Protection) are deliberately excluded since they're not really sheet-state — those are tracked via the existing resource counters / aura UI. Dragonborn is also skipped pending an ancestry sub-field.

### Added
- New `app/static/dnd5e_innate_defenses.js` curated table mapping Open5e race / class / subclass slugs to defense grants. Each grant is `{damage_resistances, damage_immunities, damage_vulnerabilities, condition_immunities, source}`; class/subclass entries can be level-tiered arrays so Monk Lv 10 Purity of Body only activates at the right level.
- `window._computeInnateDefenses(sheet)` helper that walks the race + class roster and returns a unified map of granted defenses with their source labels for tooltips.
- `_applyAutoDefenses()` inside the Defenses IIFE in `sheet_dnd5e.html`. Marks any standard chip whose label matches a grant with `data-auto="1"`, a ✨ prefix, a locked-color style, and a hover tooltip. Reverts cleanly when the grant goes away (race swap, subclass change, level drop below threshold). Re-runs on initial load, on `vtt:mc-changed`, and on race-select `change`.
- Click handler short-circuits on auto chips — pops a toast showing the source instead of toggling, so players understand why the chip won't deselect.

### Coverage (initial pass)
- **Races**: Tiefling, Dwarf (+ Hill, Mountain, Duergar variants), Aasimar (+ Protector, Scourge, Fallen), Fire Genasi, Water Genasi, Triton, Yuan-ti Pureblood, Shadar-kai, Sea Elf.
- **Classes**: Monk Lv 10 (Purity of Body — poison immunity + poisoned condition immunity).
- **Subclasses**: empty for now (PHB subclass defenses are mostly conditional; add to `SUB` in the curated table when a clean case arises).

## [0.55.0] - 2026-05-11

**Schema version:** 31

**Commit summary:** Track damage resistances, immunities, vulnerabilities, and condition immunities on character sheets

**Description:** Both D&D 5e and generic character sheets now track defenses as first-class fields. The D&D 5e sheet gets a new collapsible **Defenses** fieldset (between Conditions and Attacks) with four chip-toggle rows — Damage Resistances, Damage Immunities, Damage Vulnerabilities, and Condition Immunities. Each row pre-fills the 13 PHB damage types or 15 condition types as toggleable chips and provides a "+ Custom" input for edge cases like *"bludgeoning, piercing, and slashing from nonmagical attacks not made with silvered weapons"*. Each toggle PATCHes `/sheet-fields` immediately, so changes survive a refresh without an explicit Save. The generic sheet gets a simpler Defenses fieldset with two free-text fields (`resistances`, `immunities`). Wild Shape and Polymorph now snapshot the player's real-form defenses into `prior_form` and apply the beast's defenses to the active form — so a Druid wild-shaping into a creature with poison immunity actually gets it, and reverts cleanly to their own defenses. Open5e's free-text defense strings are parsed at import time (splitting on commas, semicolons, and " and ") into chip lists; complex tail clauses like "from nonmagical attacks" land as a single custom chip the player can clean up. Schema is JSON-only on `Character.sheet` — no SQL migration.

### Added
- New D&D 5e sheet fields: `damage_resistances`, `damage_immunities`, `damage_vulnerabilities`, `condition_immunities` (each a list of label strings). Names match the existing `LocalCreature` model and Open5e shape for consistency.
- New generic sheet fields: `resistances` and `immunities` (free-text strings — generic systems get a single line each rather than chip-toggle since they don't have a fixed taxonomy).
- New **Defenses** collapsible fieldset on the D&D 5e sheet with four chip-toggle rows. Each row colour-codes its accent (gold for resistance, teal for immunity, red for vulnerability, blue for condition immunity), a "+ Custom" input for non-standard entries, and an × button on each custom chip to remove.
- `_open5e_to_dnd5e_sheet` now parses Open5e's free-text defense strings into chip lists. Splits on commas, semicolons, and " and ". Complex tail clauses ("from nonmagical attacks", "not made with silvered weapons") land as a single custom chip rather than being mangled.
- The four new fields are whitelisted in `_SHEET_PATCH_KEYS` (so chip toggles persist via `/sheet-fields` PATCH) and added to the `update_sheet` preserve list (so a full Save without them doesn't wipe the chip state — same belt-and-braces pattern as `active_form`, `hp_rolls`, `favorite_beasts`).

### Changed
- `transform_character` snapshots all four defense lists into `prior_form` and applies the beast's defenses to the active sheet. `revert_character` restores them. Previously beast defenses were dumped into the unstructured `notes` text and not preserved across revert.
- `_open5e_to_dnd5e_sheet` no longer dumps Damage Immunities / Resistances / Condition Immunities into `notes` — they're first-class fields now. Notes still carries Hit Dice, CR, Languages, and Senses.
- `sheet.js` form-submit parses the four new JSON-array fields on save (same pattern as the existing `conditions` field).

## [0.54.1] - 2026-05-11

**Schema version:** 31

**Commit summary:** Improve full sheet readability with clearer label vs value contrast

**Description:** Labels and section headings on the full character sheet were difficult to distinguish from their associated values — both used similar font sizes and the same foreground colour family. Section legends are now larger and accent-coloured. A new `--s-label` CSS variable provides a mid-tone between `--s-fg` and `--s-mute` used for all field labels, making them clearly subordinate to values without disappearing. Stat chip labels (AC, Speed, Init, Prof) grow from 9 px to 11 px, ability/saving-throw abbreviations from 10 px to 11 px, and the background feature title/description pair gains distinct `.ft-title` / `.ft-desc` classes with matching styles.

### Changed
- `fieldset > legend` headings are now 14 px, bold, and accent-coloured.
- Added `--s-label` CSS variable (60 % fg / 40 % mute) used for field labels throughout the sheet.
- Stat chip labels (AC, Speed, Init, Prof) increased from 9 px to 11 px.
- Ability and saving-throw abbreviation labels increased to 11 px via CSS selector.
- Skill-card ability abbreviation tag increased to 11 px via CSS selector.
- Background feature title and description use new `.ft-title` / `.ft-desc` CSS classes for clear visual separation.

---

## [0.54.0] - 2026-05-11

**Schema version:** 31

**Commit summary:** Add per-user animated GIF toggle for portraits and tabletop tokens

**Description:** GIF uploads were already accepted but animated GIFs never played — canvas `drawImage()` only captures a single frame and the portrait `<img>` tag was not conditional. Portraits now render as an animated `<img>` (GIFs loop naturally) or, when animation is disabled, as a `<canvas>` that captures the first frame as a static thumbnail. Tabletop tokens with `.gif` image URLs start a `requestAnimationFrame` loop so GIF frames advance on the canvas; the loop stops automatically when no GIF tokens are present. A new "Animate GIFs" checkbox in user settings (⚙ → Animated GIFs) persists the preference server-side and applies across all devices. No operator action needed beyond redeploy.

### Added
- `users.animate_gifs` boolean column (schema v31, default `TRUE`).
- `POST /api/settings/animate_gifs` endpoint to persist the preference.
- "Animated GIFs" toggle section in user settings.
- `requestAnimationFrame` loop in `tabletop.js` that activates only while GIF tokens are on the canvas (`_syncGifLoop`).

### Changed
- Portrait on full character sheet renders as `<img>` (animated) or `<canvas>` (static first frame) depending on `animate_gifs` preference and whether the URL is a GIF.
- Portrait upload handler replaces a static canvas element with a fresh `<img>` immediately after upload so the new file is visible without a reload.
- `ME.animateGifs` flag added to the tabletop JavaScript context.
- All `sheet_dnd5e.html` render calls now receive `animate_gifs` in their template context.

### Schema
- `ALTER TABLE users ADD COLUMN animate_gifs BOOLEAN NOT NULL DEFAULT TRUE`

---

## [0.53.3] - 2026-05-11

**Schema version:** 30

**Commit summary:** Reorganize combat stat chips into 2x2 grid with AC on full sheet

**Description:** The Speed, Initiative, and Proficiency Bonus chips were displayed in a single 3-wide row. AC was only visible in the inventory section. The chips are now arranged in a 2×2 grid (AC, Speed, Initiative, Prof) so all four key combat stats are immediately visible at the top of the sheet. The AC chip is wired to the existing armor engine and updates live when equipment changes.

### Changed
- Combat stat chips on the full character sheet reorganized from 3-column row to 2×2 grid.
- AC chip added to the grid; reads the initial value from `sheet.ac` and updates live via the inventory armor engine (`id="ac-disp"`).

---

## [0.53.2] - 2026-05-11

**Schema version:** 30

**Commit summary:** Group tabletop mini-sheet spells by level across all classes

**Description:** The tabletop sidebar spell list previously showed a separate section per class per level (e.g. "Level 1 Spells - Druid", "Level 1 Spells - Wizard"), which was noisy for multiclass characters. Spells are now combined under a single "Level N Spells" heading per level, matching the full character sheet layout. For multiclass characters, each spell row gains a small italic class tag so the source is still visible. Slot pip rows remain per-class within each level group.

### Changed
- Tabletop mini-sheet spell list now groups by level (not by class × level), matching the full sheet.
- Slot pip rows are still rendered per class within each level group, labelled with the class name when multiclass.
- Each spell row shows a small italic class tag when the character is multiclass.

---

## [0.53.1] - 2026-05-11

**Schema version:** 30

**Commit summary:** Increase spell level label font size for improved readability on character sheet

**Description:** The "Cantrips" and "Level N Spells" group headings in the spell section of the full character sheet were rendered at 10px in a muted color, making them hard to read at a glance. They are now 13px and use the standard foreground color so spell level groups are clearly scannable.

### Changed
- Increased spell level group label font size from 10px to 13px and changed color from muted to foreground in the character sheet spell list.

---

## [0.53.0] - 2026-05-11

**Schema version:** 30

**Commit summary:** Add homebrew import / export with starter template download

**Description:** GMs can now move every homebrew row in a campaign — classes, subclasses, races, monsters, backgrounds, feats — into or out of a single JSON pack. Three new endpoints under `/api/campaign/{id}/homebrew/`: `export` produces a combined download, `template` returns an annotated starter file with one example row per content type, and `import` accepts the same shape and bulk-creates rows. Imports are slug-deduplicating per campaign — re-importing a pack you've already loaded is a safe no-op rather than an overwrite or an error. Each content type is processed independently so a malformed entry in one list doesn't kill the rest of the import; the response carries per-type `created` / `skipped` / `errors` counts so the GM can see what landed. New "Import & export" sub-tab inside the Homebrew tab on the campaign settings page wires three buttons: download pack, download template, and upload-to-import with status readout.

### Added
- `GET /api/campaign/{id}/homebrew/export` — returns `{format: "simplevtt-homebrew", version: 1, campaign, exported_at, classes, subclasses, races, monsters, backgrounds, feats}`. GM-only.
- `GET /api/campaign/{id}/homebrew/template` — returns the same shape pre-populated with one annotated example row per content type. GM-only.
- `POST /api/campaign/{id}/homebrew/import` — accepts a pack matching the export shape and bulk-creates rows. Skips any row whose slug already exists in this campaign. Per-type caps (200 classes / 500 subclasses / etc.) protect against pathological uploads. Returns `{ok, stats: {classes: {created, skipped, errors}, …}, totals}`. GM-only.
- Six per-type `_<content>_to_dict()` helpers in `app/routes/tabletop_routes.py` so each row's full DB shape round-trips through JSON without data loss (features, spell lists, resources, abilities, prereqs, action lists, multiclass info — all preserved).
- `HOMEBREW_EXPORT_VERSION = 1` constant. The import endpoint rejects packs whose `version` is higher than the running server supports so a future v2 schema can't silently corrupt a v1 server's data.
- "Import & export" sub-tab in the Homebrew tab on `campaign_settings.html` with three cards: Export pack, Template, and Import pack. The import card surfaces per-type stats inline after upload so a GM sees exactly which rows landed and which were skipped on slug collision.

### Schema
- No schema changes — the new endpoints operate purely on existing tables. `SCHEMA_VERSION` unchanged at 30.

## [0.52.1] - 2026-05-11

**Schema version:** 30

**Commit summary:** Reorganise campaign settings page into tabs with Homebrew sub-tabs

**Description:** The campaign settings page had grown a 13-item anchor strip after six homebrew content types landed, with every section visible at once making it slow to scroll and visually noisy. The page now uses real tabs: Basic info / People / World / Homebrew / Danger zone, with the Homebrew tab opening a second strip for the six content sub-types (Classes / Subclasses / Races / Monsters / Backgrounds / Feats). Tab state is URL-hash-aware in both directions — typing `#homebrew` or `#custom-monsters` in the address bar lands on the matching tab, and the CRUD redirect targets (`POST → 303 → …/settings#custom-monsters`) continue to land on the right tab without any change to the route handlers. Switching tabs updates the hash with `history.replaceState` so reload preserves the view but the back button doesn't fill up with intermediate tab switches.

### Added
- Tab strip (`.settings-tabs`) and Homebrew sub-tab strip (`.settings-subtabs`) replacing the old `.settings-nav` anchor links. Active state on hover/click; the danger tab is tinted red and only renders for admins (same as the old anchor).
- `data-tab` and (for Homebrew sections) `data-sub` attributes on every `<section class="settings-section">` so the switcher knows which sections belong to which tab.
- Inline switcher script at the end of the template — hash-aware on load and on every `hashchange`, falls back to `basic` when no hash is supplied.

### Changed
- `.settings-section` defaults to `display: none` and only sections with `.is-shown` render. Editors inside `<details>` cards (features-editor, spell-picker, resources-editor) keep their existing lazy-init-on-open behavior, so opening one tab doesn't pay the init cost for sections in other tabs.

## [0.52.0] - 2026-05-11

**Schema version:** 30

**Commit summary:** Wire backgrounds and feats into the D&D 5e sheet as in-place pickers

**Description:** Sheet-side consumers for the background + feat content types that landed in v0.51.0. A new "Background" select sits in the existing character-edit grid (right after Prof Bonus); on change it fetches `/api/open5e/background/<slug>?campaign_id=N`, caches the result in `sheet["background_data"]`, and renders the signature feature in a display block below the multiclass editor. A new "Feats" section above the multiclass editor renders the character's feats as collapsible cards showing name + prerequisite in the summary and the full description when expanded; a "+ Add feat" button reveals an inline typeahead search that calls `/api/open5e/feats?search=…&campaign_id=N` and adds the chosen feat (with cached prereq + desc) as a new card. Both flows persist automatically via `/sheet-fields` PATCH on every change — no explicit Save required. The "Custom" gold pill surfaces on both display paths when the resolver returns `source: "local-custom"`, matching the subclass / race / monster badge style.

### Added
- `sheet["background_data"]` (cached `{slug, name, feature, feature_desc, desc, source}` blob) and `sheet["feats"]` (list of cached feat records `{slug, name, prerequisite, desc, source}`) on `DND5E_TEMPLATE` in `app/sheet_templates.py`. Defaults: `{}` and `[]`. Existing sheets without these fields tolerate their absence since the inline picker JS treats null / undefined as empty.
- "Background" select on the character-edit panel (after the Prof Bonus input) populated from `/api/open5e/backgrounds` at sheet load. Preserves the saved display name even when the upstream API doesn't list it (legacy free-text values or homebrew the GM later deleted) by inserting a synthetic option.
- "Background" display block below the multiclass editor showing the chosen background's name, signature feature (name + description), and overall description. Hidden when nothing is picked. "↻ Sync" button re-fetches detail on demand.
- "Feats" section above the multiclass editor with collapsible `<details>` cards per feat. Each card's summary shows the feat name, a Custom pill (when applicable), and the prerequisite text inline. The body shows the full description. "✕" button removes the feat; "+ Add feat" opens an inline search panel.
- Inline IIFE at the end of `sheet_dnd5e.html` wiring both pickers — debounced search, dedupe on add, auto-persist via `/sheet-fields` PATCH on every change, source-badge rendering when `source === "local-custom"`. Threads `CAMPAIGN_ID` into every fetch when defined (sheet outside a campaign uses global-only resolution).

### Changed
- `_SHEET_PATCH_KEYS` in `app/routes/tabletop_routes.py` allows `"background_data"` and `"feats"` so the picker auto-save calls land successfully.

### Schema
- No schema changes — existing JSON `Character.sheet` column carries the new keys. `SCHEMA_VERSION` unchanged at 30.

## [0.51.0] - 2026-05-11

**Schema version:** 30

**Commit summary:** Add custom backgrounds and feats with Open5e proxy endpoints and admin surfacing

**Description:** Two new content types in one release — character backgrounds and feats. Both follow the same pattern as classes / subclasses / races / monsters: campaign-scoped DB table, dedicated resolver function with DB + reserved FS providers, GM-only CRUD routes, new authoring sections on the campaign settings page, and a section on the admin stubs panel. Two new pairs of Open5e proxy endpoints (`/api/open5e/backgrounds` + `/background/{slug}`, `/api/open5e/feats` + `/feat/{slug}`) join the existing class / subclass / race / monster proxies — each accepts `campaign_id` and prepends campaign homebrew at the top of list results, with homebrew shadowing any Open5e entry whose slug it collides with. Frontend pickers for these two content types don't exist on the sheet yet — the framework infrastructure is in place so the next iteration can add them without backend work. Both schema migrations auto-apply on next boot.

### Added
- `CustomBackground` model (campaign-scoped, unique `(campaign_id, background_slug)`): description, four proficiency strings (skills / tools / languages / equipment), and a signature feature (name + description). MVP intentionally omits Open5e's `suggested_characteristics` text since it's roleplaying flavor with no mechanical effect.
- `CustomFeat` model (campaign-scoped, unique `(campaign_id, feat_slug)`): name, prerequisite text, and the full description. Smallest model in the framework — mechanical effects live in the description rather than encoded rules.
- `resolve_background` / `resolve_feat` + DB providers + reserved FS-provider slots in `app/local_features.py`. Same chain-ordering pattern as the other resolvers.
- GM-only CRUD routes: `POST /campaign/{id}/custom-backgrounds`, `…/{bg_id}`, `…/{bg_id}/delete`, and the parallel set for `/custom-feats/…`.
- Four new Open5e proxy endpoints: `GET /api/open5e/backgrounds` (list, paginated, prepends homebrew when `campaign_id` is supplied), `GET /api/open5e/background/{slug}` (detail, resolver-first), and the parallel pair for feats. Homebrew-only response when Open5e is unreachable and there's homebrew to surface.
- "Custom backgrounds" and "Custom feats" sections on `app/templates/campaign_settings.html` with appropriate fields (proficiency strings + signature feature for backgrounds; prerequisite + description for feats). Both sections linked from the settings nav.
- Two new tables on `/admin/stubs` — campaign / name / slug / signature-feature / skill profs / author / updated for backgrounds, and campaign / name / slug / prerequisite / author / updated for feats. Same data exposed under `/admin/stubs.json` as `custom_backgrounds_db` and `custom_feats_db`.

### Schema
- New table `custom_backgrounds` (id, campaign_id, background_slug, name, description, skill_proficiencies, tool_proficiencies, languages, equipment, feature_name, feature_desc, created_by_user_id, created_at, updated_at) with `uq_custom_background(campaign_id, background_slug)`.
- New table `custom_feats` (id, campaign_id, feat_slug, name, prerequisite, desc, created_by_user_id, created_at, updated_at) with `uq_custom_feat(campaign_id, feat_slug)`.
- `SCHEMA_VERSION` bumped from 28 to 30 (one per new table).

## [0.50.0] - 2026-05-11

**Schema version:** 28

**Commit summary:** Add custom monsters with beast picker integration and source badge

**Description:** Monsters complete the local-first content framework. A new `custom_monsters` table stores per-campaign homebrew stat blocks: identity (name, size, type, alignment), combat (AC + desc, HP + hit dice, speed dict), six ability scores, defenses + senses + languages as plain text, CR (supports fractions), and four parallel action lists (actions / reactions / special abilities / legendary actions) using the same shape the features editor already supports. The Wild Shape / Polymorph beast picker (`beast_picker.js`) threads `campaign_id` into both fetches it makes — the `/api/open5e/monsters` search and the per-favorite `/api/open5e/creature/{slug}` lookup — so homebrew rows prepend the results and shadow any Open5e creature with the same slug. Each row in the picker shows a small gold "Custom" pill so GMs can tell shipped content from their own at a glance. MVP scope intentionally cuts structured skills/saves with proficient flags, spell lists, lair/regional actions, and multi-form stats; the four-list pattern reuses the existing `features_editor.js` widget so the authoring form stays consistent with classes / subclasses / races. Schema migration auto-applies on next boot.

### Added
- `CustomMonster` ORM model with unique `(campaign_id, monster_slug)`, cascade delete from campaign, `SET NULL` on creator deletion. 27 columns covering identity, combat stats, six abilities, defenses + senses, CR, and four `[{name, desc, level}]` action lists.
- `resolve_monster` + `_db_monster_provider` + `_fs_monster_provider` (reserved slot) in `app/local_features.py`. Same chain pattern as classes, subclasses, and races.
- Three GM-only routes: `POST /campaign/{id}/custom-monsters`, `POST /campaign/{id}/custom-monsters/{monster_id}`, `POST /campaign/{id}/custom-monsters/{monster_id}/delete`. Helpers: `_normalize_monster_type` (14 standard types, case-tolerant), `_parse_monster_speed` (five movement kinds, drops zeros, defaults walk=30 when all blank), `_parse_cr` (accepts "0", "1/8", "1/4", "1/2", or integer 1–30), `_parse_ability_score` (bounded 1–40), `_custom_monster_lite` (homebrew → picker lite shape with `is_custom: true`), `_cr_to_float` (CR text → float for filter comparisons).
- "Custom monsters" section on `app/templates/campaign_settings.html` with size + type + alignment row, combat fieldset (AC, AC desc, HP, hit dice, CR dropdown), five-cell speed grid (walk/fly/swim/climb/burrow), six-cell ability grid, defenses + senses fieldset, and four `[data-features-editor]` widgets for the action lists. Settings-nav link added.
- "Custom" pill badge on every homebrew row in the beast picker (gold background, matches the subclass / race badges).
- `custom_monsters_db` table on `/admin/stubs` with campaign / monster / slug / size / type / CR / AC / HP / total-actions / author / updated columns; same data plus per-list counts under `/admin/stubs.json`.

### Changed
- `/api/open5e/monsters` accepts optional `campaign_id` parameter. With it, the endpoint queries `CustomMonster` for matching homebrew (applying the same `search`, `type_filter`, and `cr_max` filters the client sent upstream), prepends them with `is_custom: true`, and drops any Open5e result whose slug collides. When Open5e is unreachable and we have homebrew, return that rather than 502.
- `/api/open5e/creature/{slug}` accepts optional `campaign_id`. Homebrew with this slug takes precedence over the Open5e fetch; Open5e is only consulted when no homebrew match exists. 404 propagates as before when neither source has the slug.
- `app/static/beast_picker.js` threads `_state.opts.campaignId` into the monsters search, the single-creature backfill, and the favorites-init parallel fetch. Picker `_rowHtml` renders a "Custom" pill when `r.is_custom === true`.

### Schema
- New table `custom_monsters` (id, campaign_id, monster_slug, name, size, type, alignment, armor_class, armor_desc, hit_points, hit_dice, speed JSON, strength, dexterity, constitution, intelligence, wisdom, charisma, damage_vulnerabilities, damage_resistances, damage_immunities, condition_immunities, senses, languages, challenge_rating, actions JSON, reactions JSON, special_abilities JSON, legendary_actions JSON, created_by_user_id, created_at, updated_at) with `uq_custom_monster(campaign_id, monster_slug)`.
- `SCHEMA_VERSION` bumped from 27 to 28.

## [0.49.0] - 2026-05-11

**Schema version:** 27

**Commit summary:** Add custom races to the local-first framework with GM authoring form and sheet badge

**Description:** Races become the third content type to plug into the resolver framework after classes and subclasses. A new `custom_races` table stores per-campaign homebrew races (slug, ability bonuses, size, speed, age / alignment / languages text, structured traits list). `_db_race_provider` registered ahead of a reserved filesystem provider; the existing `resolve_class` / `resolve_subclass` get a `resolve_race` sibling with the same signature. The `/api/open5e/race-detail` endpoint accepts `campaign_id` and threads it through the resolver, synthesising the `flavor` summary block from structured stat fields via the existing `format_race_text` / `parse_race_traits` helpers so the frontend renderer sees the same shape it does for SRD races. `/api/open5e/races` (list) accepts `campaign_id` and prepends homebrew with `is_custom: true`, deduping any collision. The sheet's three race-detail fetch sites + the races list fetch thread `CAMPAIGN_ID`, and `renderRaceTraits` now renders a "Custom" badge next to the race name when `data.source === "local-custom"`. New "Custom races" section on the campaign settings page with ability-bonus grid, size dropdown, speed input, three multi-line description fields, and the existing features-editor for traits. Admin stubs panel grows a homebrew-races section with deep-link to each owning campaign. Schema migration auto-applies on next boot.

### Added
- `CustomRace` ORM model with unique `(campaign_id, race_slug)`, cascade delete from campaign, `SET NULL` on creator deletion.
- `resolve_race` + `_db_race_provider` + `_fs_race_provider` (reserved slot, no shipped files yet) in `app/local_features.py`. Provider chain ordering mirrors classes and subclasses — DB before FS.
- Three GM-only routes: `POST /campaign/{id}/custom-races`, `POST /campaign/{id}/custom-races/{race_id}`, `POST /campaign/{id}/custom-races/{race_id}/delete`. Helpers: `_normalize_race_size` (Tiny/Small/Medium/Large/Huge/Gargantuan, case-tolerant), `_parse_ability_bonuses` (Open5e shape `{attribute, bonus}`, drops zeros, bounded -10..10).
- "Custom races" section on `app/templates/campaign_settings.html` with name, size dropdown, speed input, ability-bonus grid (six STR..CHA fields), age/alignment/languages textareas, and the existing features-editor widget repurposed for traits.
- "Custom" badge on the race-traits renderer (`renderRaceTraits` in `app/static/sheet.js`) when the response carries `source === "local-custom"`. Visual style matches the subclass badge for consistency.
- `custom_races_db` section on `/admin/stubs` with campaign / race / slug / size / speed / ability summary / trait count / author / updated columns; same data exposed under `/admin/stubs.json`.

### Changed
- `/api/open5e/race-detail` accepts an optional `campaign_id` parameter. With it the resolver runs `scopes=["campaign:N", "global"]` first; campaign homebrew shadows any SRD race with the same slug. Without it behavior is identical to v0.48.0. Response always carries a `source` string (mirrors the class and subclass endpoints).
- `/api/open5e/races` accepts `campaign_id` and merges campaign homebrew at the top with `is_custom: true`, deduping any Open5e/mirror entry whose slug is already covered.
- All four race-related fetches in `app/static/sheet.js` (races list + three race-detail sites: initial load, change handler, sync button) now thread `CAMPAIGN_ID`. localStorage cache key for the races list embeds the campaign id so one campaign's homebrew doesn't leak into another's picker.

### Schema
- New table `custom_races` (id, campaign_id, race_slug, name, ability_bonuses JSON, size, speed, age, alignment, languages, traits JSON, created_by_user_id, created_at, updated_at) with `uq_custom_race(campaign_id, race_slug)`.
- `SCHEMA_VERSION` bumped from 26 to 27.

## [0.48.0] - 2026-05-11

**Schema version:** 26

**Commit summary:** Add per-rest resource counters to homebrew classes with sheet panel merge

**Description:** Phase B — the deepest of the deferred custom-class follow-ups. Homebrew classes can now define per-rest resource counters (Channel Divinity, Bardic Inspiration, Ki, Action Surge, Wild Shape, …) using the same shape the curated SRD table uses. A new `resources` JSON column on `custom_classes` stores declarative recipes; a repeatable-rows editor on the campaign settings form lets the GM author them with conditional inputs per "max kind" — static values, ability modifiers, proficiency bonus, or a level → count threshold table. A new authenticated read endpoint exposes a campaign's homebrew recipes; the D&D 5e sheet fetches them at load time, translates each `max_kind` into a runtime function matching the existing curated table's shape, and appends them to `window._CLASS_RESOURCES`. The existing Class Resources panel surfaces homebrew counters automatically since its filter is purely on class slug. Schema migration auto-applies on next boot.

### Added
- `CustomClass.resources` JSON column (default `[]`).
- `_parse_class_resources_json` in `app/routes/tabletop_routes.py` — validates `max_kind` ∈ {static, ability_mod, proficiency, level_table}, `reset` ∈ {short, long, none}, per-kind required fields, level-table integer range (1–20), and `min_level` (1–20). Auto-derives stable `key` from each entry's name, dedupes collisions, drops empty rows, caps at 50 entries.
- `GET /api/campaign/{id}/custom-class-resources` — returns every homebrew resource recipe across all custom classes in the campaign. Auth: campaign member, GM, or admin. Each record carries `class` and `subclass: null` so the existing `resourcesFor` filter on the frontend works unchanged.
- `app/static/resources_editor.js` — reusable repeatable-rows widget. Each row has name, min level, max-kind dropdown, conditional field (number / ability dropdown / proficiency note / per-level-pair grid), reset dropdown, description, and a delete button. The level-table inputs are individual `level → count` chip pairs with their own "+ level" button. Auto-inits on `[data-resources-editor]` and `<details>` open, syncs to a hidden `resources_json` input on submit.
- "Class resources" fieldset on every custom-class form (create + edit), with a per-class count badge in the legend for existing rows.
- Inline merge script in `sheet_dnd5e.html` after `dnd5e_class_resources.js` loads. Fetches the campaign's homebrew resources, translates `max_kind` into a runtime `max` function matching the curated table's contract, and appends to `window._CLASS_RESOURCES`. Dispatches a `simplevtt:homebrew-resources-merged` event for any subsequent listener. No-op outside a campaign.
- "Resources" column on `/admin/stubs` showing per-class resource count; matching `resource_count` field in `/admin/stubs.json`.

### Schema
- New column `custom_classes.resources` (JSON on Postgres, TEXT-with-JSON-default on SQLite, default `'[]'`). `NOT NULL`; existing rows backfilled by the column default.
- `SCHEMA_VERSION` bumped from 25 to 26.

### Known limitation
- The Class Resources panel's initial render runs before the homebrew fetch resolves, so newly-added homebrew counters surface on the *next* re-render (level change, roster change, ↻ Auto-fill, or reload). This will tighten in a follow-up that has the panel listen for `simplevtt:homebrew-resources-merged` directly.

## [0.47.0] - 2026-05-11

**Schema version:** 25

**Commit summary:** Add multiclass prerequisites with a non-blocking sheet warning and admin surfacing

**Description:** Phase C of the deferred custom-class follow-ups: classes (both shipped SRD and campaign homebrew) now carry multiclass prerequisites — minimum ability scores plus the "all listed" vs "any one" mode that distinguishes Paladin's STR+CHA from Fighter's STR-or-DEX. A new `GET /api/character/{id}/multiclass-check?target_class=<slug>` endpoint resolves the target class through the same provider chain the rest of the framework uses (campaign homebrew wins over shipped FS overrides), reads the character's ability scores from `sheet.abilities`, and returns a structured pass/fail with per-ability reasons. The sheet's multiclass row hooks the check into its class-select change handler and renders a non-blocking amber banner inline when the character doesn't qualify; rules can still be ignored at the table's discretion. Three new columns on `custom_classes`, plus matching fields in `druid.json` (WIS 13) so the shipped Druid surfaces the same warning when a low-WIS character tries to dip. Schema migration auto-applies on next boot.

### Added
- `CustomClass` fields: `multiclass_prereq_abilities` (JSON dict, e.g. `{"str": 13}`), `multiclass_prereq_mode` (`"all"`/`"any"`, default `"all"`), `multiclass_proficiencies` (free-text description of profs gained on multiclassing in).
- Resolver returns all three fields on every class record (DB-backed and filesystem) so any class can carry prereqs without a code change.
- `GET /api/character/{char_id}/multiclass-check` — auth-gated (owner or GM/admin); returns `{ok, target_name, reasons, prereqs, proficiencies, note?}`. Unknown target class or target with empty prereqs both return `ok=true` with an explanatory `note`.
- "Multiclass prerequisites" fieldset on the custom-class form: six ability minimums in a tight grid, mode dropdown, proficiencies-gained text input. Mirrored on both edit and create cards.
- Inline `⚠ Multiclass: ...` banner appended below the multiclass row when prereqs fail. Re-checks on every class-select change; previous banner cleared first so stale warnings can't accumulate.
- `multiclass_prereq_abilities` / `multiclass_prereq_mode` / `multiclass_proficiencies` on the shipped `app/data/local/class_features/druid.json` (WIS 13, all mode, druid armor proficiencies).
- "Multiclass" column on `/admin/stubs` showing the requirement summary (e.g. "STR 13, CHA 13" or "STR 13 or DEX 13"); same fields exposed under `/admin/stubs.json`.

### Changed
- The class-select change handler in `app/static/sheet.js` now fires a prereq check after the existing `_fillClassDetail` / `_refreshProfTable` sequence. Skipped on read-only views and standalone (no `CHAR_ID`) renders.

### Schema
- New columns on `custom_classes`: `multiclass_prereq_abilities` (JSON on Postgres, TEXT-with-JSON-default on SQLite, default `'{}'`), `multiclass_prereq_mode` (`VARCHAR(8)` default `'all'`), `multiclass_proficiencies` (`VARCHAR(500)` default `''`). All `NOT NULL`; existing rows backfilled by the column defaults.
- `SCHEMA_VERSION` bumped from 24 to 25.

## [0.46.0] - 2026-05-11

**Schema version:** 24

**Commit summary:** Add class spell lists to homebrew classes with picker widget and player-side resolution

**Description:** Phase A of the deferred custom-class follow-ups: homebrew classes now carry a curated spell list, and the player's spell picker honors it. A new `spell_list` JSON column on `custom_classes` stores Open5e slugs; a search-as-you-type picker widget (`spell_picker.js`) lets the GM build the list from chips on the campaign settings form. On the player side, all three spell-picker fetch sites in `sheet_dnd5e.html` now thread `campaign_id`, and the `/api/open5e/spells` endpoint detects when `spell_list=<homebrew_class_slug>` is paired with `campaign_id`: it resolves the curated list via the local Open5e mirror when available, falling back to per-spell Open5e fetches when not. Both paths apply the request's search and level filters in memory before responding. Schema migration auto-applies on next boot.

### Added
- `app/static/spell_picker.js` — reusable typeahead + chip widget. Auto-inits every `[data-spell-picker]` on `DOMContentLoaded` and on `<details>` open. Initial state from `data-spells` (objects or bare slugs); syncs to a hidden `spell_list_json` input on form submit.
- `get_spells_by_slugs(slugs)` helper in `app/open5e_local.py` — single-pass in-memory bulk lookup against the local mirror; returns spells in the requested order, skips unknown slugs.
- `_parse_spell_list_json` in `app/routes/tabletop_routes.py` — accepts either bare slug strings or `{slug: ...}` objects (so the picker's chip format round-trips cleanly), validates against the `[a-z0-9-]+` slug pattern, dedupes, caps at 500 entries.
- "Spell list" fieldset on every custom-class form (create + edit). Shows current count in the legend.
- `spell_count` field on `custom_classes_db` rows in both `/admin/stubs` (new table column) and `/admin/stubs.json`.

### Changed
- `CustomClass` model gains a `spell_list` JSON column (default `[]`). The DB-backed resolver provider now surfaces it in the returned record so future endpoints can read it without re-querying.
- `/api/open5e/spells` accepts an optional `campaign_id` parameter. When supplied alongside `spell_list=<class_slug>` that matches a homebrew class, the endpoint returns spells from the curated list rather than asking Open5e for "spells whose `spell_lists` field contains a non-existent homebrew slug." Local mirror path is single-pass; mirror-less fallback does sequential Open5e fetches with a 4s timeout each (lossy by design — individual failures are skipped).
- All three spell-picker fetch sites in `app/templates/sheet_dnd5e.html` (top-of-sheet search-by-name, per-class cantrip loader, and the spellbook search panel) now thread `CAMPAIGN_ID` when defined.

### Schema
- New column `custom_classes.spell_list` (JSON on Postgres, TEXT-with-JSON-default on SQLite). Default `[]`; existing rows backfilled by the `ALTER TABLE … NOT NULL DEFAULT '[]'` so no per-row migration is needed.
- `SCHEMA_VERSION` bumped from 23 to 24.

## [0.45.0] - 2026-05-11

**Schema version:** 23

**Commit summary:** Add custom base classes, repeatable-rows features editor, and admin surfacing

**Description:** Two parallel landings. First, a vanilla-JS features editor replaces the JSON textarea on every homebrew form — repeatable rows for name/level/desc with add+delete buttons, serialized to a hidden `features_json` input on submit so the server-side validator and 400-message machinery are unchanged. Second, GM-authored base classes mirror the subclass framework end-to-end: a new `custom_classes` table (slug, hit die, six proficiency strings, optional spellcasting ability, equipment, structured features) joined by a `_db_class_provider` registered ahead of the filesystem provider in the resolver chain; `/api/open5e/class-detail` and `/api/open5e/classes` accept `campaign_id` and merge campaign homebrew at the top with `is_custom: true`; GM-only CRUD form on the campaign settings page with the new features editor; admin stubs panel grows a "Campaign homebrew classes" section deep-linking to each owning campaign. MVP scope intentionally cuts class spell lists, per-rest resource counters, and multiclass prereqs — those are big enough surfaces to deserve their own iterations later. Schema migration auto-applies on next boot.

### Added
- `app/static/features_editor.js` — reusable rows widget. Auto-initialises every `[data-features-editor]` element on `DOMContentLoaded` and on any `<details>` open so the editor inside collapsed cards inits lazily. Each editor reads its initial state from `data-features` (JSON list) and syncs to the form's hidden `features_json` input on submit.
- `CustomClass` ORM model with unique constraint on `(campaign_id, class_slug)`, cascade delete from campaign, `SET NULL` on creator deletion.
- `_db_class_provider` + `_features_to_markdown` helper in `app/local_features.py` — the list-shaped features are flattened to a markdown blob with `### Heading` per feature so existing frontend consumers see the same shape they get from Open5e. Structured form is also exposed as `features_list` for future renderers.
- Three GM-only routes: `POST /campaign/{id}/custom-classes`, `POST /campaign/{id}/custom-classes/{class_id}`, `POST /campaign/{id}/custom-classes/{class_id}/delete`. Helpers: `_normalize_hit_die` (4–12 range), `_normalize_spellcasting_ability` (str/dex/con/int/wis/cha or blank).
- "Custom classes" section on the campaign settings page, settings-nav link, and corresponding section on `/admin/stubs` and `/admin/stubs.json` (`custom_classes_db` key).

### Changed
- Custom-subclass forms (both create and edit cards) now use the features editor instead of the raw JSON textarea. Server-side parsing is unchanged because the editor serializes to the same JSON shape on submit.
- `/api/open5e/class-detail` accepts an optional `campaign_id` parameter and threads it through the resolver as `scopes=["campaign:N", "global"]`. Campaign homebrew shadows the shipped SRD class with the same slug; without `campaign_id` behavior is identical to v0.44.0.
- `/api/open5e/classes` accepts `campaign_id` and merges campaign homebrew with `is_custom: true` at the top, deduping any Open5e/mirror entry whose slug a homebrew already covers.
- All four class-related fetches in `app/static/sheet.js` (class list × 2, class-detail × 2) now thread `CAMPAIGN_ID` when defined. localStorage cache keys for the class list embed the campaign id so homebrew doesn't bleed across campaigns.

### Schema
- New table `custom_classes` (id, campaign_id, class_slug, name, hit_die, prof_armor, prof_weapons, prof_tools, prof_saving_throws, prof_skills, spellcasting_ability, equipment, features JSON, created_by_user_id, created_at, updated_at) with `uq_custom_class(campaign_id, class_slug)`.
- `SCHEMA_VERSION` bumped from 22 to 23. Migration creates the table via `CustomClass.__table__.create(checkfirst=True)`.

## [0.44.0] - 2026-05-11

**Schema version:** 22

**Commit summary:** Surface campaign homebrew subclasses in the picker, the detail panel, and the admin stubs view

**Description:** Phase 3 of homebrew subclasses — the final wiring that makes GM-authored content actually appear to players. The sheet's subclass picker now passes `campaign_id` on both list (`/api/open5e/subclasses`) and detail (`/api/open5e/subclass-detail`) fetches; the list endpoint merges campaign homebrew at the top and dedupes any Open5e entry whose slug matches a homebrew row, so a campaign-authored `circle-of-the-moon` shadows the SRD one. The detail panel shows a small "Custom" badge next to the subclass name when the response source is `local-custom`. The localStorage cache key for subclass lists now embeds the campaign id so homebrew never bleeds across campaigns. The `/admin/stubs` panel grows a new "Campaign homebrew (DB-backed)" table listing every row in `custom_subclasses` with a deep-link to its campaign's settings page.

### Added
- `is_custom: true` flag on rows in `/api/open5e/subclasses` responses for campaign homebrew (when `campaign_id` is passed).
- "Custom" pill badge next to the subclass name in `renderSubclassFeatures()`, shown only when `data.source === "local-custom"`.
- "Campaign homebrew (DB-backed)" section on `/admin/stubs` showing every `custom_subclasses` row with campaign, class, slug, feature count, author, and last-updated. Same data exposed under `/admin/stubs.json` as `custom_subclasses_db`.

### Changed
- `/api/open5e/subclasses` now accepts an optional `campaign_id` parameter. Custom rows for that campaign (filtered by `class_slug` and `search` when present) prepend the Open5e results, and any Open5e entry with a slug already covered by homebrew is filtered out so the picker doesn't show duplicates. Behavior without `campaign_id` is unchanged.
- All six `subclass-detail` / `subclasses` fetches in `app/static/sheet.js` now thread `CAMPAIGN_ID` (when defined) into the query string. Standalone-character sheets outside a campaign continue to call the global-only resolution path.
- localStorage cache keys for subclass lists are suffixed with `_c<id>` so one campaign's homebrew can't surface in another campaign's picker via a stale cache entry.

## [0.43.0] - 2026-05-11

**Schema version:** 22

**Commit summary:** Add GM-only authoring UI for custom subclasses on the campaign settings page

**Description:** Phase 2 of homebrew subclasses — a GM-facing form for the table v0.42.0 introduced. The campaign settings page now has a "Custom subclasses" section listing every homebrew authored for this campaign (collapsible per-row edit cards) plus a "+ New custom subclass" form. Each row carries a name, parent class slug, flavor description, and a features list authored as JSON (`[{"name","level","desc"}, ...]`). The server slugifies the parent class and derives the subclass slug from its display name; the slug is fixed at creation so character sheets referencing it survive renames. JSON parse errors and structural problems (missing name, non-int level, list-vs-object) come back as 400s with messages naming the offending entry. Three new POST routes — create / update / delete — all gated by the existing `_user_is_gm` check; non-GMs get 403 on every path. Frontend wiring to surface the homebrew in the subclass picker lands in phase 3.

### Added
- `POST /campaign/{id}/custom-subclasses` (create), `POST /campaign/{id}/custom-subclasses/{sub_id}` (update), `POST /campaign/{id}/custom-subclasses/{sub_id}/delete` — all GM-only, all redirect 303 to `/campaign/{id}/settings#custom-subclasses`.
- Helpers in `app/routes/tabletop_routes.py`: `_slugify_for_subclass` (shared by class and sub slug normalization), `_parse_custom_subclass_features` (returns a normalised list or raises HTTPException(400) with a human-readable message), `_require_gm_for_campaign` (single guard used by all three mutation routes).
- "Custom subclasses" section in `app/templates/campaign_settings.html` with one `<details>` edit card per existing row plus a separate `+ New` create form. Each row's features render via Jinja's `tojson(indent=2)` filter into a monospaced textarea so the GM can edit them as-is and Save.
- Settings-nav link for the new section.

### Changed
- `GET /campaign/{id}/settings` now queries `CustomSubclass` for the campaign and threads the rows into the template context as `custom_subclasses`.

## [0.42.0] - 2026-05-11

**Schema version:** 22

**Commit summary:** Add custom_subclasses table and DB-backed resolver provider for campaign homebrew

**Description:** Phase 1 of GM-authored homebrew subclasses — backend only, no authoring UI yet. A new `custom_subclasses` table stores per-campaign homebrew (parent class slug, sub slug, name, flavor, features JSON, creator). The local-features resolver gains a `_db_subclass_provider` ahead of the filesystem provider, so a row matching the active campaign shadows any shipped SRD content with the same slug. `/api/open5e/subclass-detail` now accepts an optional `campaign_id` query parameter — when present, the resolver is called with `scopes=["campaign:N", "global"]` and the response's `source` is `"local-custom"` for homebrew or `"local-srd"`/`"open5e_*"` as before. Frontend callers don't pass `campaign_id` yet, so homebrew won't surface until phase 3 wires that through — for now, rows can be inserted by SQL for testing. Schema bump auto-applies on next boot via a new `_apply_inline_migrations()` block.

### Added
- `CustomSubclass` ORM model in `app/models.py` with unique constraint on `(campaign_id, class_slug, sub_slug)` and cascade delete from the parent campaign. Creator FK is `SET NULL` so deleting a user doesn't lose their homebrew.
- `_db_subclass_provider` in `app/local_features.py` registered ahead of the filesystem provider. Walks `campaign:<id>` scope strings in caller-supplied order, returns the matching row as `(record, "local-custom")` or `None` so the next provider takes over.
- Optional `campaign_id` query parameter on `/api/open5e/subclass-detail`. When supplied, the resolver scopes are `["campaign:N", "global"]`; when absent, behavior is identical to v0.41.0.
- `db` keyword on `resolve_class` / `resolve_subclass` (and threaded into provider signatures). FS providers ignore it; the DB provider returns `None` when `db` is absent so the resolver is safe to call without a session.

### Schema
- New table `custom_subclasses` (id, campaign_id, class_slug, sub_slug, name, flavor, features JSON, created_by_user_id, created_at, updated_at) with `uq_custom_subclass(campaign_id, class_slug, sub_slug)`.
- `SCHEMA_VERSION` bumped from 21 to 22. Migration creates the table via `CustomSubclass.__table__.create(checkfirst=True)` — additive, no manual operator action.

## [0.41.0] - 2026-05-11

**Schema version:** 21

**Commit summary:** Add admin stubs panel listing local overrides and Open5e-fallback misses

**Description:** New admin page at `/admin/stubs` shows the inverse views of the local-first resolver: (a) every class / subclass file currently authored under `app/data/local/` and (b) the in-memory miss registry — every class / subclass lookup since process start that fell through to Open5e — sorted by hit count so the most-requested content surfaces first. Each miss row shows the upstream source it landed on (`open5e_mirror`, `open5e_live`, `open5e_unreachable`), first/last seen timestamps, and the class context for subclass lookups. Operators get a "Clear registry" button (in-memory only) and a `GET /admin/stubs.json` snapshot for scripted authoring pipelines that want to diff misses against on-disk overrides. Linked from the admin home under a new "Content tools" section.

### Added
- `GET /admin/stubs` (HTML), `POST /admin/stubs/clear` (clears the registry), `GET /admin/stubs.json` (JSON snapshot) — all gated by `require_admin`.
- `app/templates/admin_stubs.html` — two-section layout (Local overrides on disk · Stubbed content from Open5e).
- "Content tools" section on the admin home linking to the new panel.

## [0.40.1] - 2026-05-11

**Schema version:** 21

**Commit summary:** Restructure local_features for future custom-subclass support with provider chain and scopes

**Description:** Groundwork for per-campaign / per-user custom subclasses without committing to a specific authoring UX yet. The resolver in `local_features.py` is now a provider chain that returns `(record, source)`; adding a DB-backed provider for custom content later is a single list entry. Records carry an optional `scope` (default `"global"`) and `owner` (default `null`); resolver callers may pass a `scopes` priority list, and only matching records are returned — so a future endpoint can call `resolve_class(slug, scopes=["campaign:42", "global"])` to surface campaign-specific homebrew before the shipped SRD content. The proxy responses now echo `source` (e.g. `"local-srd"`, `"local-custom"`, `"open5e_mirror"`, `"open5e_live"`, `"open5e_unreachable"`) so the frontend can later render edit affordances only on custom content. Frontend ignores the field today — fully backward compatible, no operator action required.

### Changed
- `app/local_features.py` switched from a direct file-open API to a provider chain. New entry points `resolve_class(slug, *, scopes=None)` and `resolve_subclass(class_slug, sub_slug, *, scopes=None)` return `(record, source)` tuples; old `get_class` / `get_subclass` removed (only two callers in the just-shipped v0.40.0 — no compat shim needed).
- `_fs_class_provider` and `_fs_subclass_provider` are the only registered providers today. Each filters records by scope and derives a source label from the file's `source` field (`"srd"` → `"local-srd"`, `"custom"` → `"local-custom"`).
- `/api/open5e/class-detail` and `/api/open5e/subclass-detail` now include a `source` string on every response. Local hits report `"local-srd"`/`"local-custom"`; fallbacks report the upstream label that was already being recorded in the miss registry.
- Druid class + Land/Moon subclass JSON files gain `scope: "global"`, `source: "srd"`, `owner: null`. Replaces the previous `_local: true` marker. Old marker removed.

## [0.40.0] - 2026-05-11

**Schema version:** 21

**Commit summary:** Add local-first resolver for class and subclass feature data with miss tracking

**Description:** Class and subclass detail lookups now consult `app/data/local/` before reaching for Open5e. If a matching JSON file exists, it's returned verbatim and no upstream call is made; otherwise the previous resolution chain (LOCAL_OPEN5E mirror → live `api.open5e.com` → empty stub) still runs, and the fallback is recorded in an in-memory miss registry so an admin panel (forthcoming) can list "still stubbed from Open5e" entries by request frequency. The first authored example is the Druid class plus Circle of the Land and Circle of the Moon subclasses — picking these because the live `v1/subclasses/` endpoint has been unreliable. No operator action required; with no local files on disk, behavior is identical to v0.39.0.

### Added
- New module `app/local_features.py` with `get_class`, `get_subclass`, `record_miss`, `list_misses`, `list_local_classes`, `list_local_subclasses`. Files live under `app/data/local/class_features/<slug>.json` and `app/data/local/subclass_features/<class_slug>__<sub_slug>.json` (class-prefixed naming disambiguates same-named subclasses).
- Local override files: `druid.json` (class, full SRD-style features blob + proficiencies), `druid__circle-of-the-land.json`, `druid__circle-of-the-moon.json` (structured `[{name, level, desc}]` features matching the shape `parse_subclass_features` already produces).
- Slug validation in the resolver rejects path-traversal attempts (`..`, slashes) before touching the filesystem.

### Changed
- `/api/open5e/class-detail` and `/api/open5e/subclass-detail` now check `local_features` first. Misses are tagged by source (`open5e_mirror`, `open5e_live`, `open5e_unreachable`) so the upcoming admin view can prioritise authoring work by usage.

## [0.39.0] - 2026-05-11

**Schema version:** 21

**Commit summary:** Cache beast favorites locally so the picker works offline and skips Open5e on open

**Description:** Beast favorites added in v0.38.0 were stored as bare Open5e slugs, which meant the picker had to make one live `/api/open5e/creature/{slug}` call per favorite every time it opened. That broke the ★ Favorites section whenever Open5e was unreachable, and added unnecessary round-trips on every Wild Shape. Each favorite is now stored as a full lite stat block (`{slug, name, cr, type, size, hp, ac, source}`) right on the sheet, so the picker renders the Favorites section from local data with zero network calls. Legacy v0.38.0 favorites (bare slug strings) keep working — the picker backfills them on first open and persists the resolved data, so any second open is a cache-hit even if Open5e goes down between sessions. Star-toggling a creature now snapshots its lite shape from the current search results (the row the user just clicked has all the data we need), so adding new favorites is also network-free.

### Changed
- `sheet["favorite_beasts"]` schema changes from `["wolf", "brown-bear"]` to `[{slug, name, cr, type, size, hp, ac, source}, …]`. JSON-only on `Character.sheet`, no SQL migration. Normalization in `app/sheet_templates.py` accepts both shapes and coerces bare strings to `{slug: s}` so legacy data round-trips cleanly.
- `BeastPicker` no longer fetches favorites on open when every entry has a complete cache (the common case after a single use). Backfills only happen for entries missing `name`/`cr` — i.e. legacy slug-only entries or favorites added when Free pick was on and the row had partial data. Backfilled data is persisted so the next open is a cache-hit.
- Star toggle now snapshots the picker row's lite shape directly into the saved array rather than just the slug, so new favorites are immediately offline-ready.

### Added
- Top-of-file JSDoc on `beast_picker.js` documents the new `favorites` shape with example data + the offline-rendering guarantee.

### Fixed
- Open5e being unreachable no longer hides the ★ Favorites section. Slug-only entries that fail to backfill still render with the slug as the row label so the user can see and unstar them.

**Schema version:** 21

**Commit summary:** Add favorite beast forms with a ★ Favorites section at the top of the picker

**Description:** Players can now star creatures in the Wild Shape / Polymorph beast picker. Starred forms render in a "★ Favorites" section pinned to the top of the list panel — above the live search results — so the player's go-to forms are one click away no matter what the current search returns. Click the ☆ on any row to favorite, ★ to unfavorite. The list is persisted per-character at `sheet["favorite_beasts"]` (a list of Open5e creature slugs) and synced via `/sheet-fields` PATCH so refreshes don't lose it. When the picker opens, every favorite is fetched in parallel from a new `/api/open5e/creature/{slug}` lite-shape endpoint so the Favorites section renders the same rows (name, CR, type) as the search results. Works from both the full sheet's Wild Shape / Polymorph buttons and the tabletop mini-sheet's transform bar; favorites that match the current search term stay visible in both sections so they're never hidden behind a typo. Dead favorites (slugs that 404 upstream — e.g. renamed creatures) are silently skipped instead of breaking the picker.

### Added
- `sheet["favorite_beasts"]` field on the D&D 5e template — list of Open5e creature slugs. Default `[]`. Normalizer in `app/sheet_templates.py` coerces non-strings to drop, strips whitespace, dedupes, and caps at 50 entries.
- New endpoint `GET /api/open5e/creature/{slug}` returning the lite shape (`{slug, name, cr, type, size, hp, ac, source}`) shared with the monsters list proxy. 404 propagates so the picker can quietly skip dead favorites without crashing.
- `favorite_beasts` added to `_SHEET_PATCH_KEYS` (so the picker's persist call works) and to the server-managed preserve list in `update_sheet` (so a full sheet Save without it doesn't wipe the list).
- ★ toggle button on every picker row. Clicks intercepted before the row-select handler via `stopPropagation` so toggling never accidentally picks the beast. The picker PATCHes `/sheet-fields` on every toggle and calls an optional `onFavoritesChange` callback so the caller can refresh its cached copy.
- `window._savedBeastFavorites` injected into `sheet_dnd5e.html` and passed to `BeastPicker.open(...)` from both the legend "🐺 Wild Shape" / "🦌 Polymorph" buttons and the Class Resources "Use" button special-case.
- `data-favorites` JSON attribute on the tabletop mini-sheet's `mini-transform-bar`, plumbed into `BeastPicker.open(...)`. The `onFavoritesChange` callback writes back to the same attribute so a re-open without page reload sees the new list.

### Changed
- Beast picker list panel renders two sections instead of one — `★ Favorites` (always at top when populated) and `All beasts` (the live search results). When a search term is active and any favorite matches the term, the header switches to `Other matches` for the bottom section to make the relationship explicit.
- Status bar count now leads with `★ N favorites` when any are present, e.g. `★ 3 favorites · 12 of 50 on this page match the beast / CR filter`.

## [0.37.4] - 2026-05-11

**Schema version:** 21

**Commit summary:** Fix beast picker name search by using Open5e v2's name__icontains filter

**Description:** Typing "wolf" in the Wild Shape beast picker returned the same list as an empty search. Root cause: the proxy was sending `?search=wolf` to Open5e v2, but v2 is django-filter based and silently ignores DRF's `SearchFilter` parameter — case-insensitive name matching uses `?name__icontains=wolf` instead. The proxy now sends the v2 idiom. To insulate the picker against any future API change that might rename or drop the filter, the client also re-applies the name filter locally — so even if the server forwards an unrecognized param, the visible list still narrows to what the user typed.

### Fixed
- `/api/open5e/monsters` proxy now forwards search terms as `name__icontains=` instead of `search=` so Open5e v2 actually applies them. v1 endpoints elsewhere in the codebase (spells, classes, races, conditions) continue using `search=` since v1 supports it.
- `beast_picker.js` adds a client-side `name.includes(query)` filter on top of the server results, so the search box narrows the list even when the upstream filter is ignored, and also narrows results when Free pick is enabled (which intentionally drops the server-side filter).

## [0.37.3] - 2026-05-11

**Schema version:** 21

**Commit summary:** Parse Open5e v2 creature shape end-to-end, server-filter beasts by type and CR

**Description:** The Wild Shape / Polymorph beast picker was talking to the Open5e v2 creatures API but parsing every response with v1 field names. v2 renames `challenge_rating` to `cr`, nests ability scores under `ability_scores.{short}`, saving throw proficiencies under `saving_throws`, and skill proficiencies under `skill_bonuses` — so every transformed beast was getting template-default stats (10/10/10/10/10/10, no CR-derived proficiency bonus, no save or skill proficiencies). On top of that, the picker fetched 50 random creatures of all types and filtered client-side, which routinely left a Druid Lv 2 player staring at "No matches" because no beasts within their CR cap happened to land on page one. This release rewrites the integration to handle both API versions and to push the type / CR filter into the upstream query so the page returned is actually useful.

### Added
- New server-side helpers in `app/routes/tabletop_routes.py`: `_o5e_cr(m)` reads `cr` (v2) with fallback to `challenge_rating` (v1); `_o5e_ability(m, short, full)` reads ability scores from either the v2 nested `ability_scores` dict or the v1 top-level keys; `_o5e_save_prof` and `_o5e_skill_prof` do the same for saving-throw and skill proficiencies.
- `/api/open5e/monsters` now accepts two optional query params: `type_filter=beast` (forwarded to v2 as `type__key=beast`) and `cr_max=1/4` (parsed to a decimal and forwarded as `cr__lte=`). If the upstream API rejects the filter (4xx), the proxy retries once without it so the picker stays usable.
- Beast picker UI surfaces a live count in the modal footer — e.g. "7 of 50 on this page match the beast / CR filter" — so users can tell whether the API returned anything and how aggressively the filter is chopping.

### Fixed
- Transformed beasts now get correct ability scores, save proficiencies, and skill proficiencies from v2 responses. Previously every transform produced a creature with stat-line `10/10/10/10/10/10` and no proficiencies.
- The proficiency-bonus calculation derived from CR was always reading 0 (because `m.get("challenge_rating")` returned `None` on v2), so every wild-shaped creature had Prof +2 regardless of CR. Now derived correctly from the real `cr` value.
- Beast picker empty-state messaging is clearer: distinguishes between an empty API page ("API returned an empty page — try a different search term") and a filter mismatch ("No beasts within your CR cap on this page. Try a search term, or enable Free pick to bypass the filter").

### Changed
- Beast picker sends `type_filter=beast&cr_max={cap}` on every search when Free pick is off; toggling Free pick re-runs the search without those filters so the result set actually broadens (previously toggling only re-filtered the existing local list, which was already trimmed by the server).

## [0.37.2] - 2026-05-11

**Schema version:** 21

**Commit summary:** Fix beast picker crash on Open5e v2 dict fields and auto-populate the list on open

**Description:** The Wild Shape / Polymorph beast picker threw `(r.type || "").toLowerCase is not a function` and rendered no results on search. Root cause: the Open5e v2 creatures endpoint returns `type` and `size` as `{"key": "beast", "name": "Beast"}` dictionaries for some creatures rather than plain strings (the v1 API returned strings). Our `/api/open5e/monsters` proxy passed the values through verbatim, and the picker's client-side filter called `.toLowerCase()` on whatever it got — which crashed for dicts. Fix normalizes the values server-side with a new `_o5e_str()` helper and adds defensive coercion on the client too. While here: the picker now auto-runs an empty search on open (mirroring the Spell Browser UX) so the list is pre-loaded with beasts the character can transform into — no more "type something to start" empty state.

### Fixed
- `/api/open5e/monsters` (and the import-monster / `_open5e_to_dnd5e_sheet` / transform CR-check code paths) now coerce Open5e v2 `type` and `size` fields to plain strings via a new `_o5e_str()` helper. Dicts with `name` / `key` fields collapse to their display name; raw strings pass through unchanged.
- Client-side `beast_picker.js` adds a `_str()` defense layer that does the same coercion, so even if a future API change slips an unexpected shape through, the filter and detail panel no longer crash.

### Changed
- Beast picker now auto-runs a search the moment it opens — list panel shows "Loading beasts…" until the first page of results lands, then renders them. Users can refine by typing instead of starting from a "Search to browse beasts" prompt.

## [0.37.1] - 2026-05-11

**Schema version:** 21

**Commit summary:** Route the Wild Shape resource Use button into the beast picker

**Description:** The "⚡ Use" button on the Wild Shape entry in the Class Resources panel now opens the beast picker overlay (the same one the legend's "🐺 Wild Shape" button uses) instead of silently decrementing the counter and posting a generic "used Wild Shape" announcement. The /transform endpoint already decrements the `wild-shape` resource as a side effect of a successful transform, so the count stays consistent. Every other resource (Channel Divinity, Rage, Action Surge, Superiority Dice, …) keeps its original click-to-spend-and-announce behaviour. If the picker module isn't loaded (e.g. on a standalone sheet outside a live campaign), the click falls through to the plain decrement path so the button still does *something* useful.

### Changed
- `app/templates/sheet_dnd5e.html` Class Resources `.res-use` click handler special-cases `key === 'wild-shape'`: collects druid level + Moon subclass + character level from the roster, then calls `window.BeastPicker.open({source: 'wild-shape', …})`. Falls back to the existing `postUse(...)` decrement when the picker isn't available.

## [0.37.0] - 2026-05-11

**Schema version:** 21

**Commit summary:** Track per-class per-level HP rolls with an in-sheet picker, multi-class aware

**Description:** D&D 5e characters can now record the HP gained at each class level. A new "HP per Level" table appears inside the character edit panel (the one that opens when you click ✏ Edit by the name/level area) and shows one row per class level — pre-filled with what's stored, blank otherwise. Each non-locked row has a 🎲 Roll button that rolls `1d{hit-die}+{CON}` (using the campaign roll endpoint when in a live session so the table sees the result, falling back to a local random for standalone characters). Level 1 of the *first* class on the roster is locked to `max die + CON` per RAW; every other level (including level 1 of any subsequent multiclass) is rolled or hand-entered. A yellow banner appears above the table when any non-locked slot is still empty, prompting existing characters to backfill on their first edit. The picker also offers "Use average for empty" (fills empty slots with ⌊dN/2⌋+1+CON, the PHB optional rule) and "Apply sum → Max HP" (sets the form's Max HP to the sum of every per-level entry, and bumps current HP if it was already at the old max). Multi-classing is fully supported: `sheet["hp_rolls"]` is keyed by class slug (e.g. `{"druid": [10, 6, 7, 5, 8], "wizard": [4, 3]}`) and `normalize_dnd5e_sheet` keeps each per-class list synchronized with that class's current level — adding a level appends an empty slot, removing a level trims, dropping a class removes its history. Every edit PATCHes `/sheet-fields` immediately so refreshes don't lose work, and the field is on the server-side preserve list so a full sheet Save can't wipe it. Schema is JSON-only — no migration required.

### Added
- `sheet["hp_rolls"]` field on the D&D 5e template — `{class_slug: [int, …]}`. Default `{}`. Normalizer in `app/sheet_templates.py` trims/pads each list to its class level, drops orphaned class entries, and coerces non-integer values to 0.
- "HP per Level" subsection inside `#char-edit-panel` in `sheet_dnd5e.html` with a yellow incompleteness banner, per-class blocks (one row per level with input + 🎲 Roll button), subtotals per class, a running grand sum, and two helper buttons: "Apply sum → Max HP" and "Use average for empty".
- Inline IIFE renders the picker from the live roster and `window._savedHpRolls`. Re-renders on `vtt:mc-changed` (level up/down, swap class) and on CON changes. Each input change or 🎲 click writes through the existing `/sheet-fields` PATCH endpoint (works on both campaign and standalone characters).
- `hp_rolls` added to `_SHEET_PATCH_KEYS` in `tabletop_routes.py` so the patch endpoint accepts it, and to the server-managed-preserve list in `update_sheet` so a full Save without `hp_rolls` doesn't wipe the field (mirrors the pattern that fixed `active_form` / `prior_form` in v0.35.4).

## [0.36.2] - 2026-05-11

**Schema version:** 21

**Commit summary:** Fix active-form banner rendering for every D&D 5e character regardless of transform state

**Description:** The "✨ Revert to true form" banner at the top of the full D&D 5e sheet was appearing for every character — including freshly created ones who had never been Wild Shaped or Polymorphed. Brand-new characters from any preset (including the new Druid Moon Lv 5 preset) loaded with the banner already showing. Root cause: the banner's `<div>` carried an inline `style` attribute with **two** `display:` declarations — `display:none` (when `active_form` was unset) followed later in the same string by `display:flex` (for layout). CSS resolves duplicate declarations by taking the **last** one, so `display:flex` always won and the banner rendered no matter what. Fix wraps the entire banner in a Jinja `{% if _af %}` so it isn't emitted at all when the character isn't transformed. The single JS reference (`document.getElementById('revert-form-btn')`) already uses optional chaining, so removing the element when there's no active form has no other side effects.

### Fixed
- Active-form banner on `sheet_dnd5e.html` no longer renders when `sheet["active_form"]` is unset. Brand-new characters (from a preset or blank) load without a spurious "Reverted to true form" button.

**Schema version:** 21

**Commit summary:** Make Skills and Spells sections collapsible on the tabletop mini-sheet with per-character memory

**Description:** The tabletop player drawer's mini-sheet now lets each player collapse the Skills and Spells sections to keep the drawer tidy when those panels aren't needed. Click the section label (or its chevron) to toggle. The collapse state persists in `localStorage` under a per-character + per-section key (`simplevtt_mini_collapse_<charId>_<skills|spells>`) so the next page load remembers exactly how each character was left. A separate storage namespace from the full-sheet fieldset collapsibles means the two contexts are independent — collapsing Skills on the mini-sheet doesn't affect the same section on the standalone full sheet.

### Added
- New `.mini-collapsible` / `.mini-collapsible-header` / `.mini-collapsible-body` / `.mini-collapsible-chevron` classes in `tabletop.html`. Headers show a rotating chevron and toggle the body's `display:none` via a `collapsed` CSS class on the wrapper.
- One-line IIFE on the tabletop that wires up every `.mini-collapsible` on page load: reads its persisted state, applies the `collapsed` class if needed, and binds a click handler that toggles + persists. Clicks inside any nested `<button>` / `<a>` / `<input>` / `<select>` / `<textarea>` are ignored so existing controls (cast / strike / slot pips / rest) still work.
- Wrapped both the Skills and Spells sections in the new collapsible markup. The Spells wrapper sits outside the existing `mini-spells` container so its slot pips and cast buttons stay intact.

**Schema version:** 21

**Commit summary:** Add character presets dropdown with six pre-built leveled D&D 5e characters for fast testing

**Description:** The "+ New Character" panel on `/characters` now has a "Start from" dropdown that pre-populates the sheet with a fully-built, leveled-up character instead of an empty default. Six D&D 5e presets are included to exercise the framework's feature surface in one click each: 🐺 Moon Druid Lv 5 (Wild Shape), ⚔ Battle Master Fighter Lv 5 (Action Surge / Superiority Dice), ✨ Life Cleric Lv 5 (Channel Divinity / prepared spells), 🔥 Evocation Wizard Lv 5 (Fireball / Sculpt Spells), 💢 Berserker Barbarian Lv 4 (Rage), and 🗡 Thief Rogue Lv 3 (Sneak Attack). Each preset comes with class roster, ability scores, HP, AC, speed, saving throw & skill proficiencies, attacks, prepared spells, spell slots, race, background, and notes describing the class's signature abilities. The two existing "Blank — Generic" and "Blank — D&D 5e" options remain as defaults at the top of the list, preserving current behaviour for anyone who wants an empty sheet. The Class Resources panel auto-fills on first sheet load (no need to pre-populate Rage / Channel Divinity / Wild Shape counters — they appear when the player opens the sheet).

### Added
- New module `app/character_presets.py` with a `PRESETS` registry, helper builders (`_dnd5e_base`, `_add_class`, `_add_attack`, `_add_spell`, `_set_spell_slots`, etc.), and six leveled D&D 5e characters plus two blank options. Add presets by appending to `PRESETS`.
- "Start from" dropdown on both creation forms in `app/templates/all_characters.html` (campaign tab and standalone tab) with the preset's description shown below the selector and the suggested name auto-filled (only until the user types something custom).
- `preset` form field handled in `POST /characters/new` and `POST /characters/new-standalone`. When the key is unknown or blank, the existing behaviour (blank sheet for the campaign's game system / chosen template) is preserved.

### Changed
- The standalone creation form's "Sheet Type" select becomes a hidden field — the preset choice now drives the template implicitly, so users don't have to keep template and preset in sync manually.

## [0.35.4] - 2026-05-11

**Schema version:** 21

**Commit summary:** Fix Wild Shape characters getting permanently stuck after a sheet save

**Description:** A druid (or polymorphed character) who clicked Save on the full sheet while transformed would become permanently stuck in beast form. Root cause: `buildSheet()` in `sheet.js` only emits sheet fields that have form inputs, and `active_form` / `prior_form` are server-managed with no inputs — so the save payload never included them. The `update_sheet` endpoint then did `char.sheet = body["sheet"]` which **replaced the entire sheet**, wiping both transform fields. `active_form` being gone meant the banner disappeared from a fresh sheet load, but the BEAST stats were still in `sheet["hp"]` / `sheet["abilities"]` / etc. Even more visibly: when `active_form` was still present (e.g. via the mini-sheet banner) but `prior_form` had been wiped, clicking Revert 409'd with "Character is not currently transformed" — because the endpoint checked `prior_form` first. This release fixes the bug going forward AND provides a rescue path for already-stuck characters.

### Fixed
- `update_sheet` (`POST /api/campaign/{id}/character/{char_id}`) now preserves server-managed transform fields (`active_form`, `prior_form`) when the client submits a sheet save without them. Saving while transformed no longer wipes out the form snapshot or strands the player.
- `/revert` is now tolerant of "stuck" characters: if `active_form` is set but `prior_form` was lost (legacy data from before this fix), the endpoint still clears `active_form` and returns `{ok: true, stats_restored: false}`. The UI surfaces a clear alert telling the player to edit HP / abilities / AC / speed / attacks back to their true-form values manually. Only returns 409 now if BOTH fields are unset (genuinely not transformed).
- Roll-log "Reverted to true form" card includes a "prior stats not restored, please edit manually" suffix when the rescue path triggers, so the GM and table see what happened.

### Changed
- Revert handlers on the full sheet (`sheet_dnd5e.html`) and tabletop mini-sheet (`tabletop.html`) read `stats_restored` from the JSON response and pop an alert before reloading when it's `false`.

**Schema version:** 21

**Commit summary:** Open full character sheet in a new tab and retire the in-page popup modal

**Description:** The mini-sheet's "Open full sheet →" button now opens the standalone D&D 5e sheet in a new browser tab instead of injecting it as a popup modal over the tabletop. Double-clicking a token on the map does the same. The retired modal path used a DOMParser+innerHTML injection that **stripped every inline `<script>` block from the sheet template** before mounting it, then re-fetched only `sheet.js` and ran it. That meant features wired up in inline scripts — Wild Shape / Polymorph buttons, the Class Resources panel, the Revert flow, short/long-rest handlers, the subclass picker, spell-slot pip renderer, transform field-lock — all silently no-op'd inside the modal context. Now the full sheet always loads via the canonical `/campaign/{id}/character/{cid}/sheet` route with every inline script intact, and `CAMPAIGN_ID` is set lexically (the safe pattern). No more silent feature gaps depending on which way you opened the sheet.

### Changed
- `app/templates/tabletop.html`: mini-sheet "Open full sheet →" is now an `<a target="_blank" rel="noopener">` pointing at the standalone sheet route. The `<div id="modal-root">` mount point and the now-orphaned `.modal-bg` / `.modal` CSS rules are removed.
- `app/static/tabletop.js`: `window.openSheet(charId)` is now a thin `window.open(url, '_blank', 'noopener')` helper. The DOMParser injection, `_sheetJs` cache, and `window.closeSheet` definition are removed. Canvas token double-click still calls `openSheet` and so also opens a new tab.

### Removed
- In-page popup-modal rendering of the character sheet on the tabletop. Inline `onclick="closeSheet()"` buttons inside the sheet template still work because `character_page.html` (the standalone page) defines its own `window.closeSheet` that navigates back to the character list.

## [0.35.2] - 2026-05-11

**Schema version:** 21

**Commit summary:** Fix Revert and Use buttons not working on the standalone D&D 5e sheet

**Description:** On the standalone D&D 5e sheet (the `/campaign/{id}/character/{cid}/sheet` route), clicking "✨ Revert to true form" did nothing — and the same bug silently disabled every "Use" button in the Class Resources panel from calling the live `/resource` endpoint. Both features had been working only on the tabletop modal path because of a scoping mistake in the inline IIFEs introduced in v0.34.0 and v0.35.0. The two blocks read `window.CAMPAIGN_ID`, but `CAMPAIGN_ID` on the standalone sheet page is declared with `const` at script-top-level (in `character_page.html`) — a classic-script top-level `const` lives in the Script Record's lexical environment and is **not** copied onto `window` or `globalThis`. So `window.CAMPAIGN_ID` was always `undefined`, the early-return at the top of each IIFE fired, and no click handler was ever attached to the Revert button (or to the live-broadcast path of the resource Use buttons). The fix reads `CAMPAIGN_ID` via a bare-identifier `typeof` guard — the same pattern already used throughout `sheet.js` — and stores it as `_CAMPAIGN_ID` inside each IIFE to avoid shadowing the outer binding.

### Fixed
- Revert button on the standalone D&D 5e sheet now actually POSTs to `/api/campaign/{id}/character/{cid}/revert` and reloads. Previously the inline IIFE's early-return prevented its click handler from ever being attached.
- Class Resources "⚡ Use" buttons on the standalone sheet now also broadcast the spend via `/resource` so other clients (mini-sheet, popped roll log) see the WS update. Previously the live-broadcast path was guarded by the same broken `window.CAMPAIGN_ID` check, so spends only updated the local form state — they neither persisted server-side nor announced in chat until the next full sheet Save.

## [0.35.1] - 2026-05-11

**Schema version:** 21

**Commit summary:** Surface Wild Shape / Polymorph buttons on the tabletop mini-sheet

**Description:** The Wild Shape / Polymorph framework introduced in v0.35.0 was previously only reachable from the standalone D&D 5e sheet. This release surfaces the same beast picker on the tabletop player drawer's mini-sheet — Druid level 2+ characters see a "🐺 Wild Shape" button next to their rest controls; characters with the Polymorph spell get a "🦌 Polymorph" button. When transformed, the mini-sheet shows the active form (e.g. "🐺 Wolf CR 1/4") with a "✨ Revert" button. The picker modal markup is now a shared Jinja partial (`_beast_picker_modal.html`) and the open/search/transform logic moves into a reusable `app/static/beast_picker.js` module so the sheet and tabletop both call the same code path. Server endpoints and CR-cap rules are unchanged from v0.35.0.

### Added
- New shared partial `app/templates/_beast_picker_modal.html` and module `app/static/beast_picker.js` (exposes `window.BeastPicker.open({campaignId, characterId, source, druidLevel, isMoonDruid, characterLevel, onSuccess})`).
- Mini-sheet "Transform" bar in the tabletop player drawer with Wild Shape / Polymorph buttons (visibility driven by class roster and spell list, mirroring the standalone sheet) and an active-form badge + Revert button when a transform is in effect.
- Tabletop `transform_update` WS handler — when any character on the player drawer transforms or reverts (including from another open tab or the GM doing it on their behalf), the tabletop reloads so the mini-sheet picks up the new HP / AC / badge.

### Changed
- `app/templates/sheet_dnd5e.html` now `{% include %}`s the shared modal partial instead of carrying its own copy. The inline picker JS (search, render, confirm) was removed in favour of calling `window.BeastPicker.open(...)`. Button visibility, Revert wiring, and field locking remain inline.
- `beast_picker.js` is loaded ahead of `sheet.js` (in the standalone sheet) and ahead of `tabletop.js` (on the tabletop), so both consumers can call `BeastPicker.open(...)` synchronously.

## [0.35.0] - 2026-05-11

**Schema version:** 21

**Commit summary:** Add Wild Shape and Polymorph framework with beast picker and stat-swap

**Description:** D&D 5e characters can now transform into a beast and use its stat block as their own. Druids see a "🐺 Wild Shape" button in the Class Resources fieldset (level 2+) and any character with the Polymorph spell prepared sees a "🦌 Polymorph" button. Both open a beast picker overlay that searches Open5e, filters by type (Beast) and CR (Druid Wild Shape table for the source class, or target level / 4 for Polymorph), and supports a "Free pick (homebrew)" toggle that bypasses the cap. On Transform, the server snapshots the character's HP/AC/speed/abilities/skills/saves/attacks into `sheet["prior_form"]`, applies the beast's stats (Wild Shape keeps INT/WIS/CHA; Polymorph replaces all six per RAW), sets `sheet["active_form"]`, decrements the Wild Shape resource counter, and broadcasts a `transform_update` WS message. A yellow active-form banner pins to the top of the sheet with a "✨ Revert to true form" button; the revert restores the prior form (with optional Wild Shape HP overflow). Token image and size on the tabletop are unchanged in this release — token sync is a follow-up. Schema is JSON-only, no migration required.

### Added
- New `POST /api/campaign/{id}/character/{char_id}/transform` and `/revert` endpoints. The transform endpoint enforces 5e Wild Shape CR caps (CR ¼/½/1 at lv 2/4/8 for default druids; 1/2/3/4/5/6 at lv 2/4/6/8/10/12+ for Moon Druids) and Polymorph CR cap (target level ÷ 4), plus type=Beast — all bypassable with `free_pick: true`.
- Beast picker overlay in `app/templates/sheet_dnd5e.html`: search, type filter, CR cap status bar, Free-pick toggle, transform button.
- "🐺 Wild Shape" and "🦌 Polymorph" buttons in the Class Resources fieldset legend. Visibility driven by class roster (Druid lv2+) and spell list (`Polymorph` present).
- Active-form banner at the top of the sheet, rendering the beast name, CR/type, and a "✨ Revert to true form" button.
- Roll-log card announcing transformations and reverts (`feature_used` WS broadcast).
- WS handler `transform_update` triggers a reload on any open sheet for the same character so mini-sheet + full sheet stay in sync.

### Changed
- D&D 5e sheet template gains `active_form: None` and `prior_form: None` default fields; `normalize_dnd5e_sheet()` drops malformed values.
- Wild Shape resource (already in v0.34.0) is now decremented automatically when a Wild Shape transform succeeds.
- Non-HP combat fields (ability scores, AC, base AC, speed, initiative bonus) become read-only on the sheet while a transform is active. HP stays editable because the form takes damage during combat.

## [0.34.0] - 2026-05-11

**Schema version:** 21

**Commit summary:** Add Class Resources panel with auto-fill for trackable D&D 5e subclass features

**Description:** D&D 5e character sheets gain a new "Class Resources" fieldset between Spells and Inventory that tracks limited-use class and subclass features — Rage, Channel Divinity, Ki, Action Surge, Bardic Inspiration, Superiority Dice, Portent, Lay on Hands, and many more. A curated recipe table (`app/static/dnd5e_class_resources.js`) auto-populates the panel based on the multiclass roster, level, and ability modifiers; players can also add custom counters by hand. Each row has a pip-style spend UI for small pools, a +/− stepper for big pools (Lay on Hands HP), and a "Use" button that decrements the counter and broadcasts a `feature_used` card to the campaign roll log so the rest of the table sees who fired what. Counters reset automatically on short/long rest (both the form-only sheet buttons and the mini-sheet `/rest` endpoint). The schema is JSON-only on `Character.sheet["resources"]`, so no SQL migration is required — existing characters will see the panel empty until they click ↻ Auto-fill.

### Added
- New `app/static/dnd5e_class_resources.js` curated recipe table with ~20 PHB class & subclass features (Barbarian Rage, Bard Bardic Inspiration / Song of Rest, Cleric Channel Divinity, Druid Wild Shape / Land Natural Recovery, Fighter Second Wind / Action Surge / Indomitable, Monk Ki, Paladin Lay on Hands / Divine Sense / Channel Divinity / Cleansing Touch, Sorcerer Sorcery Points / Wild Magic Tides of Chaos, Wizard Arcane Recovery / Divination Portent, Battle Master Superiority Dice, Tempest Wrath of the Storm, War Priest, Rogue Stroke of Luck). Each recipe is a function of class level + ability mods + proficiency bonus.
- New "Class Resources" collapsible fieldset in `app/templates/sheet_dnd5e.html` with auto-fill, add-custom-counter, edit/delete, and a pip-spend or stepper UI per resource.
- New backend endpoint `POST /api/campaign/{id}/character/{char_id}/resource` accepts `{key, delta}` / `{key, set, …}` / `{key, reset: true}` payloads. Returns 409 `{"error":"no_uses"}` when a spend would underflow. Broadcasts a `resource_update` WS message.
- New WS message type `feature_used` rendered as a compact card in the main tabletop roll log (`tabletop.js`) and the popped-out roll log (`rolls_popout.html`).
- Short-rest / long-rest sheet buttons now also refill matching resources locally; the backend `/rest` endpoint (called by the tabletop mini-sheet) also refills resources and broadcasts `resource_update` for every refilled counter so any open panel re-pips.

### Changed
- `normalize_dnd5e_sheet()` cleans and clamps the new `sheet["resources"]` list on every load. Items missing required fields (key, name) are dropped.
- `app/static/sheet.js` deserialises the `resources_json` hidden textarea into `sheet.resources` on form submit, mirroring the `classes_json` pattern.
- D&D 5e sheet template gains a `"resources": []` default field.

## [0.33.19] - 2026-05-10

**Schema version:** 21

**Commit summary:** Fix subclass picker not showing on load by deferring render until inline helpers exist

**Description:** Class/subclass interactive pickers (Bonus Cantrip dropdown, Circle Spells / Domain Spells / Oath Spells panel with its variant chooser like Land Type) no longer require pressing the ↻ Sync button to appear. The root cause was a script execution-order race. The picker render path in `sheet.js` (`_renderSubclassBlock`) reads three `window.*` helpers — `_lookupSubclassData`, `_renderSubclassSpellPanel`, `_renderFeatureGrantsPanel` — that are defined inside an **inline** `<script>` block further down in `sheet_dnd5e.html`. When localStorage already had Open5e class/subclass lists cached from a prior visit, `sheet.js`'s async `_renderEditor()` resolved its `await`s on the microtask queue and ran `_renderAllSubclassBlocks()` to completion *before* the HTML parser advanced to that inline block. The helpers were still `undefined`, so the inline picker branches silently fell through and rendered the cards without their pickers. Clicking ↻ Sync triggered a fresh re-render after every script had run, which is why it appeared to "fix" things. The fix exposes `_renderAllSubclassBlocks` as `window._mcRenderSubclassBlocks` and adds a tiny inline `<script>` immediately after the helper-defining block that calls it once — by then everything is wired up and the pickers render on cold load. As a follow-on, when the player chooses a variant (e.g. picks "Coast" from Land Type) the choice now PATCHes to the server immediately, so it survives a refresh without an explicit Save click — previously the value only lived in the hidden roster textarea and was lost on reload.

### Fixed
- Subclass picker render race: `_renderAllSubclassBlocks` is now invoked a second time at the end of `sheet_dnd5e.html`, immediately after the inline `<script>` block that defines `window._lookupSubclassData` / `_renderSubclassSpellPanel` / `_renderFeatureGrantsPanel`. Previously, on warm-localStorage loads the initial render happened in microtasks during sheet.js execution, before the HTML parser had reached the inline block — so the helpers were undefined and the inline pickers (Bonus Cantrip dropdown, variant chooser inside Circle Spells / Domain Spells / Oath Spells) silently skipped. The renderer is exposed on `window` from `sheet.js` so the trigger script in the template can find it. Curated `dnd5e_subclass_spells.js` is also now loaded before `sheet.js` (a second contributing race condition with `window._SUBCLASS_SPELLS` undefined at lookup time).
- Land Type / variant chooser selections inside the Subclass Spells panel auto-save via a fire-and-forget PATCH to `/sheet-fields` on `change`, mirroring how granted-spell picks already persist. The pick now survives a refresh without an explicit Save click.

### Changed
- `_SHEET_PATCH_KEYS` and `_CLASS_SCOPED_KEYS` in `app/routes/tabletop_routes.py` now include `subclass_choice`, so the per-class variant pick is routed into the right `classes[]` entry by the existing `class_slug`-aware patch logic.
- Renamed the no-arg helper formerly named `_classSlug()` at the bottom of `sheet_dnd5e.html` to `_primaryClassSlug()` and added a comment warning that the original name would shadow the 1-arg slugify helper at the top of the file. Both lived in different IIFEs so this was a defensive cleanup, not a bug fix — the actual picker issue was the render race above.

---

## [0.33.18] - 2026-05-10

**Schema version:** 21

**Commit summary:** Combine multiclass spells under one heading per level with inline per-class slot pills

**Description:** The previous build grouped multiclass spells by class first and then by level — so a Druid 5 / Wizard 3 / Warlock 1 sheet had three "DRUID" / "WIZARD" / "WARLOCK" section headers, each repeating "Cantrips - Druid", "Level 1 Spells - Druid", etc. Empty levels still rendered "No spells learned at this level yet." with their slot pips. That was a lot of vertical space for a layout where every spell row already carries a class-tag pill identifying its source. The renderer now combines spells by level across every class — one "Cantrips" section, one "Level 1 Spells" section, etc. — and inlines each contributing class's slot pips on the heading line. Spells inside each level sort by class-roster order then alphabetically. Collapse state moves with the new structure: keyed on `simplevtt_spgrp_<charId>_lvl<N>` instead of per (class, level).

### Changed
- `renderSpells` builds a single `byLvl` map across all classes (no longer one bucket per class). The per-class section header (the old "── DRUID ──" divider) is gone — the class-tag pill on each spell row identifies the source.
- Each level heading now renders multiple inline slot pills: one per class with slots at that level (e.g. "Level 1 Spells   Druid ●●●●   Wizard ●●●●   Warlock ●○"). Each slot row keeps its `data-cslug` / `data-lvl` attrs so the pip click handlers still post the correct (class, level) to `/cast_spell`.
- Spells within a level group sort by class roster order then alphabetically by name.
- Collapse state key migrated from per-(class, level) to per-level (`simplevtt_spgrp_<charId>_lvl<N>`); old per-class keys remain dormant in `localStorage` but are ignored.

---

## [0.33.17] - 2026-05-10

**Schema version:** 21

**Commit summary:** Class tag on spell rows, inline slot pips, and collapsible spell-level groups

**Description:** Each spell row in the D&D 5e sheet now carries a small class pill (e.g. "Druid", "Wizard") for multiclass characters so the player can tell at a glance which class list a given spell came from. The slot pip row no longer sits on its own line above each spell-level group — the pips are now inline with the level heading (`▼ Level 1 Spells - Druid  ●●●○`), giving a tighter layout. Clicking the level heading collapses the spells underneath it; collapse state is persisted per (character, class, level) in localStorage.

### Added
- Class-tag pill on spell rows in `_spellRowHtml`, gated on `_rosterIsMulticlass()` so single-class characters don't see a redundant tag on every row. Tag text is the display-name from the multiclass roster, falling back to a title-cased slug.
- `_classDisplayName(slug)` and `_rosterIsMulticlass()` helpers in the spell binder.
- ▼ chevron + click handler on each spell-level group heading. Toggling persists to `localStorage` under `simplevtt_spgrp_<charId>_<classSlug>_<level>` so a player's collapse choices survive reloads.

### Changed
- Spell-level heading layout switched from a label-only div to a flex row that owns the chevron, the label, AND the relocated slot row. The slot row's own "Lv N" label is hidden (the heading already names the level) and its border-bottom + margins are stripped so it integrates flush. Pip clicks `stopPropagation` so toggling a slot doesn't accidentally collapse the group.

---

## [0.33.16] - 2026-05-10

**Schema version:** 21

**Commit summary:** Strip Open5e's verbatim spell tables and surface the picker's starting class level

**Description:** After ↻ Sync, the old "Circle Spells" tables were still visible — they live in `entry.subclass_flavor`, which renders as italic prose at the top of the subclass-features block, so the picker swap inside the matching feature card didn't touch them. The flavor is now run through a markdown-table stripper whenever the curated picker table has data for the subclass, so the duplicate tables stop appearing next to the interactive picker. The Subclass Spells panel subtitle also now shows the feature's starting class level (the minimum `classLvl` across all grants and variants), e.g. "⭐ Always prepared (starts at class Lv 3) — does not count against your limits."

### Added
- `_stripTables(text)` helper in `sheet.js` — drops markdown-style table rows (`| col | col |`) and separator rows (`---|---`) while leaving prose intact.

### Changed
- `_renderSubclassBlock` runs `entry.subclass_flavor` through `_stripTables` before `_cleanMd` when a curated picker is in play, so the verbatim PHB spell tables stop showing alongside the picker.
- `_renderSubclassSpellPanel` computes a starting class level (min `classLvl` across `grants` and all `variants`) and appends a "(starts at class Lv N)" note to its subtitle — visible in both inline and panel-wrapper modes.

---

## [0.33.15] - 2026-05-10

**Schema version:** 21

**Commit summary:** Synthesize Circle Spells and Bonus Cantrip cards offline so the pickers always render

**Description:** The Subclass Spells and Feature Grants pickers lived inside Open5e-sourced feature cards. If those cards weren't cached — no sync, offline, Open5e errored — the pickers were nowhere to show. The renderer now synthesizes missing curated picker cards from the curated `_SUBCLASS_SPELLS` table alone: a Druid set to Circle of the Land sees "Circle Spells" + "Bonus Cantrip" cards (with their pickers inside) on first paint, even with no network. When Open5e eventually returns the real prose, the existing dedupe merges it into the synthesized card so descriptions appear alongside the same picker.

### Changed
- `_renderSubclassBlock` in `sheet.js` looks up `subclassData` at the top of the function and pushes synthesized entries for the main subclass-spells feature and every `bonusFeatures` entry whose name isn't already present in `entry.subclass_features`. The synthesized features carry the class-level computed from the curated grant data (lowest `classLvl` across `grants` and all `variants`) so the existing card-level badge reflects the unlock.
- The visible / locked feature split now keeps curated-picker features in the visible list regardless of class level — the picker stays reachable even when the player hasn't reached the unlock level yet (the "Class Lv N" labels inside the picker already communicate that).
- Removed the duplicate `subclassMainFeature` / `bonusFeaturesByName` block; both are now declared once near the top of the function and shared across the visible/locked filter and the inline-rendering loop.

---

## [0.33.14] - 2026-05-10

**Schema version:** 21

**Commit summary:** Fetch full spell details for granted subclass / feature spells

**Description:** Spells added through the Subclass Spells or Feature Grants pickers used to land in the spell list with just a name, level, and class slug — the curated table doesn't carry the full rules text, and the picker wasn't hitting Open5e. So when a player expanded a "+ Add"-ed spell row, the body was empty. The grant helpers now fire a fire-and-forget fetch against `/api/open5e/spells?search=<name>` after each add, fill in every missing field on the matching spell record (description, school, casting time, range, duration, components, damage, save ability, healing, AOE targets, concentration, `_slug`), and persist via the existing debounced spell save. A one-time backfill on initial sheet load enriches any granted spells that pre-date this fix.

### Added
- `_fetchSpellDetail(name)` helper in `sheet_dnd5e.html` — searches Open5e by name with an in-memory cache keyed by lowercased name (one fetch per unique spell per session).
- `_enrichGrantedSpell(name, classSlug)` — locates the matching granted spell record and fills any missing fields from the Open5e detail. Auto-detects concentration from the duration string. Triggers `syncSpells`, `renderSpells`, and the debounced server save so the picker dropdown / spell list / DB stay in sync.
- A one-shot backfill pass after the initial `renderSpells()` that calls `_enrichGrantedSpell` for every existing granted spell whose `desc` is empty — covers characters saved before this change.

### Changed
- `_addGrantedSpell` now fires `_enrichGrantedSpell` after pushing the spell, so descriptions appear within a moment of the player clicking +.

---

## [0.33.13] - 2026-05-10

**Schema version:** 21

**Commit summary:** Add a version footer to every page except the tabletop

**Description:** `base.html` now ends with a small "SimpleVTT vX.Y.Z · schema vN" footer so the running version is visible at a glance on every page that extends the base layout. The tabletop screen overrides the new `{% block footer %}` to empty so the canvas can keep filling the viewport without a footer eating into it. The version constants are exposed as Jinja globals from `app/templates.py`, so no route has to thread them through its context dict.

### Added
- `.site-footer` style in `style.css` — a thin top-bordered strip using `--bg-2` background and `--fg-mute` text that pins to the bottom via `margin-top:auto` on the existing flex-column body.
- `{% block footer %}` in `base.html` containing the version + schema line, plus an empty override in `tabletop.html`.

### Changed
- `app/templates.py` registers `APP_VERSION` and `SCHEMA_VERSION` as `templates.env.globals`, so every template can reference them without route context plumbing.

---

## [0.33.12] - 2026-05-10

**Schema version:** 21

**Commit summary:** Move bonus-cantrip / feature-grant picker inside the feature card body

**Description:** The Bonus Cantrip picker (and any other Feature Grants row) used to render below its feature card as a separate strip. It now lives inside the matching card body, right under the description text, separated by a thin dashed line. The card opens expanded by default so the dropdown is visible without an extra click, and the redundant "🌟 Bonus Cantrip" label that used to sit next to the dropdown is dropped (the card header already names the feature).

### Changed
- `makeCard` in `sheet.js` gains a `bodyAppend` argument that adds an extra element to the bottom of the card body. When a description is also present, a thin dashed separator divides the prose from the appended content.
- `_renderFeatureGrantsPanel` in `sheet_dnd5e.html` suppresses the per-row feature-name label when `inline: true` AND `onlyFeature` are both set — the surrounding card header carries the name already.
- `_renderSubclassBlock` visible-features loop builds the Feature Grants picker for curated `bonusFeatures` or parser-detected grants and passes it to `makeCard` as `bodyAppend`, with `startsOpen: true`.

---

## [0.33.11] - 2026-05-10

**Schema version:** 21

**Commit summary:** Replace the Subclass-Spells card body with the interactive picker

**Description:** The "Circle Spells" / "Domain Spells" / "Oath Spells" / "Psionic Spells" / "Clockwork Magic" / "Star Map" feature cards used to expand to show Open5e's verbatim PHB tables (one per terrain / domain / etc.) sitting right next to the interactive Subclass Spells picker that already had + / ✓ buttons for every spell. The card body now IS the picker — the duplicate prose tables are gone, and the card opens expanded by default so the player sees the picker without having to click. Every other feature card keeps its description as before.

### Changed
- `makeCard` in `sheet.js` gains two optional arguments: `customBody` (an element to use in place of the description text) and `startsOpen` (renders the card with its body already expanded).
- `_renderSubclassBlock` visible-features loop builds the Subclass Spells picker into a div and passes it as `customBody` for the card whose name matches `subclassData.feature`, with `startsOpen: true`. The separate inline panel previously rendered beneath that card is now gone (the picker IS the body).
- `_renderSubclassSpellPanel` inline-mode wrap is now `margin:0;padding:0;` so it sits flush inside whatever container (e.g. a feature card body) the caller appended it to.

---

## [0.33.10] - 2026-05-10

**Schema version:** 21

**Commit summary:** Fully render every class-level row in the Subclass Spells panel

**Description:** The previous build hid Subclass Spells rows the player hadn't reached yet and suppressed the panel entirely when nothing was unlocked. The class roster already has a Level picker, and the buttons themselves label their unlock ("Class Lv 3 → + Barkskin (Lv 2)"), so the gating got in the way without adding information. Every class-level row now renders with its buttons fully interactive — the player can pick whichever spells they want and the existing level picker is the source of truth for what's actually accessible.

### Changed
- `_renderSubclassSpellPanel` in `sheet_dnd5e.html` no longer splits grants into unlocked/upcoming. Every row renders, every button is enabled (subject to `readonly`), and the "unlocks at class level N" hint / "Next at class Lv N" footer are removed.

---

## [0.33.9] - 2026-05-10

**Schema version:** 21

**Commit summary:** Dedupe duplicate subclass-feature cards and level-gate the Subclass Spells panel

**Description:** Open5e occasionally returns the same subclass feature twice — typically a "Circle Spells" description paired with a separate "Circle Spells" entry holding the per-level spell tables — which surfaced as two adjacent identical cards on the sheet. Same-named features are now merged into one card before render, combining their descriptions and keeping the earliest unlock level. The Subclass Spells panel also no longer shows spells the player hasn't reached: only unlocked class-level rows render, and the whole panel is suppressed when nothing's been unlocked yet (e.g. a Lv 1 Druid with Circle of the Land set sees no Circle Spells panel because the first row unlocks at Lv 3). A compact "Next at class Lv N: …" hint replaces the dimmed locked rows so players still see what's coming.

### Changed
- `_renderSubclassBlock` in `sheet.js` runs feature lists through a new `_dedupeFeatures()` helper that merges same-named entries, concatenates non-overlapping descriptions, and keeps the earliest unlock level.
- `_renderSubclassSpellPanel` in `sheet_dnd5e.html` splits grants into unlocked / upcoming by class level. Only unlocked rows render. The panel suppresses itself entirely when no rows are unlocked (or, in inline mode, shows a single "<Feature> unlocks at class level N" hint). A single-line "Next at class Lv N: <names>" note replaces the dimmed locked rows.

---

## [0.33.8] - 2026-05-10

**Schema version:** 21

**Commit summary:** Inline Subclass Spells and Feature Grants controls beneath their describing feature cards

**Description:** The interactive Subclass Spells panel (Land Type dropdown + spell add buttons) and Feature Grants panel (cantrip choosers + fixed-grant buttons) used to render in two big blocks at the bottom of the subclass-features section, disconnected from the feature descriptions that explained them. They now render directly underneath each matching feature card — the Subclass Spells controls sit under the "Circle Spells" / "Domain Spells" / "Oath Spells" / "Psionic Spells" / "Clockwork Magic" / "Star Map" card, and individual cantrip-grant rows sit under their own "Bonus Cantrip" / "Acolyte of Nature" feature cards. Anything that can't be matched to a visible card (e.g. subclass set but features not yet synced) still falls back to the bottom panels so it's never hidden.

### Changed
- `_renderSubclassSpellPanel` accepts an `{ inline: true }` option that strips the dashed wrapper + heading so it integrates visually under the feature card.
- `_renderFeatureGrantsPanel` accepts `{ inline: true, onlyFeature: <name>, excludeFeatures: <Set> }` options — `onlyFeature` renders just one matching row inline, `excludeFeatures` filters out feature names already rendered inline so the bottom fallback never doubles up.
- `_renderSubclassBlock` in `sheet.js` now walks the visible-features loop and, after appending each card, checks whether the card matches the curated subclass-spells feature, a curated `bonusFeatures` entry, or a parser-detected grant — and inlines the right panel right after the card. A bottom-of-block fallback still renders anything left unmatched.

---

## [0.33.7] - 2026-05-10

**Schema version:** 21

**Commit summary:** Preserve granted-spell markers on refresh and surface Feature Grants without syncing

**Description:** Two bugs in the always-prepared subclass-spell flow. The spell-load mapper on `sheet_dnd5e.html` was an explicit allow-list that didn't include `class`, `_subclass_granted`, or `_granted_by` — so every refresh stripped those fields off saved spells, the ⭐ Granted pill disappeared, and the spell started counting against the prepared limit again. That's fixed; the load mapper now preserves all three. The Feature Grants panel also relied on the heuristic parser scanning Open5e-synced feature descriptions to detect "Bonus Cantrip" / "Acolyte of Nature" / etc., so it stayed empty until the player clicked ↻ Sync. A new curated `bonusFeatures` field on `_SUBCLASS_SPELLS` entries lets the panel render those grants instantly — Circle of the Land's Druid "Bonus Cantrip", Light Domain's "Bonus Cantrip" (fixed Light), and Nature Domain's "Acolyte of Nature" all appear the moment you set the subclass.

### Fixed
- Spell-load mapper in `sheet_dnd5e.html` now preserves `class`, `_subclass_granted`, and `_granted_by` so granted spells stay granted across save+refresh (the ⭐ Granted pill, prepared-skip behavior, and Feature-Grant dropdown selection now all survive a reload).

### Added
- Curated `bonusFeatures` on `_SUBCLASS_SPELLS`:
    - `circle-of-the-land`: Bonus Cantrip — choose a druid cantrip (Lv 2).
    - `light`: Bonus Cantrip — fixed Light (Lv 1).
    - `nature`: Acolyte of Nature — choose a druid cantrip (Lv 1).
- Locked-row support in the Feature Grants panel — rows whose `classLvl` is higher than the player's current class level now render dimmed with a `(Lv N)` suffix and a locked tooltip, mirroring the Subclass Spells panel.

### Changed
- `_renderFeatureGrantsPanel` reads curated `bonusFeatures` first, then runs the heuristic parser on synced features as a fallback. Deduplication is by feature name so the parser never doubles up on a curated entry.

---

## [0.33.6] - 2026-05-10

**Schema version:** 21

**Commit summary:** Show Subclass Spells and Feature Grants panels immediately and auto-sync missing subclass details

**Description:** The Subclass Spells panel (Circle / Domain / Oath Spells) was wedged behind a "no features cached yet" early-return inside the per-class subclass-features renderer, so a Druid with Circle of the Land set but unsynced features saw nothing until the player clicked ↻ Sync. The Feature Grants panel's heuristic parser also needs feature data to find "Bonus Cantrip" etc., so without Sync it found nothing. The renderer no longer returns early — Subclass Spells shows up the moment a subclass is picked (since it's driven by the curated table keyed off the subclass slug), and a background auto-sync kicks off on initial editor render for any class entry with missing subclass features or missing class features so the Feature Grants parser has something to scan within seconds of page load.

### Changed
- `_renderSubclassBlock` in `sheet.js` no longer returns when `subclass_features` is empty — it shows a quiet "Fetching subclass features from Open5e…" hint and falls through to the panel renderers, so the Subclass Spells panel always appears as soon as the subclass is set.
- New `_autoSyncMissingDetails()` runs at the end of `_renderEditor()` and walks the roster: for any class entry with a subclass set but no cached subclass features, it calls `_fillSubclassDetail`; for any entry with no `class_features` blob, it calls `_fillClassDetail`. Once each completes, the roster is re-written, the subclass blocks re-render with the freshly-fetched data, and `_saveSubclassCacheRow` persists the cache so the next refresh has it immediately.
- Tries are tracked in a session-local Set keyed by `class|subclass` so a single Open5e outage doesn't loop, but a refresh re-attempts.

---

## [0.33.5] - 2026-05-10

**Schema version:** 21

**Commit summary:** Auto-save subclass and feature granted-spell picks so they persist across refresh

**Description:** Previously a player who picked a cantrip in the Bonus Cantrip dropdown (or added a Circle / Domain / Oath spell, or removed one) had to hit Save before refreshing — otherwise their pick was lost and the dropdown reset to "— pick a cantrip —". The grant helpers now fire a debounced PATCH to `/sheet-fields` immediately after every add/remove/swap, so the dropdown's selection survives a refresh without an explicit Save click. The PATCH whitelist gains `"spells"` so the panel can write back through the existing endpoint.

### Changed
- `_addGrantedSpell` / `_removeGrantedSpell` / `_removeGrantedByFeature` in `sheet_dnd5e.html` each call a new `_saveSpellsToServer()` helper that debounces (200 ms) and PATCHes the full spells list. Dropdown swaps fire add+remove back-to-back; the debounce collapses them into one network call.
- `_SHEET_PATCH_KEYS` in `tabletop_routes.py` gains `"spells"` so the lightweight sheet-fields PATCH endpoint accepts the spells list. The campaign route's `_apply_sheet_patch` helper (which the standalone-character route also uses) routes the key through unchanged.

---

## [0.33.4] - 2026-05-10

**Schema version:** 21

**Commit summary:** Double the full character sheet portrait from 96px to 192px

**Description:** The full D&D 5e character sheet portrait was 96×96; doubled to 192×192 so the art is actually readable. The placeholder initial scales too (font-size 36px → 72px). The post-upload JS that hot-swaps a new image into the placeholder was also off — it set the new element to 90px while the surrounding markup used 96px — fixed to match the new 192px while it was being touched.

### Changed
- `sheet_dnd5e.html` portrait column width, the `<img>`/placeholder dimensions, and the placeholder's first-letter font-size all doubled.
- Portrait-upload swap-in JS now applies the doubled 192×192 dimensions (was a stale 90px).

---

## [0.33.3] - 2026-05-10

**Schema version:** 21

**Commit summary:** Re-theme subclass features, race traits, and granted-spell badges to use CSS variables

**Description:** The subclass feature cards (and their flavor text, expand chevrons, level pills, and "Future features" locked rows) were hardcoded to the dark theme's exact palette so they looked off on light, hobbiton, forge, and other themes regardless of how many times the player hit ↻ Sync. The same was true of the race-traits cards and the ⭐ Granted spell pill. All of those now use CSS variables (`var(--bg)`, `var(--bg-2)`, `var(--fg)`, `var(--fg-mute)`, `var(--border)`, `var(--accent)`, `var(--accent-bg2)`, `var(--accent-border)`) so they re-tint correctly when the player switches themes. The spell browser's "over your prepared limit" warning now uses `var(--s-danger)` instead of a fixed red.

### Changed
- `_renderSubclassBlock` in `sheet.js` — feature cards (headers, name, expand arrow, level badge, body, dimmed locked variant), the flavor block, and the "Future features" label all switched from hex literals (`#c8cce8`, `#252c45`, `#1c3040`, `#191c2b`, `#b0b4cc`, `#445`, `#3a6a50`, …) to theme tokens.
- `renderRaceTraits` and `makeTraitCard` in `sheet.js` swapped to the same set of theme tokens; the blob-paragraph fallback also picks up `--bg` / `--border` / `--fg-mute`.
- ⭐ Granted pill in the spell list now uses `--accent-bg2` background and `--accent` text so it tints with the theme rather than living in fixed pastel green.
- Spell Browser limit-bar "over cap" coloring uses `var(--s-danger)` instead of `#e07070`.

---

## [0.33.2] - 2026-05-10

**Schema version:** 21

**Commit summary:** Cover every always-prepared subclass spell list across PHB, DMG, XGtE, and TCoE

**Description:** The curated subclass-spells table now covers every D&D 5e subclass that grants always-prepared spells: all 12 cleric domains (PHB + XGtE + TCoE), all 8 druid Circle of the Land terrains plus Tasha's Circle of Spores / Circle of Wildfire / Circle of Stars, all 7 paladin oaths across PHB / DMG Oathbreaker / XGtE Conquest & Redemption / TCoE Glory & Watchers, and Tasha's Aberrant Mind and Clockwork Soul sorcerer origins (whose extra spells are "always known and don't count against your sorcerer spells known"). A slug-variation lookup means the panel now resolves whether Open5e returns the bare slug (e.g. `knowledge`) or the suffixed form (`knowledge-domain`), and the same for `oath-of-X` / `circle-of-X` prefixed slugs.

### Added
- 19 new subclass entries in `_SUBCLASS_SPELLS`: Forge, Grave, Order, Peace, Twilight (cleric domains); Circle of Spores, Circle of Wildfire, Circle of Stars (druid); Oathbreaker, Oath of Conquest, Oath of Redemption, Oath of Glory, Oath of the Watchers (paladin); Aberrant Mind, Clockwork Soul (sorcerer).
- `_lookupSubclassData(entry)` slug-variation helper that tries `<slug>`, `<slug>-domain`, `<slug-without-domain>`, `oath-of-<slug>`, `circle-of-<slug>`, and the same with optional `-the-` so the curated table matches whichever shape Open5e returns.

### Changed
- The variant-chooser save path now matches the class entry by `class` slug + display-name rather than by subclass slug, so writing a Land Type back works regardless of which slug shape the panel resolved through.
- Curated coverage is now 26 subclasses (up from 11).

---

## [0.33.1] - 2026-05-10

**Schema version:** 21

**Commit summary:** Parse class and subclass features for bonus cantrip grants and offer a chooser

**Description:** A new heuristic parser scans every class- and subclass-feature description on a character for bonus-cantrip language (e.g. Druid Circle of the Land "Bonus Cantrip — you learn one additional druid cantrip of your choice", Cleric Light Domain "Bonus Cantrip — you gain the light cantrip"). Detected grants surface in a Feature Grants panel beneath each class's subclass-features block. Choose grants render as a dropdown populated from the appropriate class's cantrip list (fetched from Open5e and cached); fixed grants render as a single + Add button. The chosen cantrip is added with `_subclass_granted: true` and tagged with the originating feature name, so swapping picks cleanly replaces the old entry without touching unrelated grants.

### Added
- `_parseCantripGrant(featureName, featureDesc, parentClassSlug)` heuristic parser recognising fixed grants ("you learn the X cantrip"), choose-from-class grants ("additional druid cantrip"), and generic "cantrip of your choice" patterns; numeric counts (one/two/three/digit) are also extracted.
- `_renderFeatureGrantsPanel(target, entry)` panel that walks `entry.subclass_features` plus the parsed `entry.class_features` blob, runs each through the parser, and renders a chooser/button per detected grant.
- Per-feature granted-spell bookkeeping: spells now carry an optional `_granted_by` tag with the source feature name; `_findGrantedByFeature` and `_removeGrantedByFeature` helpers let the chooser swap or clear a single feature's pick without touching other grants on the same class.
- Cached cantrip lookup per class slug so changing dropdowns within the same session doesn't re-hit Open5e.
- Multiclass subclass-block now also renders the Feature Grants panel alongside the existing Subclass Spells panel.

### Changed
- `_addGrantedSpell` accepts an optional 4th argument `grantedBy` and stamps it onto the spell so the chooser can re-locate the right entry.
- `window._parseFeaturesFromText` is now exposed from `sheet.js` so the spellcasting framework can scan class-features blobs without re-implementing the heading-detection logic.

---

## [0.33.0] - 2026-05-10

**Schema version:** 21

**Commit summary:** Add subclass-granted spells framework with variant chooser and always-prepared bonus spells

**Description:** Each per-class subclass-features block now renders a "Subclass Spells" panel driven by a curated table of D&D 5e PHB grants. Cleric domains, paladin oaths, and druid Circle of the Land all surface their bonus spells with [+ Add] / [✓ Added] buttons grouped by the class level at which each spell unlocks. Locked rows are dimmed until the player reaches the required class level. Druid Circle of the Land includes a Land Type dropdown (Arctic, Coast, Desert, Forest, Grassland, Mountain, Swamp, Underdark) cached on the class entry. Granted spells are tagged with `_subclass_granted: true`, render in the spell list with a ⭐ Granted pill and a locked-prepared mark, and are explicitly excluded from both the prepared/known and cantrips-known counters so they're a true bonus on top of the player's normal selections.

### Added
- `app/static/dnd5e_subclass_spells.js` — curated `_SUBCLASS_SPELLS` table covering Knowledge / Life / Light / Nature / Tempest / Trickery / War cleric domains, Devotion / Ancients / Vengeance paladin oaths, and Circle of the Land druid (with all 8 terrain variants).
- `_renderSubclassSpellPanel(target, entry)` panel renderer with grouped per-class-level [+ Add] / [✓ Added] buttons, locked rows for unmet level prerequisites, and a variant dropdown for subclasses that ask the player to pick a flavour.
- `_addGrantedSpell` / `_removeGrantedSpell` / `_hasGrantedSpell` JS helpers that tag the spell with `_subclass_granted: true` and `prepared: true`, upgrading any existing same-name entry rather than duplicating.
- ⭐ Granted pill on spell rows for at-a-glance recognition.
- Per-entry `subclass_choice` field on `sheet["classes"][i]` so the variant dropdown's selection persists across reloads.
- Multiclass subclass-features block calls into the panel renderer so each class on a multiclass sheet gets its own subclass-spells panel.

### Changed
- `_spellCountFor` and `_cantripCountFor` now skip any spell with `_subclass_granted: true`, so subclass grants do not count against prepared/known or cantrips-known limits.
- Spell row rendering treats `_subclass_granted` like a cantrip for the prepared-state visual: locked-✦ icon, no checkbox, and the always-prepared title.

---

## [0.32.3] - 2026-05-10

**Schema version:** 21

**Commit summary:** Track cantrips known per class with limit enforcement in the spell browser

**Description:** Each spellcasting class now displays a "Cantrips cur/max" tracker alongside its prepared/known leveled-spell count, sourced from the PHB / Tasha's cantrips-known column for that class at its current level (e.g. Druid Lv 5 → 3 cantrips, Wizard Lv 5 → 4). The tracker turns yellow at the limit and red when over. The spell browser's status bar shows the cantrip count for the selected class, and the detail pane warns before adding a cantrip that would exceed the limit.

### Added
- `cantrips` per-level table on every cantrip-learning class in `_SC` (bard, cleric, druid, sorcerer, warlock, wizard, artificer).
- `_cantripLimitFor()` / `_cantripCountFor()` helpers driving the new tracker.
- "Cantrips X / Y" chip on each per-class spellcasting info-bar row (and in its collapsed summary).
- Cantrips count in the spell browser limit bar plus an over-limit warning in the detail pane when adding a cantrip would exceed the class's cap.

---

## [0.32.2] - 2026-05-10

**Schema version:** 21

**Commit summary:** Compact spellcasting info bar, collapse toggle, and Auto-fill Slots in the legend

**Description:** The spellcasting info bar is now a single-line-per-class compact strip and can be collapsed by clicking its header — when collapsed it shows just a "Druid 4/8 · Wizard 2/6" summary so the spell list stays in view. The ⚡ Auto-fill Slots button moved up into the Spells fieldset legend next to 👁 Hide Unprepared, and its result message is now surfaced as a toast instead of an inline footer.

### Changed
- `#sc-info-bar` rebuilt as a collapsible card; rows render one line per spellcasting class (Class · Lv · Type · Ability · DC · Atk · Prep/Known cur/max).
- ⚡ Auto-fill Slots button moved from the info-bar footer to the Spells legend; status is now a toast.
- Collapse state is persisted per-character in localStorage.

---

## [0.32.1] - 2026-05-10

**Schema version:** 21

**Commit summary:** Show per-class spellcasting info bar and always render every available slot row

**Description:** The spellcasting info bar (Type / Ability / Save DC / Atk / Prepared) now renders one row per spellcasting class on the sheet, so a Druid 5 / Wizard 3 sees Druid's Prepared count and DC alongside Wizard's Prepared count and DC. The spell list also now shows each class's slot pip rows for every level where that class has slots, even at levels where no spells have been added yet, so empty Lv 2 / Lv 3 / etc. slots are no longer hidden. Each class's spell groups are introduced by an underlined section header so a multiclass roster reads top-to-bottom as distinct class blocks.

### Changed
- `#sc-info-bar` is now driven entirely by JS; its DOM is rebuilt as one row per spellcasting class with the class name + level prefix.
- `renderSpells()` walks every roster class, unions its slot levels with its spell levels, and renders an explicit "no spells learned at this level yet" hint when slots exist without spells.
- Each class block is preceded by a section header (e.g. "── DRUID ──") to visually separate multiclass spell lists.

---

## [0.32.0] - 2026-05-10

**Schema version:** 21

**Commit summary:** Add D&D 5e multiclassing with per-class spells, slots, and proficiencies

**Description:** Player characters can now hold up to 20 levels split between any number of D&D 5e classes. The character sheet edit panel exposes a Classes & Levels list with a "+ Add Class" button, each row picking a class, optional subclass, and level (capped at 20 total). Class Proficiencies is rendered as a table with one column per class. Spell groups are now keyed by both class and level (e.g. "Level 1 Spells - Druid"), and spell slots track per class so a Druid 5 / Wizard 3 sees independent slot pips. The spell browser exposes a class-context selector for tagging newly-added spells, the inventory item browser unions weapon/armor proficiencies across every class, and subclass features are headed with the class name. The tabletop mini-sheet shows the combined class roster sorted highest level first. No operator action is needed; existing single-class characters are auto-upgraded to a one-entry roster on first read.

### Added
- `sheet["classes"]` array on D&D 5e sheets — each entry stores `{class, subclass, level}` plus that class's `class_hit_die`, `class_armor`, …, `subclass_features`, `subclass_name`, `subclass_flavor`.
- Multiclass editor (Class & Levels list, +Add Class, ×Remove, total-level cap) inside the character edit panel.
- Class Proficiencies fieldset rendered as a multi-column table keyed by class.
- Spell Browser class chips + per-class limit bar; new spells get tagged with the chosen class on import.
- `class_slug` field on `/cast_spell` requests + `class_slug` field on `spell_slot_update` WebSocket messages so multi-class casters draw from the right slot pool.
- `normalize_dnd5e_sheet()` helper in `app/sheet_templates.py` that mirrors the highest-level class onto legacy flat fields and migrates flat `spell_slots` to the new nested-by-class shape on read.

### Changed
- Spell list grouping: spells are now grouped by `(class, level)` and headings read "Level N Spells - <Class>" (mirrored on the tabletop mini-sheet).
- `sheet["spell_slots"]` is now nested by class slug: `{"druid": {"1": {"total":4,"used":0}, …}, "wizard": {…}}`. Old flat shape is auto-migrated.
- Inventory item browser "Proficient only" filter now unions proficiencies across every class on the sheet.
- Subclass-features block is rendered once per class, prefixed with `<Class> - <Subclass>`.
- Long rest now resets every class's slots; short/long-rest broadcasts include `class_slug` per slot.
- Tabletop drawer: class tags collapse into a single combined badge ("Druid 5 / Wizard 3") sorted by level descending.

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
