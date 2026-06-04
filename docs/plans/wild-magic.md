# Wild Magic (Sorcerer subclass) — design plan

Phase E.6 of the [v2.99.193 class-content completion plan](class-content-status.md).
Path: Sorcerous Origin: Wild Magic (PHB p.103).

> **Status (v2.99.227):** 🟠 Phase 1 (Tides of Chaos announce) shipped.
> Phases 2–5 deferred.

## Why a plan doc

The wild-magic subclass is the only Phase E item whose v1 ship is
*not* a single-endpoint announce — Wild Magic Surge (Lv 1) is a
post-cast d20 trigger that runs on the GM's call after the player
casts a Lv 1+ sorcerer spell, and Bend Luck (Lv 6) is a reaction
that mutates someone else's d20 roll. Both are deep enough that
they earn their own follow-up commits. This plan freezes the
phasing so future commits can ship one at a time without
re-litigating scope.

## RAW (PHB p.103, summarised)

| Lv | Feature | RAW |
|----|---------|-----|
| 1  | **Wild Magic Surge** | When you cast a sorcerer spell of 1st level or higher, the DM can have you roll a d20 immediately after. If you roll a 1, roll on the Wild Magic Surge table to create a random magical effect. |
| 1  | **Tides of Chaos** | Once per long rest you can gain advantage on one attack roll, ability check, or saving throw. Before you regain the use, the DM can have you roll on the Wild Magic Surge table; if so, you also recover the use of Tides of Chaos. |
| 6  | **Bend Luck** | When another creature you can see makes an attack roll, ability check, or saving throw, you can use your reaction and spend 2 sorcery points to roll 1d4 and apply the number rolled as a bonus or penalty to the creature's roll. You can do so after the creature rolls but before any effects of the roll occur. |
| 14 | **Controlled Chaos** | When you roll on the Wild Magic Surge table, you can roll twice and use either number. |
| 18 | **Spell Bombardment** | When you roll damage for a spell and roll the highest number possible on any of the dice, choose one of those dice, roll it again and add that roll to the damage. You can use the feature only once per turn. |

## Phasing

### Phase 1 — Tides of Chaos announce (✅ v2.99.227)

**Endpoint:** `/api/campaign/{cid}/use_tides_of_chaos`.
**Body:** `{character_id}`.

- Validates Sorcerer subclass "Wild Magic" Lv 1+.
- Validates `sheet.tides_of_chaos_uses >= 1`.
- Decrements the counter to 0 + persists.
- Installs a `tides-of-chaos-active` buff (`effects.next_roll_advantage: True`,
  `consume_on_d20_roll: True`) — analogous to the v2.99.214 Hide in
  Plain Sight buff that the `/roll` Stealth hook consumes. The
  hook in `/roll` already reads `consume_on_d20_roll` semantically
  (one-shot stealth buff was the prototype) — Tides of Chaos
  rides the same mechanism.
- Broadcasts `feature_used` (`source: "tides-of-chaos"`).

**Long-rest refill:** in `/rest` long-rest branch, set
`sheet.tides_of_chaos_uses = 1` if `_pc_has_wild_magic(sheet, 1)`.

**Sheet patch key:** `tides_of_chaos_uses` added to
`_SHEET_PATCH_KEYS` so the harness can flip the counter.

**Tests:** 5 — happy path at Lv 1 (counter 1 → 0, buff installed,
broadcast); counter empty → 409 out_of_uses; long-rest refill
(counter 0 → 1); wrong-subclass gate (Zara Draconic by default
needs PATCH to "Wild Magic"); wrong-class gate (Krieger
Barbarian).

### Phase 2 — Wild Magic Surge auto-roll (⚪ deferred)

**Hook site:** `/cast_spell`, post-cast, when caller is Wild
Magic Sorcerer + cast `spell_level >= 1`. Roll a hidden d20 server-
side; on a 1, broadcast `wild_magic_surge` + index into the surge
table. The table itself (50 entries) lives in
`app/data/local/dnd5e/wild_magic_surge.json` (new asset).

**Tides interaction:** RAW lets the DM trigger the d20 roll before
the player regains Tides of Chaos. v1 ships the surge as
auto-rolled on every Lv 1+ sorcerer cast (lower friction); the
"GM decides" flexibility is filed.

**Composability:** the surge broadcast carries the table-entry
slug + RAW text only — none of the 50 entries auto-execute. The
GM resolves the effect manually (rolls follow-up dice, installs
buffs, etc.). Future deep-wire commits could resolve specific
high-impact entries (e.g., Fireball at self).

**Test:** smoke that asserts a wild magic Lv 1 sorcerer casting a
seeded `1` rolls a surge broadcast; non-Wild-Magic-Sorcerer cast
doesn't.

### Phase 3 — Bend Luck reaction (⚪ deferred)

**Endpoint:** `/use_bend_luck` — body `{character_id, target_combatant_id, mode}`
where mode ∈ {bonus, penalty}. Costs 2 SP (decrement
`sheet.sorcery_points` counter), marks reaction chip, broadcasts
the 1d4 roll. The bonus/penalty is announced for the GM to apply
to the target's just-rolled d20.

**Constraint:** RAW "after the creature rolls but before any
effects of the roll occur" — v1 ships announce-only since
SimpleVTT doesn't yet pause-then-resume third-party rolls. The
broadcast carries the 1d4 so the GM bumps the displayed roll
manually.

### Phase 4 — Controlled Chaos roll-twice (⚪ deferred)

Lv 14. After Phase 2 ships, extend the surge broadcast to roll
2 table entries when `_wizard_level_from_sheet >= 14` and the
caster is Wild Magic Sorcerer. UI lets the player pick one.

### Phase 5 — Spell Bombardment damage reroll (⚪ deferred)

Lv 18. Post-damage hook in `/cast_spell` damage-roll site: if any
die in the damage roll showed its max value, broadcast a
`bombardment_offer` event that the player accepts to reroll one
of those dice once per turn. Per-turn flag tracked via battle-
economy slot like Foe Slayer (v2.99.216).

## What this plan does NOT cover

- The 50-entry Wild Magic Surge table itself. Phase 2 will add
  the asset; this plan freezes the *consumption shape*, not the
  table content. Each entry's auto-resolution is its own commit.
- Cross-edition surge tables (Tasha's optional rule "Wild Magic
  Surge on each spell cast even at 1 if you don't beat the
  spell level + 1 DC" is an Optional rules variant — not RAW PHB,
  filed for an optional-rules toggle in a future config commit).
- A "Tides of Chaos refills on DM-triggered surge" automation —
  Phase 1's manual refill via the sheet PATCH covers it; Phase 2
  may grow a refill side-effect when the surge auto-fires.

## Sequencing

Phase 1 ships first because it's strictly additive and exercises
the same buff-install + `/roll` consumer plumbing we already use
for Hide in Plain Sight + Supreme Sneak — it's the lowest-friction
v1.

Phase 2 ships next when the surge table asset is ready; Phase 3
(Bend Luck) is a clean reaction endpoint and can ship in any
order after Phase 1. Phases 4-5 ship after their respective
prerequisites (Phase 4 needs Phase 2's roll site; Phase 5 is
independent but high-cost so it sits at the tail).

## References

- [Class / Subclass / Feat / Race content status](class-content-status.md) — the master inventory.
- [Hide in Plain Sight (v2.99.214)](../../CHANGELOG.md#L29957) — the `consume_on_d20_roll` buff pattern.
- [Portent (v2.99.219)](../../CHANGELOG.md#L29714) — the long-rest refill pattern that Tides of Chaos mirrors.
