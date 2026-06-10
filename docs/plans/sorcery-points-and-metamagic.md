# Sorcery Points + Metamagic — design plan

**Status:** 🟢 substantially shipped (re-audited 2026-06-10, v2.158.68) — Phase 0 shipped (v2.49.120-123): both Font of Magic endpoints + multiclass `class_slug` + ephemeral slot creation, 13 harness tests. Phase 1 shipped (v2.49.124-125): `/use_metamagic_empowered_spell` endpoint + `/cast_spell` integration on save-for-half single-target NPC path AND multi-beam attack-roll spells (Scorching Ray / Eldritch Blast / Fire Bolt) with pool reroll across all beams, 7 harness tests. **7 of 8 PHB metamagics shipped end-to-end during the v2.99.x window** (per the v2.99.192 class-content re-audit): Empowered (v2.49.124), Twinned (v2.99.33/.167/.174/.181/.183/.184/.187/.189), Distant (v2.99.34/.159), Heightened (v2.99.35-.36/.41), Careful (v2.99.38/.42), Extended (v2.99.37/.161/.165), Subtle (v2.99.162/.173/.186). **Sorcerous Restoration ✅** (v2.99.39) closes the Lv 20 capstone. **Outstanding:** Quickened Spell still announce-only (the 8th metamagic — bonus-action cast routing needs a `/cast_spell` action-economy override path); AoE multi-target Empowered loop integration (Phase 1.5) is the remaining Empowered scope finisher. The plan body below pre-dates the v2.99.x shipping arc — treat it as historical context.
**Authors:** rolling
**Last updated:** 2026-06-10 (status header re-audit; body unchanged)

A plan to ship the two interlocked Sorcerer features — **Font of
Magic** (Lv 2, the Sorcery Points pool + slot ↔ point conversion)
and **Metamagic** (Lv 3, spend Sorcery Points to modify a spell's
mechanics on the cast). The plan follows the v2.49.55 / v2.49.57 /
v2.49.112 / v2.49.114 Monk-feature precedent: dedicated endpoints
per spend-option, a resource counter on the sheet, server-side
buff machinery for the active-state tracking, and harness tests
gating each option's contract before merge.

Demo subject: **Zara Emberfire** (Sorcerer Lv 5, Draconic Bloodline
/ Red Dragon) — already in the demo seed since v2.18.1 with the
Sorcery Points resource counter (`key: 'sorcery-points'`) but no
spend-options wired.

---

## Why this matters

Pre-plan state: the Sorcerer's class table in
`docs/plans/class-content-status.md` has these rows:

| Lv | Feature | Status |
|---|---|---|
| 1 | Spellcasting | ✅ |
| 1 | Sorcerous Origin (subclass) | ✅ subclass shipped; Draconic Bloodline features 🟡 |
| 2 | Font of Magic / Sorcery Points | 🟢 counter present (curated `font-of-magic` in `_FEATURE_ECONOMY`) but slot↔point conversion endpoints not wired |
| 3 | Metamagic | ⚪ no plan, no code |
| 4 / 8 / 12 / 16 / 19 | ASI | ✅ |
| 5 / 11 / 17 | (cantrip damage scaling) | ✅ via v2.36.0 |
| 20 | Sorcerous Restoration | ⚪ |

Font of Magic and Metamagic together are what makes a Sorcerer feel
distinct from a Wizard at the table. A demo Sorcerer who can't spend
Sorcery Points is mechanically a one-trick-spellbook caster with a
shallower spell list. This plan closes that gap.

---

## Design principles

1. **One endpoint per spend-option.** Mirrors v2.49.55 Stunning
   Strike / v2.49.57 Open Hand Technique / v2.49.112 PD/SotW /
   v2.49.114 Flurry of Blows pattern. Each Metamagic option +
   each Font of Magic conversion direction gets its own
   `POST /api/campaign/{cid}/use_*` endpoint.
2. **Picker UI tagged onto the cast button.** Metamagic applies
   to a spell cast — the player picks Metamagic *before* clicking
   Cast. This is the same modal-before-fetch pattern v2.16.0 used
   for the Sneak Attack / Divine Smite uplift modal (`_showUpliftModal`
   in `sheet_dnd5e.html`).
3. **Sorcery Points is a resource counter + a buff tagger.** The
   counter on the sheet is the pool; the active Metamagic option
   rides as a one-cast buff (`metamagic-quickened-pending`,
   `metamagic-subtle-pending`, etc.) that the next `/cast_spell`
   call reads + consumes.
4. **Server-side enforcement is the source of truth.** The endpoint
   checks Sorcery Point cost, decrements atomically, installs the
   pending buff. The sheet-side picker is just a UI for the
   endpoint call. A direct API caller without the picker still
   goes through the same gates.
5. **Phased rollout per Metamagic option.** Don't try to ship all
   8 options at once. Each option has its own quirks; ship the
   simpler ones first and use the pattern to scaffold the harder
   ones.

---

## Phase 0 — Font of Magic (Lv 2)

**Goal:** Sorcery Points pool works; slot ↔ point conversion endpoints
ship; sheet button wires up. No Metamagic yet.

The Sorcery Points counter already exists on Zara's sheet
(v2.18.1). Phase 0 wires the two conversion directions per RAW
PHB p.101:

- **Spell slot → Sorcery Points** — bonus action; sacrifice a spell
  slot of level N to gain N sorcery points. Use any time during
  your turn.
- **Sorcery Points → Spell slot** — bonus action; spend points per
  the table (L1 = 2, L2 = 3, L3 = 5, L4 = 6, L5 = 7) to create a
  spell slot of that level. Only L1-L5 slots are recoverable RAW;
  the new slot disappears at the end of a long rest if unused.

### Endpoints

- `POST /api/campaign/{cid}/use_font_of_magic_to_points`
  - Body: `{character_id, slot_level: int, override?}`
  - Validates Sorcerer Lv 2+, slot of that level is available + unused.
  - Decrements the spell slot; adds `slot_level` sorcery points to
    the counter (capped at max).
  - Marks the bonus slot via `_mark_battle_economy`.
  - Broadcasts: `resource_update` (sorcery-points), `spell_slot_update`
    (the consumed slot), `feature_used` (announces "Spell slot →
    Sorcery Points").

- `POST /api/campaign/{cid}/use_font_of_magic_to_slot`
  - Body: `{character_id, slot_level: int, override?}`
  - Validates Sorcerer Lv 2+, sorcery points ≥ cost-table value
    for `slot_level`, slot_level ≤ 5.
  - Decrements sorcery points; increments the slot counter (but
    NOT past max — the "extra ephemeral slot" RAW edge case lives
    in the slot row's `current` value, with a `font_of_magic_extra`
    flag that the long-rest path strips).
  - Marks bonus slot.
  - Broadcasts same shape as above.

### Sheet wiring

Zara's `class_features` already has a `font-of-magic` row with
`_FEATURE_ECONOMY` curation (slot: 'bonus'). The sheet's
`_bindUseButtons` handler at `sheet_dnd5e.html:5076` needs two
new branches modeling the v2.49.114 Flurry of Blows pattern, but
with a *direction picker* — the click pops a small modal asking
"Convert which way?" with two radio rows (slot → points / points →
slot) + a slot-level dropdown.

### Tests

- `tests/harness/test_use_font_of_magic.py` — 6 tests:
  - L1 slot → 1 sorcery point (happy path)
  - L3 slot → 3 sorcery points
  - 2 points → L1 slot (RAW cost table)
  - 3 points → L2 slot
  - 5 points → L3 slot
  - 409 `no_slot` when sacrificing an empty slot level
  - 409 `not_enough_points` when below the cost-table threshold
  - 409 `wrong_class` for a non-Sorcerer
  - 409 `slot_too_high` when requesting L6+

**Exit criterion:** the Sorcerer's Sorcery Points counter is a real,
spendable resource. The Sorcerer class table row goes 🟢 → ✅.

---

## Phase 1 — Metamagic infrastructure

**Goal:** the picker modal + the pending-buff machinery exist; one
Metamagic option (Empowered Spell — simplest mechanics) ships as a
walking-skeleton.

### The picker modal

A new `_showMetamagicPicker(known_options)` helper in
`sheet_dnd5e.html`, modeled on `_showUpliftModal` (v2.16.0). It
opens when the player clicks a Cast button on a leveled spell IF
they have ≥ 1 sorcery point AND know at least one Metamagic option
applicable to that spell. Each row is a Metamagic option name +
cost; the player picks one and clicks Confirm, OR clicks Skip to
cast without Metamagic. The picker returns the chosen option's
slug, which the cast handler attaches to the `/cast_spell` body
as `metamagic_slug`.

### The known-options sheet field

Sorcerers learn 2 Metamagic options at Lv 3, 1 more at Lv 10,
1 more at Lv 17. The sheet's `class_features` entry for Metamagic
should carry the picked options as a list:

```json
{
  "key": "metamagic",
  "name": "Metamagic",
  "options_known": ["empowered-spell", "twinned-spell"],
  ...
}
```

The picker reads this list to drive its row enumeration.

### The pending-buff machinery

When the player picks Empowered Spell, the cast handler:

1. POSTs `/use_metamagic_empowered_spell` with `{character_id, slot_level}`.
2. That endpoint decrements 1 sorcery point + installs the
   `metamagic-empowered-pending` buff on the caster (duration 1
   round, concentration False, effects.metamagic_option =
   "empowered-spell", effects.rerolls_available = sorcerer_cha_mod).
3. The endpoint returns 200; the cast handler then POSTs to
   `/cast_spell` as usual.
4. `/cast_spell` checks for the `metamagic-empowered-pending` buff
   on the caster. If present, applies the option's effect (Empowered
   Spell: reroll up to CHA-mod damage dice once; replace the worse
   with the new). The buff drops after the cast resolves.

### Empowered Spell (Phase 1 walking skeleton)

PHB p.102 — "When you roll damage for a spell, you can spend 1
sorcery point to reroll a number of the damage dice up to your
CHA modifier (min 1). You must use the new rolls. You can use this
Metamagic option once per spell cast."

Implementation:

1. `POST /api/campaign/{cid}/use_metamagic_empowered_spell` — spend
   1 SP, install the pending buff.
2. In `/cast_spell`, after the damage roll, check for the pending
   buff. If found, scan the damage roll's individual die results;
   reroll up to CHA-mod of the lowest values; replace the originals
   with the new rolls if higher; recompute the total.
3. Add the rerolled-damage detail to the broadcast.

**Tests:**
- `tests/harness/test_use_metamagic_empowered.py` — happy path
  (Zara casts Fireball with Empowered Spell, observe rerolled
  damage dice in the breakdown), no-SP rejection, wrong-class
  rejection, picker-skipped cast still works (no buff installed).

**Exit criterion:** Empowered Spell works end-to-end on Zara
casting Fireball. The picker modal is generic enough to support
the other Metamagic options without reshape.

---

## Phase 2 — Quickened Spell + Twinned Spell

The two "feel like a different class" options. Both are 1- or
2-cost Metamagic that turn a leveled spell into something
mechanically different.

### Quickened Spell (PHB p.102, 2 SP)

"When you cast a spell that has a casting time of 1 action, you
can spend 2 sorcery points to change the casting time to 1 bonus
action for this casting."

Implementation:
1. `POST /api/campaign/{cid}/use_metamagic_quickened_spell` — spend
   2 SP, install `metamagic-quickened-pending` buff.
2. In `/cast_spell`, check for the buff. If present, the spell's
   action slot becomes "bonus" instead of "action" — the
   `_mark_battle_economy` call uses `"bonus"` for this cast.
3. Buff drops after the cast.

**Edge case:** Quickened Spell + a spell already cast as a bonus
action this turn? RAW PHB p.202 — "you can't cast another spell
during the same turn, except for a cantrip with a casting time of
1 action." So Quickening a leveled spell into a bonus action while
you've already used your action for any spell ≠ cantrip should
reject. The 409 path: `over_quickened_limit`.

### Twinned Spell (PHB p.102, cost = slot level, min 1)

"When you cast a spell that targets only one creature and doesn't
have a range of self, you can spend a number of sorcery points
equal to the spell's level to target a second creature in range
with the same spell."

Implementation:
1. `POST /api/campaign/{cid}/use_metamagic_twinned_spell` — spend
   `slot_level` SP, install `metamagic-twinned-pending` buff.
2. The picker UI lets the player pick TWO targets instead of one.
3. In `/cast_spell`, check for the buff + the second target. If
   both present, the cast resolves against BOTH targets — same
   `target_combatant_ids` multi-target loop the v2.49.85 weapon
   attack work added.

**Edge case:** Twinned Spell's restrictions — "only one creature",
"doesn't have a range of self". The picker should filter the
Metamagic options to only show Twinned for spells that qualify
(use the spell catalog's `aoe_targets: 1` + `range != "Self"`
filter from the spell JSON).

**Tests:**
- Quickened: happy path (Zara Quickens a Cure Wounds; observe
  bonus-slot marked instead of action), no-SP, already-cast-bonus-
  action edge case.
- Twinned: happy path (Zara Twins a Charm Person; two targets
  both get charmed), can't-twin-AoE edge case, cost-equal-slot-
  level rejection on insufficient SP.

**Exit criterion:** Quickened + Twinned both work end-to-end. The
picker filters options correctly per spell.

---

## Phase 3 — Subtle / Distant / Heightened / Extended / Careful

The remaining five RAW Metamagic options, in roughly increasing
implementation complexity. Each gets its own endpoint + tests.

- **Subtle Spell (1 SP)** — cast without V/S components. Mechanical
  effect: spell is invisible / inaudible to passive observers.
  SimpleVTT doesn't model V/S today; the cast announces normally.
  Filed as informational-only for v1 (the buff installs + the
  feature_used card mentions Subtle; no engine change).
- **Distant Spell (1 SP)** — double the spell's range, or cast a
  touch spell at 30 ft. Mechanical effect: range-check (v2.49.71-84)
  doubles the parsed range for this cast. Buff carries
  `effects.range_doubled: True`; the v2.49.75 `_check_cast_range`
  reads it.
- **Heightened Spell (3 SP)** — target has disadvantage on its first
  save vs the spell. Buff carries `effects.disadvantage_on_first_save:
  True`; the v2.30.0+ save-auto-resolution path reads it for the
  target's save roll.
- **Extended Spell (1 SP)** — double the spell's duration up to 24h.
  Mechanical effect: buff installed by the spell has `duration_rounds
  × 2`. The buff-install path in `/cast_spell` reads the pending
  Metamagic buff and multiplies.
- **Careful Spell (1 SP)** — when you cast a save-for-half AoE,
  choose CHA-mod allies who auto-pass. Buff carries
  `effects.careful_target_combatant_ids: [...]`; the AoE save loop
  in `/place_aoe` skips the save roll for those IDs.

**Phase 3 deliverable:** one commit per option (5 commits total),
each shipping the endpoint + the consumer-side integration in
`/cast_spell` or `/place_aoe` + harness tests.

**Exit criterion:** all 8 RAW Metamagic options work end-to-end.
The Sorcerer Lv 3 Metamagic row flips ⚪ → ✅.

---

## Phase 4 — Sheet-side Metamagic picker polish

**Goal:** the modal looks nice + the keyboard flow works on iPad.

Phase 1's `_showMetamagicPicker` ships a basic modal. Phase 4
adds:

- Per-option tooltip (the PHB description text).
- Disabled rows for options the spell doesn't qualify for
  (Twinned on AoE, Distant on Self spells, etc.) with a hint
  explaining why.
- Keyboard shortcuts (Q for Quickened, T for Twinned, etc.).
- Cost preview ("Empowered: 1 SP" / "Twinned: 3 SP at this slot").
- iPad-friendly tap targets (mirror the v2.49.96 drawer-tab
  44 px floor).

---

## Phase 5 — CI integration + coverage

- Update `.github/workflows/test-harness.yml` if the suite gets
  big enough to need parallelization.
- Update `docs/test-harness-coverage.md` with a new "Sorcerer
  Metamagic" section.
- Update the spell-validation suite plan (v2.49.103) — a
  Metamagic-applied spell should still pass the Phase 2A damage
  range-check (Empowered Spell within bounds, Quickened bonus-
  slot doesn't break the slot validation, etc.).

---

## Open questions

- **Multi-class Sorcerers.** A Lv 1/Sorcerer Lv 5 / Wizard Lv 5
  multiclass has Sorcery Points + a separate spell-slot pool.
  Phase 0's `slot_level → points` conversion uses the Sorcerer
  spell slots only RAW (PHB p.165 multiclassing). The endpoint
  should validate the slot is from a Sorcerer class, not a
  multiclassed Wizard slot. Filed.
- **Sorcerous Origin features.** Draconic Bloodline + Wild Magic
  + Storm Sorcery etc. each add their own features at Lv 1 / 6 /
  14 / 18. Not in scope here; tracked separately under the Sorcerous
  Origin subclass row in `class-content-status.md`.
- **Twinned + Magic Missile.** RAW debate — does Magic Missile
  count as "targets only one creature" since each dart can choose?
  Most rulings say no (can't twin MM). The picker filter should
  exclude MM. Filed as a per-spell tag (`twin_eligible: False`)
  on the JSON.
- **Empowered Spell + multi-target attacks.** v2.49.85 multi-target
  weapon attacks roll damage per target. If a future commit Twins
  a spell AND Empowers it, which target's dice get rerolled?
  RAW says "the damage roll" singular, so probably the first
  target. Filed.

---

## Risks

| Risk | Mitigation |
|---|---|
| Picker UI fights the existing uplift modal (Sneak Attack / Divine Smite). | The two modals can co-exist if they fire sequentially — uplift modal first (already opens on .atk-strike), Metamagic picker second (opens on .sp-cast). Order tested in Phase 1. |
| Twinned Spell + multi-target schema collision. | Twinned's "second target" rides through `target_combatant_ids` — the same field the v2.49.85 weapon multi-target uses. `/cast_spell` already accepts it; just need to plumb the buff signal through to the resolution loop. |
| Buff key collision between pending-Metamagic and other buffs. | All Metamagic pending buffs use the `metamagic-{slug}-pending` prefix. No other buff uses `metamagic-` today. Reserved namespace. |
| Demo Zara has finite Sorcery Points (5 at Lv 5). | Harness tests reset via `/long_rest` between cases; same pattern Patient Defense / Flurry tests use. |

---

## Status tracking

- [✅] Phase 0 — Font of Magic conversions + harness (v2.49.120, v2.49.121-123 polish)
- [✅] Phase 1 — Picker + pending-buff machinery + Empowered Spell (v2.49.124 walking skeleton: endpoint + sheet button + save-for-half single-target integration; v2.49.125 multi-beam pool reroll for Scorching Ray / Eldritch Blast / Fire Bolt. AoE multi-target loop integration deferred to Phase 1.5; styled picker modal deferred to Phase 4.)
- [ ] Phase 2 — Quickened + Twinned
- [ ] Phase 3a — Subtle Spell
- [ ] Phase 3b — Distant Spell
- [ ] Phase 3c — Heightened Spell
- [ ] Phase 3d — Extended Spell
- [ ] Phase 3e — Careful Spell
- [ ] Phase 4 — Picker polish
- [ ] Phase 5 — CI / coverage doc updates

Each checkbox flips green as the corresponding commit lands; the
status line at the top of this doc is updated in the same commit.
