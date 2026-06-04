# Wild Magic (Sorcerer subclass) — design plan

Phase E.6 of the [v2.99.193 class-content completion plan](class-content-status.md).
Path: Sorcerous Origin: Wild Magic (PHB p.103).

> **Status (v2.99.231):** ✅ All 5 phases shipped (Tides + Surge +
> Bend Luck + Controlled Chaos + Spell Bombardment). The plan is
> complete; the Wild Magic Sorcerer subclass is now fully wired
> end-to-end with the v1 announce-only constraints documented per
> phase.

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

### Phase 2 — Wild Magic Surge auto-roll (✅ v2.99.228)

**Hook site:** `/cast_spell`, post-cast (after `spell_cast`
broadcast). When caller is Wild Magic Sorcerer + `cslug ==
"sorcerer"` + `spell_level >= 1`, server rolls d20; on natural 1,
rolls d100, maps to a table entry via `surge_entry_for_d100()`,
broadcasts `wild_magic_surge` with `(slug, name, desc, d100,
tides_refilled)`, and refills `sheet.tides_of_chaos_uses = 1`.
The 50-entry RAW table ships inline in `app/wild_magic_surge.py`
(JSON-asset refactor deferred).

**Tides interaction:** auto-refilled — RAW says the DM can trigger
the d20 roll *before* the player regains Tides of Chaos, and if
so they "also regain the use of this feature." Auto-rolled flavor
of the design picks the player up regardless.

**Composability:** the surge broadcast carries the table-entry
slug + RAW text only — none of the 50 entries auto-execute. The
GM resolves the effect manually (rolls follow-up dice, installs
buffs, etc.). Future deep-wire commits could resolve specific
high-impact entries (e.g., Fireball at self).

**TEST_MODE escape hatch.** `/cast_spell` accepts `_force_surge_d20:
int` body param when `TEST_MODE` env is truthy, bypassing the
random d20 roll for deterministic harness tests. Silently ignored
in production.

### Phase 3 — Bend Luck reaction (✅ v2.99.229)

**Endpoint:** `/use_bend_luck` — body `{character_id, mode,
target_name?, override?}` where mode ∈ {bonus, penalty}.
Validates Wild Magic Sorcerer Lv 6+, sorcery-points >= 2, and
Phase 4 reaction chip; decrements 2 SP, rolls 1d4 server-side,
marks reaction chip, broadcasts `feature_used` (source
`bend-luck`) with `(mode, d4, signed, target_name,
sp_remaining)`.

**Constraint:** RAW "after the creature rolls but before any
effects of the roll occur" — v1 ships announce-only since
SimpleVTT doesn't yet pause-then-resume third-party rolls. The
broadcast carries the 1d4 + signed value so the GM bumps the
displayed roll manually.

### Phase 4 — Controlled Chaos roll-twice (✅ v2.99.230)

Lv 14. The Phase 2 surge hook now branches on
`_pc_has_wild_magic(sheet, 14)`: rolls the d100 surge table
twice and broadcasts both via `alternatives: [entry1, entry2]`
+ `controlled_chaos: true`. Below Lv 14 the broadcast still
carries `alternatives: [single_entry]` + `controlled_chaos:
false` so the client can render the pick UI uniformly.

The primary `(slug, name, desc, d100)` top-level fields stay
populated with `alternatives[0]` for backward-compat with any
pre-v2.99.230 client. Future UI commit will render the picker
when `controlled_chaos: true`.

### Phase 5 — Spell Bombardment damage reroll (✅ v2.99.231)

**Endpoint:** `/use_spell_bombardment` — body `{character_id,
die_size}` where die_size ∈ {4,6,8,10,12}. Validates Wild Magic
Lv 18+ + once-per-turn flag (combatant economy
`spell_bombardment_used`, mirror of Colossus Slayer's v2.60.0
flag). Rolls 1d<die_size> server-side, marks the flag,
broadcasts `feature_used` (source `spell-bombardment`) with
`(die_size, extra_damage)`.

**v1 ships announce-only.** The player invokes this after seeing
their damage roll show a max die; the GM applies the bump to the
existing damage roll manually. A deep-wire follow-up would hook
the `/cast_spell` damage-roll site to auto-detect max-rolled dice
and broadcast a `bombardment_offer` event for the player to
accept inline.

**Once-per-turn reset.** Tracked via
`combatant.economy.spell_bombardment_used`; reset client-side at
turn-advance, same plumbing as Colossus Slayer / Divine Strike.

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
