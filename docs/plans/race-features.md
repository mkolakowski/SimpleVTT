# Race features — close the SRD races gap to 100%

> **Status:** ⚪ proposed (v2.393.0 plan landing). Drives the **Races ~90% → 100%** axis of the [SRD audit](../../TODO.md#srd-5e-audit-v23900-refresh).

## Why this plan exists

The Races row in the SRD audit table has hovered at **~90%** across every refresh since v2.99.x. The audit summary says "8 wired through `_RACE_SAVE_ADVANTAGES` + damage resistance + sleep immunity + Relentless Endurance + Halfling Lucky." That's the celebratory framing — but the actual per-trait audit shows **~12 RAW race traits still unwired** plus **~15 wired only as inert sheet seeds** (skill / weapon / tool proficiencies, languages, darkvision flag). The most recent v2.392.0 ship (Dragonborn Breath Weapon) was the highest-leverage single race ship; this plan picks up from there and drives the remaining tail to closed.

## Per-race state (post-v2.392.0)

Cells: ✅ wired in engine code · 🟠 inert sheet seed (no engine read) · ⚪ unwired (GM-narrated) · N/A flavor only.

| Race | Trait | State | Where wired (or `—` for unwired) |
|---|---|---|---|
| **Dragonborn** | Draconic Ancestry selector | ✅ | `_dragonborn_ancestor` sheet field; read by `/use_breath_weapon` |
| | Breath Weapon | ✅ | `/use_breath_weapon` (v2.392.0) — `_DRAGONBORN_BREATH_PARAMS` + save-AoE dispatch |
| | Damage Resistance | ✅ | `_dragonborn_ancestry_resistance` + `damage_resistances` seed |
| **Half-Elf** | Fey Ancestry (charm + sleep) | ✅ | `_RACE_SAVE_ADVANTAGES["half-elf"]` + `_unaffected_by_sleep_spell` |
| | Darkvision 60 ft | 🟠 | `darkvision_ft` seed; no engine check |
| | Skill Versatility | 🟠 | `skill_proficiencies` seed |
| | Extra Language | N/A | Flavor |
| **Half-Orc** | Relentless Endurance | ✅ | `_pc_has_relentless_endurance_available` + `_apply_hp_change` clamp |
| | Darkvision 60 ft | 🟠 | `darkvision_ft` seed |
| | Menacing (Intimidation prof) | 🟠 | `skill_proficiencies` seed |
| | **Savage Attacks** | ⚪ | — |
| **High Elf** | Fey Ancestry (charm + sleep) | ✅ | `_RACE_SAVE_ADVANTAGES["elf"]` + sleep immunity |
| | Darkvision 60 ft | 🟠 | seed |
| | Keen Senses (Perception) | 🟠 | skill seed |
| | Elf Weapon Training | 🟠 | weapon proficiency seed |
| | High-Elf Cantrip | 🟠 | spell-list seed (manually picked at character build) |
| | **Trance** | ⚪ | — (RAW: 4-hr meditation vs 8-hr long rest; flavor-only by design) |
| **Hill Dwarf** | Dwarven Resilience (poison) | ✅ | `_RACE_SAVE_ADVANTAGES["dwarf"]` + `damage_resistances` seed |
| | Darkvision 60 ft | 🟠 | seed |
| | Dwarven Combat Training | 🟠 | weapon proficiency seed |
| | Tool Proficiency | 🟠 | tool proficiency seed |
| | **Stonecunning** | ⚪ | — (RAW: double PB on History checks about stonework) |
| | **Speed not reduced by heavy armor** | ⚪ | — (speed engine doesn't factor armor weight either way today) |
| | **Dwarven Toughness** | 🟠 | currently baked into the `hp.max` seed at character build; no per-level-up hook |
| **Human** | ASI +1 all | ✅ | Native to ability engine |
| **Lightfoot Halfling** | Halfling Lucky | ✅ | `_pc_has_halfling_lucky` + 3 surfaces (save/attack/check) |
| | Brave (frightened save adv) | ✅ | `_RACE_SAVE_ADVANTAGES["halfling"]` |
| | **Halfling Nimbleness** | ⚪ | — (RAW: move through space of any creature size > yours) |
| | **Naturally Stealthy** | ⚪ | — (RAW: hide while obscured by creature ≥1 size larger) |
| **Rock Gnome** | Gnome Cunning (INT/WIS/CHA vs magic) | ✅ | `_RACE_SAVE_ADVANTAGES["gnome"]` (`is_spell_save: True`) |
| | Darkvision 60 ft | 🟠 | seed |
| | **Artificer's Lore** | ⚪ | — (RAW: double PB on History checks about magic items / alchemical / tech) |
| | **Tinker** | ⚪ | — (RAW: craft tiny clockwork; no crafting substrate exists — **out-of-scope by design**) |
| **Tiefling** | Hellish Resistance (fire) | ✅ | `damage_resistances: ["fire"]` seed |
| | Darkvision 60 ft | 🟠 | seed |
| | **Infernal Legacy spells** | 🟠 | Thaumaturgy / Hellish Rebuke / Darkness manually seeded into the sheet's spell list; no auto-grant gate, no level-based reveal |
| | **Stout Halfling Stout Resilience** | ✅ | `_RACE_SAVE_ADVANTAGES["halfling-stout"]` (subrace) |

**Counts:** 16 ✅ · 11 🟠 · 8 ⚪ · 3 N/A.

## Scope decision: which traits to ship vs leave

This plan ships the **8 unwired** traits — every ⚪ above — except where RAW is intentionally narrative or substrate-blocked. After ship the Races coverage row goes from ~90% → essentially 100% for engine-shaped RAW.

| Trait | Phase | Ship? | Why |
|---|---|---|---|
| Half-Orc Savage Attacks | 1 | ✅ | Composes on the existing `_double_dice_for_crit` substrate at PC weapon-attack sites |
| Tiefling Infernal Legacy auto-grant | 2 | ✅ | Level-gated spell list + per-day resource seeding; mirrors v2.99.200 Pact-of-the-Tome wiring |
| Hill Dwarf Stonecunning | 3 | ✅ | Skill-check double-PB; small endpoint or roll-route flag |
| Hill Dwarf Speed-not-reduced-by-heavy-armor | 4 | ✅ | Composes on the existing speed/armor-weight gate (the gate doesn't fire today, so this lands as the gate's first consumer) |
| Halfling Nimbleness | 5 | ✅ | Move-through-larger-creature gate at `/token/move`; reuses combatant-size data |
| Halfling Naturally Stealthy | 6 | ✅ | Stealth-check size-cover gate (skill-check side, doesn't need vision LOS) |
| Rock Gnome Artificer's Lore | 7 | ✅ | Same shape as Stonecunning (Phase 3) — double PB on History; topic = "magic items / alchemical / tech" |
| Elf Trance | 8 | 🟢 (flavor) | Long-rest UI nudge only; no mechanical effect server-side per RAW |
| Rock Gnome Tinker | — | ❌ | **Out-of-scope** — needs a crafting substrate that doesn't exist (1-hour craft, GP cost, clockwork-creature catalog). Permanently GM-narrated by design. |
| 🟠 → ✅ promotions (Skill Versatility, Keen Senses, Elf Weapon Training, etc.) | — | ❌ | These are already correctly seeded onto the sheet; the proficiency math reads through. No engine work owed. Test coverage may be filed under the harness-coverage doc when convenient but not required by this plan. |

After Phase 7 the engine-shaped tail is closed. Phase 8 is the optional Trance polish (flavor toast on long rest). Tinker stays out-of-scope.

## Implementation patterns to copy

Every phase reuses an existing substrate; no new architectural primitive is needed.

- **Savage Attacks** — extend `_double_dice_for_crit(expr, *, savage_attacks: bool = False)` to append one extra die-group when the flag is true. Thread through the **player-side** weapon-attack crit sites only (NPC attacks don't get this — RAW Half-Orc trait is PC-only). Reference call sites: `tabletop_routes.py:27245`, `73559`, `90642`, `92205`, `92564`. Gate via `race_slug == "half-orc"` derived from the sheet through `_race_slug_from_sheet`.
- **Infernal Legacy** — model: v2.99.200 Pact of the Tome (Warlock). Add `_pc_infernal_legacy_spells(sheet)` returning the level-gated catalog (Thaumaturgy always · Hellish Rebuke @ Lv 3+ · Darkness @ Lv 5+). Merge into the cast-spell whitelist + auto-seed `_resources` entries for Hellish Rebuke + Darkness (both 1/day, reset on long rest). The seed runs once per `/sheet-json` projection so adding a new Tiefling PC just works without manual character-builder steps.
- **Stonecunning** — RAW: when making a History check related to the origin of stonework, the Dwarf adds 2× proficiency bonus instead of 1×. Implementation: small additive `topic` param on the History check roll (or a dedicated `/check_stonecunning` endpoint), gated via `race_slug in {"dwarf", "hill-dwarf"}`. Pattern: `_RACE_SAVE_ADVANTAGES`-shaped derivation, but on the check-roll side.
- **Speed-not-reduced-by-heavy-armor** — small predicate that suppresses the (currently no-op) heavy-armor speed reduction. The substrate doesn't fire today, so this lands as the substrate's installation + Dwarf bypass in one shot. RAW PHB p.20 STR threshold check: heavy armor "Str < Str_min" reduces speed by 10. Dwarves are exempt regardless of STR.
- **Halfling Nimbleness** — gate at `/token/move` (or the equivalent move-validation site): allow move-through when target combatant's size > mover's size. Sizes already live on each combatant (`size: "Medium" | "Large" | …`). Pattern: small predicate composed onto the existing OA-friendly-pass-through gate.
- **Naturally Stealthy** — gate on Stealth checks: allow the "hide" intent when the Halfling is obscured by a combatant ≥1 size larger. The check-rolling side already reads roll-state; this adds a `cover_combatant_id` optional param that the stealth flow consumes.
- **Artificer's Lore** — twin of Stonecunning (Phase 3). Same double-PB History-check pattern, gated via `race_slug == "gnome"` (any subrace). Topic distinguishes magic items / alchemical / tech.
- **Trance** — long-rest UI nudge: the long-rest summary card adds a "(trance — 4 hours)" line for Elves. No state-machine change; flavor only.

## Per-phase shipping plan

Each phase = one MINOR commit + 1 happy-path test + 1 error-path test (race mismatch / resource exhausted / state check). The full plan lands across 7 commits (Phases 1–7) plus optional Phase 8 flavor.

1. **Phase 1 — Half-Orc Savage Attacks** (MINOR). Extend `_double_dice_for_crit` with `extra_die` flag; thread through PC weapon-attack crit sites; gate via Half-Orc race slug. Tests: Krieger-as-Half-Orc weapon crit emits the extra die; non-Half-Orc baseline unchanged. (Krieger is currently Fighter; ship as a separate Half-Orc demo PC OR upgrade an existing demo to validate the gate. Re-using an existing seed avoids new fixture sprawl.)
2. **Phase 2 — Tiefling Infernal Legacy auto-grant** (MINOR). `_pc_infernal_legacy_spells` + level-gated catalog + `_resources` seed for Hellish Rebuke (Lv 3+) + Darkness (Lv 5+). Caelan (existing demo Tiefling Warlock per `_tiefling_*` sheet seeds) gets all three on `/sheet-json` projection.
3. **Phase 3 — Hill Dwarf Stonecunning** (MINOR). History-check double-PB with `topic` parameter. Tavik (existing Hill Dwarf demo) is the test fixture.
4. **Phase 4 — Hill Dwarf Speed-not-reduced-by-heavy-armor** (MINOR). Install heavy-armor STR-threshold speed gate; carve out Dwarf bypass. Test: Tavik in plate at STR 14 keeps base 25; non-Dwarf at STR 14 in plate loses 10.
5. **Phase 5 — Halfling Nimbleness** (MINOR). Move-through-larger gate at `/token/move`. Pip (existing Lightfoot Halfling Rogue) is the fixture.
6. **Phase 6 — Halfling Naturally Stealthy** (MINOR). Stealth-check size-cover gate. Pip is the fixture; cover combatant = an Orc or larger creature.
7. **Phase 7 — Rock Gnome Artificer's Lore** (MINOR). Twin of Phase 3 with topic = magic items / alchemical / tech. Existing Rock Gnome demo (Mira) is the fixture.
8. **Phase 8 — Elf Trance (flavor)** (PATCH). Long-rest UI card flavor for Elves. Optional polish ship.

## Out-of-scope by design

- **Rock Gnome Tinker** — needs a crafting system that doesn't exist (1-hr craft, 10 gp materials, 24-hr clockwork-creature persistence, three-active cap). Permanently GM-narrated.
- **Darkvision 60 ft (every Darkvision race)** — already correctly seeded as `darkvision_ft: 60` on every applicable PC; the actual gameplay consequence (seeing in dim light) is a vision/lighting concern that lives in Maps 2.0 (currently a backlogged plan). No engine work owed by this plan.
- **Keen Senses (Perception) / Skill Versatility / Menacing / Tool / Weapon proficiencies** — already correctly seeded as `skill_proficiencies` / `weapon_proficiencies` / `tool_proficiencies` on the sheet; the math reads through every check site. No engine work owed.
- **Languages / Age / Alignment** — pure flavor; no mechanical effect server-side.
- **Dwarven Toughness on level-up** — currently correctly baked into the demo seed's `hp.max`. A per-level-up hook would require a level-up workflow that currently lives on the character-builder side (out of session scope). Filed for the character-builder revamp.

## Test coverage commitment

Per [CLAUDE.md](../../CLAUDE.md#every-new-endpoint-commit-lands-a-harness-test): every phase ships its harness coverage in the same commit. Estimated +14 tests across 7 commits (2 per phase: happy path + error / race-mismatch). Update `docs/test-harness-coverage.md` total each commit.

## Closing the audit row

After Phases 1–7 ship the **Races** row in the [SRD audit](../../TODO.md#srd-5e-audit-v23900-refresh) flips from `~90%` to `✅ ~100%` (mirroring the Class-features / Monsters trajectory). Trance and the per-race-darkvision Maps 2.0 ties are filed at the bottom of this doc as intentional non-goals.

The audit overall ticks from ~96% → ~97% on this arc — small but the table reads consistently across categories: races joins monsters + class-features as a strictly-✅ surface.
