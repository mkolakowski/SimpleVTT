# Charged magic items — design plan

**Status:** 🟠 partial — Phase 0 ✅ (doc filed + wiki surface, v2.262.0); Phase 1 in progress (Wand of Web ✅ v2.263.0, Wand of Polymorph ✅ v2.264.0). Phases 2–5 unstarted.

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
- **Wand of Binding** (DMG p.211, rare, attunement) — 7 charges; hold monster
  (5 charges) / hold person (1+). Could be shape #1 (hold-monster) or a
  multi-action staff if both spells are wanted. Start with hold person.
- **Wand of Polymorph** (DMG p.212, rare, attunement) — ✅ **shipped
  v2.264.0**. 7 charges, 1 charge casts Polymorph (DC 15); RAW no upcast so
  `min_charges == max_charges == 1`, `base_slot_level: 4`,
  `charge_recovery: "1d6+1"`. Seeded on Zara Emberfire (Sorcerer).
- **Wand of Enemy Detection / Wand of Secrets** — utility detection; ship as a
  self-targeted "reveal" chat card (no save). Lower priority (no combat math).

### Phase 2 — Multi-action staves (drop into shape #2)

Each is one `actions` sub-map commit. The staff substrate already handles N
distinct action_keys + per-action charge costs.

- **Staff of Frost** (DMG p.202, very rare, attunement) — 10 charges; cone of
  cold (5), fog cloud (1), ice storm (4), wall of ice (4).
- **Staff of Thunder and Lightning** (DMG p.202) — 5 charges; per-property
  actions (lightning, thunder, etc.).
- **Staff of Swarming Insects** (DMG p.202) — 10 charges; giant insect (4),
  insect plague (5).
- **Staff of Power** (DMG p.202, very rare, attunement) — the big one: +2
  weapon/AC/save passive (shape #4 below) **plus** a multi-action spell list
  (cone of cold, fireball, globe of invulnerability, hold monster, levitate,
  lightning bolt, magic missile, ray of enfeeblement, wall of force). The
  passive bonuses fold into `_MAGIC_ITEM_PASSIVES`; the spells into shape #2.
  Defer the "retributive strike" break action to a follow-up.

### Phase 3 — Non-spell charge actions (NEW shape #5)

These spend charges to do something that isn't a catalogued spell cast. Needs a
small handler addition: an `action_kind: "attack"` / `"heal"` / `"buff"` branch
in `/use_item_action` that builds the roll inline instead of resolving a
`spell_slug`.

- **Ring of the Ram** (DMG p.193, rare, attunement) — 3 charges; spend 1–3 to
  make a ranged force attack (+7 to hit, 2d10 force per charge) that can shove.
  → `action_kind: "attack"`, damage `"{n}d10"` force, recharge `"1d3"` at dawn.
- **Gem of Seeing** (DMG p.171, rare, attunement) — 3 charges; spend 1 for
  truesight 60 ft for 10 min. → `action_kind: "buff"`, installs a `truesight`
  buff template (compose with the existing buff substrate).
- **Horn of Blasting** (DMG p.174, uncommon) — thunder AoE (5d6, DC 15) + deafen;
  no charges, but a per-use "explodes on a 6 of d100" risk. → `action_kind:
  "attack"` AoE, no resource row.

The new shape is the minimal generalization: the dispatch already knows the
slug + action_key + charge spend; this just routes the *effect* through the
existing attack/heal/buff resolvers instead of the spell resolver.

### Phase 4 — Random-effect table (NEW shape #6)

- **Wand of Wonder** (DMG p.213, rare, attunement) — 7 charges; each use rolls
  d100 on a 19-row effect table (cast a random spell, slow, stinking cloud,
  rain, butterflies, etc.). Needs a `_WAND_OF_WONDER_TABLE` data block + a
  `action_kind: "random_table"` branch that rolls d100, picks the row, and
  dispatches that row's sub-effect (some rows are spell casts → reuse shape #1
  resolver; some are flavor chat cards). This is the most involved phase —
  file it last.

### Phase 5 — Passive +bonus "wands" (drop into `_MAGIC_ITEM_PASSIVES`)

No charges at all — these are attack/AC riders, identical in shape to Bracers
of Archery (v2.261.0). One flag field + accumulator + attack-path read each.

- **Wand of the War Mage, +1/+2/+3** (DMG p.211, uncommon–rare, attunement) —
  +X to spell attack rolls; ignores half cover. → a `spell_attack_bonus`
  summed-int passive read at spell-attack resolution time.

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
