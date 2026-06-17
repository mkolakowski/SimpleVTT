# Magic-item automation — design plan

**Status:** ✅ framework shipped end-to-end (re-audited 2026-06-11, v2.159.31 — SRD audit refresh). Phases 1–8 all closed across v2.158.74 → v2.159.25 (32 PATCH commits + the v2.159.0 MINOR milestone): passives → attunement → actions → on-hit riders → uplifts → templates → nat-20 hooks → AoE confirm modals → line/sphere/cone geometry → Javelin of Lightning → Necklace of Fireballs → Wand of Fear → Arrow of Slaying → Sun Blade → Goggles of Night (Phase 8a–8p).

✅ **Phase 9.1 stub triage closed v2.367.0** — every actionable item from Buckets A/B/C is wired. The only remaining items are the two inherently GM-narrated Bucket A stubs (`wind-fan`, `medallion-of-thoughts`) and the ~82 archetype-J announce-only items in Bucket D. See the [stub-triage closure block](#phase-91--stub-triage-v23445-corrected-v23451) below for the substrate catalog.

**Content tail (Phase 9).** Post-Phase-9.1 (v2.367.0): roughly 60+ of 292 items now carry non-empty `actions`/`passives` (the v2.316–v2.367 sweeps mechanized everything that fit a clean template). The remainder stays announce-only by design (Bucket D archetype J). See the [SRD 5e Audit (2026-06-11 refresh)](../../TODO.md#srd-5e-audit-2026-06-11-refresh) for the original backfill prioritisation that drove this work.

**Authors:** rolling
**Last updated:** 2026-06-17 (v2.403.0 — Phase 9.2 substrate ship)

---

## Phase 9.2 — charge tracking for the announce-only tail (v2.403.0+)

The post-v2.367.0 audit found that **~24 Bucket D items carry an engine-trackable charge / per-day / lifetime counter in RAW**, even though their effect (rat swarm, fire elemental, paradise plane shift, bag-of-tricks creature draw, etc.) is GM-narrated by design. Phase 9.2 builds out the counter without claiming to model the effect — the player sees their charge tick down on the sheet, the GM has an authoritative cross-table record, and the table conversation continues as before.

### Substrate (v2.403.0)

The generalized `_use_item_action_announce_only(db, campaign_id, char, item, sheet, catalog, slug, charges_raw)` handler is a near-twin of `_use_item_action_charge_wand`, but with the spell-cast routing stripped out + a `narration` field on the catalog entry that the handler embeds in the `feature_used` broadcast summary. The catalog row shape is:

```python
"slug-here": {
    "key": "action-key",
    "name": "Display label",
    "resource_key": "slug-here",           # PC sheet resources[] row
    "requires_attunement": False,          # per the item's RAW
    "min_charges": 1, "max_charges": 1,    # most are 1/dawn
    "narration": (
        "lit the brazier and spoke the command word — a fire "
        "elemental appears within 30 ft (GM-narrated: CHA check "
        "vs the elemental to command it, concentration up to 1 hr)."
    ),
},
```

Adding the 25th item is a 2-line catalog row + a dispatch entry + a per-PC `resources[]` row in the demo seed. No engine code changes after v2.403.0.

### Substrate ship (v2.403.0–v2.403.1)

| Slug | RAW | Status |
|---|---|---|
| `bowl-of-commanding-water-elementals` | 1/dawn summon water elemental | ✅ shipped v2.403.0 |
| `brazier-of-commanding-fire-elementals` | 1/dawn summon fire elemental | ✅ shipped v2.403.0 |
| `censer-of-controlling-air-elementals` | 1/dawn summon air elemental | ✅ shipped v2.403.0 |
| `stone-of-controlling-earth-elementals` | 1/dawn summon earth elemental | ✅ shipped v2.403.0 |
| `cape-of-the-mountebank` | 1/dawn dimension door | ✅ shipped v2.403.1 |
| `iron-bands-of-binding` | 1/dawn restrain via ranged attack | ✅ shipped v2.403.1 |
| `efreeti-bottle` | 1/dawn release (d100 table outcome) | ✅ shipped v2.403.1 |
| `bag-of-tricks` | 3/dawn pulls (random animal per bag color) | ✅ shipped v2.403.1 (first multi-charge pool on the substrate) |

All four share an identical RAW shape (1/dawn, no attunement, summon-elemental + CHA-check control); the single harness file (`test_use_item_action_announce_only.py`) covers all four through one parameterized happy-path test + a 409-second-use test + a long-rest-restore test.

### Backlog (charge-bearing Bucket D items still to wire)

Grouped by template. Each batch ships as one PATCH commit.

**1/dawn (single charge, dawn reset).** ~`cape-of-the-mountebank`~ ✅ v2.403.1, `plate-armor-of-etherealness`, ~`iron-bands-of-binding`~ ✅ v2.403.1, ~`efreeti-bottle`~ ✅ v2.403.1, ~`bag-of-tricks`~ ✅ v2.403.1 (3/dawn — multi-charge under the same template).

**Multi-charge per-day (charges + per-day recharge dice).** `pipes-of-the-sewers` (3, 1d3/dawn), `helm-of-teleportation` (3, 1d3/dawn), `cube-of-force` (36, 1d20/dawn — 6 modes, needs a multi-action catalog).

**Multi-day cooldown (single use, reset > 1 day).** `horn-of-valhalla` (1/7d), `ring-of-djinni-summoning` (1/24h), `rod-of-security` (1/10d).

**Lifetime charges (`reset: "none"`).** `chime-of-opening` (10), `ring-of-three-wishes` (3), `rod-of-absorption` (50 levels — needs reaction wiring).

**Multi-dose consumables.** `restorative-ointment` (1d4+1), `dust-of-dryness` (1d6+4), `sovereign-glue` (1d6+1), `bag-of-beans` (3d4).

**One-shot consumables.** `feather-token`, `elemental-gem`, `dust-of-disappearance`, `dust-of-sneezing-and-choking`, `oil-of-etherealness`, `philter-of-love`, `potion-of-poison`, `universal-solvent`. (The existing `consumable: True` catalog flag handles destroy-on-use; the new handler just decrements + broadcasts.)

**Filed follow-up — reaction items.** `ring-of-evasion` (3 charges, 1d3/dawn). Needs reaction wiring rather than `/use_item_action` dispatch; gates on the v2.78.0 `_pc_item_reactions_for_trigger` substrate. Filed separately.

**Skip / too complex for v1.** `necklace-of-prayer-beads` (per-bead spell-cast, random bead generation), `rod-of-lordly-might` (6 mode-buttons + 3 dawn actives), `candle-of-invocation` (burn-time tracking, alignment-conditional spell list), `crystal-ball` (variant-specific 1/dawn modes), `deck-of-many-things` / `deck-of-illusions` (finite-card mechanic), `iron-flask` / `mirror-of-life-trapping` / `orb-of-dragonkind` / `sphere-of-annihilation` (state-based capture, not counter-based).

### Then the two Bucket A holdouts

After the Bucket D charge backlog closes, the final two Bucket A items get wired (the v2.367.0 closure note flagged both as "inherently GM-narrated" — Phase 9.2 reframes them with charge tracking + announce-only broadcast):

- **`medallion-of-thoughts`** — 3 charges, 1d3/dawn → detect thoughts (DC 13). Routes through the existing `_use_item_action_potion_of_mind_reading` buff handler + a charge gate.
- **`wind-fan`** — 1/dawn → gust of wind, with cumulative 20% crumble chance per same-day re-use. Engine surface: 1/dawn resource + a "wear" counter + the crumble d20 mechanic on overuse.

After this arc closes, every Bucket D item that carries a counter in RAW will be machine-tracked, every Bucket A item will be wired, and the magic-item category will be at maximum mechanizable depth without modelling Bucket D effects.

---

## Phase 9.1 — stub triage (v2.344.5, corrected v2.345.1)

After the v2.316–v2.344 content sprint, **235/239 SRD magic items are wired** (registered + collectible).

> **Count correction (v2.345.1).** The original v2.344.5 figures ("133 mechanical / 108 bare stubs / ~26 automatable") were computed by inspecting only the *static* `_MAGIC_ITEM_PASSIVES` catalog payload. That under-counted the items wired via a **per-instance seed rider** — where the catalog entry is intentionally generic (`requires_attunement` only) and the specifics ride the inventory item (`_resistance_type`, `_ability_set`, `_ac_bonus`, …). Four items flagged as "bare stubs" are in fact already mechanically live + tested via the `_resistance_type` rider: **`armor-of-resistance`, `ring-of-resistance`, `dragon-scale-mail`, `ring-of-elemental-command`** (each has a `test_item_<slug>.py`).
>
> **Progress (v2.345.0 → v2.367.0).** Twenty items wired off this triage across three sweeps, plus eleven reusable engine additions:
>
> - **Bucket A (charge-cast, v2.350.0 → v2.357.0):** `pipes-of-haunting` (frighten), `rod-of-rulership` (charm 1/dawn), `trident-of-fish-command` (dominate-beast charm), `ring-of-animal-influence` (animal-friendship charm), `robe-of-scintillating-colors` (stun), `rope-of-entanglement` (restrain — the **first `unlimited`/no-charge item**, v2.355.0), `circlet-of-blasting` (v2.356.0 — the new **`_use_item_action_spell_attack` handler**: ranged spell attacks vs AC), `ring-of-shooting-stars` (v2.357.0 — the save-for-half Necklace handler).
> - **Bucket B (passive engine, v2.345.0 → v2.366.0):** `luck-blade` (v2.345.0 — `save_bonus`); `staff-of-the-woodlands` (v2.358.0 — the new `spell_dc_bonus` substrate folded into `_compute_spell_save_dc_from_sheet`); `staff-of-the-magi` (v2.359.0 — same substrate); `adamantine-armor` (v2.364.0 — the new `crits_become_normal` passive + `_target_wearer_crits_become_normal` reader + /attack + /npc_attack crit-pipeline read sites); `arrow-catching-shield` (v2.365.0 — the new `conditional_ac_bonus_vs_ranged` field + `is_ranged_attack` kwarg on `_read_target_ac`); `shield-of-missile-attraction` (v2.366.0 — the new `resistance_to_ranged_weapon` boolean + `is_ranged_weapon_attack` kwarg threaded through `_apply_damage_to_combatant` → `_resistance_halve`).
> - **Bucket C (on-hit/crit riders, v2.346.0 → v2.367.0):** `staff-of-withering` (v2.346.0/.348.0 — +2d10 necrotic + the new `ability_disadvantage` on-hit-save rider, built on the **v2.347.0 generalized `disadvantage_on` intercept** — any ability check/save); `staff-of-striking` (v2.349.0 — +1d6 force); `sword-of-wounding` (v2.360.0 — the new `on_hit_install` rider substrate + a generalized start-of-turn-tick hook on PUT /battle); `oathbow` (v2.361.0 — the new `condition_sworn_enemy` predicate + `/declare_oathbow_sworn_enemy` endpoint, reusing the v2.158.53 Vow-of-Enmity attack-adv reader for the d20 advantage); `berserker-axe` (v2.362.0 — the new `hp_max_bonus_per_level` passive composed into `_effective_max_hp_for_sheet`; v2.363.0 — the new `on_damage_save` payload + `_maybe_item_on_damage_save` helper for the cursed berserk save); `talisman-of-pure-good` + `talisman-of-ultimate-evil` (v2.367.0 — both composed onto the existing Necklace save-for-half handler via the dispatch tuple).
>
> **Current counts (post-v2.367.0):** of 241 wired slugs, ~155+ are functional (catalog-mechanical or rider-only) and ~85 stay announce-only by design. **All three actionable Buckets are now closed.** The actionable subset from the original triage is **0 remaining**; the only Bucket A items still ⚪ are `wind-fan` (gust-of-wind forced movement) and `medallion-of-thoughts` (detect thoughts) — both inherently GM-narrated (no clean combat mechanic). The remaining ~82 Bucket-D items stay announce-only (archetype J — summons, planar travel, wish, one-shot consumables, containers, capture/imprison, exploration utility). Counts are approximate at the margins.

### Bucket A — charge-cast a save/attack spell → `_MAGIC_ITEM_ACTIONS` cast-spell template (~10) — ✅ closed v2.357.0

The strongest template (the Wand of Fear / charged-wand pattern already shipped). Each casts a defined spell with a fixed save DC or spell attack; wire the action + DC + condition/damage dispatch. Closed v2.357.0; the two ⚪ rows below (`wind-fan`, `medallion-of-thoughts`) are inherently GM-narrated.

| Slug | RAW effect | Wire as | Status |
|---|---|---|---|
| `pipes-of-haunting` | DC 15 WIS or frightened 1 min (30 ft) | Wand of Fear handler → frightened | ✅ shipped v2.350.0 |
| `rod-of-rulership` | DC 15 WIS save or charmed/obey 1 min (120 ft) | Wand of Fear handler → charmed, 1/dawn | ✅ shipped v2.351.0 |
| `trident-of-fish-command` | dominate beast (DC 15) on a beast | Wand of Fear handler → charmed, single | ✅ shipped v2.352.0 |
| `ring-of-animal-influence` | animal friendship / fear / speak-with-animals (charges) | Wand of Fear handler → charmed | ✅ shipped v2.353.0 |
| `circlet-of-blasting` | scorching ray (3 × spell attack, 2d6 fire) | spell-attack action | ✅ shipped v2.356.0 |
| `ring-of-shooting-stars` | 1-3 motes, DC 15 DEX save for half 5d4 fire | save-for-half Necklace handler | ✅ shipped v2.357.0 |
| `robe-of-scintillating-colors` | DC 15 WIS or stunned (dazzle) | Wand of Fear handler → stunned | ✅ shipped v2.354.0 |
| `rope-of-entanglement` | DC 15 DEX or restrained (at will) | Wand of Fear handler → restrained, `unlimited` | ✅ shipped v2.355.0 |
| `wind-fan` | gust of wind (forced movement, DC 13) | — | ⚪ inherently GM-narrated (no clean combat condition/damage) |
| `medallion-of-thoughts` | detect thoughts (DC 13) | — | ⚪ inherently GM-narrated (utility, no combat) |

### Bucket B — passive numeric buff → mechanical `_MAGIC_ITEM_PASSIVES` (`effects.*`) (~9) — ✅ closed v2.366.0

Always-on bonuses the engine already reads (resistance via `_resistance_halve`, save/AC/stat passives). Closed v2.366.0 — every row below ✅.

| Slug | RAW effect | Wire as | Status |
|---|---|---|---|
| `armor-of-resistance` | resistance to one damage type | `_resistance_type` rider | ✅ already live (mis-counted) |
| `ring-of-resistance` | resistance to one damage type | `_resistance_type` rider | ✅ already live (mis-counted) |
| `dragon-scale-mail` | resistance to the dragon's damage type | `_resistance_type` rider | ✅ already live (mis-counted) |
| `luck-blade` | +1 to all saves (the +1 weapon is baked) | `effects.save_bonus` | ✅ shipped v2.345.0 |
| `adamantine-armor` | crits against you become normal hits | `effects.crits_become_normal` (new) | ✅ shipped v2.364.0 |
| `staff-of-the-magi` | +2 spell attack & save DC | `effects.spell_dc_bonus` (new substrate, v1 GM-narrates the +2 spell-attack half) | ✅ shipped v2.359.0 |
| `staff-of-the-woodlands` | +2 spell attack & save DC | same substrate (the first item on `spell_dc_bonus`, v2.358.0) | ✅ shipped v2.358.0 |
| `arrow-catching-shield` | +2 AC vs ranged attacks | new `conditional_ac_bonus_vs_ranged` field + `is_ranged_attack` kwarg on `_read_target_ac` | ✅ shipped v2.365.0 |
| `shield-of-missile-attraction` | resistance to ranged-weapon damage + curse | new `resistance_to_ranged_weapon` boolean + `is_ranged_weapon_attack` kwarg on `_resistance_halve` (cursed redirect GM-narrated) | ✅ shipped v2.366.0 |

### Bucket C — on-hit / crit weapon rider → `_MAGIC_ITEM_ATTACK_RIDERS` (~7) — ✅ closed v2.367.0

The richest engine bucket of the sweep — every row below ✅ as of v2.367.0. The two alignment talismans ended up on the Necklace save-for-half handler rather than `_MAGIC_ITEM_ATTACK_RIDERS` (they're charge-cast actions, not on-hit), but they're grouped here in the original triage. See the Bucket B + C engine additions in the [Progress block](#phase-91--stub-triage-v23445-corrected-v23451) above.

| Slug | RAW effect | Wire as | Status |
|---|---|---|---|
| `staff-of-withering` | on hit: +2d10 necrotic + DC 15 CON or disadvantage | always-on `dice` rider + `ability_disadvantage` on-hit-save | ✅ shipped v2.346.0 / v2.348.0 |
| `staff-of-striking` | expend 1–3 charges → +1d6 force per charge on hit | always-on `dice` rider (+1d6) | ✅ shipped v2.349.0 |
| `sword-of-wounding` | recurring 1d4 necrotic/turn, DC 15 CON to end | on-hit recurring-damage condition (new) | ✅ shipped v2.360.0 |
| `oathbow` | vs sworn enemy: +3d6 piercing + advantage | conditional rider (declared-enemy state) | ✅ shipped v2.361.0 |
| `berserker-axe` | +1 (baked); HP-max +level while attuned; berserk save | HP-max passive + on-damage WIS save | ✅ shipped v2.362.0–v2.363.0 |
| `talisman-of-pure-good` | 7 charges, action: DC 18 CHA save → 6d6 radiant (half on save), good attune only | Necklace save-for-half handler dispatch (alignment gate + dramatic instant-kill GM-narrated) | ✅ shipped v2.367.0 |
| `talisman-of-ultimate-evil` | 6 charges, action: DC 18 CHA save → 8d6 necrotic (half on save), evil attune only | same Necklace handler dispatch | ✅ shipped v2.367.0 |

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

**Recommended batch order (updated v2.367.0):** **Buckets A, B, and C are all closed. The v2.344.5 stub triage is fully wired.** Bucket A's only remaining items (`wind-fan` + `medallion-of-thoughts`) are inherently GM-narrated. Bucket B closed v2.366.0 — `luck-blade` + resistance trio + `staff-of-the-*` spell-DC items + `adamantine-armor` (v2.364.0, `crits_become_normal`) + `arrow-catching-shield` (v2.365.0, `conditional_ac_bonus_vs_ranged`) + `shield-of-missile-attraction` (v2.366.0, `resistance_to_ranged_weapon` cursed). Bucket C closed v2.363.0 — `sword-of-wounding` (v2.360.0, `on_hit_install` + start-of-turn tick), `oathbow` (v2.361.0, `condition_sworn_enemy` + declare endpoint), `berserker-axe` (v2.362.0 HP-max + v2.363.0 cursed save). The two alignment talismans (`talisman-of-pure-good`, `talisman-of-ultimate-evil`) shipped v2.367.0 on the Necklace save-for-half handler. **Net new substrate from this sweep:** `on_hit_install` + start-of-turn-tick PUT-/battle hook, `condition_sworn_enemy` predicate, `hp_max_bonus_per_level` (composed into `_effective_max_hp_for_sheet`), `on_damage_save` payload + helper, `crits_become_normal` + `_target_wearer_crits_become_normal` reader, `conditional_ac_bonus_vs_ranged` + `is_ranged_attack` kwarg on `_read_target_ac`, and `resistance_to_ranged_weapon` + `is_ranged_weapon_attack` kwarg threaded through `_apply_damage_to_combatant` → `_resistance_halve`.

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
