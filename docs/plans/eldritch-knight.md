# Eldritch Knight (Fighter subclass) — design plan

Phase E.2 of the [v2.99.193 class-content completion plan](class-content-status.md).
Path: Fighter Martial Archetype: Eldritch Knight (PHB p.74).

> **Status (v2.99.232):** 🟠 Phase 1 (Weapon Bond picker + announce)
> shipped. Phases 2–4 deferred.

## Why a plan doc

Eldritch Knight is one of two Fighter subclasses with deep
spellcasting + battle-magic synergy (the other is Battle Master,
also unstarted). Several features (War Magic, Eldritch Strike,
Improved War Magic) interact with the `/cast_spell` + `/attack`
hot paths in non-trivial ways and want phased deep-wire commits
rather than a single big bang. This plan freezes the per-phase
scope so future commits can ship one feature at a time without
re-litigating the design.

## RAW (PHB p.74, summarised)

| Lv | Feature | RAW summary |
|----|---------|-------------|
| 3  | **Spellcasting** | 1/3 caster, Wizard spell list. INT casting; 3 cantrips + 3 spells known at Lv 3, scaling to 4/13 at Lv 20. Most picks restricted to abjuration + evocation but 2 free picks may come from any school. |
| 3  | **Weapon Bond** | Hour-long ritual; bond up to 2 weapons. Bonded: can't be disarmed while conscious; can summon as a bonus action if on same plane and you have a free hand. |
| 7  | **War Magic** | When you cast a cantrip, you can take a bonus-action weapon attack. |
| 10 | **Eldritch Strike** | On hit with a weapon attack, the target has disadvantage on the next saving throw against an Eldritch Knight spell you cast before the end of your next turn. |
| 15 | **Arcane Charge** | When you use Action Surge, you can teleport up to 30 ft to an unoccupied space you can see, before or after the action. |
| 18 | **Improved War Magic** | When you cast a Lv 1+ spell, you can take a bonus-action weapon attack (replacing War Magic's cantrip-only restriction). |

## Phasing

### Phase 1 — Weapon Bond picker + announce (✅ v2.99.232)

**Endpoint:** `/api/campaign/{cid}/use_weapon_bond`.
**Body:** `{character_id, weapon_index, override?}`.

- Validates Eldritch Knight Lv 3+.
- Reads `sheet.inventory[weapon_index]`; expects `type == "weapon"`.
- Appends the weapon's `_slug` (or name fallback) to
  `sheet.bonded_weapons` (list[str]). RAW max 2 — endpoint
  enforces.
- Broadcasts `feature_used` (source `weapon-bond`) with
  `(weapon_name, bonded_weapons)`.

**Sheet patch key:** `bonded_weapons` added to `_SHEET_PATCH_KEYS`
so the harness can flip the list directly.

**Test:** happy path adds first weapon; second weapon adds; third
weapon → 409 cap_reached; wrong subclass → 409; wrong level
(Lv 2) → 409; bad weapon_index → 400.

### Phase 2 — War Magic (⚪ deferred)

**Hook site:** `/cast_spell` post-cast for Eldritch Knight Lv 7+
when `spell_level == 0` (cantrip). Stamps a per-turn flag
`sheet.war_magic_bonus_attack_available = True`. The /attack
endpoint then accepts an `as_war_magic_bonus: true` body field
that consumes the flag instead of marking the action chip,
marking only the bonus chip.

**Test:** Eldritch Knight Lv 7 casts Fire Bolt cantrip → flag
set → /attack with `as_war_magic_bonus: true` → bonus chip
marked + flag cleared.

### Phase 3 — Eldritch Strike (⚪ deferred)

**Hook site:** `/attack` post-resolution. When attacker is
Eldritch Knight Lv 10+ AND the attack hit AND the attacker has
an "active spell" tracked from the next-turn buffer, install a
`eldritch-strike-target` buff on the target with
`effects.save_disadvantage_against_caster_id` matching the
attacker. The v2.99.X save resolver checks for this buff against
the casting char's id + drops it on consume.

**Test:** Lv 10 Eldritch Knight hits → target buff present →
next save vs caster's spell rolls at disadvantage.

### Phase 4 — Arcane Charge + Improved War Magic (⚪ deferred)

Lv 15 Arcane Charge: extend `/use_action_surge` to optionally
accept a `teleport_dest_cell` body field that moves the
attacker's token before / after the surge.

Lv 18 Improved War Magic: same plumbing as Phase 2 but the
cantrip-only constraint is dropped to "Lv 1+ spell."

## What this plan does NOT cover

- Eldritch Knight's Spellcasting feature itself — Wizard spell
  list selection / per-level spell scaling. The existing
  `/cast_spell` already handles INT-casting + class_slug routing;
  the Lv 3 EK spell-list picker UI is filed as a sheet-edit
  panel concern (the harness can already PATCH `sheet.spells`).
- The 8th-level Ability Score Improvement — pure stat bump, no
  new endpoint needed.

## Sequencing

Phase 1 first because Weapon Bond is the lowest-friction Lv 3
feature + makes a coherent narrative anchor for the subclass.
Phase 2 (War Magic) ships next as the most common in-play
trigger; Phase 3 (Eldritch Strike) builds on the per-turn flag
plumbing from Phase 2. Phase 4 is the tail (Lv 15 + 18 features
are demo-rare).

## References

- [Class / Subclass / Feat / Race content status](class-content-status.md) — the master inventory.
- [Wild Magic (Sorcerer subclass)](wild-magic.md) — the recently-completed phased-ship template (5 phases, 1 commit each).
- [Action Surge (v2.x — fighter Lv 2)](../../CHANGELOG.md#L) — Phase 4 will extend that endpoint.
