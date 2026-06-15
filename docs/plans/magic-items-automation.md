# Magic-item automation — design plan

**Status:** ✅ framework shipped end-to-end (re-audited 2026-06-11, v2.159.31 — SRD audit refresh). Phases 1–8 all closed across v2.158.74 → v2.159.25 (32 PATCH commits + the v2.159.0 MINOR milestone): passives → attunement → actions → on-hit riders → uplifts → templates → nat-20 hooks → AoE confirm modals → line/sphere/cone geometry → Javelin of Lightning → Necklace of Fireballs → Wand of Fear → Arrow of Slaying → Sun Blade → Goggles of Night (Phase 8a–8p).

**Content tail (Phase 9 — NEW).** ~42 of 292 items now carry non-empty `actions`/`passives`; 250 still have `actions: []`. The remaining work is content-only — each item is a small commit picking from the established Phase 1–8 templates. See the [SRD 5e Audit (2026-06-11 refresh)](../../TODO.md#srd-5e-audit-2026-06-11-refresh) for the magic-item action backfill prioritisation.

**Authors:** rolling
**Last updated:** 2026-06-15

---

## Phase 9.1 — stub triage (v2.344.5, corrected v2.345.1)

After the v2.316–v2.344 content sprint, **235/239 SRD magic items are wired** (registered + collectible).

> **Count correction (v2.345.1).** The original v2.344.5 figures ("133 mechanical / 108 bare stubs / ~26 automatable") were computed by inspecting only the *static* `_MAGIC_ITEM_PASSIVES` catalog payload. That under-counted the items wired via a **per-instance seed rider** — where the catalog entry is intentionally generic (`requires_attunement` only) and the specifics ride the inventory item (`_resistance_type`, `_ability_set`, `_ac_bonus`, …). Four items flagged as "bare stubs" are in fact already mechanically live + tested via the `_resistance_type` rider: **`armor-of-resistance`, `ring-of-resistance`, `dragon-scale-mail`, `ring-of-elemental-command`** (each has a `test_item_<slug>.py`). Plus **`luck-blade`** was wired in v2.345.0 (Bucket B). Corrected counts (post-v2.345.0): of 241 wired slugs, **138 are functional** (134 catalog-mechanical + 4 rider-only) and **103 are genuinely-bare GM-narrated stubs**. The actionable subset drops to **~21 items**; the remaining **~82 stay announce-only by design** (archetype J — summons, planar travel, wish, one-shot consumables, containers, capture/imprison, exploration utility). Counts are approximate at the margins (a few items straddle two buckets).

### Bucket A — charge-cast a save/attack spell → `_MAGIC_ITEM_ACTIONS` cast-spell template (~10)

The strongest template (the Wand of Fear / charged-wand pattern already shipped). Each casts a defined spell with a fixed save DC or spell attack; wire the action + DC + condition/damage dispatch.

| Slug | RAW effect | Wire as |
|---|---|---|
| `pipes-of-haunting` | DC 15 WIS or frightened 1 min (30 ft) | save → `frighten` |
| `rod-of-rulership` | DC = 8+prof+CHA WIS save or charmed/obey 1 min | save → charmed condition |
| `trident-of-fish-command` | dominate beast (DC 15) on a beast | cast-spell action (charge) |
| `ring-of-animal-influence` | animal friendship / fear / speak-with-animals (charges) | cast-spell action |
| `circlet-of-blasting` | scorching ray (3 × spell attack, 2d6 fire) | spell-attack action |
| `ring-of-shooting-stars` | ranged radiant motes + dancing lights/light | spell-attack / damage action |
| `robe-of-scintillating-colors` | DC 15 WIS or attackers gain advantage (dazzle) | save → debuff condition |
| `rope-of-entanglement` | DC 15 STR or restrained | save → restrained |
| `wind-fan` | gust of wind (DC 13) | cast-spell action |
| `medallion-of-thoughts` | detect thoughts (DC 13) | cast-spell action (utility) |

### Bucket B — passive numeric buff → mechanical `_MAGIC_ITEM_PASSIVES` (`effects.*`) (~9)

Always-on bonuses the engine already reads (resistance via `_resistance_halve`, save/AC/stat passives).

| Slug | RAW effect | Wire as | Status |
|---|---|---|---|
| `armor-of-resistance` | resistance to one damage type | `_resistance_type` rider | ✅ already live (mis-counted) |
| `ring-of-resistance` | resistance to one damage type | `_resistance_type` rider | ✅ already live (mis-counted) |
| `dragon-scale-mail` | resistance to the dragon's damage type | `_resistance_type` rider | ✅ already live (mis-counted) |
| `luck-blade` | +1 to all saves (the +1 weapon is baked) | `effects.save_bonus` | ✅ shipped v2.345.0 |
| `adamantine-armor` | crits against you become normal hits | `effects.crits_become_normal` (new) | ⚪ |
| `staff-of-the-magi` | +2 spell attack & save DC | `effects.spell_attack_bonus` / `spell_dc_bonus` (new) | ⚪ |
| `staff-of-the-woodlands` | +2 spell attack & save DC | same | ⚪ |
| `arrow-catching-shield` | +2 AC vs ranged attacks | conditional AC passive | ⚪ |
| `shield-of-missile-attraction` | resistance to ranged-weapon damage + curse | `_resistance_type` rider (conditional) | ⚪ |

### Bucket C — on-hit / crit weapon rider → `_MAGIC_ITEM_ATTACK_RIDERS` (~7)

| Slug | RAW effect | Wire as |
|---|---|---|
| `staff-of-withering` | on hit: +2d10 necrotic + DC 15 CON or disadvantage | `on_hit_save: damage_condition` |
| `staff-of-striking` | expend 1–3 charges → +1d6 force per charge on hit | on-hit `bonus_dice` |
| `sword-of-wounding` | recurring 1d4 necrotic/turn, DC 15 CON to end | on-hit recurring-damage condition (new) |
| `oathbow` | vs sworn enemy: +3d6 piercing + advantage | conditional rider (declared-enemy state) |
| `berserker-axe` | +1 (baked); HP-max +level while attuned; berserk save | HP-max passive + on-damage WIS save |
| `talisman-of-pure-good` | 6d6 radiant to non-good on touch | situational rider (low priority) |
| `talisman-of-ultimate-evil` | 6d6 necrotic to non-evil on touch | situational rider (low priority) |

### Bucket D — inherently GM-narrated (stays announce-only, archetype J) (~82)

No clean engine template; the effect is narrative, out-of-combat, or needs systems SimpleVTT doesn't model. Grouped:

- **Summons:** figurine-of-wondrous-power, horn-of-valhalla, ring-of-djinni-summoning, staff-of-the-python, bowl/brazier/censer-of-commanding-\*-elementals, stone-of-controlling-earth-elementals, elemental-gem, efreeti-bottle, dancing-sword, animated-shield
- **Planar travel / teleport:** amulet-of-the-planes, cubic-gate, well-of-many-worlds, rod-of-security, helm-of-teleportation, plate-armor-of-etherealness, oil-of-etherealness, cape-of-the-mountebank
- **Wish / fate / artifact:** ring-of-three-wishes, deck-of-many-things, deck-of-illusions, orb-of-dragonkind, sphere-of-annihilation, talisman-of-the-sphere
- **Item / structure creation:** manual-of-golems, marvelous-pigments, bag-of-beans, feather-token, instant-fortress, folding-boat, robe-of-useful-items, bag-of-tricks
- **Containers / extradimensional:** bag-of-holding, handy-haversack, efficient-quiver, portable-hole, bag-of-devouring
- **One-shot consumables:** dust-of-disappearance, dust-of-dryness, dust-of-sneezing-and-choking, oil-of-slipperiness, oil-of-sharpness, philter-of-love, potion-of-poison, restorative-ointment, sovereign-glue, universal-solvent, decanter-of-endless-water, eversmoking-bottle
- **Capture / imprison / bind:** iron-bands-of-binding, iron-flask, mirror-of-life-trapping, dimensional-shackles
- **Exploration / utility:** chime-of-opening, immovable-rod, rope-of-climbing, horseshoes-of-a-zephyr, horseshoes-of-speed, lantern-of-revealing, rod-of-lordly-might, apparatus-of-the-crab, cube-of-force, crystal-ball, helm-of-comprehending-languages, pipes-of-the-sewers, candle-of-invocation, necklace-of-prayer-beads
- **Reaction / spell-store / regen / misc:** rod-of-absorption, gloves-of-missile-snaring, ring-of-evasion, ring-of-spell-storing, ring-of-regeneration, ring-of-telekinesis, ring-of-invisibility, defender, hammer-of-thunderbolts, mithral-armor

**Recommended batch order (updated v2.345.1):** ~~Bucket B resistance trio~~ (already live via `_resistance_type`) and ~~`luck-blade`~~ (shipped v2.345.0) are done. Next: (1) Bucket C `staff-of-withering` + `staff-of-striking` (the `damage_condition` / `bonus_dice` riders already shipped for Dagger of Venom / Dwarven Thrower); (2) Bucket A condition-casters (`pipes-of-haunting`, `rod-of-rulership`, `rope-of-entanglement`) reusing the `frighten` / save-to-condition dispatch; (3) Bucket B `adamantine-armor` (needs a new `crits_become_normal` passive) + the two `staff-of-the-*` spell-DC items (need a new `spell_attack_bonus`/`spell_dc_bonus` passive).

---

A plan to give the 292 SRD magic items shipped under
`app/data/local/dnd5e/items/` real mechanical wiring. Today every magic
item's `actions` array is empty: no attunement gating, no charge
tracking, no spell-effect dispatch, no passive AC/save bonuses. A GM
who hands a player a Wand of Magic Missiles gets a description card —
the player still casts Magic Missile "by hand" from a sheet spell list
they don't have, and the wand's 7 charges live in somebody's head.

This is the single largest un-planned SRD surface found by the
2026-06-10 audit (items <25% mechanical vs ~80% for class features).

---

## Why this matters

The SRD item catalog divides into roughly:

| Shape | Examples | Count (rough) | Today |
|---|---|---|---|
| Mundane gear (weapons / armor / adventuring kit) | Longsword, Chain Mail, Rope | ~100 | ✅ weapons + armor wired (attack rolls, damage, AC via sheet) |
| **Passive-bonus wearables** | Cloak of Protection, Bracers of Defense, Ring of Protection, Amulet of Health, Belt of Giant Strength | ~40 | ⚪ description only |
| **Charge-tracked casters** | Wand of Magic Missiles, Wand of Fireballs, Staff of Healing, Ring of Spell Storing | ~45 | ⚪ description only |
| **1/day (dawn-recharge) actives** | Pearl of Power, Brooch of Shielding (absorb), Helm of Teleportation | ~30 | ⚪ description only |
| **On-hit rider weapons** | Flame Tongue (+2d6 fire), Frost Brand (+1d6 cold), Dragon Slayer, Giant Slayer | ~25 | ⚪ description only (the +1/+2/+3 weapons partially work if the GM hand-edits the attack bonus) |
| **Reaction items** | Cloak of Displacement (shipped as demo, v2.78.0), Brooch of Shielding, Arrow-Catching Shield | ~10 | 🟢 framework exists (`_pc_item_reactions_for_trigger`), 1 demo item |
| **Narrative / utility** | Bag of Holding, Alchemy Jug, Decanter of Endless Water | ~40 | ⚪ → stays announce-only by design (archetype J) |

The engine primitives these need **already exist** — this plan is
routing, not new infrastructure (the same conclusion the
[full-feature-automation](full-feature-automation.md) plan reached for
class features):

| Need | Existing primitive |
|---|---|
| Passive +AC | `effects.ac_bonus` read at `_read_target_ac` (v2.97.39) |
| Passive +saves | `bless_save_bonus`-style read at the save construction sites (v2.99.418) |
| Charges + dawn recharge | `sheet.resources[]` (`key/label/current/max/reset`) + the `rest_character` refill loop |
| Cast-from-item | `/cast_spell` already takes a spell slug + caster; needs a `source_item` bypass for slot consumption |
| On-hit riders | `_ATTACK_RIDERS` registry / `_compute_attack_auto_uplifts` (v2.99.395+) |
| Reactions | `_pc_item_reactions_for_trigger` + `/use_reaction` dispatch (v2.78.0) |
| Consumables | `/use_inventory_item` (Potion of Healing flow, v2.x Phase 4 polish) |

## Design principles

1. **Catalog, not per-item endpoints.** One `_MAGIC_ITEM_EFFECTS`
   data table in `app/routes/tabletop_routes.py` (or a sibling module)
   keyed by item slug. Each entry declares the item's mechanical
   payload in the same `effects.*` vocabulary buffs already use.
   Adding the 41st passive item is a table row, not an endpoint.
2. **Identity via `_slug`.** Inventory items added from the item
   browser already carry `_slug`. The catalog walk matches on
   `it.get("_slug")` with a normalized-name fallback (same approach
   as `_pc_item_reactions_for_trigger`'s item walk).
3. **Equipped + attuned gating.** An item's payload only applies when
   `equipped: True` AND (`attuned: True` OR the catalog entry says
   `attunement: False`). The SRD JSON already carries the
   `attunement` boolean; the sheet-side `attuned` flag is a new
   per-inventory-item field the sheet UI exposes next to `equipped`.
   RAW max-3-attuned-items enforcement is a server-side count gate.
4. **Read-time walk for passives, resource rows for actives.**
   Passive bonuses are computed at read sites (no buff install — the
   bonus appears/disappears with equip state, no expiry bookkeeping).
   Charge-tracked actives get a `sheet.resources[]` row auto-created
   on first use (the v2.158.13 Star Map auto-bootstrap pattern) so
   the existing rest-refill loop + resource pips work unchanged.
5. **"Daily at dawn" maps to long rest.** Same simplification the
   class features use; the project has no clock. Filed as a known
   v1 simplification per entry.
6. **Harness tests assert state** per the Phase-9 contract of
   full-feature-automation: AC actually changed the hit verdict,
   the slot actually came back, the charge counter decremented.

---

## New primitives (small)

### M1 — `_equipped_item_effects(sheet) -> dict`
Walks `sheet.inventory[*]` for equipped(+attuned-where-required)
items, looks each up in `_MAGIC_ITEM_EFFECTS`, and merges the
payloads (summing numeric keys like `ac_bonus` / `save_bonus`,
unioning list keys like `resistance_to`). Pure function on the sheet
— callable from every read site without battle state.

### M2 — `/use_item_action` endpoint
`{character_id, inventory_index | item_slug, action_key, charges?, override?}`.
Dispatches by catalog entry: decrement the item's resource row,
route the effect (recover slot / cast spell / install buff), mark
action economy, broadcast `feature_used(source=item-<slug>)`.
One endpoint, table-driven — the item-side mirror of `/use_reaction`.

### M3 — Attunement gate + count
`attuned: bool` on inventory items; PUT sheet path validates at most
3 attuned items (RAW DMG p.138); `_equipped_item_effects` + M2 both
require attunement when the catalog entry demands it.

---

## Phasing

### Phase 0 — Plan (this doc) ✅ v2.158.71

### Phase 1 — Passive AC/save wearables (S-M, ~2 commits)
`_MAGIC_ITEM_EFFECTS` table + `_equipped_item_effects` (M1) + wire
two read sites:

- `_read_target_ac` adds the item walk next to the v2.97.39 buff
  walk → **Cloak of Protection** (+1 AC), **Bracers of Defense**
  (+2 AC, only when no armor + no shield — gate on
  `sheet.armor`/`base_ac` semantics), **Ring of Protection** (+1 AC).
- The save-construction sites that already read buff-level save
  bonuses add the item-walk bonus → Cloak of Protection (+1 saves),
  Ring of Protection (+1 saves).

Demo fixture: give one demo PC a Cloak of Protection
(equipped+attuned). Harness: assert a borderline attack roll flips
from hit→miss when the cloak is equipped; assert the save total
includes the +1; assert un-equipping removes both.

### Phase 2 — Attunement gate (S, 1 commit)
M3. Sheet UI checkbox next to "equipped"; server-side 3-item cap;
Phase 1 effects require it. Error-path harness tests (4th attunement
→ 409; un-attuned cloak grants nothing).

### Phase 3 — Pearl of Power + 1/day actives (M, ~2 commits)
M2 `/use_item_action` + the Pearl entry: pick an expended slot level
(≤3 effective per RAW: a 4th+ slot returns as 3rd), restore it via
the same slot-mutation code `use_arcane_recovery` (v2.16.1) uses,
auto-create a `pearl-of-power` resource row (`max: 1, reset: long`).
Harness: cast to spend a slot → use pearl → `GET sheet` shows the
slot back; second use same day → 409 `out_of_uses`.

### Phase 4 — Charge-tracked wands (M-L, ~3 commits)
Wand of Magic Missiles first: 7-charge resource row; `/use_item_action`
with `charges: N` casts Magic Missile at slot level N through the
existing `/cast_spell` machinery with a `source_item` flag that skips
slot consumption (and skips the "spell not on your list" gate).
Recharge `1d6+1` at long rest via a per-entry `recharge_expression`
read by the rest loop. The "on last charge, d20 == 1 → crumbles"
RAW rule ships as a broadcast warning (auto-destroy filed as
follow-up). Wand of Fireballs / Staff of Healing follow as rows.

### Phase 5 — On-hit rider weapons (M, ~2 commits)
Flame Tongue / Frost Brand register `_ATTACK_RIDERS`-shape payloads
keyed by the equipped weapon (`weapon_hit_bonus_dice` +
`_damage_type`, already engine-read). Activation state (Flame
Tongue's command word) is a toggle on the inventory item.

### Phase 6 — Reaction items breadth (S per item)
Brooch of Shielding (Magic Missile immunity + absorb) etc. — rows in
the existing `_reactions` shape from v2.78.0, plus per-item charge
costs once Phase 4's charge plumbing exists.

### Non-goals (v1)
- Cursed items, sentient items, artifacts (Bag of Devouring stays a
  story prompt).
- Narrative utility items (Bag of Holding capacity math).
- Item identification / Identify-spell flow.
- Auto-destroy on last-charge d20 (warning only in Phase 4).

---

## Definition of done (per item)

1. Catalog entry with the item's full mechanical payload.
2. Equip/attune gating enforced server-side.
3. Effect routes through the existing engine (AC read site, slot
   mutation, `/cast_spell`, rider registry, reactions framework).
4. Charges/uses decrement + refill on the right rest.
5. Harness test asserts the **state change** (hit verdict flipped,
   slot restored, charge count, HP delta) — not just the broadcast.
6. `docs/automation-coverage.md` + `docs/test-harness-coverage.md`
   updated in the same commit.

## Related docs

- [full-feature-automation.md](full-feature-automation.md) — the
  archetype/primitive strategy this plan reuses for items.
- [reactions-automation.md](reactions-automation.md) — Phase 5 item
  reactions framework (v2.78.0) this plan extends.
- [class-content-status.md](class-content-status.md) — the content
  inventory; items get their own status table there once Phase 1
  ships.
- [`TODO.md` SRD 5e Audit](../../TODO.md#srd-5e-audit-2026-06-10) —
  the audit finding that filed this plan.
