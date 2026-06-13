# Ability-score override engine — design plan

**Status:** ✅ Complete (Phases 0-4 shipped). Phase 0 (plan) ✅ v2.211.0. Phase 1 (override substrate + STR saves/checks + carry capacity + Belt of Giant Strength Hill tier) ✅ v2.212.0. Phase 1b (weapon attack/damage read site on `/attack`) ✅ v2.213.0 — the `/attack` endpoint now appends the effective-STR modifier delta to both the to-hit roll and the damage expression for STR-keyed weapons. Phase 2a (sheet display of the boosted ability score with an item-boost marker) ✅ v2.214.0. Phase 2b (belt tier backfill via per-item `_ability_set` override) ✅ v2.215.0. Phase 3 (Amulet of Health: CON 19 override + display-derived max-HP) ✅ v2.216.0. Phase 4 (Potion of Giant Strength, timed-buff path) ✅ v2.217.0 — the override engine is now complete.

**Authors:** rolling
**Last updated:** 2026-06-13

A plan to add a RAW ability-score **override** substrate to the engine so magic items that *set* an ability score to a fixed value (Belt of Giant Strength, Amulet of Health) or *raise* one temporarily (Potion of Giant Strength) have a real surface to compose with. The override flows automatically into every downstream reader of that score — attack/damage, saves, skill checks, and carry capacity.

## RAW

**Belt of Giant Strength** (DMG p.155, requires attunement) — *sets* your Strength score to a fixed value while worn, but only if your current STR is lower:
- Hill giant — STR 21 (uncommon)
- Stone / Frost giant — STR 23 (rare)
- Fire giant — STR 25 (rare)
- Cloud giant — STR 27 (very rare)
- Storm giant — STR 29 (legendary)

**Amulet of Health** (DMG p.150, requires attunement) — *sets* your Constitution score to 19 while worn, only if your current CON is lower. (CON change retroactively adjusts max HP.)

**Potion of Giant Strength** (DMG p.187, consumable) — for 1 hour, your STR *becomes* the giant's value (Hill 21 → Storm 29), again only if higher than current. A *temporary* override (timed), not a worn one.

**Common thread:** all three **set** a score to a fixed number rather than adding a bonus, and all three only apply **if the fixed value exceeds the creature's current score**. This "max(current, fixed)" semantics is the core of the substrate — distinct from the existing additive `ac_bonus` / `save_bonus` / `check_bonus` model.

## Why this matters

Today the engine has no concept of an effective ability score that differs from the stored `abilities.STR`. Every read site (`/roll` STR weapon attack/damage, Athletics, STR saves, the carry-capacity helper) reads the raw stored score. That blocks a whole tier of iconic items:

- **Belt of Giant Strength** — the marquee martial item. Without an override surface, equipping the belt is flavor-only; the wielder's attacks, Athletics, STR saves, and carry capacity all still use the base score.
- **Amulet of Health** — sets CON 19, which must also bump max HP (a second-order effect on a derived stat, not just a roll modifier).
- **Potion of Giant Strength** — same set-to-fixed semantics with a 1-hour timer instead of a worn-while-attuned gate.
- Composes with the **carry-capacity** engine ([carrying-capacity.md](carrying-capacity.md), shipped v2.159.27): `sheet_carry_capacity_lb` reads STR, so a Belt of Giant Strength's higher STR raises carry capacity for free once STR resolution is centralised.

This is a foundational substrate, not a one-off item — once `effective_ability_score(sheet, "STR")` exists and every reader calls it, all three items (and any future score-setting effect) drop in via data.

## Design

### The core helper

A new pure helper that resolves a creature's **effective** ability score by folding override payloads over the stored base:

```python
def effective_ability_score(sheet: dict, ability: str) -> int:
    base = _read_stored_ability(sheet, ability)   # the abilities.STR base, schema-drift tolerant
    fx = _equipped_item_effects(sheet)            # existing passive walker
    override = fx["ability_set"].get(ability)     # highest set-value across equipped items
    return max(base, override) if override is not None else base
```

The `max(base, override)` is the RAW "only if higher" clause baked into the resolver, so individual read sites never re-implement it.

### Extending `_equipped_item_effects`

The existing passive walker (`tabletop_routes.py`, the function that already aggregates `ac_bonus` / `save_bonus` / `check_bonus`) gains a new aggregation:

- `out["ability_set"]: dict[str, int]` — maps an ability key (`"STR"`, `"CON"`, …) to the **highest** set-value across all equipped+attuned items carrying an `ability_set` payload. Per-payload shape:
  ```python
  {"ability_set": {"STR": 21}, "requires_attunement": True}
  ```
  Aggregation rule: for each payload's `ability_set` entries, keep the max per ability (two belts → the bigger wins; same RAW "highest applies" intent). Reuses the existing `requires_attunement` gate.

### Read sites that must switch to `effective_ability_score`

Every place that currently reads the raw stored score for a mechanical effect:

1. **`/roll` STR-based weapon attack + damage** — the ability modifier added to attack/damage rolls.
2. **`/roll` ability checks + skill checks** — Athletics (STR), and any check whose `stat_ability` is the overridden ability.
3. **`/roll` ability saves** — STR/CON saving throws.
4. **Carry capacity** — `sheet_carry_capacity_lb` (the leaf module) takes the effective STR.
5. **Sheet display** — the rendered ability score + modifier should show the effective value (with a marker that it's item-boosted), so the player sees STR 21 not STR 13 while the belt is worn.

The ability **modifier** is then `(effective_score - 10) // 2` everywhere, computed from the effective score.

### Amulet of Health's max-HP second-order effect

CON drives max HP (`+CON_mod per level`). Setting CON to 19 must re-derive max HP. Two options:

- **(a) Display-derived** — recompute max HP at read time from effective CON. Cleanest, but max HP is currently a stored field edited on the sheet, so this needs a derived-vs-stored split.
- **(b) Explicit delta** — when the amulet is equipped, add `(19 − base_CON) // 2 × level` to max HP via the existing temp/bonus-HP substrate.

Phase decision deferred to implementation; **(a)** is preferred to match the override model (effective score → effective modifier → effective derived stat) but is the larger change.

### Potion of Giant Strength's timer

The worn items (Belt, Amulet) gate on equipped+attuned. The potion is a **timed** effect (1 hour). It reuses the existing buff/duration substrate (the same one behind Potion of Heroism / Potion of Fire Resistance): drinking it installs a timed buff carrying the `ability_set: {"STR": N}` payload, and `effective_ability_score` folds active timed buffs in addition to equipped-item payloads. So the resolver reads from **two** sources: equipped-item effects + active timed buffs.

## Phasing

### Phase 0 — Plan (this doc) ⚪ v2.211.0

### Phase 1 — Override substrate + STR save/check/carry read sites (M, ~1 commit) ✅ v2.212.0

- `ability_set` aggregation in `_equipped_item_effects`.
- `effective_ability_score(sheet, ability)` + `_read_stored_ability` (schema-drift-tolerant) + `_ability_score_modifier` + `_ability_override_delta` + `_ability_for_roll`.
- `/roll` appends the override modifier delta to STR-keyed saves + ability/skill checks (composing additively with the flat save/check item bonuses).
- `sheet_carry_capacity_lb` (and the summary/over-capacity helpers) take an optional `effective_str`; `/sheet-json` passes the override-folded STR and exposes `derived.effective_abilities`.
- Belt of Giant Strength (Hill, STR 21) as the first `_MAGIC_ITEM_PASSIVES` entry + demo seed on Garrik Ironside (base STR 18 → effective 21).
- Harness `test_item_belt_of_giant_strength.py` (5 tests): effective STR on `/sheet-json`, carry 315, STR-save + Athletics override deltas, unequip-reverts.

### Phase 1b — Weapon attack/damage read site (S–M, ~1 commit) ✅ v2.213.0

The `/attack` endpoint resolves attack/damage from the sheet's stored attack entries (the ability modifier is baked in at seed/sheet-edit time, not recomputed per roll from STR), so routing it through `effective_ability_score` is a materially larger surface than the `/roll` save/check append landed in Phase 1.

Shipped: two pure helpers — `_attack_override_ability(sheet, attack)` infers the weapon's backing ability (disambiguates STR vs DEX by matching the baked `attack_bonus − proficiency_bonus` modifier against the base STR/DEX mods, finesse-desc fallback), and `_pc_attack_ability_override_delta(sheet, attack)` returns the override modifier delta for that ability (0 for non-overridden abilities, so a STR belt never inflates a DEX bow/finesse weapon). The `/attack` endpoint applies the delta to both `damage_expr_raw` (mirroring the Hex Warrior swap) and the to-hit `atk_expr`. Harness: `test_belt_boosts_weapon_attack_and_damage` + `test_belt_weapon_boost_reverts_on_unequip` on Garrik's Greatsword.

### Phase 2 — Belt tier backfill + sheet display (S–M, split into 2a/2b)

**Phase 2a — Sheet display ✅ v2.214.0.** The `#ab-card-view` ability cards render the *effective* score + modifier with an item-boost marker (a ▲ badge + accent colour) when an equipped item sets the score above its base. `_effective_abilities_for_sheet(sheet)` is the shared helper feeding all three sheet-rendering surfaces (`/sheet-json`, the API `get_sheet`, the page `character_sheet_page`); `sheet.js`'s `updateCardFromInput` reads a `data-override` attribute so unsaved player edits keep the boosted display correct (display-only — roll-building still reads the raw inputs and the server appends the delta). Playwright `test_ability_override_display.py` (2 tests) asserts Garrik's STR card shows 21/+5 with the badge visible and DEX (unboosted) shows 14 with the badge hidden.

**Phase 2b — Belt tier backfill ✅ v2.215.0.** The data-modeling question (the SRD ships a single slug `belt-of-giant-strength`, rarity "varies", covering all six tiers) is resolved in favour of a **per-inventory-item override**: an `_ability_set: {"STR": N}` field on the inventory item wins over the catalog payload's `ability_set` default in `_equipped_item_effects` (merged per-ability). This keeps the catalog faithful to the SRD's one slug and generalises to any future "varies"-rarity score-setting item. Demo: Zara Emberfire (Sorcerer, base STR 8) wears a Belt of Stone Giant Strength flagged `_ability_set: {"STR": 23}` → effective STR 23 (mod +6), carry 345 lb. Harness `test_belt_tier_override_sets_higher_str` + `test_belt_tier_override_raises_carry_capacity` assert the override beats the Hill default (21).

### Phase 3 — Amulet of Health + max-HP derivation (M) ✅ v2.216.0

Shipped: `amulet-of-health` in `_MAGIC_ITEM_PASSIVES` (`ability_set {CON: 19}`, attunement) — the CON override flows automatically into CON saves (`/roll`) and the Phase 2a boosted-ability sheet card. The max-HP second-order effect chose **option (a) display-derived**: new `_effective_max_hp_for_sheet(sheet)` computes `{base, effective, delta, level, source}` from the effective-vs-base CON modifier delta × total level (new `_sheet_total_level` helper), surfaced as `/sheet-json` `derived.effective_max_hp`. The stored `hp.max` is left untouched so combat damage math is unchanged in v1 (mutating the stored max in combat is a filed follow-up). Demo: Brother Tavik Stonebrow (Cleric Lv 8, base CON 14 → mod +2, stored max 67) → effective CON 19 (mod +4), effective max HP 83. Harness `test_item_amulet_of_health.py` (4 tests): effective CON, effective max HP +16, CON-save delta, unequip-reverts.

**Phase 3 combat follow-up ✅ v2.220.0.** The display-derived boost now also drives the combat heal-clamp AND the long-rest fill: `_apply_heal_to_combatant` (the canonical Cure Wounds / Healing Word / Aid / feature-heal path) folds the `_effective_max_hp_for_sheet` delta into its effective-max ceiling — applied before the v2.159.20 exhaustion Lv 4 halving, mirroring the v2.97.42 Aid `_buff_hp_max_bonus` extension — and `rest_character`'s long-rest branch fills to the same effective max so "full HP" matches between resting and healing. (Skipping the rest fill surfaced a real bug: a long-rested amulet wearer sat at the stored max while the combat ceiling was higher, so Life Domain's Blessed Healer self-heal would then land mid-combat where it previously no-op'd.) Still non-destructive: stored `hp.max` is never mutated, so unequipping drops the ceiling with no revert step. Harness `test_amulet_health_combat_max_hp.py` (2 tests): heal at stored max lands via the amulet ceiling; guard — without the amulet the same heal caps at the stored max.

**Phase 3 remaining heal paths ✅ v2.221.0.** The boosted ceiling now also drives the remaining non-combat heal clamps: short-rest hit dice (`rest_character`, `type: short`), Second Wind (Fighter), and Lay on Hands (Paladin → target). A new shared `_sheet_heal_ceiling(sheet)` helper (stored `hp.max` + the `_effective_max_hp_for_sheet` delta, falling back to the stored max) is the single source of truth all three sites read, so every restore path is consistent with the combat heal + long-rest fill. Still non-destructive. Harness `test_amulet_health_rest_heal_paths.py` (2 tests): short rest heals Tavik past his stored max via the ceiling; Lay on Hands tops an amulet wearer past their stored max. Second Wind isn't directly exercised (no amulet-wearing Fighter in the demo) but reads the same helper.

### Phase 4 — Potion of Giant Strength (timed) ✅ v2.217.0

Shipped: the timed half of the engine. A `giant-strength` template in `_SPELL_BUFF_MAP` carries `effects.ability_set {STR: 21}` (Hill default); the `potion-of-giant-strength` catalog entry routes through the self-buff potion handler, which stamps the specific tier onto the installed buff from the inventory item's `_ability_set` (one catalog entry covers all six tiers). Because `_install_buff` mirrors buffs onto the sheet as `_buffs_active` (durations stripped, effects retained), `_equipped_item_effects` now folds any `_buffs_active` entry carrying `effects.ability_set` into the same highest-wins map equipped items feed — so `effective_ability_score`, the sheet display, `/roll` deltas, `/attack`, carry capacity, and `/sheet-json` all compose timed buffs with equipped overrides via the existing RAW max(base, set), with zero per-site changes. Demo: Thalindra Moonwhisper (Wizard Lv 7, base STR 8 → mod -1, 120 lb cap) carries a Potion of Hill Giant Strength (`_ability_set {STR: 21}`); after drinking, effective STR 21 (mod +5), carry 315 lb, STR save +6 delta. Harness `test_potion_of_giant_strength.py` (3 tests): effective STR on `/sheet-json`, carry capacity 315, STR-save override delta.

## Non-goals (v1)

- Ability-score **bonuses** that stack additively (e.g. Manual of Gainful Exercise's permanent +2) — those are a base-score edit, not a runtime override; out of scope for the override substrate.
- Headband of Intellect (INT 19) ✅ v2.218.0 — same shape as Belt/Amulet, shipped as a pure data drop-in (`_MAGIC_ITEM_PASSIVES` row + seed on Mira Greenleaf + tests).
- Gauntlets of Ogre Power (STR 19) ✅ v2.219.0 — identical drop-in, composes with the Belt of Giant Strength via the highest-wins map (`_MAGIC_ITEM_PASSIVES` row + seed on Rowan Quickbow + tests).
- Ability-score **drain** (negative overrides from monster effects) — a different sign; the `max(base, override)` clause is one-directional by design.
- Retroactive carry-weight encumbrance recompute (the carry engine already reads STR live, so this flows for free).

## Definition of done (per phase)

1. `effective_ability_score` is a pure function; the `max(base, override)` RAW clause lives only there.
2. Every mechanical STR read site routes through the helper (no raw `abilities.STR` reads left in roll/carry paths for the overridden abilities).
3. Harness test proves an equipped belt changes attack/check/save/carry outputs and unequipping reverts them.
4. `docs/test-harness-coverage.md` updated in the same commit.

## Related docs

- [carrying-capacity.md](carrying-capacity.md) — the STR reader this composes with; `sheet_carry_capacity_lb` is read site #4.
- [magic-items-automation.md](magic-items-automation.md) — the `_MAGIC_ITEM_PASSIVES` / `_equipped_item_effects` substrate this extends.
- [temp-hp-and-bonuses.md](temp-hp-and-bonuses.md) — the bonus-HP substrate referenced by the Amulet's option (b).
- [`docs/test-harness-coverage.md`](../test-harness-coverage.md) — harness suite index.
