# Race features — close the SRD races gap to 100%

> **Status:** 🟢 partial (v2.395.0). Drives the **Races ~90% → 100%** axis of the [SRD audit](../../TODO.md#srd-5e-audit-v23900-refresh). Phase 1 (Tiefling Infernal Legacy racial Hellish Rebuke) **shipped v2.395.0**. Pre-existing: Half-Orc Savage Attacks shipped v2.99.23 (reconciled v2.394.0 from stale-audit; see below). Phases 2–6 still to ship + the optional Phase 7 Trance polish + Phase 1b/1c Infernal Legacy tail follow-ups.

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
| | Savage Attacks | ✅ | `_compute_attack_auto_uplifts` (v2.99.23) at `tabletop_routes.py:29709` — auto-uplift with `source="savage-attacks"`. Covered by `tests/harness/test_savage_attacks.py`. Stale-audit reconciliation v2.394.0 — see "Stale-audit reconciliations" below. |
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
| | Infernal Legacy spells (Thaumaturgy + Hellish Rebuke + Darkness) | 🟢 partial | Thaumaturgy + Darkness still 🟠 (manually seeded into sheet's spells + resources, no auto-grant). **Hellish Rebuke (racial, 1/long, L2) wired v2.395.0** — `_pc_has_tiefling_hellish_rebuke_racial(sheet)` + new `cast-hellish-rebuke-racial` reaction option + dedicated cast handler that consumes the `hellish-rebuke` resource (not a spell slot). Covered by `tests/harness/test_tiefling_hellish_rebuke_racial.py`. |
| | **Stout Halfling Stout Resilience** | ✅ | `_RACE_SAVE_ADVANTAGES["halfling-stout"]` (subrace) |

**Counts:** 17 ✅ · 11 🟠 · 7 ⚪ · 3 N/A (after v2.394.0 Savage Attacks reconciliation; was 16/11/8/3 in the v2.393.0 first cut).

## Scope decision: which traits to ship vs leave

This plan ships the remaining **7 unwired** traits — every ⚪ above — except where RAW is intentionally narrative or substrate-blocked. After ship the Races coverage row goes from ~90% → essentially 100% for engine-shaped RAW.

| Trait | Phase | Ship? | Why |
|---|---|---|---|
| Half-Orc Savage Attacks | — | ✅ DONE (v2.99.23) | Already shipped on `_compute_attack_auto_uplifts`; reconciled v2.394.0 |
| Tiefling Infernal Legacy auto-grant | 1 | ✅ | Level-gated spell list + per-day resource seeding; mirrors v2.99.200 Pact-of-the-Tome wiring |
| Hill Dwarf Stonecunning | 2 | ✅ | Skill-check double-PB; small endpoint or roll-route flag |
| Hill Dwarf Speed-not-reduced-by-heavy-armor | 3 | ✅ | Composes on the existing speed/armor-weight gate (the gate doesn't fire today, so this lands as the gate's first consumer) |
| Halfling Nimbleness | 4 | ✅ | Move-through-larger-creature gate at `/token/move`; reuses combatant-size data |
| Halfling Naturally Stealthy | 5 | ✅ | Stealth-check size-cover gate (skill-check side, doesn't need vision LOS) |
| Rock Gnome Artificer's Lore | 6 | ✅ | Same shape as Stonecunning (Phase 2) — double PB on History; topic = "magic items / alchemical / tech" |
| Elf Trance | 7 | 🟢 (flavor) | Long-rest UI nudge only; no mechanical effect server-side per RAW |
| Rock Gnome Tinker | — | ❌ | **Out-of-scope** — needs a crafting substrate that doesn't exist (1-hour craft, GP cost, clockwork-creature catalog). Permanently GM-narrated by design. |
| 🟠 → ✅ promotions (Skill Versatility, Keen Senses, Elf Weapon Training, etc.) | — | ❌ | These are already correctly seeded onto the sheet; the proficiency math reads through. No engine work owed. Test coverage may be filed under the harness-coverage doc when convenient but not required by this plan. |

After Phase 6 the engine-shaped tail is closed. Phase 7 is the optional Trance polish (flavor toast on long rest). Tinker stays out-of-scope.

## Stale-audit reconciliations

| Trait | First-cut audit status | Reality | Reconciled |
|---|---|---|---|
| Half-Orc Savage Attacks | ⚪ unwired (Explore agent on v2.393.0 plan) | ✅ shipped v2.99.23 — `_compute_attack_auto_uplifts` adds the bonus die at `tabletop_routes.py:29709` with `source="savage-attacks"`, covered by `tests/harness/test_savage_attacks.py` | v2.394.0 |

This is the **5th stale-audit reconciliation** in the v2.382.1 → v2.394.0 stretch, following Aura of Courage (v2.376.2), Legendary + Lair Actions (v2.376.2), Hold Person / Hold Monster (v2.382.1), and `source_char_id` on charmed-buff installs (v2.390.2). The pattern is captured in `~/.claude/projects/.../memory/feedback_check_plan_doc_before_audit_promote.md` — audit prose drifts; the code + harness tests are the source of truth. Always verify before promoting a trait from "wired" to "needs work" or vice versa.

## Implementation patterns to copy

Every phase reuses an existing substrate; no new architectural primitive is needed.

- **Infernal Legacy** — model: v2.99.200 Pact of the Tome (Warlock). Add `_pc_infernal_legacy_spells(sheet)` returning the level-gated catalog (Thaumaturgy always · Hellish Rebuke @ Lv 3+ · Darkness @ Lv 5+). Merge into the cast-spell whitelist + auto-seed `_resources` entries for Hellish Rebuke + Darkness (both 1/day, reset on long rest). The seed runs once per `/sheet-json` projection so adding a new Tiefling PC just works without manual character-builder steps.
- **Stonecunning** — RAW: when making a History check related to the origin of stonework, the Dwarf adds 2× proficiency bonus instead of 1×. Implementation: small additive `topic` param on the History check roll (or a dedicated `/check_stonecunning` endpoint), gated via `race_slug in {"dwarf", "hill-dwarf"}`. Pattern: `_RACE_SAVE_ADVANTAGES`-shaped derivation, but on the check-roll side.
- **Speed-not-reduced-by-heavy-armor** — small predicate that suppresses the (currently no-op) heavy-armor speed reduction. The substrate doesn't fire today, so this lands as the substrate's installation + Dwarf bypass in one shot. RAW PHB p.20 STR threshold check: heavy armor "Str < Str_min" reduces speed by 10. Dwarves are exempt regardless of STR.
- **Halfling Nimbleness** — gate at `/token/move` (or the equivalent move-validation site): allow move-through when target combatant's size > mover's size. Sizes already live on each combatant (`size: "Medium" | "Large" | …`). Pattern: small predicate composed onto the existing OA-friendly-pass-through gate.
- **Naturally Stealthy** — gate on Stealth checks: allow the "hide" intent when the Halfling is obscured by a combatant ≥1 size larger. The check-rolling side already reads roll-state; this adds a `cover_combatant_id` optional param that the stealth flow consumes.
- **Artificer's Lore** — twin of Stonecunning (Phase 3). Same double-PB History-check pattern, gated via `race_slug == "gnome"` (any subrace). Topic distinguishes magic items / alchemical / tech.
- **Trance** — long-rest UI nudge: the long-rest summary card adds a "(trance — 4 hours)" line for Elves. No state-machine change; flavor only.

## Per-phase shipping plan

Each phase = one MINOR commit + 1 happy-path test + 1 error-path test (race mismatch / resource exhausted / state check). The full plan lands across 6 commits (Phases 1–6) plus optional Phase 7 flavor ship.

1. **Phase 1 — Tiefling Infernal Legacy racial Hellish Rebuke** (MINOR, **shipped v2.395.0**). The first slice of Infernal Legacy: route the reaction Hellish Rebuke cast through the `hellish-rebuke` racial resource (1/long, L2) instead of consuming a spell slot. New `_pc_has_tiefling_hellish_rebuke_racial(sheet)` gate; new `cast-hellish-rebuke-racial` reaction option offered alongside the existing slot-based path; new cast handler that consumes the racial resource. Zara Emberfire (Tiefling Sorcerer Lv 5) is the demo fixture. Follow-up tail filed: **Darkness 1/long racial cast (Phase 1b)** + **auto-grant projection of Thaumaturgy / Hellish Rebuke / Darkness on `/sheet-json` so future Tiefling PCs don't need manual demo-seed wiring (Phase 1c)** — both deferred until a fresh Tiefling PC creation flow is in scope.
2. **Phase 2 — Hill Dwarf Stonecunning** (MINOR). History-check double-PB with `topic` parameter. Tavik (existing Hill Dwarf demo) is the test fixture.
3. **Phase 3 — Hill Dwarf Speed-not-reduced-by-heavy-armor** (MINOR). Install heavy-armor STR-threshold speed gate; carve out Dwarf bypass. Test: Tavik in plate at STR 14 keeps base 25; non-Dwarf at STR 14 in plate loses 10.
4. **Phase 4 — Halfling Nimbleness** (MINOR). Move-through-larger gate at `/token/move`. Pip (existing Lightfoot Halfling Rogue) is the fixture.
5. **Phase 5 — Halfling Naturally Stealthy** (MINOR). Stealth-check size-cover gate. Pip is the fixture; cover combatant = an Orc or larger creature.
6. **Phase 6 — Rock Gnome Artificer's Lore** (MINOR). Twin of Phase 2 with topic = magic items / alchemical / tech. Existing Rock Gnome demo (Mira) is the fixture.
7. **Phase 7 — Elf Trance (flavor)** (PATCH). Long-rest UI card flavor for Elves. Optional polish ship.

## Out-of-scope by design

- **Rock Gnome Tinker** — needs a crafting system that doesn't exist (1-hr craft, 10 gp materials, 24-hr clockwork-creature persistence, three-active cap). Permanently GM-narrated.
- **Darkvision 60 ft (every Darkvision race)** — already correctly seeded as `darkvision_ft: 60` on every applicable PC; the actual gameplay consequence (seeing in dim light) is a vision/lighting concern that lives in Maps 2.0 (currently a backlogged plan). No engine work owed by this plan.
- **Keen Senses (Perception) / Skill Versatility / Menacing / Tool / Weapon proficiencies** — already correctly seeded as `skill_proficiencies` / `weapon_proficiencies` / `tool_proficiencies` on the sheet; the math reads through every check site. No engine work owed.
- **Languages / Age / Alignment** — pure flavor; no mechanical effect server-side.
- **Dwarven Toughness on level-up** — currently correctly baked into the demo seed's `hp.max`. A per-level-up hook would require a level-up workflow that currently lives on the character-builder side (out of session scope). Filed for the character-builder revamp.

## Test coverage commitment

Per [CLAUDE.md](../../CLAUDE.md#every-new-endpoint-commit-lands-a-harness-test): every phase ships its harness coverage in the same commit. Estimated +14 tests across 7 commits (2 per phase: happy path + error / race-mismatch). Update `docs/test-harness-coverage.md` total each commit.

## Closing the audit row

After Phases 1–6 ship the **Races** row in the [SRD audit](../../TODO.md#srd-5e-audit-v23900-refresh) flips from `~90%` to `✅ ~100%` (mirroring the Class-features / Monsters trajectory). Trance and the per-race-darkvision Maps 2.0 ties are filed at the bottom of this doc as intentional non-goals.

The audit overall ticks from ~96% → ~97% on this arc — small but the table reads consistently across categories: races joins monsters + class-features as a strictly-✅ surface.
