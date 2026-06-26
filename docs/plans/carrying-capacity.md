# Carrying capacity — design plan

**Status:** ✅ shipped end-to-end — **all phases (0–4) now closed** (Phase 4 / Encumbrance variant shipped v2.660.0). Phases 0–3 detail:
- **Phase 0** ✅ v2.159.26 (this plan doc filed + wiki surface).
- **Phase 1** ✅ v2.159.27 (`app/content/carry_weight.py` leaf module + helpers + `/sheet-json` derived `carry` block; 37 unit tests).
- **Phase 2a** ✅ v2.159.28 (Krieger weight backfill + carry meter UI; updated `updateTotalWeight()` to prefer `i.weight_lb` numeric + skip `_in_bag_of_holding` items + red-when-over-capacity).
- **Phase 2b** ✅ v2.159.29 (RAW weight backfill for the remaining 11 demo PCs).
- **Phase 3** ✅ v2.159.30 (Bag of Holding catalog row + Brakka demo seed + integration test).
- **Phase 3b** ✅ v2.656.0 (Bag of Holding **500-lb internal capacity** — previously descriptive-only/unenforced). `sheet_bag_of_holding_weight_lb()` sums the stowed weight; `sheet_carry_summary` surfaces `bag_of_holding_weight_lb` / `bag_of_holding_capacity_lb` / `bag_of_holding_over_capacity` in the `/sheet-json` derived `carry` block, and the sheet's carry meter shows a "⚠ Bag overloaded" rupture warning past 500 lb (RAW DMG p.153). v1 assumes a single bag (the `_in_bag_of_holding` flag isn't per-container).

Future weight-related items (Heward's Handy Haversack, Belt of Giant Strength, Heroes' Feast +5 STR, Bag of Devouring) drop in via the existing substrate without new helper work. Phase 4 (Encumbrance variant rule, PHB p.176) shipped v2.660.0 as an informational derivation; the only remaining follow-up is mechanically auto-installing the encumbrance speed/disadvantage in combat (needs an inventory-change hook — see Phase 4 below).

**Authors:** rolling
**Last updated:** 2026-06-11

A plan to add RAW carrying capacity to the engine so weight-related items (Bag of Holding, Heward's Handy Haversack, Bag of Devouring, Belt of Giant Strength, etc.) have a real engine surface to compose with.

## RAW (PHB p.176)

**Carrying capacity** = `STR × 15 lb`. A creature can carry up to this without penalty.

**Push, drag, lift** = `STR × 30 lb` (variant rule, skipped v1).

**Encumbered (variant rule, PHB p.176)** — optional, shipped v2.660.0 (Phase 4):
- ≤ `STR × 5 lb` — no penalty.
- > `STR × 5 lb` — **encumbered**: speed −10 ft.
- > `STR × 10 lb` — **heavily encumbered**: speed −20 ft + disadvantage on STR/DEX/CON ability checks, saves, attacks.
- (`STR × 15 lb` is the normal **maximum carrying capacity** — see the basic rule above — not a penalty tier.)

> **Threshold correction (v2.660.0):** earlier drafts of this section + the Phase 4 note below listed the penalty tiers as STR×10 / STR×15. That was wrong — the RAW variant tiers are **STR×5 (encumbered) / STR×10 (heavily encumbered)**, with STR×15 being the carry-capacity maximum. The shipped `sheet_encumbrance()` uses the correct values.

The basic rule (`STR × 15 lb`) shipped in Phase 1; the encumbered variant shipped in Phase 4 as a **request-time derivation** (informational — the engine surfaces the tier on the sheet for the table to self-manage, it doesn't auto-install the speed/disadvantage buffs).

## Why this matters

Unblocks (currently flavor-only):
- **Bag of Holding** (RAW DMG p.153) — 500 lb capacity, weighs 15 lb regardless of contents. Without a carry-weight engine the "contents weigh 0" is descriptive UI text; with the engine it actually reduces the wielder's burden.
- **Heward's Handy Haversack** (DMG p.174) — same shape as Bag of Holding.
- **Belt of Giant Strength** (DMG p.155) — sets STR to a fixed value; the carry-capacity helper reads STR so the belt's effect on burden surfaces for free.
- **Heroes' Feast** (PHB p.250) — +5 STR for 24 hours, also auto-flows via the STR-based helper.
- **Bag of Devouring** (DMG p.153) — punishment item if a PC voluntarily climbs in. v1 doesn't need to wire this, but the engine surface gives the GM a hook.

Plus a real "you're over carry capacity" indicator on the sheet that the player can self-manage (a quality-of-life win independent of any specific magic item).

## Design

### Data shape

Per-PC sheet field derivations (NOT stored — pure read-time computation):
- `sheet.derived.carry_capacity_lb: int` = `STR_total × 15`.
- `sheet.derived.inventory_weight_lb: int` = sum of `weight × qty` across the PC's `inventory[]`.
- `sheet.derived.is_over_capacity: bool` = `inventory_weight_lb > carry_capacity_lb`.

Where the data comes from:
- **STR_total**: the existing `sheet.abilities.strength` (the standard score). Belt of Giant Strength etc. compose by overriding this — for v1 just read what's there.
- **Per-item weight**: a single integer or float on the inventory item: `item.weight_lb`. Populated from one of three sources, in priority order:
  1. The inventory item's own `weight_lb` field (set on PCs whose sheet authors care).
  2. A parsed value from the item's catalog JSON `weight` string (`"3 lb."`/`"15 lb."`/`""`).
  3. Default 0 for items with no weight data.

### New helpers

In a new leaf module `app/content/carry_weight.py` (mirrors `app/content/effective_speed.py`):

- `parse_weight_lb(weight_str: str) -> float` — parses the inconsistent catalog JSON strings (`"3 lb."`, `"3 lb. lb"` [a known SRD typo], `"1/2 lb."`, `""`) into a float. Falls back to 0 on unparsable.
- `item_weight_lb(item: dict, fallback_catalog_weight: str | None = None) -> float` — resolves a single inventory item's weight via the 3-tier priority order above.
- `sheet_inventory_weight_lb(sheet: dict, catalog_lookup: dict[str, str]) -> float` — sums weights × qty.
- `sheet_carry_capacity_lb(sheet: dict) -> int` — STR × 15.

The leaf module is pure-Python (no DB / FastAPI dependencies) so the unit tests run in-process at host speed.

### Sheet exposure

The existing `/sheet-json` endpoint adds a `derived` dict to the response (NEW top-level key, parallel to `sheet`):
```json
{
  "sheet": {...},
  "derived": {
    "carry_capacity_lb": 240,
    "inventory_weight_lb": 62.5,
    "is_over_capacity": false
  }
}
```
The `derived` key is computed at request-time from the sheet — never persisted. Clients that want to display the carry meter read it from there.

### Bag of Holding integration

Bag of Holding becomes a `_MAGIC_ITEM_PASSIVES` entry like:
```python
"bag-of-holding": [
    {
        "weight_reduction_lb": "contents",  # special marker
        "requires_attunement": False,
    },
],
```

The `weight_reduction_lb: "contents"` marker is read by `sheet_inventory_weight_lb` — when summing weights, any inventory item flagged with `_in_bag_of_holding: True` contributes only the bag's own weight (15 lb) once, not per-item. The bag itself is a separate inventory entry weighing 15 lb.

v1 simplification: the player tags items as "in the bag" by adding the `_in_bag_of_holding: True` field via the sheet UI (sheet edit — Phase 3 UI). The engine just respects the tag.

## Phasing

### Phase 0 — Plan (this doc) ✅ v2.159.26

### Phase 1 — Engine + sheet exposure (S-M, ~1 commit)

- `app/content/carry_weight.py` with the four helpers above.
- `/sheet-json` extended to populate `derived`.
- Pure-Python unit tests for `parse_weight_lb` (10+ string variants), `sheet_inventory_weight_lb`, `sheet_carry_capacity_lb`, `is_over_capacity`.
- Integration test against `/sheet-json` for one demo PC.

### Phase 2 — Demo seed weights + sheet UI meter (M, ~1 commit)

- Backfill `weight_lb` on every demo PC's inventory items (12+ PCs × 5-10 items each).
- Sheet template renders a carry meter (`weight / capacity lb`) on the inventory section header.
- Playwright test asserts the meter renders for one demo PC.

### Phase 3 — Bag of Holding catalog row + demo seed item (S, ~1 commit)

- `bag-of-holding` entry in `_MAGIC_ITEM_PASSIVES`.
- `sheet_inventory_weight_lb` honors `_in_bag_of_holding: True` items.
- Bag added to a demo PC's inventory (TBD which — likely Krieger or Garrik — the strength-based PCs who'd carry the most).
- HTTP harness test: equip Bag → flag items as in-bag → carry weight drops.

### Phase 4 — Encumbered variant rule ✅ v2.660.0

Optional variant (PHB p.176). Shipped as a **request-time derivation** rather than buff installs: `sheet_encumbrance()` classifies the load into `none` / `encumbered` (> STR×5 → speed −10) / `heavily_encumbered` (> STR×10 → speed −20 + STR/DEX/CON disadvantage), and `sheet_carry_summary()` folds the tier + penalty fields into `/sheet-json`'s `derived.carry` block (only when encumbered, to keep the unencumbered shape clean). Informational — the sheet surfaces the tier for the table to self-manage. **Deferred follow-up:** mechanically auto-installing the `speed_reduction_ft` reduction + the v2.152.0 condition-disadvantage on the combatant (so the variant gates movement + attack rolls in combat) needs an inventory-change hook to fire the install; the derivation is the substrate that follow-up will read.

## Non-goals (v1)

- Push/drag/lift (STR × 30) — not load-bearing in the engine surface.
- Encumbered variant rule (Phase 4, filed).
- Animal carry caps (mounts, pack animals).
- Vehicle cargo capacity (carts, ships).
- Currency weight (50 coins = 1 lb RAW; descriptive at v1 since no demo PC tracks coin weights).
- Container-within-container (Bag of Holding inside Heward's Handy Haversack RAW collapses both into the Astral Plane — adds a fun encounter mechanic but no v1 surface).

## Definition of done (per phase)

1. Helpers in the leaf module are pure functions (no DB / FastAPI).
2. The sheet derivation is a request-time computation (no persistence layer changes).
3. Pure-Python tests for every helper + an integration test against `/sheet-json` for at least one phase.
4. `docs/automation-coverage.md` + `docs/test-harness-coverage.md` updated in the same commit.

## Related docs

- [exhaustion-levels.md](exhaustion-levels.md) — pattern reference; this plan mirrors its phasing.
- [`docs/test-harness-coverage.md`](../test-harness-coverage.md) — harness suite index.

