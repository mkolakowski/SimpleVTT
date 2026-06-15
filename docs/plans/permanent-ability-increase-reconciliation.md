# Permanent ability-increase reconciliation — design plan

**Status:** 🟠 in progress — Option 2a chosen. Phase 0 (plan) ✅ v2.311.0. Phase 1 (port CON max-HP into `permanent_boost`) ✅ v2.312.0. Phase 2 (complete Tome trio on `permanent_boost`) ✅ v2.313.0. Phase 3 (retire the `/use_item` `ability_increase` path) filed.

**Authors:** rolling
**Last updated:** 2026-06-14

A plan to reconcile **two parallel implementations** of the same RAW feature — permanent ability-score-increase consumables (Manuals & Tomes, RAW DMG pp.176/180/208) — that now coexist in the codebase, and to decide how to complete the demo coverage for all six books without compounding the divergence.

## The problem

Two independent dispatch paths permanently raise an ability score by 2 and consume the book. They were built a day apart and overlap on the three Manuals.

### System A — `permanent_boost` on `/use_item_action` (v2.222.0 "The Studied Page", 2026-06-13)

- **Endpoint:** `POST /api/campaign/{cid}/character/{char_id}/use_item_action` with `{inventory_index, action_key: "read"}`.
- **Dispatch:** slug → `_use_item_action_permanent_boost` (tabletop_routes.py ~83455). Routed for all six slugs at ~82851.
- **Catalog:** the action catalog (~34350) carries `permanent_boost: {ability, amount, feature_name, summary_effect}` entries for **all six** books — `manual-of-gainful-exercise` (STR), `manual-of-bodily-health` (CON), `manual-of-quickness-of-action` (DEX), `tome-of-clear-thought` (INT), `tome-of-understanding` (WIS), `tome-of-leadership-and-influence` (CHA).
- **Behavior:** flat `sheet.abilities[X] += 2`, consume, broadcast `feature_used` + `inventory_update`. Returns `{ok, ability, amount, old_score, new_score, consumed, remaining_qty}`.
- **Does NOT** recompute max HP on a CON increase.
- **Demo seed:** only Lyra Sunstrider's **Tome of Leadership and Influence** (CHA).
- **Tests:** `tests/harness/test_item_manual_of_ability.py` (2 tests) — Lyra reads the tome via `/use_item_action`.

### System B — `use_kind: "ability_increase"` on `/use_item` (this session, v2.308.0–v2.310.0, 2026-06-14)

- **Endpoint:** `POST /api/campaign/{cid}/use_item` with `{character_id, inventory_index, override}`.
- **Dispatch:** `item["use_kind"] == "ability_increase"` branch in `use_item` (tabletop_routes.py ~22697).
- **Behavior:** tolerant stored-ability write (multiple key shapes) clamped to 30, consume, broadcast `feature_used` (`📖 Studied …`) + `character_update`. Returns `{ok, …, ability_increase: {ability, amount, new_score[, hp_gain]}}`.
- **DOES recompute max HP** on a CON increase (v2.309.0): `mod_delta × level` added to both `hp.max` and `hp.current`, surfaced as `hp_gain`.
- **Demo seed:** Garrik Ironside carries all three **Manuals** (STR/CON/DEX), each seeded with `use_kind: "ability_increase"`.
- **Tests:** `test_item_manual_of_gainful_exercise.py`, `test_item_manual_of_bodily_health.py`, `test_item_manual_of_quickness_of_action.py` (6 tests) — Garrik uses each via `/use_item`.

### Consequences of the overlap

1. **Dual dispatch for the three Manuals.** Garrik's seeded manuals have `use_kind: "ability_increase"` (System B) AND slugs that route to `permanent_boost` (System A). Either endpoint will raise + consume — two code paths, one item.
2. **CON max-HP logic exists in only one path.** System B recomputes max HP (RAW PHB p.173); System A does not. A Manual of Bodily Health read via `/use_item_action` raises CON but silently skips the max-HP bump.
3. **Divergent response shapes & broadcasts.** System A returns `old_score`/`new_score` and broadcasts `feature_used`+`inventory_update`; System B returns an `ability_increase` object and broadcasts `feature_used`+`character_update`. UI handlers must know which endpoint fired.
4. **Tomes are only half-demoed.** All three tomes have full System-A catalog + dispatch, but only Leadership/CHA is seeded + tested. Clear Thought (INT) and Understanding (WIS) have no demo carrier and no test.

## Why this matters

The two systems do the same RAW thing with different shapes and a behavioral gap (max HP). Leaving both in place means future ability-increase content (e.g. a hypothetical "+1 stat" reward, the Ioun Stone of Leadership) has two templates to choose from and a subtle correctness trap (CON without max HP). Before adding the two missing tomes, we should decide whether to **converge** on one path or **deliberately keep both** with a documented boundary.

## Options

### Option 1 — Complete the trio on System A, defer cleanup (lowest risk)

Seed Tome of Clear Thought (INT) + Tome of Understanding (WIS) and test them via the existing `/use_item_action` `"read"` path (mirroring `test_item_manual_of_ability.py`). No engine change. Tomes become fully demoed + consistent with the seeded Leadership tome. The Manual duplication and the CON max-HP gap remain, tracked as follow-on debt.

- **Pro:** one small commit, zero churn on shipped code, finishes the user's "Tome trio" ask immediately.
- **Con:** the duplication persists; System A's CON path is still max-HP-incorrect.

### Option 2 — Converge on one canonical path (cleanest)

Pick a survivor, port the missing capability, retire the other.

- **2a — Keep System A (`permanent_boost`), retire System B.** Port the CON max-HP recompute into `_use_item_action_permanent_boost`. Re-seed Garrik's manuals to use `action_key: "read"` (drop `use_kind`). Remove the `use_kind: "ability_increase"` branch from `/use_item` and its three test files; re-point them at `/use_item_action`. Then seed + test the two tomes. Net: one mechanism, max-HP-correct, all six books demoed.
- **2b — Keep System B (`ability_increase`), retire System A.** Move all six books onto `use_kind: "ability_increase"` demo items, delete the `permanent_boost` catalog entries + handler + dispatch + `test_item_manual_of_ability.py`, re-seed Lyra's tome. Net: one mechanism, but discards the older tested handler.

- **Pro:** single mechanism, no correctness trap, clear template for future content.
- **Con:** touches shipped + pushed code across several commits; needs careful test migration.

**Recommendation within Option 2:** 2a. System A is older, already handles all six slugs in catalog + dispatch, and its `action_key` model matches the rest of the consumable-action family (potions of fire breath, etc.). The only thing it lacks is the CON max-HP recompute, which is a small port from System B's v2.309.0 branch.

### Option 3 — Keep both, document the boundary

Declare System B (`/use_item`) the player-facing quick-use path and System A (`/use_item_action`) the catalog-action path, port the CON max-HP fix into BOTH, and add a code comment cross-linking them. Complete the tomes on whichever path their carrier uses.

- **Pro:** no removal of shipped code.
- **Con:** keeps two mechanisms forever; every future change must touch both; highest long-term maintenance cost.

## Recommended path

**Option 2a**, sequenced so the user's "Tome trio" ask is still satisfied:

- **Phase 1 — Port CON max-HP into System A.** Add the `mod_delta × level` max-HP recompute to `_use_item_action_permanent_boost`; extend `test_item_manual_of_ability.py` (or a new CON test) to assert it. Closes the correctness gap regardless of the later removal.
- **Phase 2 — Complete the Tome trio on System A.** Seed Tome of Clear Thought (INT) + Tome of Understanding (WIS) on demo casters; add `/use_item_action` `"read"` tests. Satisfies the original ask.
- **Phase 3 — Retire System B.** Re-seed Garrik's manuals to `action_key: "read"` (drop `use_kind`); remove the `ability_increase` branch from `/use_item`; migrate the three v2.308–310 test files to `/use_item_action` (or fold into `test_item_manual_of_ability.py`). One mechanism remains.

If the user prefers to ship the trio first and clean up later, run **Phase 2 alone as Option 1** and file Phases 1 + 3 as follow-on debt.

## RAW reference

- **Manual of Gainful Exercise** (STR +2), **Manual of Bodily Health** (CON +2), **Manual of Quickness of Action** (DEX +2) — DMG p.176, very rare, no attunement, 48 hours' study over 6 days.
- **Tome of Clear Thought** (INT +2), **Tome of Understanding** (WIS +2), **Tome of Leadership and Influence** (CHA +2) — DMG pp.208–209, very rare, no attunement, same study time.
- All raise the score **and its maximum**, so the +2 always lands (no RAW-20 clamp). A CON increase retroactively raises max HP by 1 per level (PHB p.173).
