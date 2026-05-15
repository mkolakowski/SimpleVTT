# Changelog

All notable changes to SimpleVTT are documented in this file.
Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) — Versioning: [SemVer](https://semver.org/spec/v2.0.0.html).

The current version is the topmost release section below.
Application version and database schema version are also published at runtime by `GET /version` and `GET /healthz`, and are defined as constants in [`app/version.py`](app/version.py).

---

## [1.7.0] - 2026-05-14

**Schema version:** 51
**Commit summary:** File-based content framework for spells / items / monsters / feats / backgrounds / conditions, ships ~860 SRD JSON files, homebrew Docker volume, shared Action button descriptor.
**Description:** Adds a file-based content framework that ships the full WotC SRD 5.1 baseline as ~860 per-slug JSON files committed to the repo (319 spells, 322 monsters, 292 items, 15 conditions, 1 feat, 1 background). A new `homebrew_data` Docker volume holds GM-authored homebrew at `/app/app/data/homebrew/<system>/<scope>/<type>/<slug>.json` and is backed up alongside the Postgres dump. A new `/admin/homebrew` page lets admins create, edit, delete, import-from-Open5e, and paste-JSON homebrew records, all written as files (no DB rows). A shared `Action` Pydantic descriptor drives every interactive button (damage / save / attack / healing / active toggle / reroll trigger / damage scaling) so future content types declare their own UI. **Additive only** — the existing `Custom*` DB-backed homebrew remains fully functional and the schema is unchanged; a future 2.0.0 PR will replace those endpoints with redirects to the new file-based authoring and drop the `custom_*` tables (the migration is staged in `app/_migrate_v52.py` but not yet wired).

### Added
- `app/action_schema.py` — shared `Action` / `ActionScalingTier` / `AreaShape` / `UpcastEntry` Pydantic models.
- `app/content_schemas.py` — nine per-type schemas (`Spell`, `Item`, `Feat`, `Monster`, `Background`, `Condition`, `ClassFeature`, `SubclassFeature`, `Race`) + `TYPE_REGISTRY`.
- `app/local_content.py` — file-based resolver with `resolve` / `search` / `write_homebrew` / `delete_homebrew`, path-traversal protection, atomic writes, mtime cache, and campaign-scope precedence over global.
- `scripts/build_srd_content.py` — developer tool that pulls Open5e API SRD content into per-slug JSON files. SRD-only by default (filters on `document__slug == "wotc-srd"`); `--include-all` widens to every Open5e document.
- `app/data/local/dnd5e/spells/` — 319 SRD spell files.
- `app/data/local/dnd5e/monsters/` — 322 SRD monster files with unified `actions: list[Action]` (replaces the legacy four-list shape).
- `app/data/local/dnd5e/items/` — 292 SRD item files (~30 magic items + weapons + armor).
- `app/data/local/dnd5e/feats/` — 1 SRD feat file (Grappler — the SRD 5.1 example).
- `app/data/local/dnd5e/backgrounds/` — 1 SRD background file.
- `app/data/local/dnd5e/conditions/` — 15 SRD condition files.
- `app/routes/homebrew_routes.py` — `GET /admin/homebrew` list + `POST /admin/homebrew/{type}/{new,<slug>/edit,<slug>/delete,import/open5e/<slug>,import/upload}`, plus read-only `GET /api/content/{type}/{slug}` for client-side resolution.
- `app/templates/admin/homebrew/list.html` — combined list/edit/import page with type tabs and inline JSON textareas.
- `app/static/action_buttons.js` — shared `renderActionButtons` + `renderActionCards` + `data-actions` auto-init hook, loaded by both `tabletop.html` and `sheet_dnd5e.html`.
- `homebrew_data` Docker volume mounted at `/app/app/data/homebrew` on both `app` and `backup` services.
- `has_spells` / `has_feats` / `has_items` / `has_backgrounds` capability flags on `GameSystem` (all True for dnd5e).
- Demo action backfills on shipped JSON: Sneak Attack (rogue.json, 10 scaling tiers), Rage (barbarian.json, active toggle + resource link), Lucky (lightfoot-halfling.json, reroll trigger).
- `app/_migrate_v52.py` — staged but unwired migration helper for a future 2.0.0 destructive cutover (exports `Custom*` rows to homebrew files, drops the tables). Public function `run_v52_migration(engine)` is callable but not yet invoked from `_apply_inline_migrations`.

### Changed
- `app/local_features.py` — rewritten as a thin shim that delegates to `local_content`. Public API (`resolve_class` / `resolve_subclass` / `resolve_race` / `resolve_background` / `resolve_feat` / `record_miss` / `list_local_*`) is preserved; the DB-backed Custom* provider functions are removed. 15 callers in `tabletop_routes.py` are unaffected.
- `app/routes/tabletop_routes.py` — `/api/open5e/spells` consults the new `local_content` tier before falling back to the Open5e mirror / live API. `_fmt_spell` honors explicit `actions: list[Action]` when present; falls back to regex extraction. `cast_spell` broadcasts `actions` + `spell_attack_roll` over the WebSocket so the client uses `renderActionButtons` natively.
- `app/static/tabletop.js` — `appendSpellCast` delegates button emission to the shared `renderActionButtons` helper; legacy regex-derived fields are synthesized into a single Action on the fly when the server doesn't ship `actions`.
- `app/templates/sheet_dnd5e.html` — racial traits panel now fetches `/api/content/races/<slug>` on load and renders the race's `actions` array via `renderActionCards`. (Class/feat/inventory integration is a follow-up.)
- `app/templates/tabletop.html`, `app/templates/sheet_dnd5e.html` — both load the new `/static/action_buttons.js`.
- `app/game_systems.py` — `GameSystem` dataclass gains four `has_*` flags.
- `docker-compose.yml`, `Dockerfile`, `scripts/backup.sh` — new `homebrew_data` volume mounted at `/app/app/data/homebrew`; `backup.sh` now also produces a `*.homebrew.tar.gz` artifact alongside the Postgres dump with matching retention.

---

## [1.6.14] - 2026-05-14

**Schema version:** 51
**Commit summary:** D20 shape redesigned to hexagon; d100 added to D&D 5e dice tray
**Description:** The d20 roll-toast icon is now a hexagon with star-of-David inner lines (two overlapping triangles at 45% opacity), making it immediately distinct from the d4 inverted triangle. The text Y-position is updated to the hexagon centroid (54). The d100 quick-die button is added to the D&D 5e dice tray (it was already present in the generic system).

### Changed
- Roll toast: d20 shape is now a hexagon + star-of-David inner lines (Option B)
- Roll toast: d20 text Y-position updated to hexagon centroid (54)

### Added
- D&D 5e dice tray: d100 quick-die button

---

## [1.6.13] - 2026-05-14

**Schema version:** 51
**Commit summary:** Fix roll toast silently broken — IS_GM out of scope
**Description:** Since v1.6.9, every incoming roll WebSocket message threw a silent `ReferenceError: IS_GM is not defined` inside the toast IIFE, so the toast never appeared. `IS_GM` is a block-scoped `const` defined only inside the Battle/Initiative Tracker IIFE and is not accessible in the toast IIFE. Fixed by replacing both occurrences with `ME.isGm`, which is globally available. The toast now correctly fires (or is suppressed) for all roll types and visibility levels.

### Fixed
- Roll toast: replaced out-of-scope `IS_GM` with `ME.isGm` so the toast fires for all rolls the user is allowed to see

---

## [1.6.12] - 2026-05-14

**Schema version:** 51
**Commit summary:** Fix dice shapes (d4/d20 distinct); enable skill + ability rolls from mini-sheet
**Description:** Three fixes in one. (1) d4 is now an **inverted** triangle (flat top, point at bottom) making it immediately visually distinct from d20 (upright triangle, point at top). d20 inner Y-lines are thickened (stroke-width 5, opacity 0.6) to clearly signal the icosahedron pattern. The text Y-position is adjusted per shape: d4 → 38 (upper third), d20 → 63 (lower third). (2) The die regex now accepts expressions without a leading count (`d20` treated as `1d20`). (3) The `#players-drawer` click delegation is extended to also match `.mini-sk-btn`, so all 18 skill buttons now fire rolls with the correct expression and note. Ability buttons already had `.mini-roll-btn` and were working.

### Fixed
- Roll toast: d4 shape is now an inverted triangle (flat top, point bottom) — no longer confused with d20
- Roll toast: d20 inner Y-lines increased to stroke-width 5 / opacity 0.6 for clear icosahedron marking
- Roll toast: die parser now handles expressions without a leading count (e.g. `d20`, `d6+2`)
- Mini-sheet: skill buttons now fire rolls (delegation handler extended to `.mini-sk-btn`)

---

## [1.6.11] - 2026-05-14

**Schema version:** 51
**Commit summary:** Roll numbers now rendered inside die SVGs
**Description:** The rolling number is now displayed inside each die shape rather than in a separate element below. Each die is a DOM-built SVG with a `<text>` child that cycles independently (1–sides) during the ease-out animation. On landing: single-die rolls show `r.total` inside the die with a bounce-scale animation; multi-die rolls parse per-die results from the breakdown string (`[3,5]` → 3 and 5) and show them inside each die, with a "= total" sum line beneath. The d8 inner horizontal line was removed since it crossed the number; d4/d20 decorative lines don't conflict because they avoid the centroid zone.

### Changed
- Roll toast: numbers now appear inside the die SVG shapes (single die: 82 px; 2–3 dice: 60 px; 4–5: 46 px; 6: 38 px)
- Roll toast: each die cycles its own 1–sides range independently during the animation
- Roll toast: on landing, single die shows the final total; multi-die shows per-die parsed values + "= total" sum
- Roll toast: d8 shape no longer has an inner horizontal line (would overlap the number)

---

## [1.6.10] - 2026-05-14

**Schema version:** 51
**Commit summary:** Dice shape icons in roll toast; one icon per die rolled
**Description:** The roll toast now displays an inline SVG icon for each die in the expression — roll `2d6+1d8` and you see two d6 shapes and one d8 shape wobbling during the animation. Icons are stroke-only outlines in the accent colour: d4 (triangle), d6 (rounded square), d8 (diamond), d10 (pentagon-kite), d12 (pentagon), d20 (triangle with inner lines), d100 (concentric circles). Up to 6 icons are shown; they scale down automatically for 4–6 dice. The icons wobble alternately during the rolling animation and stop when the result lands.

### Added
- Roll toast: SVG die-shape icons (d4/d6/d8/d10/d12/d20/d100) between the label and the rolling number
- Roll toast: die icons wobble during the animation and settle on landing

---

## [1.6.9] - 2026-05-14

**Schema version:** 51
**Commit summary:** Roll toast fires for all visible rolls, not just own rolls
**Description:** Previously the roll toast only appeared for the current user's own rolls. It now fires for every roll the user is allowed to see, using the same visibility rules as the roll log: `gm_only` toasts are suppressed for non-GMs, `gm_and_roller` toasts are suppressed for players who aren't the roller, and `public` rolls show to everyone. When someone else's roll triggers the toast, their character/display name is prepended to the label line (e.g. "🎲 Thorn — 1d20+5").

### Changed
- Roll toast: now shown for any roll visible to the current user, not just own rolls
- Roll toast: label includes the roller's name when showing someone else's roll
- Roll toast: visibility correctly gated (`gm_only` hidden from players, `gm_and_roller` hidden from uninvolved players)

---

## [1.6.8] - 2026-05-14

**Schema version:** 51
**Commit summary:** Dice tray in Player tab; ease-out roll animation
**Description:** A Dice panel now lives in the Player tab so players can roll without switching tabs. It has the same expression input, visibility select, quick-die buttons, and merge logic as the Roll Log tray. The roll animation is reworked from a fixed 70 ms interval to an ease-out timing curve (50 → 55 → 60 → 75 → 100 → 150 → 220 → 320 → 430 ms per frame) so it tumbles fast at first then slows to a suspenseful crawl before landing.

### Added
- Player tab: collapsible Dice panel with roll form, visibility selector, and quick-die buttons

### Changed
- Roll animation: replaced fixed-interval flicker with ease-out timing curve for suspense

---

## [1.6.7] - 2026-05-14

**Schema version:** 51
**Commit summary:** Roll popup works on mobile; dice cycling animation; remove 4d6kh3 quick-die
**Description:** Three small polish changes to rolling UX. On mobile the roll result popup was being hidden behind browser chrome at `bottom: 24px`; it now appears as a vertically-centred overlay instead. A brief dice-cycling animation (9 frames of random numbers at 70 ms each) precedes the real result, which lands with a bounce-scale effect. The `4d6kh3` quick-die button is removed from the D&D 5e dice tray — it was for one-time ability score generation during character creation and does not belong in the combat tray.

### Changed
- Roll popup: on mobile (≤640 px) the toast is centred on-screen instead of pinned at `bottom: 24px`
- Roll popup: the result number cycles through random values for ~630 ms before landing on the real total with a bounce animation
- D&D 5e quick dice: removed `4d6kh3` button

---

## [1.6.6] - 2026-05-14

**Schema version:** 51
**Commit summary:** Redesign HP stat block in mini-sheet with two-zone layout
**Description:** The HP area of the D&D 5e mini-sheet is reworked into a cleaner two-zone layout. The primary row shows a large current HP number flanked by circular −/+ step buttons, with AC and Speed as side chips in a column to the right. A footer row groups Temporary HP (with its own step buttons), hit dice, and the Short/Long rest buttons. Replaced the old 4-column `.msb-combat` grid.

### Changed
- Mini-sheet HP stat block: redesigned as primary row (HP stepper + AC/Speed chips) + footer row (Temp HP + hit dice + rest buttons)
- HP step buttons changed from rectangular (36 px) to 26 px circles for a more compact look
- Temp HP stepper moved to the footer row alongside hit dice and rest buttons

---

## [1.6.5] - 2026-05-14

**Schema version:** 51
**Commit summary:** Initiative tracker shows portraits for all combatants including GM
**Description:** The initiative tracker now shows the token portrait (image_url → colour swatch fallback) for every combatant entry, including GM entries which previously always rendered a plain 10 px colour dot. The `.init-swatch` CSS is bumped to 24 px to match the portrait image size so the column is consistent when no art is set.

### Changed
- Initiative tracker: GM card entries now show token portrait instead of a fixed colour swatch; falls back to swatch if no image is set
- `.init-swatch` CSS size increased from 10 px to 24 px to match portrait dimensions

---

## [1.6.4] - 2026-05-14

**Schema version:** 51
**Commit summary:** Remove session/settings buttons from topbar
**Description:** Start/End Session and Campaign Settings are now exclusively in the GM Tools Session card (added in 1.6.2). The duplicate buttons in the top row have been removed entirely, and the now-unused mobile CSS rule hiding them is also cleaned up.

### Changed
- Topbar: Start/End Session button and Campaign Settings link removed (accessible via GM Tools → Session card)

---

## [1.6.3] - 2026-05-14

**Schema version:** 51
**Commit summary:** Token management shows portraits and labels controller as GM
**Description:** Two small UX improvements to the Token Management panel. The "No controller" label in the controller dropdown is renamed to "GM" — clearer and shorter. Each token row now shows the token's portrait as a 28 px circle: it uses the token's own art (`image_url`) first, falls back to the linked character's portrait (`portrait_url`), and falls back to the colour swatch for tokens with neither.

### Changed
- Token Management: controller dropdown default option renamed from "No controller" to "GM"
- Token Management: token rows now show a 28 px circular portrait (token art → character portrait → colour swatch)

---

## [1.6.2] - 2026-05-14

**Schema version:** 51
**Commit summary:** Condense mobile topbar; move session controls to GM Tools
**Description:** On mobile (≤640 px) the campaign topbar is condensed to just the campaign title — the thumbnail and GM action buttons are hidden. Session controls (Start/End Session and Campaign Settings link) are moved to a permanent Session card at the top of the GM Tools drawer, so they are always reachable on any screen size. The topbar GM actions are hidden via media query on mobile but the buttons remain in GM Tools.

### Changed
- Mobile topbar: thumbnail and GM action buttons hidden on mobile; topbar collapses to a single title line
- GM Tools: new Session card at the top with Start/End Session button, live status indicator, and Campaign Settings link

---

## [1.6.1] - 2026-05-14

**Schema version:** 51
**Commit summary:** Initiative tracker uses full mini-sheet cards inline
**Description:** Clicking a combatant entry in the initiative tracker now expands the full interactive mini-sheet (HP +/− controls, ability roll buttons, skill/attack/spell tabs, rest buttons, wild shape) directly inside the tracker. The `.mini-body` DOM node is physically moved from the Characters section into the initiative card on expand and returned on collapse, so all existing event handlers continue working without duplication. For players this applies to their own characters; other combatants remain simple rows. For GMs this applies to their own characters in addition to the existing editable Init/HP inputs; other-player characters still show the static `buildInitSheet()` panel. All mini-sheet button handlers were re-delegated from `#player-char-list` to `#players-drawer` so they fire regardless of whether the buttons are in the Characters section or the initiative tracker.

### Changed
- Initiative tracker: expanding a combatant card for a linked own-character shows the full interactive mini-sheet (HP, abilities, skills, attacks, spells, rests) inline instead of a read-only stat panel
- Mini-sheet button event delegation widened from `#player-char-list` to `#players-drawer` so all handlers work when the sheet is displayed inside the initiative tracker

---

## [1.6.0] - 2026-05-13

**Schema version:** 51
**Commit summary:** Server-default theme env var and spell row shading in character sheets
**Description:** Two improvements. (1) A new `APP_DEFAULT_THEME` environment variable lets server operators set the theme applied to new/unauthenticated sessions instead of hardcoding "dark". Any valid theme slug is accepted; the default remains "dark". (2) Spell rows in the D&D 5e character sheet now have alternating row shading (even rows use the input background, odd rows use the card background) so long spell lists are easier to scan.

### Added
- `APP_DEFAULT_THEME` env var: operators can set the server-wide default UI theme (valid: `dark`, `midnight`, `dim`, `light`, `forest`, `bubblegum`, `fire`, `oled`, `hobbiton`, `hearthstone`, `mosswood`, `inkwell`, `forge`, `sepia`); defaults to `dark`

### Changed
- D&D 5e sheet → Spells: spell rows now have alternating background shading for readability

---

## [1.5.10] - 2026-05-13

**Schema version:** 51
**Commit summary:** GM initiative entries use mini-sheet card style with editable stats in body
**Description:** GM initiative tracker entries now use the same gradient-header card design as the Players-tab character mini-sheets. The header (always visible) shows the colour swatch, character name, current initiative, and HP. Clicking anywhere on the header expands a body showing editable initiative/HP inputs and remove button, followed by the character stat panel (AC, Speed, ability scores, attacks). Open/closed state is preserved across re-renders (e.g. when HP is edited). Active-turn entries get a brighter gradient on the header to maintain the highlight.

### Changed
- GM initiative tracker: entries redesigned to match mini-sheet card style; header shows name, initiative, and HP; body contains edit controls and character stats
- Open/expanded state is preserved when `renderBattle()` re-renders after an edit

---

## [1.5.9] - 2026-05-13

**Schema version:** 51
**Commit summary:** Dice roller and roll request combined into a single card
**Description:** The dice roller form and GM Roll Request panel at the bottom of the roll log drawer are now grouped inside a single "🎲 Dice Roller" card (gradient header, accent border, drop shadow). The roll request remains a collapsible sub-section within the card — its own outer card border and shadow are stripped so it blends flush into the parent card, separated only by a thin divider line.

### Changed
- Roll log drawer: dice roller form, quick-dice buttons, and GM Roll Request panel are now contained in a single unified card

---

## [1.5.8] - 2026-05-13

**Schema version:** 51
**Commit summary:** Roll log redesign — side-column total layout
**Description:** Roll log entries are redesigned with a side-column layout (Option B). Each card now has a narrow accent-tinted column on the left containing the roll total, and the right side holds a compact header (avatar, name, visibility badge, time) above the expression and breakdown. Visibility colouring (GM-only = danger red, GM+roller = amber) is expressed through the column background and border rather than a left stripe. Spell-cast, weapon-attack, and feature-used cards are unaffected.

### Changed
- Roll log: entries redesigned with side-column total layout; total moves to an accent-tinted left column, header simplified (no gradient), breakdown below expression in the right panel
- Roll log: visibility colour applied to total column background instead of left border stripe

---

## [1.5.7] - 2026-05-13

**Schema version:** 51
**Commit summary:** GM initiative entries expand inline to show character mini-sheet
**Description:** In the GM initiative tracker, clicking a combatant's name now expands that entry in place, showing a compact character sheet: AC, Speed, Initiative modifier, Passive Perception, a 6-stat ability score grid, and up to 6 attacks with hit bonus and damage. The row becomes a card with the existing controls as the header and the stat panel as a collapsible body. Manual combatants (no linked character) remain non-expandable. Players still get the previous behaviour (clicking opens the Players-tab mini-sheet card).

### Changed
- GM initiative tracker: each linked-character entry is a card that expands inline on name-click to show AC, Speed, Initiative mod, Passive Perception, ability scores, and attacks
- Player initiative tracker: name click still opens the Players-tab mini-sheet (unchanged)

---

## [1.5.6] - 2026-05-13

**Schema version:** 51
**Commit summary:** Initiative click-to-open mini-sheet, token art in player initiative, sepia theme
**Description:** Three improvements. (1) Initiative tracker rows with a linked character now open that character's mini-sheet when clicked (both GM and player views); the name is underline-dotted to hint interactivity. (2) Player initiative rows show the character's portrait/token art as a 24 px circle instead of the plain colour swatch; falls back to the swatch when no image is set. (3) New "Sepia" dark theme — warm amber ink on a deep espresso background, added alongside the fantasy theme set.

### Added
- Initiative tracker: clicking a row with a linked character opens (or closes) that character's mini-sheet and scrolls it into view
- Initiative tracker: player view shows token art portrait as a circular thumbnail next to each combatant name
- Settings → Appearance: new **Sepia** theme (dark amber/espresso palette matching the fantasy theme set)

### Changed
- `combatantFromToken` and char-picker now store `image_url` on each combatant for use by the player initiative render

---

## [1.5.5] - 2026-05-13

**Schema version:** 51
**Commit summary:** Card styling for roll log, initiative tracker, and pinned active encounter
**Description:** Three visual consistency updates. (1) Roll log cards, roll-request cards, and spell-cast cards all gain the accent-tinted border and drop shadow matching the new interface style; the card header now uses the gradient background with a 2px accent border-bottom (colour-coded per visibility: purple for public, red for GM-only, amber for GM+roller). (2) Initiative tracker rows are now individual rounded cards with an accent-tinted border and shadow; the active-turn row uses the full accent border instead of a left-only stripe. (3) The active/loaded encounter is always pinned at the top of the Encounters panel above the folder groups, regardless of search or tag filters; it is not duplicated inside its folder.

### Added
- Encounters panel: active encounter is always shown pinned above folder groups with an "▶ Active" label and a divider; it is excluded from folder groups to avoid duplication

### Changed
- Roll log: roll cards, roll-request cards, and spell-cast cards updated to match the site-wide card style (accent border, drop shadow, gradient header with 2px accent border-bottom)
- Roll log: header border-bottom colour-coded to match visibility — accent for public, danger for GM-only, amber for GM+roller
- Initiative tracker: rows changed from flat bottom-bordered items to individual rounded cards; active-turn row highlighted with full accent border and glow shadow

---

## [1.5.4] - 2026-05-13

**Schema version:** 51
**Commit summary:** Encounter items and folder groups rendered as mini cards
**Description:** Each saved encounter in the Encounters panel is now rendered as a rounded mini card (accent-tinted border, box-shadow, 8px radius) instead of a flat bordered row. The currently-active encounter keeps its cyan tint. Folder groups are also styled as cards with the same gradient header treatment as the GM Tools panels — accent-coloured folder name, chevron, overflow:hidden — with encounter cards stacked inside the folder body.

### Changed
- Encounters panel: each encounter row is a rounded mini card with accent border and drop shadow
- Encounters panel: folder group wrappers styled as cards with gradient header (matching GM Tools panel card style); chevron now accent-coloured
- Active encounter retains its cyan highlight inside the new card shape

---

## [1.5.3] - 2026-05-13

**Schema version:** 51
**Commit summary:** Card styling for GM Tools and Roll Request collapsible panels
**Description:** The three GM Tools panels (Encounters, Token Management, Music) and the GM-only Roll Request panel in the dice drawer now share the same card visual treatment as the character mini-sheets: accent-tinted border, 8px border-radius, drop shadow, gradient header that highlights on hover, and a 2px accent border-bottom on the header when open. The custom per-panel marker/chevron CSS is consolidated into a single `.gm-panel` class. Content inside each panel is padded via a `gm-panel-body` wrapper.

### Changed
- GM Tools drawer: Encounters, Token Management, and Music panels styled as cards matching the character sheet card design
- Dice/Roll Log drawer: Roll Request (GM-only) panel also styled as a card
- Per-panel `summary::marker` and chevron CSS consolidated into a single `.gm-panel` selector

---

## [1.5.2] - 2026-05-13

**Schema version:** 51
**Commit summary:** Mini-sheet always shows as a card; header is the sole open/close toggle
**Description:** The separate character name row above the expanded card is removed. The card (with its gradient header) is now always visible — clicking the header expands or collapses the body. The fav star and concentration dot are moved into the card header. The generic-template sheet also gets a styled card header. The favourites re-ordering logic is updated to sort `char-detail` nodes directly (no longer requires a `char-row` sibling).

### Changed
- Tabletop Players tab: character cards are always visible as styled cards; the flat name/expand-button row is removed
- Fav star (☆/★) and concentration dot (🧿) moved into the card header
- Clicking anywhere on the card header (except the fav star) opens/closes the body
- Generic-template characters also get a styled card header showing the character name and template type
- `applyFavs()` now sorts `char-detail` cards directly instead of pairing `char-row` + `char-detail` siblings

---

## [1.5.1] - 2026-05-13

**Schema version:** 51
**Commit summary:** Mini-sheet card style and header as open/close toggle
**Description:** The D&D 5e (and generic) mini-sheet panel is now presented as a card: rounded corners, accent-coloured border, drop shadow, and no ambient padding so the gradient header bleeds cleanly to the card edges. The expand/collapse arrow button has been removed from the character name row; instead, clicking the gradient header (or the character name row) opens and closes the card. The header shows a ▶ arrow that rotates 90° when the card is open, and highlights on hover to make its interactivity clear.

### Changed
- Tabletop mini-sheet: presented as a rounded card with border, box-shadow, and overflow-hidden
- Tabletop mini-sheet: header is now the primary open/close toggle (▶ arrow indicator, hover highlight); the separate expand button on the character name row has been removed
- Character name row click still also opens/closes the card for convenience

---

## [1.5.0] - 2026-05-13

**Schema version:** 51
**Commit summary:** Option A — full D&D 5e mini-sheet redesign with stat block header and tab strip
**Description:** Complete visual redesign of the D&D 5e mini-sheet panel in the tabletop Players tab. The old flat list of rows is replaced by a structured layout with three zones: (1) a gradient header showing character name, class(es), race, and level; (2) a compact stat block with HP/Temp/AC/Speed in a 4-column grid and a rest bar beneath it; (3) a 3-row ability grid showing modifier values prominently (raw scores removed) above roll buttons, with the Check/Save toggle retained. Below the ability grid, a tab strip organises Skills, Attacks, and Spells into separate panels — tabs only appear when that section has content. Active tab is persisted per-character in `localStorage`. All existing JS data attributes and behaviour (HP live-edit, Short/Long rest, ability rolls, attacks, spells, Wild Shape transform) are preserved unchanged.

### Added
- Tabletop mini-sheet: gradient header zone showing character name, class/race/level subtitle
- Tabletop mini-sheet: compact stat-block grid — HP (editable), Temp HP, AC, Speed in a 4-column row; Hit Dice and Short/Long rest buttons on the row below
- Tabletop mini-sheet: tab strip (Skills | Attacks | Spells) — Attacks and Spells tabs only rendered when the character has content for them; active tab persisted to `localStorage`

### Changed
- D&D 5e mini-sheet layout fully redesigned — raw ability scores removed; modifiers shown at larger size (`mac-mod-lg`); sheet body reorganised into header / stat block / abilities / tabbed content zones
- Tab content replaces the previous always-visible collapsible sections for Skills, Attacks, and Spells; Wild Shape bar remains below tabs

---

## [1.4.9] - 2026-05-13

**Schema version:** 51
**Commit summary:** Fix internal server error — unclosed Jinja2 block after spells section
**Description:** v1.4.8 introduced a Jinja2 template error that caused a 500 on every tabletop page load. When the Wild Shape block was inserted after the Spells section, the `{% endif %}` that closed the `{% if _spell_vis.any %}` block was accidentally consumed by the replacement and not restored, leaving the block open. Added the missing `{% endif %}` after the spells collapsible closing tag.

### Fixed
- Tabletop page: 500 internal server error caused by an unclosed `{% if _spell_vis.any %}` Jinja2 block introduced in v1.4.8

---

## [1.4.8] - 2026-05-13

**Schema version:** 51
**Commit summary:** Fix Wild Shape never appearing; move to below spells; ability toggle Check/Save
**Description:** Two bugs fixed and one new UI feature. (1) The Wild Shape / Polymorph transform bar was never shown because Jinja2 `{% set %}` inside `{% for %}` loops does not write back to the outer scope — `_druid_lv`, `_moon`, and `_has_poly` were always their initial values. The block is rewritten using `namespace()` so loop assignments propagate correctly. Legacy top-level `class`/`level` fields are also checked as a fallback. (2) The transform bar is moved from above Abilities to below Spells, matching the user's requested position. (3) The two separate Check and Save button rows in the Abilities grid are replaced with a single row of combined buttons. A Check/Save pill toggle above the grid switches all six buttons between ability check and saving throw mode, keeping the layout compact while giving quick access to both rolls.

### Fixed
- Wild Shape / Polymorph bar was never rendered for any character — Jinja2 loop scoping bug caused `_druid_lv` and `_has_poly` to always be their default (0 / false); rewritten with `namespace()`
- Legacy `class`/`level` top-level sheet fields now also count toward druid level detection (in addition to the classes roster)

### Changed
- Tabletop mini-sheet: Wild Shape / Polymorph bar moved to below the Spells section
- Abilities grid: the separate Check and Save rows (12 buttons) are replaced by 6 combined buttons with a Check / Save pill toggle; clicking the toggle switches all buttons between ability check and saving throw rolls without changing the layout

---

## [1.4.7] - 2026-05-13

**Schema version:** 51
**Commit summary:** Clicking character name row toggles mini-sheet open/closed
**Description:** In the tabletop Players tab, the character name and the blank space around it now toggle the mini-sheet panel open or closed, the same as clicking the ▶/▼ expand button. The fav-star button on the left and the expand button on the right are excluded so their own actions still work. The name text gains a pointer cursor to signal it is interactive.

### Changed
- Tabletop Players tab: clicking the character name or blank row area expands/collapses the mini-sheet (previously only the ▶ button did this)

---

## [1.4.6] - 2026-05-13

**Schema version:** 51
**Commit summary:** Wild Shape favorites dropdown on tabletop mini-sheet
**Description:** The Wild Shape button in the tabletop mini-sheet is now a dropdown. Clicking "🐺 Wild Shape ▾" expands a panel that lists the druid's saved favorite beasts as direct-transform buttons (name + CR + HP shown per row). Clicking any row immediately posts to the transform API and reloads the page — no full beast picker modal required. A "⊕ Browse all…" button at the bottom of the dropdown opens the full beast picker for searching/adding favorites. When no favorites are saved yet, the dropdown shows a prompt to use Browse. The dropdown closes when clicking outside or selecting a beast. The ▾ arrow rotates to ▴ while open.

### Added
- Tabletop mini-sheet: Wild Shape button is now a dropdown listing saved favorites as one-click transform buttons
- Each favorite row shows creature name, CR, and HP; clicking transforms immediately without opening the picker modal
- "Browse all…" entry at the bottom opens the full beast picker (same path as before)
- Dropdown closes on outside click; arrow rotates to indicate open/closed state

### Changed
- Wild Shape button changed from a direct picker-open button to a dropdown trigger; full picker accessible via "Browse all…"

---

## [1.4.5] - 2026-05-13

**Schema version:** 51
**Commit summary:** Fix Wild Shape not replacing STR/DEX/CON with beast's physical stats
**Description:** After a Wild Shape or Polymorph transform, the character sheet was not reliably showing the beast's physical ability scores (STR/DEX/CON). Two bugs fixed: (1) `_o5e_ability` only tried the lowercase 3-letter key (`str`) when reading nested `ability_scores` from the Open5e v2 API — if the endpoint returns uppercase (`STR`) or full-name (`strength`) keys the scores silently fell back to 10; now all three variants are tried. (2) SQLAlchemy's plain `JSON` column does not always detect a JSON dict mutation as dirty even when re-assigned; `flag_modified(char, "sheet")` is now called before every `db.commit()` in the transform and revert endpoints to guarantee the change is written.

### Fixed
- Wild Shape / Polymorph: STR/DEX/CON (and other ability scores) now correctly replaced with the beast's stats after transforming
- `_o5e_ability` now tries lowercase short (`str`), uppercase short (`STR`), and full name (`strength`) keys inside `ability_scores`, so ability scores are correctly parsed regardless of which Open5e API build is in use
- Transform and revert endpoints: `flag_modified(char, "sheet")` added before every commit to ensure SQLAlchemy detects the JSON mutation and persists it

---

## [1.4.4] - 2026-05-13

**Schema version:** 51
**Commit summary:** Embed full SRD stat blocks in Quick Pick presets — works completely offline
**Description:** Previously, Quick Pick preset rows only carried HP and AC; ability scores, attacks, speed, and traits only appeared if the Open5e background fetch succeeded. All 27 preset beasts now have fully embedded SRD stat blocks (STR/DEX/CON/INT/WIS/CHA, all speed types, traits such as Pack Tactics / Keen Smell / Pounce / Spider Climb, complete action descriptions with attack bonuses and damage dice, and a one-sentence description summarising each form's Wild Shape use case). The detail panel renders the complete stat block immediately on row click with no API dependency. The Open5e background fetch still runs when available and may enrich data further, but the preset is fully usable without it.

### Changed
- All 27 Quick Pick presets now embed full SRD stat blocks: abilities, speed (all movement types), traits, actions, and a description
- Beast picker detail panel: traits section added (bullet list of passive abilities); description shown in italics below the creature type line; speed now shows all movement types (walk, fly, swim, burrow, climb) instead of walk-only
- Preset detail is rendered immediately on click — no API call required for complete stat display

---

## [1.4.3] - 2026-05-13

**Schema version:** 51
**Commit summary:** Token Ring panel collapsed by default
**Description:** The Token Ring colour/style picker on the character sheet now starts collapsed. A clickable "Token Ring ▶" header expands it; clicking again collapses it. No state is persisted — it re-collapses on each page load.

### Changed
- Character sheet: Token Ring panel is collapsed by default; click the header row to expand/collapse

---

## [1.4.2] - 2026-05-13

**Schema version:** 51
**Commit summary:** Fix beast picker 502 — presets select instantly, backend resolves v1 slugs via name search
**Description:** v1.4.1's preset slug resolution fired a `/api/open5e/monsters` search on every row click, which returned 502 and left the Transform button permanently disabled when Open5e was unreachable. Presets now select immediately using their cached stats (same path as search results), with full stats fetched in the background and silently ignored on failure. The backend `_fetch_open5e_creature` now falls back to a name-search when a direct slug lookup 404s, so v1-style slugs (`wolf`) resolve to the correct v2 key automatically. `_runSearch` now calls `_renderList()` even on failure so Quick Picks and Favorites remain visible when the search API is down.

### Fixed
- Beast picker: opening the picker / clicking a preset no longer shows 502 when Open5e is unreachable
- Preset rows now select instantly (HP/AC shown from local data); Transform button enables immediately
- `_fetch_open5e_creature`: v1-style slugs that 404 on `/v2/creatures/{slug}/` are automatically resolved via name search (`brown-bear` → search → `brown-bear-a5esrd`)
- Beast picker: Quick Picks and Favorites remain visible even when the `/api/open5e/monsters` search returns an error

---

## [1.4.1] - 2026-05-13

**Schema version:** 51
**Commit summary:** Fix Quick Picks transform failure; add ability scores and attacks to beast detail panel
**Description:** Quick Picks (preset beasts) could not transform because they used Open5e v1-style slugs (`wolf`) while the backend fetches from the v2 API which uses different keys. Selecting a preset now triggers a name-search to resolve the real v2 slug before sending to the transform endpoint. The detail panel in the beast picker also now shows a full ability score table (STR/DEX/CON/INT/WIS/CHA with modifiers), speed, and all actions/attacks when any beast (preset, favorite, or search result) is selected, via a new `?full=1` mode on the creature-detail endpoint.

### Fixed
- Wild Shape Quick Picks could not transform — preset slugs were v1-style and did not match Open5e v2 keys; clicking a preset now resolves the correct v2 slug via a name search before enabling Transform

### Added
- Beast picker detail panel: ability score grid (STR/DEX/CON/INT/WIS/CHA + modifiers), speed, and full action/attack list shown for every selected beast
- `GET /api/open5e/creature/{slug}?full=1` — returns ability scores, actions, and speed in addition to the lite shape; used by the picker detail panel

---

## [1.4.0] - 2026-05-13

**Schema version:** 51
**Commit summary:** Wild Shape quick-pick presets in the beast picker
**Description:** The Wild Shape beast picker now shows a "⚡ Quick Picks" section populated from a hardcoded list of 27 common SRD beasts, automatically filtered to the druid's current CR cap. Players can pick Wolf, Brown Bear, Dire Wolf, Tiger, and many others without typing a search term. The presets respect the Free Pick toggle (shows all 27 when on), de-duplicate against the ★ Favorites section so each beast only appears once, and are fully selectable for the Transform action. No schema change.

### Added
- Wild Shape / Beast Picker: "⚡ Quick Picks" section with 27 curated SRD beasts (Cat, Rat, Raven, Poisonous Snake, Giant Rat, Wolf, Panther, Giant Badger, Constrictor Snake, Black Bear, Ape, Giant Wasp, Brown Bear, Dire Wolf, Giant Spider, Tiger, Giant Constrictor Snake, Polar Bear, Allosaurus, Ankylosaurus, Killer Whale, Giant Scorpion, Elephant, Triceratops, Giant Crocodile, Mammoth, Tyrannosaurus Rex)
- Presets are filtered by CR cap at render time; Free Pick shows all 27; presets already in Favorites are hidden to avoid duplicate rows
- `_findInState()` extended to resolve clicks on preset rows (no live-search result required)

---

## [1.3.0] - 2026-05-13

**Schema version:** 51
**Commit summary:** Token ring colour and style picker on the character sheet
**Description:** Players can now customise the decorative ring drawn around their token on the tabletop directly from their character sheet. A new "Token Ring" panel appears below the portrait (edit mode, campaign characters only) with a colour swatch and five ring-style choices: Solid, Dashed, Double, Glow, and Spiked. Changes are broadcast in real time over WebSocket so every connected client sees the updated ring immediately. Ring style is stored in a new `ring_style` column on the `characters` table (schema v51). The canvas reads both the character's preferred colour and style from a `charById` lookup map, allowing per-character ring customisation independently of the per-token GM colour override.

### Added
- Character sheet: "Token Ring" panel below portrait — colour swatch + five ring-style buttons (Solid, Dashed, Double, Glow, Spiked) with inline SVG previews
- `POST /api/campaign/{id}/character/{id}/ring-style` — player or GM sets ring colour and style; broadcasts `character_ring_update` over WebSocket
- Five canvas ring styles in `tabletop.js`: `_drawRing()` with solid, dashed, double-concentric, glow (canvas shadow), and 8-point spiked star

### Changed
- `tabletop.js`: `drawToken()` now reads ring colour and style from a `charById` lookup (`character.color`, `character.ring_style`) instead of using only `t.color`
- `tabletop.js`: new `character_ring_update` WebSocket handler updates `charById` and re-renders the canvas
- `char_data` payload now includes `ring_style` so the canvas has the value on page load

### Schema
- `characters.ring_style VARCHAR(20)` — nullable, defaults to `solid` when absent (schema v51)

---

## [1.2.11] - 2026-05-13

**Schema version:** 50
**Commit summary:** Fix spell slot and resource pip buttons stretched into ovals by global min-height rule
**Description:** The global `button { min-height: 44px }` rule introduced in v1.2.7 was overriding the explicit `height` on the 18 px spell slot pips and 14 px resource pips, causing them to stretch vertically into ovals. Added `min-height:0` to both pip button inline styles so they can render at their intended square size while still being governed by the global rule everywhere else.

### Fixed
- Character sheet: spell slot pips restored to 18×18 px circles (`min-height:0` added to inline style)
- Character sheet: class resource pips restored to 14×14 px circles (`min-height:0` added to inline style)

---

## [1.2.10] - 2026-05-13

**Schema version:** 50
**Commit summary:** Touch target remediation phase 3 — D&D 5e character sheet section buttons
**Description:** Added `.sheet-section-btn { font-size: 11px; min-height: 44px; padding: 0 10px; }` to the `sheet_dnd5e.html` `<style>` block and replaced inline `font-size:11px;padding:2px 8px` / `padding:3px 10px` overrides on 24 section-header action buttons with the new class. Complex buttons with custom visual styles (rest buttons, browser close/search, filter chips) had only their padding overrides removed. All elements now derive their 44 px minimum tap height from the global `button { min-height: 44px }` rule with no conflicting padding overrides. Completes the three-phase touch target remediation.

### Changed
- `sheet_dnd5e.html`: `.sheet-section-btn` CSS class added (44 px min-height)
- `sheet_dnd5e.html`: 24 section-header buttons converted to `.sheet-section-btn` — `#char-edit-btn`, `#bg-sync-btn`, `#feats-add-btn`, `#mc-add-class-btn`, `#hp-rolls-apply-max`, `#hp-rolls-fill-avg`, `#ab-edit-btn`, `#ab-done-btn`, `#st-edit-btn`, `#st-done-btn`, `#sk-edit-btn`, `#sk-done-btn`, `#browse-weapons-btn`, `#add-custom-attack-btn`, `#spell-browser-btn`, `#add-custom-spell-btn`, `#hide-unprepared-btn`, `#sc-autofill-btn`, `#resources-sync-btn`, `#resources-add-btn`, `#wild-shape-btn`, `#polymorph-btn`, `#browse-items-btn`, `#add-custom-item-btn`, `#sync-race-btn`, `#sync-class-btn`
- `sheet_dnd5e.html`: padding overrides removed from `#short-rest-btn`, `#long-rest-btn`, `.defense-custom-add-btn`, `#ib-search-btn`, `#ib-close-btn`, `#sb-search-btn`, `#sb-close-btn`, `.ib-cat` chips, `.sb-lvl` chips

---

## [1.2.9] - 2026-05-13

**Schema version:** 50
**Commit summary:** Touch target remediation phase 2 — tabletop encounter panel and roll-request controls
**Description:** Replaced all inline `padding` and `font-size` style strings on JS-created encounter-library buttons with named CSS classes (`.enc-action-btn`, `.enc-modal-btn`, `.enc-spawn-btn`) in the tabletop `<style>` block. Removed padding overrides from the encounter edit form inputs and selects, the roll-request panel buttons and visibility select, the audio-enable button, and the Import & Place button in `tabletop.js`. All elements now inherit the global 44 px (standard) or 32 px (compact) min-height rules without inline overrides fighting them.

### Changed
- `tabletop.html`: encounter action icon buttons (💾 📋 ✎ 🗑) now use `.enc-action-btn` CSS class (32 px min-height, compact panel)
- `tabletop.html`: encounter edit Save / Cancel buttons now use `.enc-modal-btn` CSS class (44 px min-height)
- `tabletop.html`: spawn-point Set / Clear buttons now use `.enc-spawn-btn` CSS class (32 px min-height, compact panel)
- `tabletop.html`: encounter edit form inputs and selects no longer override padding — inherit global 44 px min-height
- `tabletop.html`: roll-request panel `#rr-send-btn`, `#rr-clear-btn`, `#rr-vis` select — padding overrides removed
- `tabletop.html`: `#audio-enable` button — padding override removed
- `tabletop.js`: Import & Place button — padding override removed

---

## [1.2.8] - 2026-05-13

**Schema version:** 50
**Commit summary:** Touch target remediation phase 1 — campaign settings selects
**Description:** Removed the inline `padding` overrides from the playlist category select and the encounter-library sort select in campaign settings. Both now fall through to the global `select { min-height: 44px }` rule introduced in v1.2.7. The `.track-actions` audio buttons were already compliant via the global `button` rule and required no changes.

### Fixed
- Campaign settings: playlist category `<select>` (`pl-category-select`) no longer overrides padding — inherits global 44 px min-height
- Campaign settings: encounter library sort `<select>` (`enc-lib-sort`) no longer overrides padding — inherits global 44 px min-height

---

## [1.2.7] - 2026-05-13

**Schema version:** 50
**Commit summary:** Enforce Apple 44px minimum touch targets across the tabletop UI
**Description:** Added `min-height: 44px` to the global `button` rule (with `display: inline-flex; align-items: center; justify-content: center`) and to `input`/`select` in `style.css`, so all standard interactive elements meet Apple's HIG minimum by default. Compact button classes inside the tabletop's dense panels (mini-sheet, tracker, concentration controls) are overridden to 32–36 px — a large improvement from the previous 12–17 px — with 44 px applied to standalone action buttons (quick-die, rest, roll-request presets, character-expand, open-full). CLAUDE.md updated with a standing rule covering future touch-target requirements.

### Changed
- `style.css`: base `button` rule gains `min-height: 44px; display: inline-flex; align-items: center; justify-content: center`
- `style.css`: `input` (non-checkbox/radio/range) and `select` gain `min-height: 44px`
- `tabletop.html`: `.char-expand-btn`, `.mini-open-full`, `.mini-rest-btn`, `.rr-quick`, `.rr-dc-preset` → `min-height: 44px`
- `tabletop.html`: `.tt-btn`, `.tt-ctrl`, `.mini-hp-step`, `.mac-btn`, `.mini-sk-btn`, `.conc-controls button` → `min-height: 36px`
- `tabletop.html`: `.mini-roll-btn`, `.mini-cast-btn`, `.mini-strike-btn` → `min-height: 32px`
- `CLAUDE.md`: added touch-target rule requiring 44 px on standard elements and ≥32 px on compact panel elements

---

## [1.2.6] - 2026-05-13

**Schema version:** 50
**Commit summary:** Show roll expression in roll log cards
**Description:** Each roll log card now displays the original formula (e.g. `3d20d`, `1d20+5`) as a small monospace line above the large total, matching exactly what was typed in the roller input. Both the server-rendered history cards and live WebSocket cards are updated.

### Added
- Roll log: formula line (`.roll-card-expr`) above the total on every roll card, showing the original expression as typed

---

## [1.2.5] - 2026-05-13

**Schema version:** 50
**Commit summary:** Enlarge roll-expression clear button touch target for iPad/mobile
**Description:** The ✕ clear button inside the roll expression field had a ~12×14 px tap area, which is far too small for touch devices and caused it to appear non-functional on iPad. The button now spans the full height of the input row and is 44 px wide, meeting Apple's minimum 44×44 px touch-target guideline. The input's right padding is increased to match so typed text never slides under the button.

### Fixed
- Dice roller: ✕ clear button touch target enlarged to 44 px wide × full input height; reliable on iPad and other touch devices

---

## [1.2.4] - 2026-05-13

**Schema version:** 50
**Commit summary:** Fix dice parser to correctly handle count > 1 on advantage/disadvantage rolls
**Description:** When the client consolidates repeated quick-die clicks into e.g. `3d20d`, the dice parser was ignoring the count and only rolling a single disadvantage pair (2 dice). It now rolls one pair per count, keeps the appropriate value from each pair, and sums the results. The breakdown reflects each pair: `3d20d[14,6]kl1 [3,11]kl1 [17,2]kl1=11 => 11`.

### Fixed
- Dice parser: `Nd20d` / `Nd20a` now rolls N independent advantage/disadvantage pairs instead of silently ignoring the count

---

## [1.2.3] - 2026-05-13

**Schema version:** 50
**Commit summary:** Reverse roll log order — newest entries at the bottom
**Description:** The roll log now shows the oldest entries at the top and the newest at the bottom, matching a chat-style reading direction. The drawer body auto-scrolls to the bottom whenever a new card is appended and whenever the Roll Log tab is opened.

### Changed
- Roll log: entries are displayed oldest-to-newest (newest at bottom) instead of newest-to-oldest
- Roll log: drawer body auto-scrolls to the latest entry on new roll, and when the Roll Log tab is opened

---

## [1.2.2] - 2026-05-13

**Schema version:** 50
**Commit summary:** Consolidate repeated quick-die clicks into a single dice term
**Description:** Clicking the same quick-die button multiple times now merges the dice count into a single term instead of concatenating separate expressions. For example, clicking d20 three times produces `3d20` rather than `1d20+1d20+1d20`. Works for all die types including advantage/disadvantage and keep-highest modifiers (e.g. three dis clicks → `3d20d`).

### Fixed
- Dice roller: repeated quick-die clicks now consolidate into one term (e.g. `3d20d` instead of `1d20d+1d20d+1d20d`)

---

## [1.2.1] - 2026-05-13

**Schema version:** 50
**Commit summary:** Roll formula clear button
**Description:** A ✕ button appears inside the roll expression input once the user starts typing. Clicking it clears the formula and returns focus to the input.

### Added
- Dice roller: ✕ button inside the roll expression field clears the typed formula; button is hidden when the field is empty

---

## [1.2.0] - 2026-05-13

**Schema version:** 50
**Commit summary:** Animated map thumbnails, encounter folder persistence, UI polish
**Description:** GIF and video maps now generate a static JPEG thumbnail on upload (Pillow frame 0 for GIFs; ffmpeg for MP4/WebM) — the thumbnail is used in encounter cards so animated content displays instantly without loading the full animation. Encounter folder open/closed state is now persisted to localStorage per campaign, surviving page reloads. The current-encounter chip in the Encounters panel header now uses the amber tag-chip style (matching active tag chips). A ⟳ Refresh button is added to the Token Management panel. The player sound panel is simplified to: track name, progress bar, enable-audio button, and mute + volume slider — removing the category volume slider, resync button, and settings link.

### Added
- Maps: static JPEG thumbnail generated on upload for GIFs (Pillow frame 0) and videos (ffmpeg at 0.5 s); `thumbnail_url` stored in the database and returned in encounter API responses
- Encounters: `map_thumbnail_url` field in the encounter API response; `buildRow` uses it in preference to `map_image_url` for the card thumbnail
- Token Management panel: ⟳ Refresh button rerenders the token tracker list without reloading the page
- Encounter folders: open/closed state saved to `localStorage` keyed by campaign ID — persists across page reloads

### Changed
- Encounters: current-encounter chip in the panel header now styled as an amber tag chip (matching active tag filter chips) instead of the previous cyan chip
- Player sound panel: simplified to track name (summary), progress bar, enable-audio button, and mute + volume slider row; category volume section, resync button, and category-volumes link removed

### Schema
- v50: `ALTER TABLE maps ADD COLUMN thumbnail_url VARCHAR(500)`

---

## [1.1.0] - 2026-05-13

**Schema version:** 49
**Commit summary:** Map folders, encounter editor inline labels, checkbox layout fixes
**Description:** Maps in Campaign Settings can now be organised into named folders — each folder renders as a collapsible `<details>` group. A Folder column (auto-saves on blur, datalist autocomplete) and a Folder field in the upload form are added. The encounter editor fields (Name, Notes, Tags, Folder, Map, Playlist/Mode) now render their labels inline to the left of each input rather than stacked above, saving vertical space. The "Stop audio on load" and "Use spawn points" checkboxes have `flex-direction:row` enforced so the tick box is always to the left of the label text.

### Added
- Maps: `folder` column on the `maps` table (schema v49); maps in Campaign Settings are grouped into collapsible folder sections
- Maps: Folder column in the map table (auto-saves on blur); Folder field in the Upload Map form; datalist autocomplete from existing map folders

### Changed
- Encounter editor: field labels (Name, Notes, Tags, Folder, Map, Playlist/Mode) now appear inline to the left of each input instead of stacked above — saves ~40 % of vertical height in the edit panel
- Encounter editor: "Stop audio on load" and "Use spawn points" checkboxes explicitly use `flex-direction:row` so the checkbox is always visually to the left of the text

### Schema
- v49: `ALTER TABLE maps ADD COLUMN folder VARCHAR(120) DEFAULT ''`

---

## [1.0.0] - 2026-05-13

**Schema version:** 48
**Commit summary:** Encounter card redesign, tag auto-expand, character remove-from-campaign
**Description:** Encounter cards are restructured — the thumbnail now fills the left side at full card height with a hover-reveal ▶ play button overlaid on it; the separate play button is removed. Meta info (token count, description, tags) moves to the right column beneath the action buttons. Selecting a tag in the encounter filter automatically expands any collapsed folders that contain matching encounters. Campaign Settings character management now detaches a character from the campaign instead of deleting it — the sheet and user assignment are preserved.

### Changed
- Encounter cards: thumbnail is now a tall left-column panel (52 px wide, full card height) with an overlay ▶ play button that appears on hover; separate ▶ load button removed from the action row
- Encounter cards: meta info (token/init counts), description, and tag chips moved from below the thumbnail to below the action buttons in the right column
- Encounter tag filter: selecting a tag auto-expands all folders that contain matching encounters
- Campaign Settings → Characters: "Delete" button renamed to "Remove"; action now sets `campaign_id = NULL` on the character record rather than deleting it — the sheet and owner assignment are untouched

---

## [0.99.0] - 2026-05-12

**Schema version:** 48
**Commit summary:** GM "View as Player" preview mode
**Description:** GMs can now open the tabletop rendered exactly as any player would see it. A "Preview Tabletop as Player" picker in Campaign Settings → People opens a new tab at `/campaign/{id}?view_as={user_id}`. The page renders with `is_gm=False` for the chosen player — their roll log (only rolls they can see), their Player tab, no GM Tools drawer, no token management, etc. A fixed amber banner at the top identifies the preview and provides an "Exit preview" link back to the GM view. The session gate is bypassed so the GM can preview even when the session is inactive.

### Added
- Campaign Settings → People: "Preview Tabletop as Player" section with a player dropdown and "👁 View as Player" button; opens `/campaign/{id}?view_as={user_id}` in a new tab
- Tabletop route: `?view_as=<user_id>` query parameter; GM-only — verified the target is a campaign member before switching context
- Tabletop: amber fixed banner shown in preview mode displaying the player name and an "Exit preview" link

---

## [0.98.1] - 2026-05-12

**Schema version:** 48
**Commit summary:** GM music panel speaker emoji replaced with mute toggle button
**Description:** The 🔊 span in the GM Tools music progress bar is now a clickable button that toggles mute on/off. It shows 🔊 when unmuted and 🔇 when muted, with a matching tooltip. The slider auto-mutes/unmutes as before, and the button stays in sync.

### Changed
- GM Tools music panel: speaker emoji (`🔊`) replaced with `<button id="audio-mute">` that toggles mute; label updates to 🔇 when muted and back to 🔊 when unmuted
- `audio.js`: mute button label/title kept in sync from the volume slider and on page load

---

## [0.98.0] - 2026-05-12

**Schema version:** 48
**Commit summary:** Open5e tab in Add Token modal, collapsible panel state persistence, TODO backlog additions
**Description:** The Add Token modal on the tabletop now includes an Open5e tab — GMs can search any creature by name, preview its type/CR, and click "Import & Place" to import the template and drop a token at the viewport centre in one step. All `<details>` panels on the tabletop page (initiative, roll requests, encounters, music, token management, etc.) now remember their open/closed state per campaign in `localStorage` and restore automatically on page load. Three new backlog items were added to TODO.md: Playlist Builder with Existing Songs, Initiative Tracker Roll Prompt, and Philips Hue Integration.

### Added
- Add Token modal: new **Open5e** tab with live creature search (debounced, 350 ms), name/type/CR preview rows, and an "Import & Place" button that imports the creature template and places a token at the viewport centre
- Tabletop: all `<details id="…">` panels persist their open/closed state to `localStorage` keyed by `vtt_details_{campaignId}_{panelId}`; state is restored on next load
- TODO.md: Playlist Builder with Existing Songs, Initiative Tracker Roll Prompt, Philips Hue Integration backlog entries

---

## [0.97.0] - 2026-05-12

**Schema version:** 48
**Commit summary:** GM sound panel removed from Player tab; volume slider added to music progress bar
**Description:** GMs no longer see the Sound section in the Player drawer — all audio controls are in GM Tools. The progress bar row in the GM Tools music panel now has a 🔊 volume slider occupying the right third of the line. The browser-autoplay unlock button (`audio-enable`) is also wired into the GM Tools panel so GMs can unblock audio without the player sound panel.

### Changed
- Player drawer: Sound section (`#player-sound-panel`) is now hidden for GMs; it remains visible for players
- GM Tools music panel: progress bar row restructured — left 2/3 is the elapsed / track bar / total, right 1/3 is a 🔊 master volume slider (`id="audio-volume"`)
- GM Tools music panel: `id="audio-enable"` (browser autoplay unlock) button added above the progress bar, hidden by default, shown by `audio.js` when needed

---

## [0.96.0] - 2026-05-12

**Schema version:** 48
**Commit summary:** Open5e creature search, spawn snapping fix, map dimension auto-detect
**Description:** Adds an inline Open5e creature search panel to the token templates section so GMs can search and import any monster without leaving campaign settings. Fixes spawn point placement so any click within a grid cell reliably registers for that cell. Map uploads now auto-detect pixel dimensions from the image file (Pillow on the backend; Image/Video API on the frontend for instant pre-fill); the width/height fields remain editable as a fallback for video maps or manual override.

### Added
- Token Templates: "🔍 Open5e" button opens an inline search panel; type to search creatures, click Import to create a D&D 5e token template in one step (uses existing `/api/open5e/monsters` proxy and `/api/campaign/{id}/templates/import-monster` endpoint)
- Map upload: client-side dimension detection via `Image`/`Video` API — width and height fields auto-populate when a file is selected, with a "✓ Dimensions detected from image" confirmation note
- `Pillow` added to `requirements.txt` for server-side image dimension detection

### Changed
- Open5e base URL is now read from `OPEN5E_BASE_URL` env var (defaults to `https://api.open5e.com`) across all creature-fetching endpoints in tabletop_routes.py
- Spawn point snapping changed from `Math.round` to `Math.floor` so clicking anywhere within a grid cell places the spawn in that cell, not the nearest grid-line intersection (affects both mouse and touch handlers)
- Map upload (both `/campaign/{id}/settings/maps` and admin route): if the uploaded file is an image, Pillow reads its actual pixel dimensions and overrides the form values

---

## [0.95.0] - 2026-05-12

**Schema version:** 48
**Commit summary:** Initiative tracker battle controls + UI declutter + multi-select token picker
**Description:** Moves all battle management into the Initiative tracker (GM-only), removes the dedicated Battle tab and drawer, cleans up header labels, increases encounter folder font size with bold-on-open, adds multi-select to the player token modal, and updates token cards to use portrait thumbnails prominently.

### Changed
- Initiative tracker: From Map / +Character / +Manual / Roll All combatant buttons moved to top of initiative panel (GM-only)
- Initiative tracker: ◀ / Next ▶ / ↺ Start / 🗑 navigation buttons now appear above the initiative list instead of below
- Removed Battle tab button and Battle drawer panel entirely
- Removed "Player" heading text from the Player drawer (tab label unchanged)
- Removed "GM Tools" heading text from the GM Tools drawer (tab label unchanged)
- Encounter folders: font size increased from 10px to 13px; folder name bolds when expanded
- Token selector (Players tab): cards now toggle a selection state; a "Place Selected (N)" button places all chosen characters at once; removing an on-map token still works with a single click

---

## [0.94.0] - 2026-05-12

**Schema version:** 48

**Commit summary:** Encounter save form — map-tag auto-fill, song mode, folder dropdown, stop-audio inline

**Description:** Four improvements to the encounter save form. Selecting a map now auto-populates the Tags field with that map's tags. Playback mode gains a "Song" option that shows a track picker populated from the selected playlist; the chosen track is stored in a new `auto_play_track_id` column on `encounters` (schema v48) and played directly on load. The folder field is replaced with a smart dropdown showing existing folders plus a "+ New folder…" sentinel that reveals a text input. The "Stop audio on load" checkbox moves inline with the playback mode selector.

### Added
- `auto_play_track_id` nullable FK column on `encounters` (schema v48)
- "Song" playback mode: stores a specific track and seeks it on encounter load
- Song picker `<select>` that populates from the chosen playlist's tracks
- Folder dropdown built from existing encounter folders; "+ New folder…" reveals a text input
- `ENC_MAP_TAGS` and `PLAYLIST_TRACKS` JS constants emitted from Jinja2 for client-side lookups

### Changed
- Selecting a map in the encounter save form auto-fills the Tags field
- Stop audio on load checkbox moved inline with the playback mode selector
- Map/playlist selectors moved to a 2-column row; mode row is separate

### Schema
- `encounters.auto_play_track_id INTEGER` — nullable FK → `playlist_tracks.id ON DELETE SET NULL`

---

## [0.93.0] - 2026-05-12

**Schema version:** 47

**Commit summary:** Wider sidebar, map upload progress bar, inline grid size editing

**Description:** Three UX improvements. The tabletop sidebar is widened from 430 px to 480 px. Map uploads in campaign settings now show an XHR-based progress bar with a percentage counter instead of a blank wait; the page reloads automatically on completion. The map table now has an editable grid size field per row that saves on blur via a new `POST /campaign/{id}/settings/maps/{id}/grid_size` endpoint, matching the existing inline name and tags editing pattern.

### Added
- Map upload progress bar (XHR + `upload.onprogress`); page auto-reloads on success
- Inline grid size input in the campaign settings map table, saved on blur
- `POST /campaign/{campaign_id}/settings/maps/{map_id}/grid_size` backend route

### Changed
- Sidebar width increased from 430 px to 480 px (tab bar and panels wrapper updated to match)
- Map upload size label updated from 25 MB to 80 MB to match the raised backend limit

---

## [0.92.8] - 2026-05-12

**Schema version:** 47

**Commit summary:** Raise map upload limit from 25 MB to 80 MB

**Description:** The per-file size check on map uploads is raised to 80 MB in both the admin portal route (`admin_routes.py`) and the campaign-settings route (`tabletop_routes.py`). No other limits (audio, portraits, thumbnails) are changed.

### Changed
- Map upload size cap raised from 25 MB to 80 MB in `admin_routes.py` and `tabletop_routes.py`

---

## [0.92.7] - 2026-05-12

**Schema version:** 47

**Commit summary:** Quick-die buttons stack expressions instead of auto-rolling

**Description:** Clicking a quick-die button (d4, d6, d8 …) now appends the die to the current expression field (`1d6` → `1d6+1d8`) rather than replacing it and auto-submitting. The roll only fires when the Roll button is pressed, giving players time to build multi-die expressions by clicking several buttons in sequence.

### Changed
- Quick-die buttons append `+{expr}` to `roll-expr` instead of replacing it and auto-submitting the form

---

## [0.92.6] - 2026-05-12

**Schema version:** 47

**Commit summary:** Merge dice roller and Roll Request into a single combined footer

**Description:** The dice roller form and Roll Request panel are now one unified section at the bottom of the Roll Log drawer. All users share the expression input and quick-dice buttons; clicking a die populates `roll-expr` which the Roll Request also reads when posting. The GM-only Roll Request block sits below, separated by a border and labelled "GM only", and remains collapsible. The separate `rr-expr` input and `rr-expr-die` button row are removed. The visibility selector for the roll request moves to the send row (right-aligned).

### Changed
- Dice roller and Roll Request merged into one footer section
- Roll Request reads `roll-expr` (shared with the roller) instead of its own expression field
- `rr-expr` input and `rr-expr-die` quick-die row removed
- Roll Request visibility selector moved inline with the Post to Log / Clear buttons
- GM-only Roll Request block separated by a border with a "GM only" label in the summary

### Removed
- Separate Roll Request footer `<div>` (merged into the roller footer)
- `rr-expr` input field
- `rr-expr-die` button row

---

## [0.92.5] - 2026-05-12

**Schema version:** 47

**Commit summary:** Roll Request — dice buttons populate expression field

**Description:** The system's quick-dice buttons (d4, d6, d8, etc.) now appear inside the Roll Request panel as a second row. Clicking one fills the dice expression field instead of auto-rolling, giving the GM a fast way to set a custom expression without typing. These buttons use a dedicated `rr-expr-die` class so they don't trigger the main roller's auto-submit behaviour.

### Added
- Quick-dice row inside Roll Request panel; clicking a die button populates `#rr-expr`

---

## [0.92.4] - 2026-05-12

**Schema version:** 47

**Commit summary:** Roll Request — hover tooltips, larger DC input, DC preset buttons

**Description:** Three UX improvements to the Roll Request panel. All interactive elements now carry `title` tooltip text: the Save/Check mode buttons describe what saving throws and ability checks are; each attribute button (STR–CHA) lists the skills and situations it covers. The DC input is rendered larger (14 px bold) so the value is easier to read at a glance. Three DC preset buttons — 10 (Normal), 18 (Challenging), 21 (Extremely Difficult) — sit inline with the DC field and populate it on click.

### Added
- `title` tooltip on the Save mode button explaining saving throws
- `title` tooltip on the Check mode button explaining ability checks
- `title` tooltips on STR/DEX/CON/INT/WIS/CHA attribute buttons listing relevant skills
- DC preset buttons: **10** Normal, **18** Challenging, **21** Extremely Difficult
- `.rr-dc-preset` CSS class for preset button styling

### Changed
- DC input font size increased to 14 px bold for legibility

---

## [0.92.3] - 2026-05-12

**Schema version:** 47

**Commit summary:** Roll Request — toggle between Saving Throw / Ability Check with combined attribute buttons

**Description:** The Roll Request panel previously showed two separate rows of six buttons each (one for saves, one for checks), totalling twelve buttons. Now there is a single row of six attribute buttons (STR / DEX / CON / INT / WIS / CHA) and a two-state toggle above them. The toggle controls whether clicking an attribute fires a saving throw or an ability check request; the label and stat key are derived from the combination at click time. Switching the toggle while an attribute is already selected updates the label and stat key immediately.

### Changed
- Replaced 12 fixed `rr-quick` buttons (6 saves + 6 checks) with a Saving Throw / Ability Check mode toggle and 6 combined attribute buttons
- JS derives `label` and `stat_key` from the selected attribute + current mode at click time
- Switching the mode toggle updates the label/stat of any already-selected attribute button

---

## [0.92.2] - 2026-05-12

**Schema version:** 47

**Commit summary:** Move Roll Request to bottom of Roll Log drawer

**Description:** The GM-only Roll Request panel moves from the GM Tools drawer to the bottom of the Roll Log drawer, where it sits directly beneath the dice roller form. The collapsible `<details>` behaviour is preserved. The panel is gated on `is_gm` so players never see it.

### Changed
- Roll Request `<details>` panel relocated from GM Tools drawer to the fixed footer of the Roll Log drawer
- Removed Roll Request from GM Tools drawer

---

## [0.92.1] - 2026-05-12

**Schema version:** 47

**Commit summary:** Player sidebar layout tweaks — initiative buttons, volume slider, mute placement

**Description:** Three small layout improvements to the Player drawer. GM initiative controls (◀ / Next ▶ / ↺ Start / 🗑) now appear below the combatant list rather than above it, so the list reads top-to-bottom before showing controls. The Vol label and range slider are now on a single line. The 🔈 mute button moves from the Vol row to sit beside the ⟳ Resync button.

### Changed
- GM initiative control buttons rendered after `#initiative-list` instead of before it
- Vol label and volume slider placed on one flex row
- Mute button moved from the Vol row to the Resync/controls row

---

## [0.92.0] - 2026-05-12

**Schema version:** 47

**Commit summary:** Sidebar always visible — remove collapse, pin, and close controls

**Description:** The sidebar is now permanently visible; there is no way to hide or collapse it. The animated slide-in/slide-out drawer system is replaced with a static 430 px column with a tab bar for switching between panels. The open-arrow button, pin button, and all per-panel close buttons are removed. Tab state is persisted to `localStorage` so the last-visited panel is restored on reload. The mobile media query is simplified: on narrow screens the map pane is hidden and the sidebar expands to full width as before, but all dead references to the removed elements are stripped.

### Changed
- Sidebar is now always 430 px wide — no collapse, no slide animation
- Replaced animated drawer controller JS with a minimal tab-switcher (open/pin/close logic removed)
- Tab selection persisted to `localStorage` per campaign; last tab is restored on page load
- Removed `#drawer-open-btn` (open-arrow), `#drawer-pin-btn` (pin button), and all `<button class="drawer-close">` buttons from the HTML
- Simplified `@media (max-width: 640px)` block: removed dead `.is-open`, `#drawer-open-btn`, and `#drawer-pin-btn` references

---

## [0.91.0] - 2026-05-12

**Schema version:** 47

**Commit summary:** Sidebar reorganisation — initiative and sound to Player, token management to GM Tools, HP thresholds

**Description:** Major sidebar restructure. The initiative tracker (with GM controls) and a compact sound panel move to the top of the Player drawer so all users see turn order in one place. Token Management moves from the Battle drawer to GM Tools. The Settings drawer is removed — its only content (sound) is now in Player. The Battle drawer becomes a GM-only tab for adding combatants. Players no longer see raw HP or initiative numbers in the tracker; instead they see a named threshold label (Healthy / Wounded / Bloodied / Critical / Dead by default) coloured by health level. GMs can rename the five threshold labels in Campaign Settings → Basic info. A new `hp_thresholds` JSON column on the `campaigns` table stores per-campaign threshold labels.

### Added
- HP threshold system: players see a named label (e.g. "Bloodied") instead of raw HP in the initiative tracker
- `hp_thresholds` JSON column on `campaigns` table (schema v47); defaults to five built-in labels
- GM threshold editor in Campaign Settings → Basic info: rename any of the five labels, boundaries fixed at ≥76 / ≥51 / ≥26 / ≥1 / 0 %
- `hpThreshold()` JS helper driven by the server-supplied `HP_THRESHOLDS` constant

### Changed
- Initiative tracker moved from Battle drawer to top of Player drawer (visible to all users)
- Sound controls moved from Settings drawer to Player drawer as a compact collapsible card
- Token Management moved from Battle drawer to GM Tools drawer
- Settings drawer removed (was sound-only; sound now lives in Player)
- Battle drawer is now GM-only (tab button gated on `is_gm`); contains only add-combatant controls
- Player view of initiative list no longer shows initiative number or raw HP — shows turn order + threshold label only
- GM view unchanged: editable initiative, HP cur/max, remove button

### Schema
- `campaigns.hp_thresholds JSON` — nullable; null means use application defaults

---

## [0.90.7] - 2026-05-12

**Schema version:** 46

**Commit summary:** Expose WebM/MP4 animated maps in file pickers

**Description:** The backend already accepted `video/webm` and `video/mp4` for map uploads and rendered them as looping `<video>` elements on the tabletop. The file picker `accept` attribute on both the admin and campaign-settings map upload forms was still restricted to `image/*`, which hid video files in the OS file dialog. Updated both inputs to `accept="image/*,video/mp4,video/webm"` and updated the label copy to reflect the supported formats.

### Fixed
- Map upload file picker in admin (`admin_campaign.html`) now accepts `.mp4` and `.webm` in addition to images
- Map upload file picker in campaign settings (`campaign_settings.html`) now accepts `.mp4` and `.webm` in addition to images

---

## [0.90.6] - 2026-05-12

**Schema version:** 46

**Commit summary:** Make Roll Request, Music, and Characters collapsible cards in the sidebar

**Description:** Four sidebar sections are now wrapped in collapsible `<details>` cards matching the existing pattern used by Encounters and Token Management. Roll Request and Music (both in the GM Tools drawer) and Characters (Player drawer) gain a chevron summary header and can be collapsed to save vertical space. Collapsed state is controlled natively by the browser `<details>` element; all sections default to open.

### Changed
- Wrapped Roll Request section in `<details id="roll-request-panel">` with chevron summary (GM Tools drawer)
- Wrapped Music section in `<details id="music-panel">` with chevron summary (GM Tools drawer)
- Wrapped character list in `<details id="player-chars-panel">` with "Characters" chevron summary (Player drawer)
- Added CSS chevron-flip rules for `#roll-request-panel`, `#music-panel`, and `#player-chars-panel`

---

## [0.90.5] - 2026-05-12

**Schema version:** 46

**Commit summary:** Fix map not rendering and encounters folders not loading after panel reorganisation

**Description:** Two regressions introduced when the encounters panel was moved and the animated map background layer was added. The canvas `background:#222` CSS was blocking the bg-layer from showing through transparent canvas pixels; removing it restores map rendering. The encounters controller `<script>` block is located above the encounters HTML in the DOM; wrapping the IIFE in `DOMContentLoaded` ensures `document.getElementById('encounters-list')` resolves successfully before the controller initialises.

### Fixed
- Removed `background:#222` from the tabletop canvas inline style so the animated/static bg-layer element behind it is visible through transparent canvas pixels
- Wrapped the encounters controller IIFE in `document.addEventListener('DOMContentLoaded', …)` so the script no longer exits early when the encounters panel HTML hasn't been parsed yet

---

## [0.90.4] - 2026-05-12

**Schema version:** 46

**Commit summary:** Move Encounters panel from Battle drawer to GM Tools drawer

**Description:** The Encounters panel (save, load, search, tag filter) now lives at the top of the ⚙ GM Tools drawer instead of inside the ⚔ Battle drawer. The Battle drawer remains visible to all players and now only contains initiative tracking and token management. The encounters controller script and all element IDs are unchanged so no backend or data changes are required.

### Changed
- Moved `#encounters-panel` HTML from the Battle drawer to the top of the GM Tools drawer
- Removed the "GM only" badge from the encounters summary since the entire GM Tools drawer is already GM-gated
- Replaced the top `border-top` separator with a `border-bottom` to suit the new position at the top of the drawer

---

## [0.90.3] - 2026-05-12

**Schema version:** 46

**Commit summary:** Clamp tabletop pan so at least one grid square stays visible

**Description:** Panning the map can no longer push it entirely off-screen. A `clampPan()` guard runs inside `applyTransform()` — the single call-site for all pan/zoom changes — and enforces that at least one grid square's worth of map remains inside the viewport at all times. The constraint applies to mouse drag, scroll-wheel zoom, pinch-to-zoom, touch pan, and restored GM view positions.

### Changed
- Added `clampPan()` to `applyTransform()` in `tabletop.js`; enforces a minimum one-grid-square overlap between the map canvas and the visible pane on every transform update

---

## [0.90.2] - 2026-05-12

**Schema version:** 46

**Commit summary:** Add From Map button to populate initiative tracker from active map tokens

**Description:** A new "🗺 From Map" button in the Battle drawer adds every token currently on the active map to the initiative list in one click. Character tokens resolve DEX modifier, initiative bonus, and current HP from their linked character sheet; NPC tokens pull the same stats from their token template sheet. Tokens already in the tracker are skipped so clicking the button a second time is safe. "Roll All" continues to work as before.

### Added
- "🗺 From Map" button in the GM battle controls that bulk-adds all tokens on the active map as combatants, deduplicating against entries already in the list
- `combatantFromToken()` helper that resolves DEX mod and HP from a linked character sheet or token template sheet
- `_hpFromSheet()` helper that handles both numeric and object HP fields across character and NPC sheets

---

## [0.90.1] - 2026-05-12

**Schema version:** 46

**Commit summary:** Upload audio tracks one at a time with per-file progress bar

**Description:** The audio upload form now sends each selected file as a separate XHR request and displays a progress bar while each one transfers. The label updates to show "Uploading X of Y: filename" as the queue advances, and the page reloads automatically once all files finish. Any file that fails shows an inline error without aborting the remaining queue.

### Changed
- Replaced native form submission for audio uploads with a sequential XHR loop that uploads one file per request
- Progress bar and status label appear below the upload zone during transfer; page reloads ~700 ms after the last file completes
- Submit button now reads "Upload N files" when multiple files are selected

---

## [0.90.0] - 2026-05-12

**Schema version:** 46

**Commit summary:** Add animated map support for GIF and WebM/MP4 video backgrounds

**Description:** Map backgrounds are now rendered as native HTML elements instead of being drawn onto the canvas, allowing animated GIFs to play and WebM/MP4 video files to loop continuously. The canvas remains on top and draws only the grid and tokens, which are composited transparently over the background layer. Both new formats can be uploaded through the GM campaign settings and the admin portal. No operator action required.

### Added
- Accept `video/webm` and `video/mp4` MIME types for map image uploads in both the admin and GM settings upload routes
- Render animated map backgrounds via a `<img>` (for images and GIFs) or `<video autoplay loop muted>` (for WebM/MP4) element placed behind the canvas; the element receives the same pan/zoom transform as the canvas

### Changed
- Map background is no longer drawn via `ctx.drawImage()` on the canvas; the canvas is now transparent so the HTML background layer shows through beneath the grid and tokens
- `gif-token-overlay` given explicit `z-index:2` to maintain correct stacking order above the new background layer

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

## [0.89.0] - 2026-05-12

**Schema version:** 46

**Commit summary:** Show content source on race and subclass headers and in the picker dropdowns

**Description:** The character sheet now visibly distinguishes content sources for races, subclasses, and the multi-class subclass blocks. A small coloured pill appears next to the rendered name — green "SRD" for shipped FS files, orange "Custom" for campaign-authored homebrew, and blue "Open5e" for content fetched from the mirror or live API. Class, subclass, and race picker dropdowns also suffix each option with its source (e.g. "Hill Dwarf · SRD", "My Race · Custom", "Some Race · 5e Core Rules") so users can pick the version they want when multiple sources expose the same name. No backend or schema changes.

### Added
- ``_sourceBadgeSpec`` / ``_appendSourceBadge`` helpers in ``app/static/sheet.js`` covering ``local-custom``, ``local-srd``, ``open5e_mirror``, and ``open5e_live``. Each badge carries a tooltip explaining what the source means and where to go to manage it.
- Source suffixes in ``populateSelect`` so class / subclass / race dropdowns show the origin of each entry inline. Empty/missing source renders as the bare name.

### Changed
- ``renderSubclassFeatures``, ``renderRaceTraits``, and the per-class-block ``_renderSubclassBlock`` headers now call the shared badge helper. Previously only ``local-custom`` content was visually marked; SRD and Open5e content now also display their source.

---

## [0.88.0] - 2026-05-12

**Schema version:** 46

**Commit summary:** Ship Paladin, Ranger, Bard, and Monk SRD classes — finishing the local SRD class baseline

**Description:** Phase 3 of the class-content rollout — the four remaining SRD classes (half-casters and hybrids) are now served from on-disk JSON. Combined with the existing Druid and the Phase 1/2 classes, every SRD 5.1 class now ships locally alongside its SRD-listed subclass. Subclass slugs match Open5e (``oath-of-devotion``, ``hunter``, ``college-of-lore``, ``way-of-the-open-hand``) so detail lookups by Open5e listing slug resolve locally. The full SRD baseline (12 classes × the SRD-listed subclass for each, plus Druid's two) is now in.
### Added
- ``app/data/local/dnd5e/class_features/paladin.json`` — d10, Cha half-caster, Divine Sense / Lay on Hands pools, 4 Fighting Styles, Divine Smite slot scaling, Aura of Protection / Courage with 10ft→30ft range bump, Improved Divine Smite, Cleansing Touch.
- ``app/data/local/dnd5e/class_features/ranger.json`` — d10, Wis half-caster (known list), Favored Enemy and Natural Explorer with full SRD lists, 4 Fighting Styles, Primeval Awareness, Land's Stride, Hide in Plain Sight, Vanish, Feral Senses, Foe Slayer.
- ``app/data/local/dnd5e/class_features/bard.json`` — d8, Cha full caster with ritual casting, Bardic Inspiration with die scaling and Font of Inspiration short-rest recharge at L5, Jack of All Trades, Song of Rest, Expertise (L3 + L10), Countercharm, Magical Secrets at L10/14/18, Superior Inspiration.
- ``app/data/local/dnd5e/class_features/monk.json`` — d8, no spellcasting, Unarmored Defense (Dex + Wis), Martial Arts with die scaling, Ki with full point pool / DC formula, Flurry of Blows / Patient Defense / Step of the Wind, Unarmored Movement speed bumps, Deflect Missiles, Slow Fall, Stunning Strike, Ki-Empowered Strikes, Evasion, Stillness of Mind, Purity of Body, Tongue of the Sun and Moon, Diamond Soul, Timeless Body, Empty Body, Perfect Self.
- ``app/data/local/dnd5e/subclass_features/paladin__oath-of-devotion.json`` — Oath Spells table, Channel Divinity: Sacred Weapon, Channel Divinity: Turn the Unholy, Aura of Devotion, Purity of Spirit, Holy Nimbus.
- ``app/data/local/dnd5e/subclass_features/ranger__hunter.json`` — Hunter's Prey / Defensive Tactics / Multiattack / Superior Hunter's Defense, each with the SRD's three-option pick.
- ``app/data/local/dnd5e/subclass_features/bard__college-of-lore.json`` — Bonus Proficiencies, Cutting Words, Additional Magical Secrets, Peerless Skill.
- ``app/data/local/dnd5e/subclass_features/monk__way-of-the-open-hand.json`` — Open Hand Technique, Wholeness of Body, Tranquility, Quivering Palm.

---

## [0.87.0] - 2026-05-12

**Schema version:** 46

**Commit summary:** Ship Wizard, Cleric, Sorcerer, and Warlock SRD classes with their SRD subclasses

**Description:** Phase 2 of the class-content rollout — the four SRD core spellcaster classes are now served from on-disk JSON, alongside Druid plus the Phase 1 martials. Each class file sets the correct ``spellcasting_ability`` field (int / wis / cha / cha), embeds the relevant spellcasting mechanics in the features blob (cantrips known, prepared vs known casters, ritual rules, pact-magic slot scaling for Warlock), and ships its SRD subclass as a structured features list. Slugs match Open5e so subclass detail lookups by Open5e listing slug resolve locally (``school-of-evocation``, ``life-domain``, ``draconic-bloodline``, ``the-fiend``).

### Added
- ``app/data/local/dnd5e/class_features/wizard.json`` — d6, Int caster, prepared list, Spellcasting, Arcane Recovery, Arcane Tradition, Spell Mastery, Signature Spells.
- ``app/data/local/dnd5e/class_features/cleric.json`` — d8, Wis caster, prepared list, Spellcasting, Divine Domain (chosen at L1), Channel Divinity / Turn Undead with scaling uses, Destroy Undead CR thresholds, Divine Intervention.
- ``app/data/local/dnd5e/class_features/sorcerer.json`` — d6, Cha caster, known list, Spellcasting, Sorcerous Origin, Font of Magic with sorcery-point / slot exchange table, eight Metamagic options described in-line, Sorcerous Restoration.
- ``app/data/local/dnd5e/class_features/warlock.json`` — d8, Cha caster, Pact Magic with full slot-count / slot-level scaling, Eldritch Invocations, three Pact Boon choices (Chain / Blade / Tome), Mystic Arcanum, Eldritch Master.
- ``app/data/local/dnd5e/subclass_features/wizard__school-of-evocation.json`` — Evocation Savant, Sculpt Spells, Potent Cantrip, Empowered Evocation, Overchannel.
- ``app/data/local/dnd5e/subclass_features/cleric__life-domain.json`` — Domain Spells table, Bonus Proficiency (heavy armor), Disciple of Life, Channel Divinity: Preserve Life, Blessed Healer, Divine Strike, Supreme Healing.
- ``app/data/local/dnd5e/subclass_features/sorcerer__draconic-bloodline.json`` — Dragon Ancestor color table, Draconic Resilience, Elemental Affinity, Dragon Wings, Draconic Presence.
- ``app/data/local/dnd5e/subclass_features/warlock__the-fiend.json`` — Expanded Spell List, Dark One's Blessing, Dark One's Own Luck, Fiendish Resilience, Hurl Through Hell.

---

## [0.86.0] - 2026-05-12

**Schema version:** 46

**Commit summary:** Ship Fighter, Barbarian, and Rogue SRD classes locally with Champion, Berserker, and Thief subclasses

**Description:** Phase 1 of the class-content rollout — the three SRD martial classes (no spellcasting) and their SRD-listed subclasses are now served from on-disk JSON, alongside the existing Druid. Each class file carries full proficiencies, equipment choices, multiclass prerequisites, and a markdown blob of leveled features from 1st through 20th level. Each subclass file ships its features as the structured ``[{name, level, desc}]`` list the renderer prefers. Slugs match Open5e (``champion``, ``path-of-the-berserker``, ``thief``) so detail lookups by Open5e listing slug resolve locally.

### Added
- ``app/data/local/dnd5e/class_features/fighter.json`` — d10 hit die, all armor + shields, Str/Con saves, 6 fighting styles described in-line, Second Wind, Action Surge, Extra Attack scaling, Indomitable.
- ``app/data/local/dnd5e/class_features/barbarian.json`` — d12 hit die, light/medium/shields, Str/Con saves, Rage with full damage / uses scaling table, Unarmored Defense, Reckless Attack, Danger Sense, Brutal Critical scaling, Relentless / Persistent Rage, Indomitable Might, Primal Champion.
- ``app/data/local/dnd5e/class_features/rogue.json`` — d8 hit die, light armor + thieves' tools, Dex/Int saves, Expertise, Sneak Attack with full 1d6→10d6 scaling, Thieves' Cant, Cunning Action, Uncanny Dodge, Evasion, Reliable Talent, Blindsense, Slippery Mind, Elusive, Stroke of Luck.
- ``app/data/local/dnd5e/subclass_features/fighter__champion.json`` — Improved Critical, Remarkable Athlete, Additional Fighting Style, Superior Critical, Survivor.
- ``app/data/local/dnd5e/subclass_features/barbarian__path-of-the-berserker.json`` — Frenzy, Mindless Rage, Intimidating Presence, Retaliation.
- ``app/data/local/dnd5e/subclass_features/rogue__thief.json`` — Fast Hands, Second-Story Work, Supreme Sneak, Use Magic Device, Thief's Reflexes.

---

## [0.85.0] - 2026-05-12

**Schema version:** 46

**Commit summary:** Merge shipped FS classes into the classes search endpoint and admin stubs

**Description:** Mirrors the 0.83.0 races change for classes. ``/api/open5e/classes`` now lists shipped FS classes between campaign homebrew and Open5e results, with dedupe-by-slug, so the picker surfaces the SRD baseline even when Open5e is unreachable. ``list_local_classes()`` now returns dicts (slug + name + hit die + file) to match the equivalent races helper, and the admin "Local-features stubs" Classes section renders as a table for parity with the Races and Subclasses sections. No schema change. The ``/admin/stubs.json`` shape changes for the ``local_classes`` field — admin-only and used for scripting; any consumer iterating string slugs needs to read ``entry["slug"]`` instead.

### Added
- Shipped FS classes are merged into ``/api/open5e/classes`` search results (between campaign homebrew and Open5e), with dedupe-by-slug. When Open5e is unreachable the picker now still lists the SRD baseline.

### Changed
- ``local_features.list_local_classes()`` now returns ``[{slug, name, hit_die, file}]`` instead of a bare ``list[str]``. The admin stubs Classes section renders as a table consistent with the Races and Subclasses sections.

---

## [0.84.0] - 2026-05-12

**Schema version:** 46

**Commit summary:** Extend the system column to every Custom* table for symmetric multi-system support

**Description:** Follow-on to 0.83.0 — the ``system`` column introduced on ``CustomRace`` is now also present on ``CustomClass``, ``CustomSubclass``, ``CustomBackground``, ``CustomFeat``, and ``CustomMonster``. All six tables default to ``dnd5e`` for existing rows, so this remains purely additive and requires no operator action. With every campaign-authored content type now system-aware, the day a second system arrives there's no asymmetric backfill to chase.

### Schema
- Added ``system VARCHAR(40) NOT NULL DEFAULT 'dnd5e'`` to ``custom_classes``, ``custom_subclasses``, ``custom_backgrounds``, ``custom_feats``, and ``custom_monsters``. Resolver and search endpoints don't filter on it yet; the column ships ahead of need.
- ``SCHEMA_VERSION`` bumped from 45 to 46.

---

## [0.83.0] - 2026-05-12

**Schema version:** 45

**Commit summary:** Ship nine SRD races locally and namespace shipped content by game system

**Description:** The nine D&D 5e SRD races (Hill Dwarf, High Elf, Lightfoot Halfling, Human, Dragonborn, Rock Gnome, Half-Elf, Half-Orc, Tiefling) are now served from on-disk JSON, so race pickers and race-detail lookups work offline against the SRD baseline. Shipped filesystem content has been moved under a game-system root — `app/data/local/dnd5e/` — so a future second system can ship alongside without renames. ``CustomRace`` gains a ``system`` column (default ``dnd5e``) to mirror the same partitioning for campaign-authored homebrew. No operator action required; the column is added automatically on next boot.

### Added
- Nine race JSON files under ``app/data/local/dnd5e/races/`` covering the SRD 5.1 baseline. Each flattens base race + SRD subrace traits into one playable record (e.g. ``hill-dwarf.json`` contains both shared Dwarf traits and the Hill Dwarf subrace bonuses), mirroring how Open5e returns subrace-slug lookups.
- ``local_features._fs_race_provider`` now actually reads files (was a no-op stub). Speed is normalised from int to ``{"walk": int}`` so the race-detail adapter handles FS and DB records uniformly.
- ``local_features.list_local_races()`` discovery helper used by ``/admin/stubs``.
- Shipped FS races are merged into ``/api/open5e/races`` search results (positioned between campaign homebrew and Open5e), with dedupe-by-slug. When Open5e is unreachable the picker now still lists the SRD baseline.
- Admin "Local-features stubs" page gains a Races table alongside the existing Classes and Subclasses tables; ``/admin/stubs.json`` exposes the same list.

### Changed
- ``app/data/local/{class_features,subclass_features}/`` moved to ``app/data/local/dnd5e/{class_features,subclass_features}/``. The existing Druid class + Circle of the Land / Circle of the Moon subclass files relocate accordingly. ``_CLASS_DIR``, ``_SUBCLASS_DIR``, and the new ``_RACE_DIR`` constants in ``app/local_features.py`` now resolve under the ``dnd5e`` subtree.

### Schema
- ``custom_races.system VARCHAR(40) NOT NULL DEFAULT 'dnd5e'`` — reserved for future multi-system support. The resolver and search endpoints do not filter on it yet; the column ships ahead of need so the day a second system arrives there's no backfill required.
- ``SCHEMA_VERSION`` bumped from 44 to 45.

---

## [0.82.0] - 2026-05-12

**Schema version:** 44

**Commit summary:** Pin the currently-running encounter in the Battle drawer and tidy the encounters panel layout

**Description:** The Battle drawer's Encounters panel now keeps the currently-loaded encounter visible at all times. Loading an encounter records it on the campaign; the panel summary surfaces its name as a chip even when the panel is collapsed, and the matching row in the list gets a cyan-tinted highlight when expanded. Two layout fixes ride along: the Sort label/select now renders inline (the global ``label`` rule had been forcing the select onto a new line) on both the tabletop Battle drawer and the campaign-settings library, and folder summaries gain a rotating ▶ chevron so it's obvious they expand on click.

### Added
- ``Campaign.current_encounter_id`` (nullable FK → encounters, ON DELETE SET NULL). Set by ``_perform_encounter_load`` whenever an encounter is loaded (via the explicit Load endpoint or the session-start auto-load hook). Cleared automatically if the encounter is deleted.
- ``is_current`` flag on every row returned by ``GET /api/campaign/{id}/encounters`` (true for the one matching ``campaign.current_encounter_id``).
- New ``#enc-current-chip`` element in the tabletop Encounters panel summary — shows ``▶ <encounter name>`` while a current encounter exists. Hidden when none is set.

### Changed
- Tabletop Encounters panel: rows for the current encounter render with a cyan border + background tint to distinguish them from the rest of the library.
- Tabletop + campaign-settings Encounter "Sort" label: inline-flex now forces ``flex-direction: row`` so the global ``label { flex-direction: column }`` rule from ``style.css`` can't push the select onto its own line.
- Tabletop + campaign-settings encounter folder summaries: native marker suppressed (``list-style: none``) and replaced with a ``▶`` chevron span that rotates 90° on open, matching the existing panel chevron affordance.
- ``app/version.py``, ``README.md``, ``CHANGELOG.md`` — MINOR bump to 0.82.0. ``SCHEMA_VERSION`` bumped from 43 to 44.

### Schema
- New ``campaigns.current_encounter_id`` column (INTEGER NULL, FK → encounters(id) ON DELETE SET NULL). Inline migration in ``_apply_inline_migrations()``; existing campaigns get NULL until their next encounter load.
- ``SCHEMA_VERSION`` bumped from 43 to 44.

## [0.81.0] - 2026-05-12

**Schema version:** 43

**Commit summary:** Add per-user tabletop zoom-speed slider and damp the default iPad pinch sensitivity

**Description:** Pinch zoom on iPad was twitchy because the raw `newDist/startDist` ratio is way too sensitive on a small touchscreen. v0.81 introduces a `User.zoom_speed` multiplier (default 1.0, range 0.3–1.5) applied to both wheel and pinch, plus a baked-in 0.6 baseline dampener on pinch. At default settings: wheel feels the same as before, pinch is roughly 60% as sensitive as v0.79.0. A slider on the user-settings page lets each user tune the multiplier for their devices; the value is saved on the account so it carries across browsers.

### Added
- `User.zoom_speed` (FLOAT NOT NULL DEFAULT 1.0). Schema v43 inline migration adds the column with the safe default so every existing user keeps their pre-v0.81 wheel feel.
- `POST /api/settings/zoom_speed` (auth-required). Body: `{zoom_speed: float}`. Server clamps to `[0.3, 1.5]` with `_coerce_zoom_speed`. NaN / non-numeric → 1.0.
- **User settings → 🔭 Tabletop zoom speed** section with a 0.3–1.5 slider (step 0.1). Live label updates while dragging; the save fires on `change` so the endpoint isn't hammered on every tick.
- `ME.zoomSpeed` global in `tabletop.html` (baked from `user.zoom_speed`).
- `_zoomSpeed()` defensive helper in `tabletop.js` — reads `ME.zoomSpeed`, defaults to 1.0, clamps to `[0.3, 1.5]`.

### Changed
- Wheel zoom in `tabletop.js`: per-notch factor is now `Math.pow(1.12, _zoomSpeed())` instead of a fixed 1.12. At 1.0 this is identical to the pre-v0.81 behavior.
- Pinch zoom in `tabletop.js`: the raw distance ratio is raised to the power of `0.6 * _zoomSpeed()` before being applied to the scale. The 0.6 baseline brings the default pinch from "way too fast" to "natural"; the user multiplier on top tunes from 0.18× to 0.9× of the raw ratio's sensitivity. Anchor-the-center math stays the same.
- `app/version.py`, `README.md`, `CHANGELOG.md` — MINOR bump to 0.81.0. `SCHEMA_VERSION` bumped from 42 to 43.

### Schema
- New `users.zoom_speed` column (FLOAT NOT NULL DEFAULT 1.0).
- `SCHEMA_VERSION` bumped from 42 to 43.

## [0.80.0] - 2026-05-12

**Schema version:** 42

**Commit summary:** Persist the GM canvas pan and zoom across page refreshes per campaign and map

**Description:** The tabletop canvas now remembers the GM's pan + zoom across page refreshes. Keyed per `(campaign, map)`, so each map keeps its own view — flipping between maps doesn't smear the same offset across them. State lives in `localStorage`; saves are debounced 250 ms so panning or pinching doesn't hammer the storage on every frame. Players are deliberately excluded: the v0.77.0 auto-center on first controlled token still fires on session start, and layering a persisted view on top would create a confusing jump.

### Added
- `app/static/tabletop.js` — view-persistence block under the pan / zoom variable declarations:
  - `VIEW_KEY` — `simplevtt_gm_view_${CAMPAIGN_ID}_${MAP_ID}` when the user is the GM and a map is active, else `null` (everything is a no-op when null).
  - `scheduleSaveView()` — debounced (250 ms) writer that stores `{panX, panY, scale}`. Failures (quota, disabled storage) are swallowed silently.
  - `applyTransform()` now calls `scheduleSaveView()` so every interaction path (wheel zoom, mouse pan / drag, touch pan / pinch / drag) writes the new state without each callsite needing to know.
  - Restore block runs synchronously at init: reads `VIEW_KEY`, validates the three numbers, clamps `scale` to `[MIN_SCALE, MAX_SCALE]`, applies. Corrupt JSON is ignored and overwritten on the next interaction.

### Changed
- `app/version.py`, `README.md`, `CHANGELOG.md` — MINOR bump to 0.80.0. No schema change.

## [0.79.0] - 2026-05-12

**Schema version:** 42

**Commit summary:** Add touch controls to the tabletop canvas for pan zoom drag tap and double-tap on iPad

**Description:** Tabletop canvas gains a touch-event layer alongside the existing mouse handlers so iPad / tablet users get full interaction. One-finger drag pans the map (or drags a movable token when started on one); two-finger pinch zooms around the gesture's center, with pan auto-adjusted so the world coord under the midpoint stays put; a quick tap fires the spawn-arm click-to-set when armed; two taps in quick succession behave like a dblclick and open the character sheet on the tapped token. CSS sets `touch-action: none` on the map pane so the browser's default scroll / zoom doesn't pre-empt these gestures.

### Added
- `app/static/tabletop.js` — new touch-event block under the existing mouse handlers. Tracks four states: `touchPan`, `touchPinch`, `touchDrag`, and a `tapStart` snapshot used for tap / double-tap detection. State machine:
  - **One-finger touchstart**: arm spawn-set if armed (records the spawn immediately); otherwise hit-test for movable token (drag) → fall back to pan.
  - **Two-finger touchstart**: cancel any single-finger state, snapshot scale / pan / midpoint, enter pinch.
  - **touchmove**: pinch (clamped to `[MIN_SCALE, MAX_SCALE]`, midpoint anchored), drag (writes to the local token), or pan (updates `panX` / `panY` deltas).
  - **touchend / touchcancel**: finalize drag (snap-to-grid + `POST /token/{id}/move`), or transition from pinch back to pan when one finger lifts. Final tap with <12 px movement + <350 ms duration registers as a tap; two taps within 400 ms + 30 px → dblclick.
- `app/templates/tabletop.html` — `.map-pane { touch-action: none; }` on the existing CSS rule so the browser stops intercepting the gestures.

### Changed
- `app/version.py`, `README.md`, `CHANGELOG.md` — MINOR bump to 0.79.0. No schema change.

## [0.78.5] - 2026-05-12

**Schema version:** 42

**Commit summary:** Add field labels to the Battle drawer encounter edit form and split Map from the Playlist row

**Description:** Light layout pass on the Battle drawer's per-row encounter Edit form. Each input now sits under a small uppercase label (Name / Notes / Tags / Folder / Map / Playlist / Mode) instead of relying on placeholder text alone — the form reads as a labeled stack instead of a rowful of identical-looking inputs. Map dropdown gets its own row; Playlist + Mode share a row below it. Stop-audio-on-load and the spawn-points sub-panel stay where they were.

### Changed
- `app/templates/tabletop.html` — added a `labeledField(labelText, inputEl)` helper in the encounter row's `buildRow` and wrapped Name / Notes / Tags / Folder / Map / Playlist+Mode in it. The previous `mapPlaylistRow` (3-col map | playlist | mode) was split: Map sits on its own labeled row, Playlist + Mode share a `playlistRow` 2-col grid under their shared label. Placeholders shortened since the label carries the field name now.
- `app/version.py`, `README.md`, `CHANGELOG.md` — PATCH bump to 0.78.5. No schema change.

## [0.78.4] - 2026-05-12

**Schema version:** 42

**Commit summary:** Stop inferring a playlist from the now-playing track on save and make spawn Set use the existing token position

**Description:** Two bug fixes for the encounter editor. (1) Saving an encounter without an explicit playlist no longer silently inherits whatever's currently playing — picking "— no playlist —" is now respected and the encounter saves with `auto_play_playlist_id=null`. The JS save handlers always send the field (null when empty) so the server doesn't fall back to the "infer from `campaign.now_playing_track_id`" branch. (2) Clicking **Set** on a character row in the spawn-points editor now copies that character's current token position when one exists on the active map, instead of always arming click-to-set. The click-to-set arming still kicks in when the character has no token yet.

### Changed
- `app/templates/tabletop.html`:
  - Battle drawer encounter Save form now sends `auto_play_playlist_id` even when the dropdown is empty (`null`). The server's "no field" branch only fires for legacy callers that omit the key, not for the GM explicitly picking "no playlist".
  - Spawn editor **Set** button: if the character has a token on the active map AND the encounter's bound map matches the active map, the button POSTs the token's current `(x, y)` directly to `/encounters/{eid}/spawn`. If no token exists, it falls back to the arming + click-to-set flow. The button's title attribute reflects the mode it will use.
- `app/templates/campaign_settings.html` — same playlist-field fix in the New encounter form: always sends `auto_play_playlist_id` (null for empty).
- `app/static/tabletop.js` — new `window.vttFindTokenForCharacter(charId)` helper returns the active-map token tied to a character (or null).
- `app/version.py`, `README.md`, `CHANGELOG.md` — PATCH bump to 0.78.4. No schema change.

## [0.78.3] - 2026-05-12

**Schema version:** 42

**Commit summary:** Tighten encounter library layout: inline shuffle mode with playlist picker, collapse folders by default, glue Sort label to its dropdown

**Description:** Three small layout tweaks to the encounter library on both surfaces. The shuffle-mode dropdown now sits inline with the map + playlist pickers (3-column grid) instead of taking its own row below them. Encounter folders default to collapsed on first paint instead of open, matching how the playlist `<details>` blocks already render. The Sort label hugs its dropdown via `inline-flex + white-space:nowrap` so the word and the control can't separate when the surrounding row wraps.

### Changed
- `app/templates/tabletop.html`:
  - Battle drawer encounter **Save form**: map / playlist / mode pickers now share one 3-column grid (`grid-template-columns:1fr 1fr auto`) instead of a 2-col grid plus a separate Mode row.
  - Battle drawer encounter **per-row Edit form**: same 3-column row built dynamically in JS (`mapPlaylistRow`); the old `modeRow` + `Mode` label disappear. Stop-audio-on-load checkbox moves to its own line right below.
  - Sort label uses `display:inline-flex;align-items:center;gap:4px;white-space:nowrap` so the word "Sort" and the dropdown never separate.
  - Folder `<details>` blocks default closed: `isOpen` derived from `!!folderOpen[folder]` (sticky once the GM toggles).
- `app/templates/campaign_settings.html`:
  - Sort label gets the same `inline-flex + nowrap` treatment.
  - Settings library folder `<details>` blocks default closed too.
- `app/version.py`, `README.md`, `CHANGELOG.md` — PATCH bump to 0.78.3. No schema change.

## [0.78.2] - 2026-05-12

**Schema version:** 42

**Commit summary:** Collapse the Save current state form in the Battle drawer Encounters panel by default

**Description:** The "💾 Save current state" form inside the Battle drawer's Encounters panel used to always render expanded, pushing the encounter list down. It's now a collapsible `<details>` — closed on first paint, click the summary line to expand and save. Saves the dominant vertical space for the actual library list.

### Changed
- `app/templates/tabletop.html` — converted `#encounters-save-form` from a `<div>` to a `<details>` element with the "💾 Save current state" header as the `<summary>`. All existing inputs + handlers continue to work unchanged.
- `app/version.py`, `README.md`, `CHANGELOG.md` — PATCH bump to 0.78.2. No schema change.

## [0.78.1] - 2026-05-12

**Schema version:** 42

**Commit summary:** Keep tabletop GM Music playlists collapsed by default instead of auto-opening the one with the playing track

**Description:** The tabletop's GM Music panel used to auto-expand whichever playlist contained the currently-playing track. With growing libraries that pushed the rest of the panel down on every page load and re-collapsed when the GM switched playlists. All GM Music playlists now render collapsed by default; the GM clicks the chevron on the one they want, matching the v0.74.1 behavior for the campaign settings playlist cards.

### Changed
- `app/templates/tabletop.html` — removed the `{% if now_playing and now_playing.id in playlist.tracks ... %} open{% endif %}` class modifier on the `.gm-playlist` wrapper. Every playlist row renders collapsed on first paint.
- `app/version.py`, `README.md`, `CHANGELOG.md` — PATCH bump to 0.78.1. No schema change.

## [0.78.0] - 2026-05-12

**Schema version:** 42

**Commit summary:** Add a stop-audio-on-load toggle to encounters so the GM picks continue vs stop when no playlist is bound

**Description:** Fixes the audio handling on encounter load. Previously, loading an encounter with no playlist bound just left the currently-playing music alone — there was no way to ask for a clean silent transition. Each encounter now carries a `stop_audio_on_load` boolean. On load, the audio decision is three-way: when a playlist IS bound it plays (unchanged); when no playlist is bound and the toggle is on, audio stops; when no playlist is bound and the toggle is off (default), audio continues — same behavior as before for every existing encounter.

### Added
- `Encounter.stop_audio_on_load` (BOOLEAN NOT NULL DEFAULT FALSE). Schema v42 inline migration adds the column with a safe default so existing encounters keep their pre-v0.78 behavior.
- `_encounter_to_dict` returns the new field.
- `create_encounter` + `PATCH /encounters/{eid}` accept `stop_audio_on_load`.
- **"Stop audio on load (when no playlist is selected)" checkbox** in all four encounter forms: Battle drawer Save form, Battle drawer per-row Edit form, campaign-settings + New form, and campaign-settings per-card Edit form. Each input has a tooltip explaining that the playlist takes precedence when one IS bound.

### Changed
- `_perform_encounter_load` audio branch now does three-way dispatch instead of "playlist or nothing":
  1. **Playlist set** → start that playlist (existing behavior, unchanged).
  2. **No playlist + `stop_audio_on_load=True`** → call `_stop_audio_for_campaign(reason="skipped")` to clear `now_playing_*` and broadcast `audio_stop`. Skipped when nothing is playing.
  3. **No playlist + `stop_audio_on_load=False`** (default) → no-op; current audio continues.
- `app/version.py`, `README.md`, `CHANGELOG.md` — MINOR bump to 0.78.0. `SCHEMA_VERSION` bumped from 41 to 42.

### Schema
- New `encounters.stop_audio_on_load` column (BOOLEAN NOT NULL DEFAULT FALSE).
- `SCHEMA_VERSION` bumped from 41 to 42.

## [0.77.0] - 2026-05-12

**Schema version:** 41

**Commit summary:** Auto-center the player canvas on their first controlled token at session start and on encounter load

**Description:** Players' canvas viewport now pans to their first controlled token automatically — on initial session load (after the GM hits Start session and the waiting page redirects them to the tabletop) and after every encounter load (a `token_add` arriving for their character recenters the view). GMs are unaffected: they control many tokens and the auto-pan would yank their view around mid-prep, so the helper short-circuits on `ME.isGm`. No schema change.

### Added
- `centerOnToken(token)` helper in `app/static/tabletop.js`. Pans `panX` / `panY` so the token's world-coord center lands at the map-pane viewport center, accounting for the current `scale`. Returns false when the pane hasn't been laid out yet so the caller can decide whether to retry.
- `findMyFirstControlledToken()` — first token in the local `tokens` array that the current user controls (via `controller_user_id` OR via being the linked character's owner).
- `centerOnFirstControlledToken()` — the player-only convenience wrapper. No-op when `ME.isGm` is true.

### Changed
- Initial-load: `setTimeout(centerOnFirstControlledToken, 0)` runs after the synchronous initial `render()` so the browser has a chance to lay out the map pane before we read its rect. Covers both the GM-clicks-Start path (waiting page redirects → fresh tabletop page load) and the encounter-map-switched path (the `map_change` WS broadcast triggers `location.reload()`).
- `token_add` WS handler now calls `centerOnFirstControlledToken()` after pushing the new token + re-rendering. Encounter loads cascade `token_add` per token — the moment the player's controlled token arrives the view recenters; subsequent token_adds are idempotent.
- `app/version.py`, `README.md`, `CHANGELOG.md` — MINOR bump to 0.77.0. No schema change.

## [0.76.0] - 2026-05-12

**Schema version:** 41

**Commit summary:** Add map rename and free-form tags with inline editing on the campaign settings maps table

**Description:** The campaign settings → Maps section gets the same kind of light inline editing the playlists section has. The Name column is now an editable input that auto-saves on blur; a new Tags column does the same for free-form GM-side tags. The upload form gains a matching optional tags input. Tags use the same normalisation as encounter and playlist tags (trim, dedupe case-insensitive, ≤40 chars each, ≤20 entries). A shared `<datalist>` autocompletes tag names across all map rows and the upload form.

### Added
- `Map.tags` (JSON list, default `[]`). Schema v41 inline migration adds the column with the JSON / TEXT dialect split used by every other JSON column.
- `POST /campaign/{cid}/settings/maps/{mid}/rename` (GM-only). JSON body `{name}`. Empty / whitespace-only names are rejected so a blank row never lands in the table.
- `POST /campaign/{cid}/settings/maps/{mid}/tags` (GM-only). JSON body `{tags}` (array or comma-separated string). Reuses the existing `_parse_tags` helper for normalisation.
- `tags` form field on the existing upload route (`POST /campaign/{cid}/settings/maps`).
- **Campaign settings → World → Maps**: new Tags column between Name and Grid. Name + tags inputs auto-save on blur; the tags input echoes back the server's normalised list (dedupe + trim visible without a page reload). Shared `#map-tag-list` `<datalist>` aggregates every map's current tags for autocomplete in both the inline edit inputs and the upload form.

### Changed
- `app/version.py`, `README.md`, `CHANGELOG.md` — MINOR bump to 0.76.0. `SCHEMA_VERSION` bumped from 40 to 41.

### Schema
- New `maps.tags` column (JSON on Postgres / TEXT on SQLite, NOT NULL DEFAULT `[]`).
- `SCHEMA_VERSION` bumped from 40 to 41.

## [0.75.0] - 2026-05-12

**Schema version:** 40

**Commit summary:** Add description and tags fields to playlists and show the description on the tabletop

**Description:** Each playlist now carries an optional short description and a list of free-form tags. The campaign settings → Audio section exposes both as auto-saving inputs at the top of each playlist's body (above the track list), plus matching fields on the New playlist form. The tabletop GM Music panel renders the description next to the playlist name (muted, em-dash separator) so the GM can see what each playlist is for without having to recall the name. Tags are metadata-only for now — searched and surfaced in settings, not displayed on the tabletop.

### Added
- `Playlist.description` (VARCHAR(200) NOT NULL DEFAULT '') and `Playlist.tags` (JSON list, default `[]`) columns. Schema v40 inline migration adds both with safe defaults.
- `POST /campaign/{cid}/playlists/{pid}/description` (GM-only). Body: `{description: str}`. Empty / missing clears.
- `POST /campaign/{cid}/playlists/{pid}/tags` (GM-only). Body: `{tags: list | str}`. Accepts either a JSON array or a comma-separated string. Server-side normalisation: trimmed, deduped (case-insensitive), each tag capped at 40 chars, list capped at 20 entries (same rules as the encounter tag helper).
- `_normalize_playlist_tags` helper in `audio_routes.py` — single normalisation point reused by create + the tags endpoint.
- `create_playlist` (POST form handler) gained optional `description` and `tags` form fields.
- **Campaign settings → Audio**: each playlist body now starts with a description input and a tags input that auto-save on blur. The tag input reflects the server's normalised value after save so dedupe + trim are visible without a page reload.
- **Campaign settings → New playlist form**: optional `description` and `tags` inputs alongside the existing name + category.
- **Tabletop GM Music panel**: playlist label shows `Name — Description` when a description is set (muted suffix); the surrounding `title` tooltip includes it too.

### Changed
- `app/version.py`, `README.md`, `CHANGELOG.md` — MINOR bump to 0.75.0. `SCHEMA_VERSION` bumped from 39 to 40.

### Schema
- New `playlists.description` column (VARCHAR(200) NOT NULL DEFAULT '').
- New `playlists.tags` column (JSON on Postgres / TEXT on SQLite, NOT NULL DEFAULT `[]`).
- `SCHEMA_VERSION` bumped from 39 to 40.

## [0.74.1] - 2026-05-12

**Schema version:** 39

**Commit summary:** Stop auto-expanding the first playlist on the campaign settings page

**Description:** The campaign settings → Audio section used to open the first playlist's `<details>` block by default. With a growing library that pushes the rest of the section (and now the encounters library below it) down on every page load. All playlists now render collapsed; the GM clicks the chevron on the one they want.

### Changed
- `app/templates/campaign_settings.html` — removed the `{% if loop.first %}open{% endif %}` attribute on the playlist `<details>` element. Every playlist now renders collapsed on first paint.
- `app/version.py`, `README.md`, `CHANGELOG.md` — PATCH bump to 0.74.1. No schema change.

## [0.74.0] - 2026-05-12

**Schema version:** 39

**Commit summary:** Add default encounter on session start plus encounter folders and name/tag/folder search

**Description:** Three additions to the encounters library. (1) Campaign settings → Basic info gets a new "Default encounter on session start" dropdown; clicking ▶ Start session runs the same load flow as the manual ▶ Load button (strict reset on the bound map + GM tokens + player positions or spawn points). Failures are tolerated and logged — a broken default encounter never blocks session start. (2) Each encounter now has an optional **folder** (single-level, free-form string) for library organisation. Both library surfaces render rows grouped by folder in collapsible `<details>` blocks (open by default; unfiled rows group at the bottom), and the Save / New / per-row Edit forms get a folder input with `<datalist>` autocomplete from existing folders in the campaign. (3) Both libraries get a **search** input — case-insensitive substring match against name, any tag, or folder — that composes with the existing tag filter chip (AND).

### Added
- `Encounter.folder` (VARCHAR(120) NOT NULL DEFAULT '') — single-level grouping string. Empty = "Unfiled" group in the UI.
- `Campaign.default_encounter_id` (nullable FK → encounters, ON DELETE SET NULL) — the encounter that auto-loads on Start session. Same pattern + `use_alter=True` as `auto_play_playlist_id`.
- `_perform_encounter_load(db, campaign, enc, *, start_audio, user_id)` async helper extracted from `load_encounter`. The route is now a thin wrapper that parses the body + permission-checks and delegates. `start_session` calls the same helper.
- `start_session` honors `campaign.default_encounter_id`: after flipping `session_active=True` and triggering audio auto-play, it loads the default encounter with `start_audio=False` so the audio setting doesn't fight with the encounter's auto-play. Failures are caught + logged at WARN, never raised.
- `campaign_settings_save` accepts `default_encounter_id` (Form, optional). Validates the encounter belongs to the campaign before assigning; empty / invalid clears.
- **Campaign settings → Basic info** gains a "⚔ Encounter on session start" fieldset with a "Default encounter" dropdown (mirrors the existing 🎵 Audio fieldset structure).
- `_encounter_to_dict` returns `folder`. `create_encounter` + PATCH accept `folder`.
- **Battle drawer Encounters panel**: search input above the sort + tag-filter row; folder input (with datalist autocomplete) in the Save form and in each per-row Edit form; collapsible per-folder grouping.
- **Campaign settings → World → Encounters**: search input alongside the sort + tag-filter row; folder input in the New form and in each card's Edit form; collapsible per-folder grouping (each folder rendered as a bordered `<details>` block).
- Shared `<datalist>` elements `#enc-folder-list` (Battle drawer) and `#enc-lib-folder-list` (settings) populated from current library on every refresh.

### Changed
- `load_encounter` route function is now a thin wrapper around `_perform_encounter_load`. The behavior is identical from the caller's perspective.
- The Battle drawer + settings library rerender functions now apply the search filter (substring match across name, tags, folder) on top of the existing tag-chip filter, then group the surviving rows by folder before rendering.
- `app/version.py`, `README.md`, `CHANGELOG.md` — MINOR bump to 0.74.0. `SCHEMA_VERSION` bumped from 38 to 39.

### Schema
- New `encounters.folder` column (VARCHAR(120) NOT NULL DEFAULT '').
- New `campaigns.default_encounter_id` column (INTEGER NULL, FK → encounters(id) ON DELETE SET NULL).
- `SCHEMA_VERSION` bumped from 38 to 39.

## [0.73.0] - 2026-05-12

**Schema version:** 38

**Commit summary:** Move spawn points onto encounters as a per-encounter toggle and make load strict about token presence

**Description:** Spawn points are now an encounter feature instead of a standalone per-map one. Each encounter has a **Use spawn points for players** toggle in its edit form; when on, the GM gets a per-character Set / Clear list, and clicking Set arms click-to-set on the canvas so the next click on the encounter's bound map records that character's spawn coordinate. Loading an encounter is now **strict**: Pass 1 deletes every token on the target map (GM-owned and player-owned alike), then Pass 2 recreates only what the encounter describes — GM tokens from the saved payload + player tokens either from the encounter's spawn points (when the toggle is on) or from the snapshot's saved player positions (when off). A player whose character isn't in the encounter has their token removed on Load. The v0.71.0 standalone Battle-drawer Spawn Points panel and its `/maps/{mid}/spawn*` endpoints are gone; `Map.player_spawns` stays in the schema for backward compat but isn't read.

### Added
- `Encounter.use_spawn_points` (boolean, default false) and `Encounter.spawn_points` (JSON, default `{}`) columns. Schema v38 inline migration adds both with safe defaults so existing encounters keep loading exactly as they did before.
- `POST /api/campaign/{cid}/encounters/{eid}/spawn` (GM-only). Body: `{character_id: int, x?: float, y?: float}`. Set the coord when both are present and numeric; clear the entry when either is missing or null. Returns the updated encounter dict.
- `_encounter_to_dict` returns `use_spawn_points` + `spawn_points`.
- `create_encounter` and `PATCH /encounters/{eid}` accept `use_spawn_points` + `spawn_points` (the PATCH wholesale-replaces the dict; the new `/spawn` route is the per-character incremental path).
- **Battle drawer encounter row edit form** gains a "Use spawn points for players" checkbox and, when enabled, a per-character list with Set / Clear / coord readout. Set arms click-to-set; Clear POSTs to the new `/spawn` route. A hint above the list tells the GM whether they're on the right map (Set is disabled until the active map matches the encounter's bound map).
- `vttSetSpawnContext({encounterId, mapId, spawns})` / `vttSpawnPlacedCallback(encId, charId, x, y)` helpers bridging the inline encounter panel and the canvas in `tabletop.js`. Edit-open sets the context; Cancel / Save / Esc clears it.

### Changed
- `load_encounter` now uses **strict** semantics. Pass 1 deletes every token on the target map (was: only GM tokens). Pass 2 creates GM tokens from the payload as before; for player tokens it consults `use_spawn_points`: when true, one token per `spawn_points` entry (placed at the spawn coord, grid-snapped to the bound map); when false, fall back to the snapshot's saved player tokens. Players absent from the encounter no longer have their tokens preserved on Load — they're removed.
- Canvas marker pass in `tabletop.js` now reads from the currently-editing encounter context (set by the panel when the GM opens an edit form) instead of `Map.player_spawns`. Markers only render when the encounter's bound map matches the active map.
- Click-to-set in `tabletop.js` now routes to `POST /encounters/{eid}/spawn` (was: `PATCH /maps/{mid}/spawn`). The arming flow refuses to engage without a spawn context to land in.
- `load_encounter` docstring rewritten to describe the strict + spawn-points behavior. Battle drawer Load confirm dialog text reflects the same.
- `app/version.py`, `README.md`, `CHANGELOG.md` — MINOR bump to 0.73.0. `SCHEMA_VERSION` bumped from 37 to 38.

### Removed
- `PATCH /api/campaign/{cid}/maps/{mid}/spawn` and `POST /api/campaign/{cid}/maps/{mid}/place-players-at-spawn` (the v0.71.0 standalone map-level spawn-points endpoints).
- Battle drawer **📍 Spawn Points** collapsible panel + its inline panel controller `<script>` block.
- WS message type `spawn_update` (no callers after the panel removal).
- `tabletop.js` exports `vttGetSpawns` and `vttRefreshSpawnPanel`. Helpers replaced by `vttSetSpawnContext` / `vttSpawnPlacedCallback`.

### Schema
- New `encounters.use_spawn_points` column (BOOLEAN NOT NULL DEFAULT FALSE).
- New `encounters.spawn_points` column (JSON NOT NULL DEFAULT `{}` on Postgres, TEXT on SQLite).
- `maps.player_spawns` (from v0.71.0) stays in place but is no longer read. No destructive migration.
- `SCHEMA_VERSION` bumped from 37 to 38.

## [0.72.0] - 2026-05-12

**Schema version:** 37

**Commit summary:** Restore saved player positions on encounter load instead of preserving the live placement

**Description:** Tightens the encounter Load semantics so player tokens behave symmetrically with GM tokens — every player token in the saved bundle snaps to its saved position when Load is pressed, instead of being preserved in place. This is the behavior the GM expected for "press Play and players appear where I prepped them." Players whose characters were on the map at save time get moved; players whose characters were not in the saved bundle are untouched (their tokens stay exactly where they are). Reverses the v0.66.0 "preserve player tokens as-is" decision after the user clarified the intent during the v0.70.0–v0.71.0 prep-features arc. No schema change.

### Changed
- `load_encounter` Pass 2 player-token branch: previously skipped (Option B from v0.66.0) when a token already existed for that character on the target map. Now replaces it — deletes the existing token, broadcasts `token_delete`, then creates a fresh token at the saved coords and broadcasts `token_add`. Characters absent from the saved payload still aren't touched, so the GM can have additional players who weren't in the prep and they stay put.
- `load_encounter` docstring rewritten to spell out the new GM-vs-player handling. The "Pass 1 deletes only GM tokens" rule still holds; the change is in Pass 2.
- Battle drawer Load confirm dialog wording updated to reflect the new behavior: "Player tokens for characters in the saved encounter will move to their saved positions; other player tokens are untouched." Also updated the ▶ Load button's `title` and the panel-block comment so the surface area reads consistently.
- `app/version.py`, `README.md`, `CHANGELOG.md` — MINOR bump to 0.72.0. No schema change (the `encounters.payload` shape already captures player tokens as of v0.70.0).

## [0.71.0] - 2026-05-12

**Schema version:** 37

**Commit summary:** Add per-character spawn points on each map for session prep and split-party setups

**Description:** New session-prep feature for GMs: drop a designated starting marker for each player character on every battle map, then drop everyone at their spots in one click at the table. Designed for split-party setups — different characters can start in different rooms / corners / levels of the same map. Each map gets its own per-character spawn dict (Schema v37 — additive `maps.player_spawns` JSON column). A new "📍 Spawn Points" collapsible panel in the Battle drawer (GM-only) lists every campaign character; the GM clicks **Set**, then clicks anywhere on the canvas to record that character's spawn coordinates (snapped to the grid). **Clear** removes a marker. **📍 Place all** at the bottom drops each player's token at their saved spawn — characters already on the active map are skipped so deliberate pre-placements aren't overwritten. The canvas renders a dashed ring in each character's color with their initial inside as a GM-only marker; players don't see prep state.

### Added
- `Map.player_spawns` JSON column. Default `{}`. Keyed by character id (string) → `{x, y}`. Inline migration in `_apply_inline_migrations` (Schema v37) adds the column with `JSON` on Postgres, `TEXT` on SQLite — same dialect-split pattern used by every other JSON column in the schema.
- `PATCH /api/campaign/{cid}/maps/{mid}/spawn` (GM-only). Body: `{character_id: int, x?: float, y?: float}`. Provide coords to set; omit (or null) to clear. Broadcasts a `spawn_update` WS message so other connected GMs stay in sync.
- `POST /api/campaign/{cid}/maps/{mid}/place-players-at-spawn` (GM-only). For each character with a saved spawn AND no token on the map, creates a token at the saved coords (snapped to the grid). Returns `{placed, already_placed}`. Skipped characters are tokenless-by-choice and never overwritten.
- New WS message type `spawn_update` (`{map_id, character_id, spawn?: {x, y}}`).
- **Battle drawer → 📍 Spawn Points** (GM-only, collapsible). Per-character rows with color swatch, name, current coords (or "(unset)"), and **Set** / **Clear** buttons. Bulk **📍 Place all** button + status line at the bottom. A persistent banner appears above the canvas while click-to-set is armed; Esc cancels.
- Canvas markers: dashed character-colored ring with the character's initial in the center, drawn at 0.85 opacity so live tokens stay dominant. GM-only render (player clients render nothing). Marker pass added to `render()` after the token pass.
- `window.vttArmSpawn(charId)` / `window.vttCancelSpawnArming()` / `window.vttGetSpawns()` / `window.vttGetCharacters()` / `window.vttRefreshSpawnPanel` helpers bridging the canvas (in `tabletop.js`) and the panel controller (inline in `tabletop.html`).
- `MAP_ID` global in `tabletop.html` — needed because click-to-set + bulk-place endpoints address the map directly.

### Changed
- `tabletop.js` canvas `mousedown` handler intercepts the left-click when click-to-set is armed: snaps to the grid, PATCHes the new coord, then exits arming mode. Right-click pans as before. `crosshair` cursor while armed (driven by a `body.spawn-arming` class).
- `tabletop.js` WS handler chain gained a `spawn_update` branch that mutates the local `playerSpawns` dict and re-renders the canvas + panel.
- `initial-data` JSON injected into `tabletop.html` now includes the active map's `player_spawns`.
- `app/version.py`, `README.md`, `CHANGELOG.md` — MINOR bump to 0.71.0. `SCHEMA_VERSION` bumped from 36 to 37.

### Schema
- New `maps.player_spawns` column (JSON / TEXT per dialect). Defaults to `{}`.
- `SCHEMA_VERSION` bumped from 36 to 37.

## [0.70.0] - 2026-05-12

**Schema version:** 36

**Commit summary:** Add encounter prep features for player tokens map selector playlist selector blank drafts thumbnails and tag autocomplete

**Description:** Five combat-prep additions to the encounters feature. (1) **Player tokens are now part of the encounter snapshot.** Save captures GM and player tokens alike. On load, each saved player token is placed at its saved position **only if** that character has no token on the target map yet (Option B) — so a player who's already placed themselves is never yanked around, but absent players auto-appear where the GM staged them. (2) **Map selector** in both Save and Edit forms; the GM can bind an encounter to a map other than the currently-active one. (3) **Playlist + playback-mode selector** in both forms; the GM picks the auto-play playlist directly instead of inferring from whatever's currently streaming. (4) **+ New Encounter** flow on the campaign-settings library — creates a blank draft (name + map + playlist + tags + notes) without touching the live tabletop; token positions are filled in later via 💾 Update from the Battle drawer. (5) **Map thumbnails** on every encounter row in both surfaces, plus **tag autocomplete** via a shared `<datalist>` populated from the existing library. No schema change.

### Added
- `+ New Encounter` button + collapsible form on campaign settings → World → Encounters. Posts `payload: {tokens: [], battle_state: {}}` so the server's create endpoint treats it as a draft rather than a state snapshot.
- `POST /api/campaign/{id}/encounters` now accepts optional `map_id`, `auto_play_playlist_id`, `auto_play_mode`, and an explicit `payload` in the body. When `payload` is present, the server skips the live-state snapshot entirely. `map_id` + `auto_play_playlist_id` are validated against the campaign's own maps + playlists so the GM can't bind to another campaign's resources.
- `PATCH /api/campaign/{id}/encounters/{eid}` now accepts the same `map_id` / `auto_play_playlist_id` / `auto_play_mode` keys for in-place rebinding.
- `_encounter_to_dict` returns `map_image_url` (for thumbnails) and `auto_play_playlist_name` (for richer hover/preview text).
- Map / Playlist / Mode dropdowns in the **Save** form (Battle drawer), and matching dropdowns in the **per-row Edit** forms on both the Battle drawer and the campaign settings library.
- Map thumbnail (36×24 on the Battle drawer, 60×40 on settings) at the start of every encounter row. Falls back to a monogram tile or em-dash when no map is bound.
- Tag autocomplete via shared `<datalist>` elements (`#enc-tag-list` on the tabletop, `#enc-lib-tag-list` on settings). Refilled on every list refresh so freshly-added tags appear immediately as suggestions.

### Changed
- `_snapshot_encounter_payload` no longer filters out `controller_user_id IS NOT NULL` — player-controlled tokens are now part of the saved bundle. Each token entry includes the `controller_user_id` to disambiguate on load.
- `load_encounter` Option B: saved player-token entries (`character_id` set) are placed at the saved position **only when the character has no token on the target map**. Existing player tokens are never moved or replaced; the v0.66.0 "preserve as-is" guarantee still holds. A missing character surfaces as a non-fatal warning instead of failing the whole load.
- `campaign_view` (tabletop route) now passes `all_maps` to the template alongside `playlists` so the Battle drawer's selectors and per-row edit dropdowns can populate without a separate fetch.
- `app/version.py`, `README.md`, `CHANGELOG.md` — MINOR bump to 0.70.0. No schema change.

## [0.69.0] - 2026-05-12

**Schema version:** 36

**Commit summary:** Add a Players tab to the Add Token modal for placing or removing player character tokens

**Description:** The "+ Add Token" modal in the Battle drawer's Token Management panel gains a third tab — **Players** — alongside the existing **Library** (NPCs/monsters) and **Blank Token** tabs. The GM can now drop a player character's token onto the map without leaving the Token Management workflow. Each card in the grid shows the character's portrait (falling back to the player's portrait, then a colored initial avatar tinted with the character's roll-log color), the character name, and the player's display name underneath. Tokens already on the active map are dimmed with an "On map" badge; clicking dismisses them via the existing `DELETE /character/{cid}/token` endpoint. Tokens not yet placed are dropped at the GM's viewport center via the v0.65.0 `place-token` endpoint with viewport coords. No new endpoints — the tab reuses the same surfaces the mini-sheet ⊕/⊖ buttons already call.

### Added
- **Players tab** in `#add-token-modal` between Library and Blank Token. Renders a responsive grid of player characters from the existing `char_data` payload. Card UX:
  - Portrait: character `portrait_url`, else owner user portrait from `USER_PORTRAITS`, else a 90px-tall avatar tile tinted with the character's color (or owner color) showing the first letter of the name.
  - Name + owner display name under the avatar.
  - "On map" badge in the top-right corner when a token for this character already exists on the active map. The card is dimmed (`opacity:0.78`) and the click handler routes to the `DELETE` (remove) path.
  - Click handler is busy-locked while the request is in flight to prevent double-fires; modal closes on success.
  - Helpful empty state ("No player characters in this campaign yet.") for fresh campaigns.

### Changed
- `campaign_view` in `app/routes/tabletop_routes.py` — `char_data` now includes `portrait_url` and `color` per character so the new Players tab can render proper avatars without duplicating the user_*_map merge logic the mini-sheet already does.
- `app/version.py`, `README.md`, `CHANGELOG.md` — MINOR bump to 0.69.0. No schema change.

## [0.68.0] - 2026-05-12

**Schema version:** 36

**Commit summary:** Add encounter duplicate hover-preview sort and free-form tag filtering across the library UIs

**Description:** Phase 5 of the combat encounters feature (see `docs/encounters-plan.md`). The library gets quality-of-life polish: a 📋 Duplicate button per row that POSTs a copy of the bundle with "(copy)" appended to the name; a browser-native hover tooltip on each row that lists the saved token names + map name; a Sort dropdown (Recent / A–Z); and free-form GM-chosen tags ("boss", "random", "set-piece", …) for grouping. Tags are an additive `encounters.tags` JSON column (Schema v36); clicking a tag chip in the new filter bar narrows the visible rows. Both surfaces — the tabletop Battle drawer Encounters panel and the campaign-settings Encounters section — got the same set of features, and the settings surface is now fully client-side rendered from `/api/encounters` so sort, tag filter, duplicate, edit, and delete all update without a page reload.

### Added
- `encounters.tags` JSON column. Default `[]`. Server-side normalisation: trimmed, deduped (case-insensitive), each tag capped at 40 chars, list capped at 20 entries. Accepted as either a JSON array or a comma-separated string in `POST /encounters` + `PATCH /encounters/{eid}` bodies.
- `POST /api/campaign/{id}/encounters/{eid}/duplicate` (GM-only). Copies an existing encounter into a fresh row with " (copy)" suffix on the name; payload + map + playlist + tags + notes carried over; new `created_at` / `updated_at`.
- `_parse_tags(value)` helper in `tabletop_routes.py` — central normalisation point reused by create + PATCH.
- `_encounter_to_dict` now returns `tags`, `map_name`, `token_names` (capped at 25), and `token_names_extra` (overflow count). The new fields power the hover-preview tooltip and the per-row map summary.
- **Battle drawer Encounters panel**:
  - Sort dropdown (Recent / A–Z) above the list.
  - Tag filter chip bar above the list. Active chip toggles on/off; filter is purely client-side over the most recent fetch.
  - 📋 Duplicate icon button on each row.
  - Browser-native `title` attribute with the multi-line token + map + tags preview.
  - Tags input in the Save form (comma-separated) and in the per-row Edit form.
  - Tag chips render under each row's description when present.
- **Campaign settings → World → Encounters**:
  - Full client-side rendering from `/api/encounters` (replaces the previous server-rendered cards).
  - Sort dropdown + tag filter chip bar.
  - 📋 Duplicate button on each card alongside ✎ Edit / 🗑 Delete.
  - Hover preview tooltip, tag chips on each card, tags input in the inline edit form.

### Changed
- `app/version.py`, `README.md`, `CHANGELOG.md` — MINOR bump to 0.68.0. `SCHEMA_VERSION` bumped from 35 to 36.

### Schema
- New `encounters.tags` column (`JSON NOT NULL DEFAULT '[]'` on Postgres, `TEXT NOT NULL DEFAULT '[]'` on SQLite — same dialect-split pattern used by `custom_classes.spell_list`).
- `SCHEMA_VERSION` bumped from 35 to 36. Inline migration in `_apply_inline_migrations()` runs the `ALTER TABLE encounters ADD COLUMN tags …` on existing deployments at boot.

### Coming next
- Encounters feature is now feature-complete per the original plan. Future polish ideas (tag autocomplete, multi-tag AND/OR filters, encounter sharing across campaigns, etc.) are out of scope for the planned phases.

## [0.67.0] - 2026-05-12

**Schema version:** 35

**Commit summary:** Add encounter rename overwrite and delete with inline UI on tabletop and campaign settings

**Description:** Phase 4 of the combat encounters feature (see `docs/encounters-plan.md`). Saved encounters are now fully editable: the GM can rename them, replace notes, re-snapshot the current state into an existing entry (so "Goblin Ambush" evolves without spawning a sibling row each session), and delete entries from the library. Three new endpoints back this — `PATCH /encounters/{eid}` for name + notes, `POST /encounters/{eid}/update` for in-place re-snapshot (payload + map_id + auto_play_playlist_id + auto_play_mode all replaced; name + notes + created_at preserved), and `POST /encounters/{eid}/delete` for removal. Both the tabletop Battle drawer and the campaign settings "Encounters" section get the inline UI. The Battle drawer row gains three new icon buttons next to `▶`: 💾 Update (re-snapshot), ✎ Edit (inline rename + notes form), 🗑 Delete (confirm + remove). The campaign settings library gets ✎ Edit + 🗑 Delete on each card and a card-removed-on-empty fallback so the section gracefully degrades back to the empty state without a page reload.

### Added
- `PATCH /api/campaign/{id}/encounters/{eid}` (GM-only). Body: `{name?, description?}`. Either or both. Empty/whitespace `name` is rejected. Returns the updated dict.
- `POST /api/campaign/{id}/encounters/{eid}/update` (GM-only). Re-snapshots the current campaign state into the existing row: replaces `payload`, `map_id`, `auto_play_playlist_id`, `auto_play_mode`; preserves `name`, `description`, `created_at`. `updated_at` auto-bumps via the column's `onupdate=func.now()`. Reuses `_snapshot_encounter_payload`.
- `POST /api/campaign/{id}/encounters/{eid}/delete` (GM-only).
- **Battle drawer Encounters panel** — each row now carries `▶` Load / 💾 Update / ✎ Edit / 🗑 Delete icon buttons. ✎ swaps the row's title row for an inline name + notes form with Save / Cancel; Save PATCHes and refreshes the list. 💾 Update prompts for confirmation, POSTs `/update`, and refreshes. 🗑 prompts for confirmation, POSTs `/delete`, refreshes.
- **Campaign settings → World → Encounters** — each card now carries `✎ Edit` and `🗑 Delete` actions on its title row. Edit swaps the card to an inline name + notes form (`<input>` + `<textarea>`) with Save / Cancel; Save PATCHes and re-renders the visible name + description from the server's response without a page reload. Delete confirms, POSTs `/delete`, and removes the card from the DOM; if the last card is removed, the container is replaced with the same SSR empty-state copy.

### Changed
- `app/version.py`, `README.md`, `CHANGELOG.md` — MINOR bump to 0.67.0. No schema change (the `encounters` table + columns from v0.64.0 cover the new endpoints; `updated_at` was already in place with `onupdate=func.now()`).

### Coming next
- Phase 5 — duplicate / preview-on-hover / sort / tags.

## [0.66.0] - 2026-05-12

**Schema version:** 35

**Commit summary:** Add encounter load flow with two-pass clear and apply and preserve player tokens

**Description:** Phase 3 of the combat encounters feature (see `docs/encounters-plan.md`). The GM can now reload a saved encounter at the table by clicking **▶ Load** on its row in the Battle drawer Encounters panel. The load flow is two-pass: it deletes GM-owned tokens on the **target map** (the encounter's bound map, or the current active map if the encounter has none), switches `Campaign.active_map_id` if the encounter binds a different map, recreates the saved tokens, and restores the in-memory battle / initiative state. **Player tokens are never touched** — their positions and map assignments are preserved exactly as they were (Open Question 1 in the plan, resolved in favor of "preserve as-is"). If the map switches, the existing player token stays on the old map until the GM or player moves it — the GM is expected to make the call mid-session. Audio auto-starts when the saved encounter had a playlist playing at save time and the GM keeps the default `start_audio=true`. Missing token templates fall back to a manual token with the saved label override; a missing playlist skips audio. Both surface as non-fatal `warnings[]` in the response and pop a single `alert` after the load lands. Delete UI is Phase 4 and still pending.

### Added
- `POST /api/campaign/{id}/encounters/{eid}/load` (GM-only) — two-pass clear + apply. Body: `{start_audio?: bool = true}`. Returns `{ok, map_switched, tokens_created, tokens_deleted, warnings}`. Player tokens (`controller_user_id IS NOT NULL`) are explicitly excluded from the Pass 1 delete sweep; saved entries with `character_id` set are skipped during Pass 2 recreation (we don't recreate player tokens — they live across loads).
- New WS message `map_change` (`{map_id}`) — broadcast by the load flow when the active map switches. Clients reload to render the new map; the canvas wasn't built to swap maps in place. Same-map loads use the existing surgical `token_delete` + `token_add` + `battle_update` broadcasts so connected clients update without a reload.
- **▶ Load** button on each encounter row in the Battle drawer Encounters panel. Click prompts a confirm dialog summarising token counts; warnings from the server pop in a second alert.

### Changed
- `app/static/tabletop.js` — WS message handler chain gained a `map_change` branch that triggers `location.reload()` so all connected clients land on the new map.
- `app/version.py`, `README.md`, `CHANGELOG.md` — MINOR bump to 0.66.0. No schema change (the `encounters` table from v0.64.0 + the save endpoint from v0.65.0 are both reused as-is).

### Coming next
- Phase 4 — rename + overwrite + delete (`PATCH /encounters/{eid}`, `POST /encounters/{eid}/update`, `POST /encounters/{eid}/delete`).
- Phase 5 — duplicate / preview-on-hover / sort / tags.

## [0.65.0] - 2026-05-12

**Schema version:** 35

**Commit summary:** Add encounter save flow and place new tokens at the GM viewport center

**Description:** Phase 2 of the combat encounters feature (see `docs/encounters-plan.md`). The GM can now save the current state — active map + GM-owned tokens + battle hub state + currently-playing playlist — as a named encounter from a new save form in the Battle drawer's Encounters panel. Player-controlled tokens (`controller_user_id IS NOT NULL`) are intentionally skipped from the snapshot. The library is append-only for this release; load / delete UI is planned for a later phase. Same release also fixes token placement: the GM's `⊕` button on player mini-sheets and the `+ Add Token` modal now drop new tokens at the **center of the visible viewport** (the map-pane rect, accounting for pan + zoom), so tokens land where the GM is looking rather than at the often-offscreen geometric center of the map.

### Added
- `POST /api/campaign/{id}/encounters` (GM-only) — saves the current state. Body: `{name, description?}`. Snapshots GM-owned tokens on the active map + the in-memory battle hub state + the active map id + the currently-streaming playlist id. Player-controlled tokens (`controller_user_id IS NOT NULL`) are intentionally skipped from the token snapshot.
- `_snapshot_encounter_payload(db, campaign)` helper in `tabletop_routes.py` — central place for the save shape, reusable by the future load flow.
- `vttViewportCenterWorld()` + internal `viewportCenterWorld()` helper in `app/static/tabletop.js` — returns the world-space (canvas-coord) center of the GM's current viewport (map-pane rect, accounting for pan + zoom).
- **Battle drawer Encounters panel** now ships its Save UI: a name + notes input with a "💾 Save" button below the list. Save shows a transient "Saved." status and refreshes the list. A footer line notes that load + delete buttons are coming in a future release.

### Changed
- `place_character_token` (POST `/api/campaign/{id}/character/{char_id}/place-token`) now accepts an optional JSON body `{x, y}`. When the body is missing or the coords don't parse, the legacy map-center default is used so non-browser callers stay unaffected. When coords are provided, they're snapped to the active map's grid so the new token sits cleanly on a cell.
- `app/static/tabletop.js`:
  - The `⊕` (place character token) handler now sends the viewport-center world coords as the body of the POST. The `⊖` (DELETE) path is unchanged.
  - The `+ Add Token` modal's template-card and blank-token paths both send `{x, y}` from `viewportCenterWorld()` instead of the previous `(100, 100)` literal.
- `app/version.py`, `README.md`, `CHANGELOG.md` — MINOR bump to 0.65.0. No schema change (the `encounters` table from v0.64.0 is reused as-is).

### Coming next
- Phase 3 — load flow (`POST /encounters/{eid}/load`), two-pass clear + apply, player-token preservation, audio auto-start, ▶ Load button.
- Phase 4 — rename + overwrite + delete UI.
- Phase 5 — duplicate / preview-on-hover / sort / tags.

## [0.64.0] - 2026-05-12

**Schema version:** 35

**Commit summary:** Add encounters table and a read-only library UI on the tabletop and campaign settings

**Description:** First slice of the combat encounters feature (Phase 1 of the plan in `docs/encounters-plan.md`). A new `encounters` table stores a GM-saved bundle of `{map, tokens, initiative seed, optional playlist}` as a JSON payload, keyed to a campaign with a cascading FK. Two read-only listing surfaces consume it — a GM-only "⚔ Encounters" collapsible section under Token Management in the Battle drawer, populated by a new `GET /api/campaign/{id}/encounters` fetch on first open, and a full-width Encounters section under the **World** tab of campaign settings that server-renders from the same model. No save or load buttons yet; both surfaces currently show "None yet" plus a note that the save / load flow is coming. Existing deployments auto-upgrade — the new table is created via `Encounter.__table__.create(checkfirst=True)` on next boot.

### Added
- `Encounter` model (`app/models.py`): `id`, `campaign_id` (FK → campaigns, ON DELETE CASCADE, indexed), `name`, `description`, `map_id` (FK → maps, SET NULL), `auto_play_playlist_id` (FK → playlists, SET NULL), `auto_play_mode`, `payload` (JSON), `created_at`, `updated_at`. Includes ORM relationships back to campaign / map / playlist for future render-time joins.
- `GET /api/campaign/{campaign_id}/encounters` (GM-only) — returns a list of `{id, name, description, map_id, auto_play_playlist_id, auto_play_mode, token_count, initiative_count, created_at, updated_at}` projections, sorted by `created_at` desc. Powers the Battle-drawer list.
- `_encounter_to_dict` helper in `tabletop_routes.py` so the listing projection lives in one place (Phase 2+ will reuse it).
- **Battle drawer** — new `<details id="encounters-panel">` block inside `{% if is_gm %}`, immediately under Token Management. Wears the same gold "GM only" pill + chevron-rotate-on-collapse animation as the Token Management panel. JS lazy-fetches the list via the new endpoint on first paint and renders a stack of card rows (name, token/init count, optional description). Empty state shows "None saved yet."; error state shows the HTTP status. A small note clarifies the save/load buttons are coming in a future release.
- **Campaign settings → World tab** — new `<section id="encounters" data-tab="world">` between Token Templates and the Homebrew tab sections. Server-rendered cards from `encounters` template var, with map id / playlist id / mode summary, created-at date, and optional description. Empty state lives inline.

### Changed
- `campaign_view` and `campaign_settings` in `app/routes/tabletop_routes.py` now load encounters server-side. `campaign_settings` passes them as `encounters` to the template; `campaign_view` does the fetch via the JS path so the SSR payload stays unchanged for everyone else.
- `app/version.py`, `README.md`, `CHANGELOG.md` — MINOR bump to 0.64.0. `SCHEMA_VERSION` bumped from 34 to 35.

### Schema
- New `encounters` table (see Added). `_apply_inline_migrations()` now calls `Encounter.__table__.create(bind=engine, checkfirst=True)` as the Schema v35 step.
- `SCHEMA_VERSION` bumped from 34 to 35.

### Coming next
- Phase 2 (Save current state): `POST /encounters` capture flow + a "💾 Save current state as encounter" form in the Battle drawer.
- Phase 3 (Load): two-pass server flow with player-token preservation. Open question 1 in `docs/encounters-plan.md` (player-token position on map switch) needs a decision before Phase 3 begins.

## [0.63.0] - 2026-05-12

**Schema version:** 34

**Commit summary:** Restrict token add and remove to the GM and split Token Management into Players and NPCs sections

**Description:** Players can no longer add or remove their own character tokens from the map — the GM owns all placement now. The server-side `place_character_token` and `remove_character_token` endpoints both gate on `_user_is_gm`, so even a player who tries to call the API directly gets a 403. The client-side `canPlaceChar` helper that controls the ⊕/⊖ buttons in the player mini-sheet now returns `!!ME.isGm`, so players don't see those controls at all. To make the GM's life easier under this new model, the Token Management panel in the Battle drawer now groups its rows into two labeled sections — **👤 Players** (tokens whose `controller_user_id` is set, i.e., character tokens belonging to a player) and **⚙ GM / NPCs** (tokens with no controller) — with a small count next to each header. No schema change; the split is a pure presentation rearrangement of the existing token tracker.

### Changed
- `app/routes/tabletop_routes.py`:
  - `place_character_token` — removed the "GM OR character owner" branch; the route now returns 403 unless the requester is the campaign GM.
  - `remove_character_token` — same tightening; player-driven removal is gone.
- `app/static/tabletop.js`:
  - `canPlaceChar(charId)` simplified to `return !!ME.isGm;`. Player drawers no longer render the add/remove token buttons.
  - `renderTokenTracker` now splits its `tokens` array on `controller_user_id` and renders two `<div class="tt-section-header">` blocks (👤 Players, ⚙ GM / NPCs) with per-section counts. Per-row build logic was extracted into an inner `_renderToken(t)` helper to avoid duplication.
- `app/version.py`, `README.md`, `CHANGELOG.md` — MINOR bump to 0.63.0. No schema change.

### Removed
- Player ability to add or remove their own character's token from the map. Players who want a token on the board ask the GM, who places it from the Token Management panel.

## [0.62.0] - 2026-05-12

**Schema version:** 34

**Commit summary:** Move Token Management to the Battle drawer with a GM-only tag and a collapsible body

**Description:** The token panel that used to live in the GM Tools drawer (titled "Tokens") moves into the Battle drawer where the GM actually uses it during combat — next to the initiative list and battle controls. It's renamed **Token Management**, is gated by `{% if is_gm %}` (the Battle drawer itself is visible to every player so the new block needs its own gate), wears a small gold "GM only" pill on the summary line so the GM can tell at a glance what the players DON'T see, and is wrapped in a `<details>` element that collapses with a chevron animation. The `+ Add Token` button moved out of the summary row into the body so clicking it doesn't also toggle the collapsed state. The old GM Tools "Tokens" section is left as a `{# moved … #}` comment for context. No backend changes — `add-token-btn` and `token-tracker-list` are still queried by id, so the existing `tabletop.js` token-add and tracker-render code paths work unchanged.

### Changed
- `app/templates/tabletop.html`:
  - Removed the **Tokens** sub-section from the GM Tools drawer (lines that previously rendered the `<h4>Tokens</h4>` block + `+ Add Token` button + `#token-tracker-list`).
  - Added a new `<details id="token-management-panel" open>` block inside the Battle drawer's body, gated `{% if is_gm %}`. Summary line carries the chevron + "Token Management" heading + a "GM only" pill. Body has the `+ Add Token` button and the existing `#token-tracker-list`.
  - Added CSS rules for `#token-management-panel summary::-webkit-details-marker { display: none; }` (Webkit), `summary::marker { content: ''; }` (Firefox), and chevron rotation on `[open]`.
- `app/version.py`, `README.md`, `CHANGELOG.md` — MINOR bump to 0.62.0. No schema change.

### Coming next
- The combat encounter system the GM asked for (load tokens + map + initiative as a single preset) — design + phasing landed as a planning doc at `docs/encounters-plan.md`.

## [0.61.0] - 2026-05-12

**Schema version:** 34

**Commit summary:** Add Previous / Play-Pause / Skip transport buttons to the GM Tools music panel with synced server state

**Description:** GMs can now jump back, jump forward, and pause/resume audio directly from the GM Tools music panel — three new buttons sit between the "Now playing" label and the progress bar. Skip and Previous land like a manual track change (current track finalized as `skipped` in the play log; new track starts with `source=manual`). Pause is fully synchronized: clicking ⏸ Pause records the seek offset server-side so every connected client pauses at the same position; clicking ▶ Play resumes by adjusting `now_playing_started_at` so the existing client-side time-sync math puts everyone back on the same frame. WS-reconnects mid-pause re-sync the new client to the paused state (the existing reconnect sync payload now carries `paused` and `paused_offset_s` fields). The Pause / Play button glyph flips automatically based on server-authoritative state — no client-only optimism.

### Added
- New `Campaign.now_playing_paused_offset_s` column (FLOAT, nullable). When non-null, audio is paused at this many seconds into the current track.
- Inline migration `Schema v34` in `app/database.py` adds the column.
- Two new helpers in `app/routes/audio_routes.py`:
  - `_pause_audio_for_campaign(db, campaign)` — records the seek offset (`now - started_at`) and broadcasts `audio_pause`. Does NOT finalize the in-flight `AudioPlayEvent` (pause is mid-listen, not a play termination).
  - `_resume_audio_for_campaign(db, campaign)` — sets `started_at = now - offset`, clears the pause field, re-broadcasts `audio_play` with the adjusted timestamp.
  - `_find_sibling_track(db, current, direction, *, loop)` — generalized prev/next lookup used by `next_in_playlist`, `/audio/skip`, and `/audio/previous`. `next_in_playlist` was refactored to use it (the inline sibling search is gone).
- Four new endpoints under `/campaign/{id}/audio/`:
  - `POST /skip` (GM-only) — advances to the next track; `prev_reason="skipped"`, `source="manual"`. Stops if at end of playlist with loop off.
  - `POST /previous` (GM-only) — jumps to the previous track; same labels. No-op at track 1 with loop off.
  - `POST /pause` (GM-only) — broadcasts `audio_pause`.
  - `POST /resume` (GM-only) — broadcasts a fresh `audio_play` with adjusted `started_at`.
- New WS message type `audio_pause` (data: `{paused_offset_s: float}`). Clients pause their `<audio>` element and freeze the progress bar; the drift-correction loop now skips iterations while paused.
- Three new fields on the `audio_play` payload: `paused: bool`, `paused_offset_s: float | null`. The WS-reconnect sync uses the same payload, so a player who joins during a pause lands at the right position in the right state.
- Six new client-side globals in `app/static/audio.js`: `vttSkipTrack`, `vttPreviousTrack`, `vttPauseAudio`, `vttResumeAudio`, `vttTogglePause` (calls pause or resume based on current state), plus `vttAudioIsPaused()` / `vttAudioHasTrack()` getters for UI to query the source of truth.
- Three new buttons in the GM Tools music panel (`tabletop.html`): `⏮ Prev`, a state-aware `⏸ Pause` / `▶ Play` toggle, and `Skip ⏭`. The toggle's glyph + label re-render on every relevant WS message via a tracked-state block in the GM-sync IIFE.

### Changed
- `_now_playing_payload` now includes `paused` and `paused_offset_s` so reconnecting clients sync to the correct play/pause state, not just the right track.
- `_start_track_for_campaign` clears `now_playing_paused_offset_s` (starting a new track always exits pause mode).
- `_stop_audio_for_campaign` clears `now_playing_paused_offset_s` (stop exits pause mode).
- `audio.js` `audio_play` handler: a "same track, different timing" check distinguishes resume (no `<audio>.src` reload) from fresh play (full reset). Idempotency check now also compares `paused` state.
- `audio.js` time-sync drift-correction loop bails out while paused so we don't override the GM's pause.
- GM Tools now-playing sync block in `tabletop.html` tracks `{_gmCurTrackId, _gmCurTrackName, _gmCurPaused}` as module-level state and routes all updates through `_renderGmAudio()`, so label + row highlight + transport-button glyph stay in lockstep across `audio_play`, `audio_pause`, and `audio_stop`.

### Schema
- New `campaigns.now_playing_paused_offset_s` (FLOAT, nullable).
- `SCHEMA_VERSION` bumped from 33 to 34.

## [0.60.0] - 2026-05-12

**Schema version:** 33

**Commit summary:** Record an AudioPlayEvent log per track and surface a history panel in campaign settings

**Description:** Every audio play now lands a row in a new `audio_play_events` table — recorded by the shared audio helpers in `audio_routes.py`, so manual GM clicks, session-start auto-plays, playlist auto-advances, and loops all feed the log uniformly. Each row tracks `track_id` / `playlist_id` (FKs, `ON DELETE SET NULL` so the history survives deletions) plus snapshot `track_name` / `playlist_name` strings (so the row remains readable after renames or removals), `started_at` / `ended_at` / `duration_s`, an `ended_reason` (`completed` / `skipped` / `stopped` / `session_end` / `ongoing`), a `source` (`manual` / `auto_start` / `auto_next` / `loop`), and the `triggered_by_user_id`. The campaign settings page gets a new collapsed "📊 Audio history" details panel with three sub-sections — a one-line summary (total play count + total listening time), a Top Tracks table (top 10 by play count with totals), and a Recent Plays table (last 50, newest first, with timestamp / duration / ended-reason / source). Closed when nothing has been played; auto-populates as soon as the first track lands. No client-side changes required for the recording — the existing `audio_play` WS broadcasts continue to work identically, just with audit rows landing alongside.

### Added
- New `AudioPlayEvent` model in `app/models.py` with full field docs (FKs, snapshot names, lifecycle columns, controlled-vocabulary `ended_reason` and `source`).
- Inline migration `Schema v33` in `app/database.py` creates the table via `AudioPlayEvent.__table__.create(bind=engine, checkfirst=True)` so existing deployments pick it up on next boot.
- Two new helpers in `app/routes/audio_routes.py`:
  - `_finalize_play_event(db, campaign_id, reason)` — closes any in-flight row with the given reason, computing `duration_s`. Idempotent.
  - `_open_play_event(db, campaign_id, track, source, user_id)` — inserts a new ongoing row with snapshot names.
- Both `_start_track_for_campaign` and `_stop_audio_for_campaign` now accept `source` / `prev_reason` / `reason` / `user_id` kwargs and call the new helpers automatically. `play_track`, `next_in_playlist`, `session/start` auto-play, and `session/end` were updated to pass the right labels for each call site.
- `next_in_playlist` was refactored to call the shared `_start_track_for_campaign` / `_stop_audio_for_campaign` helpers instead of mutating campaign state inline. Distinguishes `auto_next` (advancing) from `loop` (same single track replaying).
- New "📊 Audio history" `<details>` panel at the bottom of the Audio section in `campaign_settings.html` — Top Tracks table (grouped by snapshot `track_name`, top 10 by play count) + Recent Plays table (last 50 by `started_at desc`) + a summary line. Capped row counts keep the page render fast even on long-running campaigns.

### Schema
- New table `audio_play_events`: id, campaign_id (FK → campaigns, indexed), track_id (FK → playlist_tracks, nullable+SET NULL, indexed), playlist_id (FK → playlists, nullable+SET NULL), track_name (str, snapshot), playlist_name (str, snapshot), started_at (datetime, indexed), ended_at (datetime, nullable), duration_s (int, nullable), ended_reason (str, default 'ongoing'), source (str, default 'manual'), triggered_by_user_id (FK → users, nullable+SET NULL).
- `SCHEMA_VERSION` bumped from 32 to 33.

## [0.59.0] - 2026-05-12

**Schema version:** 32

**Commit summary:** Add audio playback progress bar to the player Settings drawer and GM Tools music panel

**Description:** The audio UI now shows a live progress bar with elapsed time, total duration, and a filling track that advances in real time as the current track plays. Two bars render in parallel — one under the "🎵 Sound" section of the player Settings drawer (visible to everyone) and one under the "Music" section of the GM Tools drawer (visible to GMs while picking the next track). Both update on the same `<audio>.timeupdate` event (~250 ms cadence), so playback drift correction and metadata loading naturally feed the UI. The bar appears once track metadata loads (when `<audio>.duration` becomes known) and hides on `audio_stop`. Click-to-seek is intentionally not included in this PR — the bar is read-only.

### Added
- `.audio-progress` markup in `app/templates/tabletop.html` — one instance below `#audio-now-playing` in the Settings drawer, one below `#gm-now-playing-label` in the GM Tools music panel. Each shows `0:00` elapsed / `0:00` total + a 4px filling bar. Hidden by default; revealed on `loadedmetadata`.
- `_setProgress(elapsed, total)`, `_showProgress(visible)`, `_fmtTime(seconds)`, and `_progressEls()` helpers in `app/static/audio.js`. `_progressEls` is re-queried on each call so lazy-rendered panels still pick up the bar without an explicit re-bind.
- `<audio>.timeupdate` event listener drives the bar; same listener handles both bars in a single update pass. The existing `loadedmetadata` listener now also paints the initial values + reveals the bar.

### Changed
- `audio_play` WS handler resets the bar to `0:00 / 0:00` while metadata loads (before `loadedmetadata` populates real values).
- `audio_stop` WS handler hides the bar and resets the display.

## [0.58.1] - 2026-05-12

**Schema version:** 32

**Commit summary:** Auto-sync audio to newly-connected WebSocket clients so players hear the live position on reconnect

**Description:** When a player's WebSocket connects to a campaign that has audio playing — whether on first page load or after a network blip / tab sleep / browser refresh — the server now privately sends them the current `audio_play` payload so their `<audio>` element seeks to the same offset everyone else is hearing. Previously, the only audio sync on connect came from the HTML page render, which meant WS reconnects (which keep the page alive but drop the socket) would leave the player silent until the GM manually replayed or hit the existing Resync button. The new sync is targeted to the just-connected socket only — broadcasting would interrupt every other client for no reason. A client-side idempotency guard in `audio.js` ensures that on a *fresh* page load (where the page render already initialized audio and the new WS sync arrives moments later with identical data) the second handler call short-circuits and doesn't re-load the `<audio>` element.

### Added
- `app/routes/tabletop_routes.py` — the `/ws/campaign/{campaign_id}` WebSocket endpoint now reads `campaign.now_playing_track_id` during the auth phase, builds the `audio_play` payload via the existing `_now_playing_payload` helper, and sends it privately to the new socket after `hub.connect()` accepts it. Errors during the send are caught + logged.
- `app/static/audio.js` — `handleMessage` short-circuits when the incoming `audio_play` has the same `track_id`, `started_at_ms`, and `file_url` as the current state. Prevents an unnecessary `<audio>.src` reload glitch on first connect (because the page already initialized audio from the HTML data attribute moments earlier).

### Behaviour change
- After a network blip or browser refresh while audio is playing, the client now silently re-syncs to the live position without the player needing to click anything.

## [0.58.0] - 2026-05-12

**Schema version:** 32

**Commit summary:** Auto-play a configured playlist on session start and auto-stop audio on session end

**Description:** GMs can configure a campaign so that clicking **Start session** automatically begins playing a chosen playlist for everyone, and clicking **End session** stops audio for everyone. The Campaign Settings → "🎵 Audio on session start" fieldset has two new fields: an "Auto-play playlist" dropdown (lists every playlist on the campaign, plus a "— None (don't auto-play) —" option) and a "Play mode" selector with **In order** (start at track 1) and **Shuffle** (pick a random track each session) modes. Auto-start re-fires every session — shuffle re-shuffles each time. Auto-stop runs the same path as the manual "⏹ Stop playback" button, so any audio that was playing — whether started via auto-play or manually mid-session — is cleanly stopped when the session ends. Both behaviours tolerate errors (missing playlist, deleted track, no tracks) silently so a misconfigured auto-play never blocks a session from starting.

### Added
- Two new columns on `campaigns`:
  - `auto_play_playlist_id` (nullable FK to `playlists.id`, `ON DELETE SET NULL`).
  - `auto_play_mode` (string, default `"order"`, accepts `"order"` / `"shuffle"`).
- Inline migration block `Schema v32` in `app/database.py` adds both columns to existing deployments on next boot.
- Two reusable helpers in `app/routes/audio_routes.py`:
  - `_start_track_for_campaign(db, campaign, track)` — sets `now_playing_*` and broadcasts `audio_play`. The manual `/audio/play` endpoint now calls through this.
  - `_stop_audio_for_campaign(db, campaign)` — clears `now_playing_*` and broadcasts `audio_stop`. Idempotent.
- New "🎵 Audio on session start" fieldset on `campaign_settings.html` with playlist + mode pickers.
- Two new optional fields on `POST /campaign/{id}/settings`: `auto_play_playlist_id`, `auto_play_mode`. Playlist ID is validated to belong to this campaign before assignment.

### Changed
- `POST /campaign/{id}/session/start` now reads `campaign.auto_play_playlist_id` and, if set, picks a track based on `auto_play_mode` ("order" → first track; "shuffle" → `random.choice` over the playlist's tracks) and calls `_start_track_for_campaign`. Errors during auto-play are caught and logged so a broken config doesn't block session start.
- `POST /campaign/{id}/session/end` now calls `_stop_audio_for_campaign` after the session ends if anything is currently playing.

### Schema
- New `campaigns.auto_play_playlist_id` (INTEGER, nullable, FK → playlists.id ON DELETE SET NULL).
- New `campaigns.auto_play_mode` (VARCHAR(10), NOT NULL, DEFAULT `'order'`).
- `SCHEMA_VERSION` bumped from 31 to 32.

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
