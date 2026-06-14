# Charged magic items — design plan

**Status:** ✅ complete — every named item shipped. Phase 0 ✅ (doc filed + wiki surface, v2.262.0); Phase 1 ✅ (Wand of Web ✅ v2.263.0, Wand of Polymorph ✅ v2.264.0, Wand of Binding ✅ v2.266.0, Wand of Enemy Detection ✅ v2.277.0 — closes the phase + the plan); Phase 2 ✅ (Staff of Frost ✅ v2.267.0, Staff of Swarming Insects ✅ v2.268.0, Staff of Thunder and Lightning ✅ v2.272.0, Staff of Power ✅ v2.274.0); Phase 3 ✅ (Ring of the Ram ✅ v2.269.0 — the `action_kind: "attack"` shape; Gem of Seeing ✅ v2.270.0 — the `action_kind: "buff"` shape; Horn of Blasting ✅ v2.271.0 — the first charge-less `attack_aoe` item); Phase 4 ✅ (Wand of Wonder ✅ v2.273.0 — the `action_kind: "random_table"` d100-table shape); Phase 5 ✅ (Wand of the War Mage +1/+2/+3 ✅ v2.265.0 / v2.276.0 — passive spell-attack rider, all three tiers).

**Authors:** rolling
**Last updated:** 2026-06-14

A plan to extend the **existing** charge/action substrate to the remaining
SRD 5e charged magic items. The engine is already load-bearing — this plan is
a backlog of drop-ins grouped by which existing shape each item fits, plus two
genuinely-new shapes (a non-spell charge action and a random-effect table)
that need a small substrate addition.

## What already exists (do NOT rebuild)

The charge engine shipped across the v2.158.x "Magic-items Phase 4–5" run and
later item commits. The pieces, all in `app/routes/tabletop_routes.py`:

- **`_MAGIC_ITEM_ACTIONS`** (~line 32877) — slug → action config. Three shapes
  already in production:
  1. **Single spell-cast wand** (`wand-of-magic-missiles`,
     `wand-of-fireballs`, `wand-of-lightning-bolts`): `spell_slug` +
     `min_charges`/`max_charges` + `base_slot_level`. Spending _n_ charges
     casts the spell at `base_slot_level + (n - min_charges)`.
  2. **Multi-action staff** (`staff-of-healing`, `staff-of-fire`,
     `staff-of-charming`): an `actions` sub-map keyed by `action_key`, each
     entry its own spell + charge cost.
  3. **State-toggle** (`flame-tongue`): `actions` flip a per-item boolean
     (`_lit`) with no charges/resource row.
- **`/use_item_action`** endpoint — dispatches by `slug` + `action_key`,
  enforces the per-payload `requires_attunement` gate, decrements the resource
  row, broadcasts the cast/result.
- **Per-item charge resource rows** — auto-created in the demo seed
  (`resource_key`), surfaced on the sheet.
- **RAW recharge dice** (v2.158.86) — a resource row carrying a
  `charge_recovery` dice string (e.g. `"1d6+1"`) rolls that expression on the
  matching rest instead of a full refill. Lives in `_refill_feature_uses`'s
  caller (~line 80782). **This is the "regain 1dX+Y at dawn" substrate — it is
  done.** Items map "daily at dawn" → long rest.
- **Passive flag/derived substrate** (`_MAGIC_ITEM_PASSIVES` +
  `_equipped_item_effects`) — for always-on bonuses that need no activation
  (e.g. Bracers of Archery's `ranged_bow_damage_bonus`, v2.261.0).

So: spell wands, multi-action staves, dice recharge, attunement gating, and
passive bonuses are all **already solved**. This plan only adds *content* on
those rails, plus two new shapes.

## Remaining SRD charged items, grouped by shape-fit

### Phase 1 — Single-spell wands (drop into shape #1)

Pure content commits: add a `_MAGIC_ITEM_ACTIONS` row + a demo seed + a harness
test each. No engine change.

- **Wand of Web** (DMG p.213, rare, attunement) — ✅ **shipped v2.263.0**. 7
  charges, 1 charge casts Web (save DC 15); RAW no upcast so
  `min_charges == max_charges == 1`, `base_slot_level: 2`,
  `charge_recovery: "1d6+1"`. Seeded on Thalindra (Wizard).
- **Wand of Binding** (DMG p.211, rare, attunement) — ✅ **shipped v2.266.0**.
  7 charges, 1 charge casts Hold Person (save DC 15); RAW no upcast on the wand
  so `min_charges == max_charges == 1`, `base_slot_level: 2`,
  `charge_recovery: "1d6+1"`. Seeded on Brother Tavik Stonebrow (Cleric). RAW
  also casts Hold Monster for 5 charges — deferred until that spell is
  catalogued (would become a shape #2 multi-action staff entry).
- **Wand of Polymorph** (DMG p.212, rare, attunement) — ✅ **shipped
  v2.264.0**. 7 charges, 1 charge casts Polymorph (DC 15); RAW no upcast so
  `min_charges == max_charges == 1`, `base_slot_level: 4`,
  `charge_recovery: "1d6+1"`. Seeded on Zara Emberfire (Sorcerer).
- **Wand of Enemy Detection / Wand of Secrets** — utility detection; ship as a
  self-targeted "reveal" chat card (no save). Lower priority (no combat math).

### Phase 2 — Multi-action staves (drop into shape #2)

Each is one `actions` sub-map commit. The staff substrate already handles N
distinct action_keys + per-action charge costs.

- **Staff of Frost** (DMG p.202, very rare, attunement) — ✅ **shipped
  v2.267.0**. 10 charges (regains 1d6+4 at dawn). v1 ships the marquee Cone of
  Cold action (5 charges → 8d8 cold, CON save, 60-ft cone) through the
  generalized save-for-half AoE-damage handler; `min == max == 5`, `save_dc:
  "spell"`. Seeded on Thalindra Moonwhisper (Wizard). Fog Cloud (1) / Ice Storm
  (4) / Wall of Ice (4) + the cold resistance are GM-narrated.
- **Staff of Thunder and Lightning** (DMG p.202, very rare, attunement) —
  ✅ **shipped v2.272.0**. 5 charges (regains 1d6+1 at dawn). v1 ships the
  marquee Thunder action (2 charges → 2d6 thunder, CON save, 60-ft-radius
  thunderclap centered on the wielder) through the generalized save-for-half
  AoE-damage handler; `min == max == 2`, flat `save_dc: 17` (RAW Thunder is
  DC 17, not the `"spell"` sentinel). Seeded on Magnus Hexbinder (Bronze
  Dragonborn Warlock). The deafen-1-min-on-fail rider + the Lightning /
  Lightning Strike / combined 5-charge properties are GM-narrated.
- **Staff of Swarming Insects** (DMG p.202, rare, attunement) — ✅ **shipped
  v2.268.0**. 10 charges (regains 1d6+4 at dawn). v1 ships the marquee Insect
  Plague action (5 charges → 4d10 piercing, CON save, 20-ft-radius sphere)
  through the generalized save-for-half AoE-damage handler; `min == max == 5`,
  `save_dc: "spell"`. Seeded on Mira Greenleaf (Druid). Giant Insect (4, the
  summon) is GM-narrated.
- **Staff of Power** ✅ v2.274.0 (DMG p.202, very rare, attunement) — the big
  one: +2 weapon/AC/save passive (shape #4 below) **plus** a multi-action spell
  list (cone of cold, fireball, globe of invulnerability, hold monster,
  levitate, lightning bolt, magic missile, ray of enfeeblement, wall of force).
  The +2 AC / save / spell-attack passive bonuses fold into
  `_MAGIC_ITEM_PASSIVES`; the three damaging spells (Fireball / Lightning Bolt
  10d6 5th-level DEX, Cone of Cold 8d8 CON) route through shape #2's
  save-for-half AoE handler at the wielder's spell save DC. Seeded on Thalindra
  Moonwhisper (Wizard) with a 20-charge / 2d8+4 resource row. The marquee sheet
  button surfaces Fireball; Lightning Bolt + Cone of Cold are API-reachable.
  The non-damaging spells and the "retributive strike" break action are
  GM-narrated (deferred to a follow-up).

### Phase 3 — Non-spell charge actions (NEW shape #5)

These spend charges to do something that isn't a catalogued spell cast. Needs a
small handler addition: an `action_kind: "attack"` / `"heal"` / `"buff"` branch
in `/use_item_action` that builds the roll inline instead of resolving a
`spell_slug`.

- **Ring of the Ram** (DMG p.193, rare, attunement) — ✅ **shipped v2.269.0**.
  The first non-spell charge action: 3 charges; spend 1–3 to make a ranged
  force attack (+7 to hit, 2d10 force per charge) that can shove. Shipped the
  new `action_kind: "attack"` branch + `_use_item_action_attack` handler (1d20
  + `to_hit` vs the target's AC, `dice_per_charge` scaled by charges spent,
  crit doubling), recharge `"1d3"` at dawn. Seeded on Garrik Ironside
  (Fighter). The 5-ft-per-charge shove is GM-narrated in v1.
- **Gem of Seeing** (DMG p.171, rare, attunement) — ✅ **shipped v2.270.0**.
  The first `action_kind: "buff"` charge action: 3 charges; spend 1 for
  truesight 60 ft for 10 min. Shipped the new `action_kind: "buff"` branch +
  `_use_item_action_buff` handler (decrements the charge, installs the
  `truesight` buff template — `effects: {truesight_ft: 60}`, 100 rounds — on
  the wielder's own combatant via the existing `_install_buff` substrate),
  recharge `"1d3"` at dawn. Seeded on Rowan Quickbow (Ranger). The mechanical
  truesight reads (auto-detect illusions, see invisible, see ethereal) are
  GM-narrated in v1.
- **Horn of Blasting** (DMG p.174, uncommon, no attunement) — ✅ **shipped
  v2.271.0**. The first charge-less item action: a 30-ft-cone DC 15 CON save
  → 5d6 thunder + deafened 1 min on a fail, half + no deafen on a pass.
  Shipped the `_use_item_action_horn_of_blasting` handler (`action_kind:
  "attack_aoe"`) — reuses the necklace save-for-half AoE-damage loop but with
  NO resource row / no charge gate, and installs the `deafened` condition only
  on a failed save (via `_resolve_feature_save`'s `condition_buff`). Seeded on
  Krieger Stonefist (Barbarian). The RAW 20% self-destruct per blow is
  GM-narrated in v1. **Closes Phase 3.**

The new shape is the minimal generalization: the dispatch already knows the
slug + action_key + charge spend; this just routes the *effect* through the
existing attack/heal/buff resolvers instead of the spell resolver.

### Phase 4 — Random-effect table (NEW shape #6)

- **Wand of Wonder** (DMG p.213, rare, attunement) — ✅ **shipped v2.273.0**. 7
  charges; each use rolls d100 on the `_WAND_OF_WONDER_TABLE` chaos table (21
  inclusive `[lo, hi]` bands — cast a random spell, slow, stinking cloud, rain,
  butterflies, lightning bolt, fireball, petrification, etc.). The
  `action_kind: "random_table"` branch routes to `_use_item_action_wand_of_wonder`,
  which decrements 1 charge, rolls d100 (or honors a `force_roll` 1-100
  override), looks up the row, broadcasts `feature_used`, and returns
  `{roll, row_key, effect, description, resource}`. Per-row sub-effects are
  GM-adjudicated in v1 (the content-on-a-shape strategy) rather than auto-cast —
  landing the random-table substrate with zero per-effect engine work. Seeded
  on Zara Emberfire (Draconic Sorcerer); new sheet-UI `random-table` picker
  (no target/param + a local toast of the rolled effect). Future work could
  auto-dispatch the spell-cast rows through the shape #1 resolver.

### Phase 5 — Passive +bonus "wands" (drop into `_MAGIC_ITEM_PASSIVES`)

No charges at all — these are attack/AC riders, identical in shape to Bracers
of Archery (v2.261.0). One flag field + accumulator + attack-path read each.

- **Wand of the War Mage, +1/+2/+3** (DMG p.211, uncommon–rare, attunement) —
  ✅ **shipped v2.265.0**. +X to spell attack rolls; ignores half cover. A
  `spell_attack_bonus` summed-int passive in `_equipped_item_effects` (the
  slug defaults to +1; the +2/+3 tiers ride a per-item `_spell_attack_bonus`
  rider), surfaced on `/sheet-json derived` and folded into the caster's
  spell attack roll at cast-resolution time. Seeded on Magnus Hexbinder
  (Warlock) at +2; the very-rare **+3** tier ships on Zara Emberfire
  (Sorcerer) as of v2.276.0, completing the +1/+2/+3 set. The
  ignore-half-cover clause is GM-narrated in v1.

## Phasing & commit cadence

One item = one commit = one version bump, per CLAUDE.md. Within a phase the
items are independent and ship in any order. Recommended sequence:

1. **Phase 1** items first (zero engine risk, pure content on shape #1).
2. **Phase 5** Wand of the War Mage (zero engine risk, Bracers clone).
3. **Phase 2** staves (zero engine risk, content on shape #2).
4. **Phase 3** new `action_kind` shape (one small engine commit to add the
   branch, then content commits per item).
5. **Phase 4** Wand of Wonder last (largest new surface).

Each content commit lands ≥1 harness test (happy path asserting the WS
broadcast + the resource decrement, plus an error path — wrong action_key /
no charges / attunement gate) per the harness-discipline rule, and bumps the
total-test-count line in `docs/test-harness-coverage.md`.

## Why this matters

The charge engine is one of SimpleVTT's deepest automation surfaces, but its
*content* coverage stops at ~3 wands + 3 staves. The remaining SRD charged
items are the long tail GMs actually hand out (Staff of Power, Wand of Wonder,
Ring of the Ram, Gem of Seeing). Every Phase 1/2/5 item is a near-zero-risk
drop-in on rails that already exist and are already tested — high content yield
per commit. Phases 3–4 add two small, well-scoped engine shapes that unlock the
rest of the tail.

## Out of scope (v1)

- Retributive strike / staff-break self-destruct actions (Staff of Power, Staff
  of the Magi) — a "destroy item, AoE" branch; file separately.
- Charge-overload risk tables (Staff of the Magi absorb/overload) — niche.
- Attunement-cap enforcement changes — unchanged; the existing `/attune`
  runtime cap stands.
