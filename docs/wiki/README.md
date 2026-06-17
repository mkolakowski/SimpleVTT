# SimpleVTT wiki

In-repo documentation hub for SimpleVTT — how-to guides, system explainers, design plans, and visual references for contributors and operators. Versioned alongside the code so every guide carries the version it was written for.

Guides land at `docs/wiki/<slug>.{md,html}`. Plans live at `docs/plans/<slug>.md`. References live at `docs/<slug>.md`. The top-level repo docs (`CHANGELOG.md`, `CLAUDE.md`, `TODO.md`, `CREDITS.md`, `README.md`) stay at the repo root but are surfaced through the wiki nav. Every wiki page carries the same nav strip via `app/templates/_wiki_nav.html` (Jinja includes) or via the server-side injector in `app/routes/wiki_routes.py::_inject_wiki_nav` (standalone HTML guides).

## SRD 5e automation coverage

How much of the SRD 5.1 ruleset SimpleVTT mechanically automates, by content category, as of **v2.404.10**. "Automated" means the engine derives or enforces the rule (saves, damage, passive item effects, class features, conditions) rather than leaving it to GM narration. Recomputed each audit pass; see [TODO](../../TODO.md) for the breakdown and gaps.

| Category | Count | Automated |
|----------|-------|-----------|
| Races | 9 | ✅ ~100% |
| Monsters | 322 | ✅ ~100% |
| Conditions | 15 | ~92% |
| Class features | 222 rows | ✅ 100% |
| Spells | 319 | ~83% |
| Magic items | 239 / 239 wired | ✅ 100% |

**Overall ~97%.** **Magic items joins Monsters + Class features + Races as a strictly-✅ surface** after the v2.403.0–v2.404.0 magic-items closure arc — Phase 9.2 wired charge tracking for 22 Bucket D items + both Bucket A holdouts (wind-fan with cumulative-20% tear-on-overuse, medallion-of-thoughts) through the new `_use_item_action_announce_only` + dedicated handlers, and v2.404.0 Phase 9.3 closed the 4 umbrella catalog slugs (potion-of-healing real heal handler with tier picker for 4 SRD tiers, spell-scroll real cast handler reading `_spell_slug`, weapon-1-2-or-3 + wand-of-the-war-mage-1-2-or-3 passive stubs). **Spells moved ~79% → ~83%** via the v2.404.1–v2.404.10 [spell utility-upcast arc](../plans/spell-utility-upcast.md): nine target-scaling utility spells (Invisibility, Fly, Enhance Ability, Longstrider, Charm Person, Bane, Command, Animal Friendship, Blindness/Deafness) now ride the v2.380.0 / v2.381.0 cap-extension substrate across both `_SPELL_BUFF_MAP` and `_SPELL_TARGET_CAPS`. Prior arcs that already shipped: the v2.392.0–v2.399.2 [race-features arc](srd-races-implementation.md) (Dragonborn Breath Weapon, Tiefling racial Hellish Rebuke, Hill Dwarf Stonecunning + heavy-armor speed bypass, Rock Gnome Artificer's Lore, plus recognition flags for Halfling Nimbleness + Naturally Stealthy); magic-item content tail (v2.316–v2.344); class-feature strictly-✅ 100% (Aura of Courage shipped v2.368.0, Unarmored Defense / Deflect Missiles / Cleansing Touch v2.369.0–v2.370.1); AoE auto-targeting arc (sphere/cone/line picker + cast_spell parity v2.373.0–v2.376.0); lair-action arc end-to-end (metallic + Lich + Kraken backfill + condition map + regional effects v2.377.0–v2.382.0); and the entire condition-enforcement audit (Sneak Attack ally-skip + 3 PC-action incapacitated gates + Grappled-ends-on-grappler-incap + Charmed-can't-target-charmer across /attack + /cast_spell, v2.385.0–v2.391.0). The remaining ~3% is dominated by **content-layer utility-spell mechanical depth** (duration-scaling, AoE-radius scaling, summon-level scaling — filed in TODO as a v2.5x arc) + the permanently-GM-narrated condition clauses (Charmed clause 2 social-check, Grappled clause 3 out-of-reach movement, Deafened hearing-checks — substrates that don't exist by design). Known defects are tracked in [BUGS](../../BUGS.md).

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
| [Lair actions & regional effects catalog](lair-regional-catalog.md) | Markdown (reference) | GMs + contributors | ✅ shipped · refreshed v2.382.0 (metallic + Lich/Kraken regional effects backfill; the entire lair-action arc is now closed) |
| [SRD race rules — implementation guide](srd-races-implementation.md) | Markdown (reference + how-to) | GMs + players + contributors | ✅ shipped (v2.400.0) — per-race trait coverage after the v2.392.0–v2.399.2 race-features arc |
| [SRD conditions — implementation guide](srd-conditions.md) | Markdown (reference + how-to) | GMs + players + contributors | ✅ shipped (v2.402.0) — per-condition clause coverage after the v2.385.0–v2.401.0 enforcement + UI-surfacing arc |

## Design plans

Per-subsystem design docs + implementation roadmaps. Working docs that explain "why was this built this way" and "what's still deferred." Served through the wiki at `/wiki/doc/plan-<slug>`.

| Plan | Format | Audience | Status |
|------|--------|----------|--------|
| [Advantage & disadvantage](../plans/advantage-disadvantage.md) | Markdown (design) | Contributors | 🟠 Phases 1 + 2a–2f shipped (v2.2.0–v2.157.0); Phase 3 blocked on Maps 2.0; Phase 4a (Cloak of Displacement) shipped v2.252.0; Phase 4b (Cloak of Elvenkind) shipped v2.253.0 |
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
| [Spell utility-upcast arc](../plans/spell-utility-upcast.md) | Markdown (closure retrospective) | Contributors | ✅ shipped (v2.404.1 → v2.404.9, 2026-06-17) · 9 target-scaling utility spells closed across `_SPELL_BUFF_MAP` + `_SPELL_TARGET_CAPS` |
| [Spell-validation test suite](../plans/spell-validation-suite.md) | Markdown (design) | Contributors | 🟠 partial · Phase 1 smoke + 2A damage landed |
| [Sorcery Points + Metamagic](../plans/sorcery-points-and-metamagic.md) | Markdown (design) | Contributors | 🟢 Font of Magic + 7/8 metamagics + Sorcerous Restoration shipped (v2.49.120–v2.99.x); Quickened + AoE Empowered remain |
| [Warlock Pact Boon](../plans/warlock-pact-boon.md) | Markdown (design) | Contributors | ✅ all three boons shipped (Tome v2.99.200 / Blade v2.99.212 / Chain v2.99.213) |
| [Wild Magic (Sorcerer subclass)](../plans/wild-magic.md) | Markdown (design) | Contributors | ✅ All 5 phases shipped (v2.99.227–231) |
| [Eldritch Knight (Fighter subclass)](../plans/eldritch-knight.md) | Markdown (design) | Contributors | 🟠 Phase 1 + Arcane Charge P1 + Improved War Magic P1 shipped (v2.158.11–.12); War Magic + Eldritch Strike remain |
| [Battle Master (Fighter subclass)](../plans/battle-master.md) | Markdown (design) | Contributors | ✅ 16/16 maneuvers shipped (v2.99.252–.266); Know Your Enemy + Relentless blocked on Lv 18+ fixture |
| [Paladin oaths (non-Devotion)](../plans/paladin-oaths.md) | Markdown (design) | Contributors | 🟢 Lv 15/20 capstones all ✅ (v2.99.283–.292); outstanding: Conquest Lv 3/7 + Redemption Lv 3 + Glory Lv 3 + Vengeance Phase 2 |
| [Magic-item automation](../plans/magic-items-automation.md) | Markdown (design) | Contributors | ✅ framework + Phases 1–9.1 shipped (v2.158.74–v2.367.0); 🟠 Phase 9.2 charge tracking for the announce-only Bucket D tail in flight (v2.403.0+) |
| [Exhaustion levels](../plans/exhaustion-levels.md) | Markdown (design) | Contributors | ✅ Phases 0–4 shipped (v2.159.17–.22) · 32 tests · framework complete |
| [Carrying capacity](../plans/carrying-capacity.md) | Markdown (design) | Contributors | ✅ Phases 0-3 shipped (v2.159.26–.30) · 38 tests · Bag of Holding live |
| [Legendary actions + lair actions](../plans/legendary-actions.md) | Markdown (design) | Contributors | ✅ Phases 1a + 1b + 1c + 2 shipped (v2.159.33–2.167.0) — cost backfill + budget gate + /use_legendary_action endpoint + turn-start refresh + GM init-tracker spend buttons + Adult Red Dragon demo template + server-side save-AoE damage dispatch + UI target-pick wiring + result chat card + reference-attack (Tail Attack) dispatch + legendary-resistance pool & /spend_legendary_resistance + failed-save auto-prompt (defer-then-spend/decline via /decline_legendary_resistance) + GM 🛡️ resistance badge & floating Spend/Decline prompt banner (v2.167.0 Phase 2 UI) + lair-action data layer (v2.168.0 Phase 3a — app/content/lair_actions.py leaf module, Red Dragon volcanic lair, folded into the monster projection, 13 unit tests) + lair-action engine (v2.169.0 Phase 3b — /set_in_lair toggle + /trigger_lair_action save-AoE/condition dispatch reusing the legendary save path, in_lair_changed & lair_action_resolved broadcasts, 10 harness tests) + GM lair-action UI (v2.170.0 Phase 3c — floating #_lair_action_panel with Enter/Exit toggle + per-action Trigger buttons, in_lair_changed/lair_action_resolved WS handlers, 4 Playwright tests) + chromatic lair backfill (v2.171.0 — Black/Blue/Green/White dragons added to LAIR_ACTIONS_BY_SLUG, 3 new condition templates, 6 unit + 1 trigger test; metallic + Lich/Kraken filed) + no-repeat guard (v2.172.0 — RAW MM p.11 same-action-two-rounds-in-a-row rejection via last_lair_action_id + 409 lair_action_repeated + GM panel "Used last round" disable, 4 harness + 1 Playwright test) + once-per-round counter (v2.173.0 — RAW MM p.11 one-lair-action-per-round rejection via lair_acted_round vs state.round + 409 lair_already_acted_this_round + GM panel "Acted this round" disable & banner, 6 harness tests) + initiative-20 auto-surfacing (v2.174.0 — RAW MM p.11 init-count-20 prompt: _renderLairActionPanel derives "init 20 reached" from the live turn order, shows a bright banner + border glow + one-shot per-round toast when the lair should act, "not yet reached" hint before; front-end only, 1 Playwright test) + initiative-20 server broadcast (v2.175.0 — RAW MM p.11: promotes the init-20 prompt to a server-authoritative lair_init_20_reached WS event from PUT /battle when the turn order enters the init-20 zone, deduped per round via a lair_init20_broadcast_round marker on the battle state; the client toast now rides the broadcast, 7 harness tests) + initiative-20 player visibility (v2.176.0 — the lair_init_20_reached handler gains a non-GM branch: players get a "🌋 The lair stirs…" flavor toast, no GM-only mechanics, while the GM keeps the mechanical nudge; front-end only, 2 Playwright tests) + lair-action roll-log card (v2.177.0 — lair_action_resolved now renders a persistent 🌋 roll-log card for the whole table (owner + action + save line + per-target ✅/❌/⏳ pills, modeled on the v2.163.0 legendary AoE card), with an additive owner_name broadcast field so it's self-contained on reload; 1 HTTP + 1 Playwright test) + regional effects (v2.178.0 — RAW MM p.11 passive zone-wide regional effects for all five chromatic dragons via the app/content/regional_effects.py leaf module, folded into the monster projection as regional_effects; flavor-only descriptive entries, 13 unit tests) + regional-effects GM panel (v2.179.0 — the floating #_lair_action_panel now lists the lair's passive regional effects under a "🌐 Regional Effects" heading, rendered independent of the in-lair toggle since they radiate while the creature dwells in its lair; front-end only, 1 Playwright test) + player-facing regional flavor (v2.180.0 — players get their own read-only #_regional_effects_panel showing the same passive effects in a blue palette, with the GM controls + creature name omitted so it reads as atmosphere not a monster reveal; front-end only, 1 Playwright test) + regional-effect fade tracker (v2.181.0 — RAW MM p.11: when the lair-dweller dies its regional effects "fade over the course of 1d10 days"; new GM-only POST /set_regional_fade with a start/advance/clear action discriminator seeds a regional_fade {days_total, days_remaining, faded} countdown on the battle state, ticks it down a day at a time, flips faded at zero, broadcasts regional_fade_changed, carried forward by the /battle PUT guard; a real mechanical day-countdown not flavor-only, 8 harness tests); Phases 1 + 2 + 3 complete — the lair-action arc is closed |
| [Ability-score override engine](../plans/str-override.md) | Markdown (design) | Contributors | 🟠 Phase 1 shipped (v2.212.0) — `effective_ability_score` substrate + STR saves/checks/carry-capacity + Belt of Giant Strength (Hill, STR 21); Amulet of Health + Potion of Giant Strength + weapon attack/damage (Phase 1b) filed |
| [Charged magic items](../plans/charged-items.md) | Markdown (design) | Contributors | ⚪ proposed — backlog of SRD charged-item drop-ins on the existing charge/recharge substrate (Phases 1–5) |
| [Permanent ability-increase reconciliation](../plans/permanent-ability-increase-reconciliation.md) | Markdown (design) | Contributors | ✅ shipped — converged both Manuals & Tomes dispatch paths onto permanent_boost (Phases 0-3, v2.311.0-v2.314.0); all six books read via /use_item_action, max-HP-correct |
| [Race features (close the SRD races gap)](../plans/race-features.md) | Markdown (design) | Contributors | 🟢 partial (v2.399.0) — Phases 1+2+3+4a+5a+6 shipped (Tiefling racial Hellish Rebuke + Hill Dwarf Stonecunning + heavy-armor speed bypass + Halfling Nimbleness + Naturally Stealthy recognition flags + Rock Gnome Artificer's Lore); plus pre-existing Savage Attacks (v2.99.23, reconciled v2.394.0). Phases 4b/5b (full Halfling-trait enforcement) filed for the future movement / Stealth-cover substrate arcs. |
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
| [Condition enforcement audit](../condition-enforcement-audit.md) | Markdown (audit) | Contributors | ✅ shipped (v2.384.0) · Charmed / Grappled / Incapacitated per-clause review |
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
| [BUGS — known-defect tracker](../../BUGS.md) | Markdown (tracker) | Contributors | ✅ shipped · living |

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
