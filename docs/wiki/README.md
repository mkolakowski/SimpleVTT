# SimpleVTT wiki

In-repo documentation hub for SimpleVTT — how-to guides, system explainers, design plans, and visual references for contributors and operators. Versioned alongside the code so every guide carries the version it was written for.

Guides land at `docs/wiki/<slug>.{md,html}`. Plans live at `docs/plans/<slug>.md`. References live at `docs/<slug>.md`. The top-level repo docs (`CHANGELOG.md`, `CLAUDE.md`, `TODO.md`, `CREDITS.md`, `README.md`) stay at the repo root but are surfaced through the wiki nav. Every wiki page carries the same nav strip via `app/templates/_wiki_nav.html` (Jinja includes) or via the server-side injector in `app/routes/wiki_routes.py::_inject_wiki_nav` (standalone HTML guides).

## Available guides

| Guide | Format | Audience | Status |
|-------|--------|----------|--------|
| [Roll-log guide](roll-log-guide.html) | HTML (visual) | GMs + contributors | ✅ shipped (v2.43.1) |
| [Toast notifications guide](toast-notifications-guide.html) | HTML (visual) | GMs + contributors | ✅ shipped (v2.43.8) |
| [Realtime broadcasts catalog](realtime-broadcasts-catalog.md) | Markdown (reference) | Contributors | ✅ shipped (v2.43.14) |
| [Endpoint catalog](endpoint-catalog.md) | Markdown (reference) | Contributors | ✅ shipped (v2.43.15) |
| [Architecture overview](architecture-overview.md) | Markdown (system map) | Contributors | ✅ shipped (v2.43.16) |
| [First-run setup](first-run-setup.md) | Markdown (how-to) | Operators | ✅ shipped (v2.43.17) |
| [Running a session as GM](running-a-session-as-gm.md) | Markdown (how-to) | GMs | ✅ shipped (v2.43.18) |
| [The character sheet](the-character-sheet.md) | Markdown (how-to) | Players + GMs | ✅ shipped (v2.43.19) |
| [Demo mode](demo-mode.md) | Markdown (how-to) | Operators | ✅ shipped (v2.43.21) |
| [PC vs NPC combat systems](pc-vs-npc-systems.md) | Markdown (reference) | Contributors | ✅ shipped (v2.49.167) |
| [Reactions automation](reactions.md) | Markdown (how-to) | GMs + players | ✅ shipped (v2.82.0) |
| [Targeting system guide](targeting-system-guide.html) | HTML (visual) | GMs + contributors | ✅ shipped (v2.49.168) |
| [Battle & Characters tab sheets](battle-character-sheets-guide.html) | HTML (visual) | Players + GMs + contributors | ✅ shipped (v2.49.182) |
| [Unified mini-sheet mockups](unified-mini-sheet-mockups.html) | HTML (visual) | Contributors (design review) | ⚪ 3 mockups · companion to design plan (v2.49.186) |
| [Consume-without-refund audit](consume-without-refund-audit.md) | Markdown (reference) | Contributors | ✅ shipped (v2.97.8) |
| [Visual regression harness](visual-regression-harness.md) | Markdown (reference) | Contributors | ✅ shipped · local-only (v2.97.13) |
| [Testing checklist](testing-checklist.md) | Markdown (per-version log) | Contributors | ✅ shipped (v2.99.8) |

## Design plans

Per-subsystem design docs + implementation roadmaps. Working docs that explain "why was this built this way" and "what's still deferred." Served through the wiki at `/wiki/doc/plan-<slug>`.

| Plan | Format | Audience | Status |
|------|--------|----------|--------|
| [Advantage & disadvantage](../plans/advantage-disadvantage.md) | Markdown (design) | Contributors | 🟠 Phases 1 + 2a–2f shipped (v2.2.0–v2.157.0); Phase 3 blocked on Maps 2.0 |
| [Class / subclass / feat / race content](../plans/class-content-status.md) | Markdown (inventory) | Contributors | 🟢 / 🟠 / ⚪ living inventory |
| [Full class-feature automation](../plans/full-feature-automation.md) | Markdown (design) | Contributors | 🟠 Phases 0–7 shipped; Phase 8 in progress (v2.158.x) |
| [On-hit damage riders (automation Phase 2)](../plans/on-hit-riders.md) | Markdown (design) | Contributors | ✅ shipped |
| [Feature saving throws (automation Phase 3)](../plans/feature-saves.md) | Markdown (design) | Contributors | ✅ shipped |
| [Temp HP + roll bonuses (automation Phase 4)](../plans/temp-hp-and-bonuses.md) | Markdown (design) | Contributors | ✅ shipped |
| [Auras (automation Phase 5)](../plans/auras.md) | Markdown (design) | Contributors | ✅ shipped |
| [Forced movement, speed & summons (automation Phase 6)](../plans/movement-and-summons.md) | Markdown (design) | Contributors | ✅ shipped (v2.99.431–.446) |
| [Death saving throws](../plans/death-saves.md) | Markdown (design) | Contributors | 🟠 Phases 1 + 3a + 3b shipped (v2.150.0–v2.151.0); 3c + 4 deferred |
| [Demo mode](../plans/demo-mode.md) | Markdown (design) | Contributors | ✅ shipped (v2.3.0) |
| [Encounter-sim test suite](../plans/encounter-sim-test-suite.md) | Markdown (design) | Contributors | ⚪ plan finalized · Phase 1 PoC pending |
| [Movement-OA flow](../plans/movement-oa-flow.md) | Markdown (design) | Contributors | ✅ All phases (1–6) shipped (v2.99.52–v2.99.57) |
| [Player simulacrum](../plans/player-simulacrum.md) | Markdown (design) | Contributors | ⚪ design only · all phases unstarted |
| [Reactions automation](../plans/reactions-automation.md) | Markdown (design) | Contributors | 🟠 Phases 1–6 shipped (v2.67.0–v2.78.0); v3 auto-resolution backlog filed |
| [Ruler & range enforcement](../plans/ruler-and-range.md) | Markdown (design) | Contributors | ✅ All phases shipped (1, 2, 3A–E) |
| [Spell up-casting](../plans/spell-upcasting.md) | Markdown (design) | Contributors | 🟠 Mechanisms shipped (A+B+C, v2.108.0–v2.110.0); + higher_level prose parser (v2.125.0) auto-covers the tail; 34/319 hand-annotated |
| [Spell-validation test suite](../plans/spell-validation-suite.md) | Markdown (design) | Contributors | ⚪ proposed · Phase 0–5 unstarted |
| [Sorcery Points + Metamagic](../plans/sorcery-points-and-metamagic.md) | Markdown (design) | Contributors | 🟢 Font of Magic + 7/8 metamagics + Sorcerous Restoration shipped (v2.49.120–v2.99.x); Quickened + AoE Empowered remain |
| [Warlock Pact Boon](../plans/warlock-pact-boon.md) | Markdown (design) | Contributors | ✅ all three boons shipped (Tome v2.99.200 / Blade v2.99.212 / Chain v2.99.213) |
| [Wild Magic (Sorcerer subclass)](../plans/wild-magic.md) | Markdown (design) | Contributors | ✅ All 5 phases shipped (v2.99.227–231) |
| [Eldritch Knight (Fighter subclass)](../plans/eldritch-knight.md) | Markdown (design) | Contributors | 🟠 Phase 1 + Arcane Charge P1 + Improved War Magic P1 shipped (v2.158.11–.12); War Magic + Eldritch Strike remain |
| [Battle Master (Fighter subclass)](../plans/battle-master.md) | Markdown (design) | Contributors | ✅ 16/16 maneuvers shipped (v2.99.252–.266); Know Your Enemy + Relentless blocked on Lv 18+ fixture |
| [Paladin oaths (non-Devotion)](../plans/paladin-oaths.md) | Markdown (design) | Contributors | 🟢 Lv 15/20 capstones all ✅ (v2.99.283–.292); outstanding: Conquest Lv 3/7 + Redemption Lv 3 + Glory Lv 3 + Vengeance Phase 2 |
| [Magic-item automation](../plans/magic-items-automation.md) | Markdown (design) | Contributors | ✅ framework shipped Phases 1–8 (v2.158.74–v2.159.25); Phase 9 content tail (~250 items) is P2 |
| [Exhaustion levels](../plans/exhaustion-levels.md) | Markdown (design) | Contributors | ✅ Phases 0–4 shipped (v2.159.17–.22) · 32 tests · framework complete |
| [Carrying capacity](../plans/carrying-capacity.md) | Markdown (design) | Contributors | ✅ Phases 0-3 shipped (v2.159.26–.30) · 38 tests · Bag of Holding live |
| [Legendary actions + lair actions](../plans/legendary-actions.md) | Markdown (design) | Contributors | 🟠 Phases 1a + 1b + 1c shipped (v2.159.33–2.162.0) — cost backfill + budget gate + /use_legendary_action endpoint + turn-start refresh + GM init-tracker spend buttons + Adult Red Dragon demo template + server-side save-AoE damage dispatch + UI target-pick wiring; Phase 1c attack-roll dispatch + chat card + Phases 2–3 pending |
| [Autonomous click-through test harness](../plans/test-harness.md) | Markdown (design) | Contributors | ✅ Phases 1–5 shipped (212 tests) |
| [Unified mini-sheet](../plans/unified-mini-sheet.md) | Markdown (design) | Contributors | ⚪ proposed · 3 mockups · Phase 1–3 unstarted |
| [Wiki expansion](../plans/wiki-expansion.md) | Markdown (TODO companion) | Contributors | 🟠 living roadmap |
| [Combat encounters](../encounters-plan.md) | Markdown (proposed) | Contributors | ⚪ proposed · not started |
| [Multi-system refactor](../multi-system-refactor.md) | Markdown (proposed) | Contributors | ⚪ proposed · not started |

## References

Reference docs at `docs/` that aren't operator/GM guides but are useful to contributors. Served at `/wiki/doc/<slug>`.

| Reference | Format | Audience | Status |
|-----------|--------|----------|--------|
| [Roll-log card layout](../roll-log-card-layout.md) | Markdown (semantic ref) | Contributors | ✅ shipped |
| [Test harness coverage catalog](../test-harness-coverage.md) | Markdown (index) | Contributors | ✅ shipped · living |
| [Automation coverage audit](../automation-coverage.md) | Markdown (index) | Contributors | ✅ shipped · living |
| [Demo image-generation prompts](../demo/image-prompts.md) | Markdown (asset notes) | Contributors | ✅ shipped |

## Repo documentation

Canonical top-level documents at the repo root. Mirrored through the wiki so they're reachable from the same nav as everything else. Served at `/wiki/doc/<slug>`.

| Doc | Format | Audience | Status |
|-----|--------|----------|--------|
| [README](../../README.md) | Markdown (install + deploy) | Operators | ✅ shipped |
| [CHANGELOG](../../CHANGELOG.md) | Markdown (release history) | All | ✅ shipped · living |
| [CHANGELOG (pre-2.0 archive)](../../CHANGELOG_v1.md) | Markdown (release history) | All | ✅ archived |
| [CLAUDE — contributor + agent guidelines](../../CLAUDE.md) | Markdown (contributing) | Contributors | ✅ shipped · living |
| [CREDITS & attribution](../../CREDITS.md) | Markdown (license) | All | ✅ shipped |
| [TODO — planned features backlog](../../TODO.md) | Markdown (backlog) | Contributors | ✅ shipped · living |
| [TODONE — completed to-do archive](../../TODONE.md) | Markdown (archive) | Contributors | ✅ shipped · living |

## TODO — guides to write

This wiki is a stub. The list below is what we want it to grow into.

### How-to guides (operator + GM-facing)

- [x] **First-run setup.** Stand up a fresh `docker compose up`, register the first user, create a campaign, invite players, and run a first session. Where the seed data goes; how to disable demo mode; how to reset the database. → [first-run-setup.md](first-run-setup.md).
- [ ] **Inviting players.** The two membership flows (open registration vs invite-only), GM colors, per-player portrait, the demo-user accounts.
- [x] **Running a session as GM.** Initiative tracker, action-economy chips, target picker, the GM Tools drawer, encounter snapshots. → [running-a-session-as-gm.md](running-a-session-as-gm.md).
- [ ] **Building an encounter.** Encounters panel CRUD, token templates, monsters from the SRD bestiary vs homebrew, spawn-point layout, default-encounter wiring on a campaign.
- [ ] **Maps + grids + tokens.** Uploading maps, scaling, grid overlay (`show_grid`), placing PC and monster tokens, the token-tracker side panel.
- [ ] **Homebrew content authoring.** Custom monsters (template editor), custom items, custom spells, the homebrew JSON contract.
- [ ] **Player onboarding.** What players see vs. what the GM sees, the character sheet, the roll log, the dice toast, the per-character action economy chips.
- [ ] **Backups + restore.** The `simplevtt-backup` container, daily `pg_dump` cycle, restoring from a backup, exporting / importing a campaign.
- [ ] **Theming.** The 8 built-in themes (Dark / Midnight / Dim / Light / Forest / Bubblegum / OLED / Fire), the per-user theme preference, font preferences, accessibility considerations (contrast, motion).

### System explainers (contributor-facing)

- [x] **Architecture overview.** FastAPI + SQLAlchemy + Jinja2 + HTMX + vanilla JS + Postgres. Where the realtime hub lives (`app/realtime.py`). The per-campaign WebSocket fan-out model. Why no SPA framework. → [architecture-overview.md](architecture-overview.md).
- [ ] **The action-economy system.** The four chips (Act / Bns / Rxn / Mov), the over-budget gate, strict-action-economy mode, the `_mark_battle_economy` helper, Phase 4a layered dimming, the audit badge. See also `docs/plans/action-economy.md`.
- [ ] **The targeting system (Phase T.0–T.9).** Double-tap targeting, the target-picker modal, the targeting state machine (`window._targetingState`), localStorage cross-tab sync, the mobile 🎯 button. See also `docs/plans/targeting.md`.
- [ ] **The buff slot system (Phase C).** `_install_buff` / `_remove_buff` / `_get_buffs`, concentration anchors, paired-buff cleanup on concentration drop, save-or-suck condition install, the buff descriptive layer on the sheet.
- [ ] **The damage flow (Phase B).** Resistance, vulnerability, Hunter's Mark, Colossus Slayer, Smite uplifts, the `_attack_damage_log` for Undo, the `/undo_attack_damage` endpoint.
- [ ] **Auto-resolution: attack, save, heal, damage.** When the server resolves rolls server-side vs prompts the client; the campaign-level `auto_apply_damage` toggle; `auto_attack_*` / `auto_save_*` / `auto_heal_*` payload fields; the spell-cast pill row.
- [x] **The roll log + dice toast.** Card variants, the oversized pill row, persistence in localStorage, visibility filtering, the dice toast lifecycle. → [roll-log-guide.html](roll-log-guide.html) + [toast-notifications-guide.html](toast-notifications-guide.html).
- [ ] **The click-through test harness.** Why the harness exists, how `conftest.py` wires the demo PCs to authenticated httpx clients, the `WSCollector` contract, when to add a happy-path vs error-path test. See also `docs/plans/test-harness.md`.
- [ ] **SRD + local content resolution.** `app/data/local/dnd5e/` JSON files, the `local_content.resolve(slug, type=…)` lookup, how spells / items / monsters are enriched.
- [ ] **Schema migrations.** The inline `_apply_inline_migrations()` model in `app/database.py`, `SCHEMA_VERSION` bumps, how to write a forward-only migration step.
- [x] **Realtime broadcasts.** The full broadcast catalog (battle_update, roll, weapon_attack, spell_cast, feature_used, resource_update, presence_update, character_death_save, heal_applied, …), payload shapes, visibility filtering, client handler map. → [realtime-broadcasts-catalog.md](realtime-broadcasts-catalog.md).

### Reference cards

- [ ] **Card variant reference** — quick visual index of every roll-log card type. (Roll-log guide HTML is the first entry of this category.)
- [ ] **Theme palette reference** — side-by-side strip showing all 8 themes' tokens (--bg, --bg-2, --fg, --accent, --danger, --c-heal, --c-crit, --c-damage, --c-buff).
- [x] **Endpoint catalog** — every `/api/campaign/{cid}/…` endpoint with method, payload shape, broadcast(s) emitted. → [endpoint-catalog.md](endpoint-catalog.md).

## Contributing guides

A guide entry lives at `docs/wiki/<slug>.{md,html}` and gets a row in the "Available guides" table above. Each guide should:

- Open with a one-sentence summary of what it covers + audience.
- State the version it was written for (so future readers can date the screenshots / examples).
- Include code-location pointers for anything in the codebase the reader might want to grep.
- For HTML mocks: be self-contained (inline CSS, no external assets) so it can be opened with `file://` and not break. The server injects the v2.49.9 wiki nav after `<body>` at request time — don't bake it into the file.

When you add a guide, a plan, or a reference doc: update this README's table, the matching table in `app/templates/wiki.html`, and (for plans / refs / repo docs) the allowlist in `app/routes/wiki_routes.py::_DOC_ALLOWLIST` so the new doc is reachable through the wiki nav.
