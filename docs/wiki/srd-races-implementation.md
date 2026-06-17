# SRD Race Rules — Implementation Guide

How SimpleVTT implements the 9 SRD 5.1 races (CC BY 4.0). For each race, this guide lists every RAW trait, what fires automatically vs. what you click vs. what's GM-narrated, and the underlying mechanism (endpoint, helper, or sheet seed) so you know what to expect at the table.

Verified against the codebase at **v2.399.2** (2026-06-17 audit). Status legend:

| Symbol | Meaning |
|---|---|
| ✅ | Engine derives or enforces the rule — happens automatically when the trigger fires. |
| 🟢 | Recognition only — `/sheet-json` exposes a `derived.*` block; the underlying substrate (movement-through-creatures, Stealth-cover) isn't enforced server-side yet, so the trait is vacuously satisfied. |
| 🟠 | Passive seed — applied via a sheet field (`damage_resistances`, `skill_proficiencies`, `darkvision_ft`, etc.); the universal proficiency / resistance math reads through. No dedicated engine helper, none needed. |
| ⚪ | Genuinely unwired (rare — flagged where it appears). |
| OOS | Out-of-scope by design. Documented in [`docs/plans/race-features.md`](/wiki/doc/plan-race-features). |
| N/A | Flavor only (Languages, Age, Alignment, Size descriptors). |

**Headline:** all 9 races are at **~100% mechanical coverage** as of v2.399.2. Every RAW trait that has an engine analog is wired or recognized; the two intentional deferrals (Dwarven Toughness per-level HP hook, Tiefling Darkness 1/day racial cast) and two recognition-only Halfling traits are documented below.

---

## TL;DR — what fires when

If you're a GM running a session and just want to know what to expect at the table:

| You'll see this fire automatically | You click this | GM-narrated |
|---|---|---|
| **Halfling Lucky** rerolls — d20=1 on any attack / save / ability check, the kept d20 is rerolled and a 🍀 chat-card explains why | **Dragonborn Breath Weapon** — action button → fire/cone/line picker | High Elf Trance (long-rest flavor) |
| **Half-Orc Relentless Endurance** — incoming damage that would set you to 0 HP clamps to 1 instead; resource counter decrements 1/long rest | **Hill Dwarf Stonecunning** — `/check_stonecunning` endpoint rolls a History check at 2× PB | Rock Gnome Tinker (no crafting system) |
| **Half-Orc Savage Attacks** — crit with a melee weapon adds an extra weapon die to damage | **Rock Gnome Artificer's Lore** — `/check_artificers_lore` endpoint rolls a History check at 2× PB | Dragonborn cosmetic-only traits |
| **Fey Ancestry** (Half-Elf / Elf) — saves vs. Charmed roll at advantage; sleep spells skip the PC entirely | **Tiefling Hellish Rebuke (racial)** — `damage_taken` reaction prompt offers the 1/long-rest free-cast option alongside the slot path | Halfling Naturally Stealthy (Stealth-cover substrate filed) |
| **Dwarven Resilience** — saves vs. Poisoned roll at advantage; poison damage halved | | Halfling Nimbleness (move-through-creatures substrate filed) |
| **Gnome Cunning** — INT/WIS/CHA saves vs. spells roll at advantage | | Dwarven Toughness per-level HP (character-builder filed) |
| **Hellish Resistance** — fire damage halved on Tieflings | | |
| **Heavy-armor speed bypass** — Hill Dwarves wearing plate/splint at low STR don't lose 10 ft | | |
| **Dragonborn Damage Resistance** — ancestor-typed damage halved | | |

---

## Dragonborn

Pick a draconic ancestry at character creation (Black / Blue / Brass / Bronze / Copper / Gold / Green / Red / Silver / White). Set `_dragonborn_ancestor` on the sheet to the lowercase name; this picks your breath weapon's damage type, shape, and save ability.

| Trait | Status | How it works |
|---|---|---|
| Draconic Ancestry | ✅ | Sheet field `_dragonborn_ancestor` selects from the 10-ancestry table at `_DRAGONBORN_BREATH_PARAMS`. The Breath Weapon endpoint reads this; an unknown ancestor returns 409 `unknown_ancestry`. |
| Breath Weapon | ✅ | `POST /api/campaign/{cid}/use_breath_weapon` — action consumes the `breath-weapon` resource (1/short rest). Per-target DEX or CON save (depends on ancestry); DC = 8 + CON mod + PB. Damage scales 2d6 → 3d6 (Lv 6) → 4d6 (Lv 11) → 5d6 (Lv 16). Save-for-half via the v2.99.405 feature-save resolver. Pre-fill targets via `/battle/line-targets` (chromatic) or `/battle/cone-targets`. |
| Damage Resistance | ✅ | Ancestor-derived via `_dragonborn_ancestry_resistance()` + `damage_resistances` seed. Read by `_resistance_halve` on the damage pipeline. |
| ASI (+2 STR / +1 CHA) | ✅ | Applied at character creation by the ability engine. |
| Speed 30, Medium, Languages | N/A | Sheet seeds / flavor. |

**Demo PC:** Magnus Hexbinder (Warlock, Bronze Dragonborn). Try clicking his "Breath Weapon" action button mid-combat.

---

## Half-Elf

| Trait | Status | How it works |
|---|---|---|
| ASI (+2 CHA + 2 of choice) | ✅ | Ability engine + character builder. |
| Darkvision (60 ft) | 🟠 | `darkvision_ft: 60` sheet seed. No engine consumer today — gameplay effect lives in the Maps 2.0 lighting/vision work (filed). |
| Fey Ancestry (charm + sleep) | ✅ | `_RACE_SAVE_ADVANTAGES["half-elf"]` adds `2d20kh1` to saves vs. the Charmed condition. Sleep spells (e.g. PHB *Sleep*) skip Half-Elf targets entirely via `_unaffected_by_sleep_spell`. |
| Skill Versatility (2 skill profs) | 🟠 | `skill_proficiencies` sheet seed picked at character creation. The universal ability-check math reads through. |
| Extra Language | N/A | `languages` seed. |

**Demo PC:** Sir Caelan Lightbringer is Variant Human, not Half-Elf — but Lyra Sunstrider (Half-Elf Bard) carries the Fey Ancestry on her sheet.

---

## Half-Orc

| Trait | Status | How it works |
|---|---|---|
| ASI (+2 STR / +1 CON) | ✅ | Ability engine. |
| Darkvision (60 ft) | 🟠 | Sheet seed; Maps 2.0 territory. |
| Menacing (Intimidation prof) | 🟠 | Sheet seed; check math reads through. |
| Relentless Endurance | ✅ | When damage would set a Half-Orc PC to 0 HP, `_apply_hp_change` clamps to 1 HP instead and decrements the `relentless-endurance` resource (1/long rest). Fires a 💪 chat-card + `resource_update` broadcast. Doesn't fire if the PC would be killed outright by massive damage. |
| Savage Attacks | ✅ | On a critical hit with a melee weapon attack, `_compute_attack_auto_uplifts` adds an extra weapon-die roll to the damage breakdown with `source="savage-attacks"`. Shipped v2.99.23. |

**Demo PC:** Krieger Stonefist (Half-Orc Barbarian, Greataxe 1d12+4). Watch the roll log for the extra die-roll on his crits.

---

## High Elf

| Trait | Status | How it works |
|---|---|---|
| ASI (+2 DEX / +1 INT) | ✅ | Ability engine. |
| Darkvision (60 ft) | 🟠 | Sheet seed; Maps 2.0 territory. |
| Keen Senses (Perception prof) | 🟠 | Sheet seed; check math reads through. |
| Fey Ancestry (charm + sleep) | ✅ | `_RACE_SAVE_ADVANTAGES["elf"]` — shared parent slug applies to all Elf subraces (High, Wood, Dark). Same mechanism as Half-Elf. |
| Trance | OOS | RAW = pure narrative ("4-hour meditation vs. 8-hour sleep") — no mechanical effect server-side. Filed as Phase 7 long-rest UI polish in the [race-features plan](/wiki/doc/plan-race-features). |
| Elf Weapon Training (4 weapons) | 🟠 | `weapon_proficiencies` sheet seed; attack math reads through. |
| Cantrip (1 Wizard cantrip) | 🟠 | Picked at character creation; lands in `sheet.spells` and casts via the normal `/cast_spell` route. Structurally a creation-time choice, not an engine concern. |
| Extra Language | N/A | Seed. |

---

## Hill Dwarf

The single most-mechanically-rich race in the SRD — three engine-shaped traits land on Tavik out of the box.

| Trait | Status | How it works |
|---|---|---|
| ASI (+2 CON / +1 WIS) | ✅ | Ability engine. |
| Darkvision (60 ft) | 🟠 | Sheet seed; Maps 2.0 territory. |
| Dwarven Resilience (poison save adv + poison resistance) | ✅ | `_RACE_SAVE_ADVANTAGES["dwarf"]` adds `2d20kh1` to saves vs. the Poisoned condition AND vs. poison-damage spells (the damage-type half via OR semantics). `damage_resistances: ["poison"]` seed halves poison damage on `_resistance_halve`. |
| Dwarven Combat Training (4 weapons) | 🟠 | `weapon_proficiencies` sheet seed; attack math reads through. |
| Tool Proficiency (artisan's tools) | 🟠 | `tool_proficiencies` sheet seed. |
| Stonecunning | ✅ | `POST /api/campaign/{cid}/check_stonecunning` — rolls `1d20 + INT mod + 2 × PB` (RAW: grants proficiency even if you're not History-proficient). Optional `note` field echoes back the stonework topic. Broadcasts a 🪨 chat-card with `source="stonecunning"`. |
| Speed Not Reduced by Heavy Armor | ✅ | `_pc_heavy_armor_speed_penalty(sheet)` returns 0 for Dwarves regardless of STR; non-Dwarves wearing equipped chain mail / splint / plate at STR below the requirement lose 10 ft (the underlying RAW PHB p.144 penalty installed in the same commit). `_speed_walk_from_sheet` subtracts the penalty; `/sheet-json` surfaces `derived.heavy_armor_speed_penalty: {penalty_ft, source}` when it fires. |
| Dwarven Toughness (+1 HP / level) | 🟠 + ⚠️ | Baked into the demo seed's `hp.max` as a flat number ("+1 × 8 levels" for Lv 8 Tavik). **No engine helper** — a Dwarf PC created via the character builder won't auto-gain +1 HP on level-up. Filed for the character-builder revamp arc. |

**Demo PC:** Brother Tavik Stonebrow (Hill Dwarf Cleric Lv 8, chain mail equipped, INT 10, PB +3). His Stonecunning check is `1d20 + 0 + 6` (so 7–26). Try the endpoint with `note="origin of these temple walls"` to see the chat-card text.

---

## Human

| Trait | Status | How it works |
|---|---|---|
| ASI +1 to all six abilities | ✅ | Ability engine. |
| Extra Language | N/A | Seed. |

Standard Human is the simplest — six ability bumps applied at character creation. SimpleVTT also supports Variant Human (+1 to two abilities + 1 skill + 1 feat at character creation) via the same engine + the v2.99.24 feat-grant pathway.

---

## Lightfoot Halfling

| Trait | Status | How it works |
|---|---|---|
| ASI (+2 DEX / +1 CHA) | ✅ | Ability engine. |
| Lucky (reroll d20 nat 1 — attack, check, save) | ✅ | Fires at three surfaces: `/attack` (`_maybe_halfling_lucky_attack_reroll`), `/roll` save/check (`_pc_has_halfling_lucky` + reroll on kept d20 = 1). On reroll, the new value replaces the original and a 🍀 chat-card explains the trigger. |
| Brave (frightened save adv) | ✅ | `_RACE_SAVE_ADVANTAGES["halfling"]` adds `2d20kh1` to saves vs. the Frightened condition. |
| Halfling Nimbleness (move through larger creature) | 🟢 | Recognition flag `derived.halfling_nimbleness` on `/sheet-json` (v2.399.0). Underlying RAW PHB p.190 "moving through other creatures" substrate doesn't exist server-side — `/token/move` doesn't gate creature-crossing today, so the Halfling exemption is vacuously satisfied. Phase 4b (full enforcement) filed for the Maps 2.0 arc. |
| Naturally Stealthy (hide behind larger creature) | 🟢 | Recognition flag `derived.naturally_stealthy` on `/sheet-json` (v2.399.0). Underlying Stealth-cover gate (PHB p.177) doesn't exist — `/roll` with `stat_key="Stealth"` always rolls without LOS / cover checks. Phase 5b filed. |
| Speed 25, Small, Languages | N/A | Flavor + seed. |

**Demo PC:** Pip Quickfingers (Lightfoot Halfling Rogue). Roll a 1 on her attack or save and watch the reroll fire.

---

## Rock Gnome

| Trait | Status | How it works |
|---|---|---|
| ASI (+2 INT / +1 CON) | ✅ | Ability engine. |
| Darkvision (60 ft) | 🟠 | Sheet seed; Maps 2.0 territory. |
| Gnome Cunning (INT/WIS/CHA save adv vs. magic) | ✅ | `_RACE_SAVE_ADVANTAGES["gnome"]` with `is_spell_save: True` — fires on INT/WIS/CHA saves caused by *spells* (not poison, not breath weapon, etc.). Adds `2d20kh1` to the save expression. |
| Artificer's Lore | ✅ | `POST /api/campaign/{cid}/check_artificers_lore` — twin of Stonecunning. Rolls `1d20 + INT mod + 2 × PB` for History checks on magic items / alchemical objects / technological devices. Optional `note` field echoes the topic. Broadcasts 🔧 chat-card with `source="artificers-lore"`. |
| Tinker | OOS | RAW = craft a Tiny clockwork device (1 hr + 10 gp + AC 5 / 1 HP / 24-hr fade / 3-active cap). Needs a crafting substrate that doesn't exist in v2.x (would touch inventory, gold tracking, the timed-device state machine). Permanently GM-narrated by design. |

**Demo PC:** None ships as a Rock Gnome today. To exercise `/check_artificers_lore`, PATCH any PC's race to "Rock Gnome" for the test scope (see `tests/harness/test_check_artificers_lore.py` for the pattern).

---

## Tiefling

| Trait | Status | How it works |
|---|---|---|
| ASI (+2 CHA / +1 INT) | ✅ | Ability engine. |
| Darkvision (60 ft) | 🟠 | Sheet seed; Maps 2.0 territory. |
| Hellish Resistance (fire damage) | ✅ | `damage_resistances: ["fire"]` sheet seed; `_resistance_halve` halves all incoming fire damage on Tiefling targets. |
| Infernal Legacy — Thaumaturgy cantrip (at-will) | 🟠 | Seeded into the Tiefling PC's spell list at character creation with `_racial_granted: True`. Casts via the normal `/cast_spell` cantrip path (no slot consumed). Future Tiefling PCs need the cantrip added manually until the auto-grant projection (Phase 1c) ships. |
| Infernal Legacy — Hellish Rebuke 1/long (Lv 3+, L2) | ✅ | `_pc_has_tiefling_hellish_rebuke_racial` gate + `cast-hellish-rebuke-racial` reaction option offered alongside the existing slot-based path. Consumes the `hellish-rebuke` resource (not a spell slot). Broadcasts `feature_used(source=hellish-rebuke-racial, reaction_kind=race-feature, damage_expr=3d10)` + a `resource_update`. Once the resource hits 0 the racial option disappears; the slot-based cast remains while slots last. |
| Infernal Legacy — Darkness 1/long (Lv 5+) | 🟠 + filed | The `darkness-racial` resource is seeded on Zara's sheet, but `/cast_spell` doesn't yet branch on it — casting Darkness today consumes a spell slot regardless. Same gap shape as pre-v2.395.0 Hellish Rebuke; filed as **Phase 1b** in the race-features plan. |

**Demo PC:** Zara Emberfire (Tiefling Sorcerer Lv 5). When she takes damage in combat, the reaction prompt offers her racial Hellish Rebuke (1/long, L2) — pick that to keep her L1 Sorcerer slots untouched.

---

## Out-of-scope by design

The [race-features plan](/wiki/doc/plan-race-features) explicitly carves these out:

- **Rock Gnome Tinker** — needs an inventory + gold + 24-hr clockwork-creature substrate that v2.x doesn't have.
- **Elf Trance** — RAW = pure narrative; long-rest UI polish filed as Phase 7.
- **Darkvision (every Darkvision race)** — already seeded as `darkvision_ft: 60`; the gameplay effect (seeing in dim light) lives in the Maps 2.0 lighting/vision arc.
- **Dwarven Toughness per-level hook** — currently correct on the demo seed; a character-builder PC won't auto-gain the +1 HP on level-up until the character-builder revamp arc lands.

## Filed follow-ups (substrate-dependent)

These traits are recognized but their full RAW enforcement waits on substrates that haven't been built:

- **Halfling Nimbleness (Phase 4b)** — install the RAW PHB p.190 "moving through other creatures" gate at `/token/move`; Halfling exemption already gated in `_pc_has_halfling_nimbleness`. Composes with Maps 2.0.
- **Halfling Naturally Stealthy (Phase 5b)** — install the RAW PHB p.177 Stealth-cover gate at `/roll`; Lightfoot exemption already gated in `_pc_has_naturally_stealthy`.
- **Tiefling Darkness 1/long racial (Phase 1b)** — route `/cast_spell` through the `darkness-racial` resource for Tieflings Lv 5+ before falling back to slot consumption. Mirror of the v2.395.0 Hellish Rebuke ship.
- **Tiefling Infernal Legacy auto-grant (Phase 1c)** — derive Thaumaturgy / Hellish Rebuke / Darkness onto `/sheet-json` for any Tiefling PC based on level, so future character-builder Tieflings don't need manual seed wiring.

## What to read next

- [Race features plan](/wiki/doc/plan-race-features) — the design doc tracking the v2.392.0–v2.399.0 race-features arc plus filed follow-ups.
- [Reactions automation guide](/wiki/reactions) — covers the `cast-hellish-rebuke-racial` option among many others.
- [Targeting system guide](/wiki/targeting-system-guide) — the Breath Weapon endpoint takes pre-resolved target IDs; this guide explains how to compute them.
- [Test harness coverage](/wiki/doc/test-harness-coverage) — per-test catalog including all race-trait harness files.
