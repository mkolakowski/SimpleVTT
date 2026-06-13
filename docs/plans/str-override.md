# Ability-score override engine — design plan

**Status:** ⚪ proposed (Phase 0 = this doc, filed 2026-06-13, v2.211.0).

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

### Phase 1 — Override substrate + STR read sites (M, ~1 commit)

- `ability_set` aggregation in `_equipped_item_effects`.
- `effective_ability_score(sheet, ability)` helper + `_read_stored_ability` schema-drift-tolerant reader.
- Switch the `/roll` STR attack/damage/check/save read sites to the effective score.
- Switch `sheet_carry_capacity_lb` to the effective STR.
- Belt of Giant Strength (Hill, STR 21) as the first `_MAGIC_ITEM_PASSIVES` entry + demo seed on a martial PC (Garrik / Krieger).
- Harness: equip belt → STR attack/Athletics/STR save/carry-capacity all reflect STR 21; unequip → revert.

### Phase 2 — Belt tier backfill + sheet display (S–M, ~1 commit)

- Remaining belt tiers (Stone/Frost 23, Fire 25, Cloud 27, Storm 29) as catalog rows.
- Sheet renders the effective ability score + modifier with an item-boosted marker.
- Playwright test asserts the boosted score renders.

### Phase 3 — Amulet of Health + max-HP derivation (M, ~1 commit)

- `ability_set: {"CON": 19}` payload + the chosen max-HP derivation (a vs b above).
- Demo seed + harness test asserting effective CON 19 + adjusted max HP.

### Phase 4 (filed) — Potion of Giant Strength (timed)

- Timed-buff path feeding `ability_set` into `effective_ability_score`.
- Consumable dispatch + 1-hour duration + harness test.

## Non-goals (v1)

- Ability-score **bonuses** that stack additively (e.g. Manual of Gainful Exercise's permanent +2) — those are a base-score edit, not a runtime override; out of scope for the override substrate.
- Headband of Intellect (INT 19), Gauntlets of Ogre Power (STR 19) — same shape as Belt/Amulet, drop in via data once Phase 1 lands; not separately phased.
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
