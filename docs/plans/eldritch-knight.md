# Eldritch Knight (Fighter subclass) — design plan

Phase E.2 of the [v2.99.193 class-content completion plan](class-content-status.md).
Path: Fighter Martial Archetype: Eldritch Knight (PHB p.74).

> **Status (re-audited 2026-06-10, v2.158.68):** 🟢 partial — Phase 1
> (Weapon Bond picker + announce) shipped v2.99.232. **Arcane Charge
> Lv 15+ Phase 1 ✅** (v2.158.11: permanent `arcane-charge-active`
> buff with `teleport_max_ft=30` + `requires_action_surge=True`
> effect keys). **Improved War Magic Lv 18+ Phase 1 ✅** (v2.158.12:
> `improved-war-magic-active` flag buff with `min_spell_level=1`).
> **Lv 10 Eldritch Strike — ✅ shipped (PC-target path; reconciled
> v2.648.4).** Both halves are live and harness-tested: the install
> endpoint `POST /use_eldritch_strike` (v2.99.268 — gated on EK Lv 10+,
> installs the `eldritch-strike-target` buff carrying
> `effects.save_disadvantage_against_caster_id`, `test_eldritch_strike.py`)
> AND the save-resolver read (v2.158.54 — the PC-target save site swaps
> the saver's d20 → `2d20kl1` when the saver carries the buff naming
> THIS caster, consume-on-first-save, RAW adv/dis cancellation,
> `test_eldritch_strike_resolver.py`). Two genuine enhancements remain,
> filed as Phase 3b/3c below: **auto-install on a weapon hit** (today the
> marker needs a manual `/use_eldritch_strike` call; RAW it's automatic
> on hit) and the **NPC-target path** (the endpoint only installs the
> buff for PC targets, and the resolver read is in the PC-save branch —
> the common "EK hits a monster then casts at it" case isn't wired).
> **Outstanding (other features):** Lv 7 War Magic (bonus-action weapon
> attack after cantrip cast — `/cast_spell` post-cast bonus-attack
> rider); Arcane Charge Phase 2 (`/use_action_surge` reads the buff +
> surfaces a teleport budget); Improved War Magic Phase 2 (`/cast_spell`
> reads the buff + allows the bonus-action weapon attack when
> `spell_level >= 1`).

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

### Phase 2 — War Magic (🟠 advisory shipped; economy-route filed)

**Phase 2a — `/cast_spell` advisory ✅ shipped v2.648.6.** On an
action-cast cantrip by an EK Lv 7+ (`_pc_has_eldritch_knight(sheet, 7)`),
`/cast_spell` post-resolution broadcasts a `feature_used(source=war-magic-advisory)`
naming the available bonus-action weapon attack — so the player is
prompted instead of having to call `/use_war_magic` blind. Respects
Improved War Magic (Lv 18, `_pc_improved_war_magic_min_level >= 1`),
widening the trigger to any Lv 1+ spell. The bonus attack is resolved via
the existing `/use_war_magic` (marks the bonus chip, v2.99.267) + the
player's weapon attack. Harness:
`test_war_magic.py::test_war_magic_advisory_on_ek_cantrip` (+ a non-EK
negative test).

**Phase 2b — economy-route ✅ shipped v2.648.8.** `/attack` now accepts
`as_war_magic_bonus: true`, which — gated to an EK Lv 7+ — retargets the
over-budget gate + `_mark_battle_economy` to the **bonus** slot (reusing
the `attack_slot` plumbing from v2.644.0's `as_reaction`). So the
bonus-action weapon attack rides `/attack` directly (one call, marks the
bonus chip) instead of `/use_war_magic` + a separate override attack. A
non-EK caller falls through to a normal action attack. Harness:
`test_war_magic.py::test_war_magic_bonus_attack_marks_bonus_slot` (+ a
non-EK negative test). The cantrip-cast precondition stays GM-tracked
(matching `/use_war_magic`); a per-turn flag + round-stamp enforcement
(the cloak-suppression pattern) is filed as optional follow-up.

**Test:** Eldritch Knight Lv 7 casts Fire Bolt cantrip → advisory fires
(2a, shipped); `/attack as_war_magic_bonus` → bonus chip marked (2b,
shipped).

### Phase 3 — Eldritch Strike (✅ PC-target path shipped)

**Shipped (reconciled v2.648.4):**
- **Install:** `POST /use_eldritch_strike` (v2.99.268) — validates EK
  Lv 10+ via `_pc_has_eldritch_knight(sheet, 10)`, installs the
  `eldritch-strike-target` buff on the target with
  `effects.save_disadvantage_against_caster_id: <ek_id>` +
  `consume_on_first_save: True` (10-round duration). Harness:
  `test_eldritch_strike.py`.
- **Read:** the per-cast PC-target save site (v2.158.54) calls
  `_saver_has_eldritch_strike_vs_caster(campaign_id, saver_id, caster_id)`;
  when the saver carries the buff naming this caster it swaps the
  saver's d20 → `2d20kl1` (with RAW PHB p.173 adv/dis cancellation) and
  drops the buff. Mirrors the Heightened Spell metamagic idiom at the
  same site. Harness: `test_eldritch_strike_resolver.py`.

**Filed enhancements (genuinely unbuilt):**
- **3b — auto-install on a weapon hit. ✅ shipped v2.648.5.** On a
  confirmed hit in `/attack` post-resolution, when the attacker is EK
  Lv 10+ (`_pc_has_eldritch_knight(sheet, 10)`), the `eldritch-strike-target`
  buff installs automatically — no manual `/use_eldritch_strike` call.
  The install logic was extracted into a shared `_install_eldritch_strike(...)`
  helper that both the endpoint and the `/attack` hook call. Purely
  beneficial to the EK, so no opt-in prompt. Harness:
  `test_eldritch_strike.py::test_es_auto_installs_on_weapon_hit` (+ a
  non-EK negative test).
- **3c — NPC-target path. ✅ shipped v2.648.7.** `_install_eldritch_strike`
  now installs the marker on NPC combatants too (via
  `_install_buff_on_combatant_id`), and the NPC auto-save site in
  `/cast_spell` reads it — swapping the NPC save to `2d20kl1`, dropping the
  one-use marker (new `_remove_buff_from_combatant_id` helper), and firing
  a consume broadcast. Mirrors the NPC Heightened-Spell wire at the same
  site. So the common "EK hits a monster then casts a save spell at it"
  case is now fully automated (install on hit via 3b + NPC-save read).
  Harness: `test_eldritch_strike_resolver.py::test_eldritch_strike_npc_save_disadvantage`.

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
