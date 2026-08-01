# Battle Master (Fighter subclass) — design plan

Phase E.1 of the [v2.99.193 class-content completion plan](class-content-status.md).
Path: Fighter Martial Archetype: Battle Master (PHB p.73).

> **Status (re-audited 2026-06-11, v2.159.31 — SRD audit refresh):**
> ✅ shipped end-to-end. All 16 PHB Battle Master maneuvers shipped
> as individual `/use_*` endpoints with per-maneuver harness tests
> across v2.99.252 → v2.99.266 (Trip Attack v2.99.233 was Phase 1;
> the per-maneuver batch closed v2.99.252–v2.99.266, with
> Commander's Strike at v2.99.266 as maneuver 16/16). Know Your
> Enemy + Relentless (Lv 18) are the only remaining capstones;
> blocked on a Lv 18+ Fighter demo fixture rather than the engine.
> The 2026-06-10 SRD audit kept this in P2; the v-numbers actually
> pre-dated the audit but the header wasn't refreshed.

## Why a plan doc

Battle Master is the Fighter subclass with the deepest tactical
toolkit: a Combat Superiority dice pool plus 16 maneuvers that
each have their own contract (some on-hit, some on-miss, some
reactive). Shipping all 16 in one commit is too big; shipping
none of them blocks any other E phase. The plan freezes a
"one maneuver per commit" cadence after the v1 spine ships
(dice pool + Trip Attack as the canonical maneuver).

## RAW (PHB p.73-74, summarised)

| Lv | Feature | RAW |
|----|---------|-----|
| 3  | **Combat Superiority** | 4 superiority dice (d8) per short or long rest. 3 maneuvers known. Maneuver save DC = 8 + prof + max(STR mod, DEX mod). |
| 3  | **Student of War** | Proficiency with one artisan's tool. (Pure flavor — no endpoint.) |
| 7  | **Know Your Enemy** | After 1 minute of study, learn two pieces of info from a list about a creature's stats. |
| 7  | **Combat Superiority scaling** | Maneuvers also restore at Lv 7 (still 4 dice; gains 2 more at Lv 7 → total **5 dice**). Die size scales to d10 at Lv 10. |
| 9  | **Indomitable** | Reroll a failed save (already shipped — v2.56.0 / v2.99.x for Lv 9/13/17 scaling). Not subclass-gated. |
| 10 | **Improved Combat Superiority (Lv 10)** | Superiority die → d10. |
| 15 | **Relentless** | When you roll initiative, you regain one superiority die if you have none left. |
| 15 | **Combat Superiority scaling** | Pool grows to 6 dice. |
| 18 | **Improved Combat Superiority (Lv 18)** | Superiority die → d12. |

**Maneuvers** (RAW 16): Commander's Strike, Disarming Attack,
Distracting Strike, Evasive Footwork, Feinting Attack, Goading
Attack, Lunging Attack, Maneuvering Attack, Menacing Attack,
Parry, Precision Attack, Pushing Attack, Rally, Riposte,
Sweeping Attack, **Trip Attack**.

## Phasing

### Phase 1 — Combat Superiority pool + Trip Attack (✅ v2.99.233)

**Endpoint:** `/api/campaign/{cid}/use_trip_attack`.
**Body:** `{character_id, override?}`.

- Validates Battle Master Lv 3+.
- Validates `sheet.resources` contains a `superiority-dice`
  entry with `current >= 1`.
- Decrements the counter by 1.
- Reads die size from `sheet.superiority_die_size` (default `d8`
  if absent; the harness seeds it via PATCH).
- Rolls `1d<size>` server-side.
- Computes Maneuver Save DC = 8 + prof + max(STR_mod, DEX_mod).
- Broadcasts `feature_used` (source `trip-attack`) with
  `(extra_damage, save_dc, die_size, dice_remaining)`.

v1 ships announce-only — the +d8 damage and Str save are
announced for the GM to apply manually. The /attack endpoint
does not yet take a `maneuver: "trip"` body field.

**Sheet patch key:** `superiority_die_size` added to
`_SHEET_PATCH_KEYS` so the test can flip it from `d8` to `d10` /
`d12` for Lv 10 / 18 scaling tests.

**Test:** happy path at Lv 3 d8; out-of-dice 409; wrong subclass
409; level gate 409.

### Phase 2 — Pool refill on short/long rest (✅ shipped in v2.1042.4)

Refill happens via the generic reset-kind path in `/rest`
(`rest_character`): a **short** rest refills `reset: "short"`
resources, and a **long** rest refills short + long. The demo's
`superiority-dice` resource is curated with `reset: "short"`, so it
comes back on a short rest — the RAW Battle Master contract. The
**`reset: "short"` requirement** is the single thing curated content
must get right for the pool to refill correctly.

Covered by `tests/harness/test_battle_master_rest_refill.py`
(v2.1042.4 "The Whetstone"): deplete Garrik's Battle Master pool, then
assert a short rest refills 1/4 → 4/4 and a long rest refills 0/4 → 4/4.

### Phase 3 — Maneuvers (⚪ deferred, batched)

15 remaining maneuvers, one endpoint each:

- Commander's Strike (reaction → give an ally a melee attack)
- Disarming Attack (target Str save → drop weapon)
- Distracting Strike (advantage on next ally's attack)
- Evasive Footwork (superiority die → AC bonus this turn)
- Feinting Attack (advantage on next attack)
- Goading Attack (Wis save → disadvantage attacking others)
- Lunging Attack (extra 5 ft reach)
- Maneuvering Attack (ally moves without provoking)
- Menacing Attack (Wis save → frightened)
- Parry (reaction → reduce damage by superiority die + DEX mod)
- Precision Attack (add to attack roll, pre or post)
- Pushing Attack (Str save → 15 ft push)
- Rally (give ally temp HP = die + CHA)
- Riposte (reaction on miss → counter melee attack)
- Sweeping Attack (deal die damage to adjacent target)

Each is a Phase 3.x commit. Cadence: one maneuver per commit,
batched as the project sees player demand.

### Phase 4 — Know Your Enemy (⚪ deferred)

Lv 7. Action: announce a free-form "study target X" event; v1
just broadcasts the prompt and lets the GM hand back 2 facts.
Could later wire to monster stat blocks (HP / AC / damage type
/ ability score / movement / size / class levels / saves).

### Phase 5 — Relentless (⚪ deferred)

Lv 15. Hook into the `/battle PUT` turn-advance for "initiative
rolled this round" + auto-bump `superiority-dice.current` to 1
if currently 0. Easiest as a battle-state inspector on
turn_index == 0.

## What this plan does NOT cover

- Indomitable (Fighter Lv 9, not subclass-gated). Already
  shipped via the Lv 9/13/17 reroll path.
- Action Surge (Fighter Lv 2). Already shipped.
- Second Wind (Fighter Lv 1). Already shipped.
- Champion subclass features. That's its own subclass with its
  own plan (Improved Critical already shipped).

## Sequencing

Phase 1 ships first because Combat Superiority + Trip Attack is
the minimum spine that exercises the dice-pool plumbing + one
maneuver contract. Phase 2 (long-rest refill) is mostly a
verification ship — already works via the generic resource
refresh. Phase 3 batches the remaining 15 maneuvers; player
demand drives ordering. Phases 4-5 are tail features.

## References

- [Class / Subclass / Feat / Race content status](class-content-status.md) — the master inventory.
- [Eldritch Knight (Fighter subclass)](eldritch-knight.md) — the parallel Fighter subclass plan (also v1 announce-style).
- [Wild Magic (Sorcerer subclass)](wild-magic.md) — recently completed 5-phase Sorcerer plan (template for this one).
