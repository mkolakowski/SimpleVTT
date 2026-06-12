"""Phase 2A.2 — exact-value damage assertions via seeded dice.

The Phase 2A backfills (`test_spell_catalog_damage.py` attack-roll,
`test_spell_catalog_multibeam.py`, `test_spell_catalog_save_damage.py`,
`test_spell_catalog_autohit.py`) all range-check the rolled damage
against the dice band. This file closes the filed Phase 2A.2 follow-up:
seed the RNG (`/api/test/dice/seed`) so each cast is deterministic, then
parse the engine's own damage *breakdown* string and assert it's exactly
self-consistent — the individual dice shown sum to the reported subtotal,
the subtotals sum to the reported grand total, the grand total equals the
response's rolled field, and the dice expression (count + sides) is
exactly the one the catalog declares for that spell at the caster's level.

Why parse the breakdown instead of predicting the seeded roll: the cast
path draws from a shared running RNG (attack d20s, saves, then damage), so
predicting the exact damage value would couple the test to the draw order.
The breakdown carries the actual dice rolled (`8d6[3,5,1,...]=24  =>  24`),
so verifying arithmetic self-consistency + the exact `NdM` shape is both
robust and genuinely exact — a content edit that changes "8d6" → "8d8", or
an engine bug that fudges a total away from the dice it claims to have
rolled, fails here where a band check would not.

Covers one representative per damage shape, so all four response shapes
that surface a breakdown are exercised:
  - attack-roll  → `auto_attack_damage_breakdown` (Fire Bolt, 2d10)
  - multi-beam   → `auto_attack_beams[*].damage_breakdown` (Scorching Ray, 2d6/beam)
  - save-for-half→ `auto_save_damage_breakdown` (Fireball, 8d6)
  - auto-hit     → `auto_hit_targets[*].breakdown` (Magic Missile, 1d4+1/dart)

A crit doubles the dice (2d10 → 4d10, 2d6 → 4d6), so the attack-roll and
multi-beam blocks accept either the base or the doubled count and band the
total accordingly — the self-consistency + exact-sides check still holds.

Same scratch-caster bulk-inject scaffolding as the other Phase 2 files,
plus the v2.183.0 TEST_MODE flags toggle for the save/auto-hit shapes.
"""
from __future__ import annotations

import re

from .conftest import CAMPAIGN_ID
from .spell_catalog import load_all_spells

_SCRATCH_CASTER = "Thalindra Moonwhisper"
_SCRATCH_CLASS = "wizard"

# Each die token in a breakdown: "8d6[3,5,1]=24" / "2d20kh1[5,12]kh1=12".
_DICE_TOKEN = re.compile(r"(\d+)d(\d+)[a-z0-9]*\[([0-9,]+)\][a-z0-9]*=(-?\d+)")
# The grand total the engine appends: "...  =>  24".
_GRAND_TOTAL = re.compile(r"=>\s*(-?\d+)\s*$")


def _all_entries(spells: list[dict]) -> list[dict]:
    out: list[dict] = []
    for s in spells:
        slug = (s.get("slug") or "").strip()
        if not slug:
            continue
        out.append({
            "name": s.get("name") or slug,
            "_slug": slug,
            "level": int(s.get("level_int") or 0),
            "class": _SCRATCH_CLASS,
            "prepared": True,
            "casting_time": s.get("casting_time") or "1 action",
        })
    return out


def _abundant_slots() -> dict:
    return {_SCRATCH_CLASS: {str(lvl): {"total": 999, "used": 0} for lvl in range(1, 10)}}


def _check_breakdown(breakdown: str, *, sides: int, allowed_counts: set[int],
                     reported_total: int) -> list[str]:
    """Assert the breakdown is exactly self-consistent for a single
    `count d sides (+flat)` damage roll. Returns a list of failure
    strings (empty == OK)."""
    fails: list[str] = []
    tokens = _DICE_TOKEN.findall(breakdown or "")
    die_tokens = [(int(c), int(s), rolls, int(sub)) for c, s, rolls, sub in tokens]
    matching = [t for t in die_tokens if t[1] == sides]
    if len(matching) != 1:
        return [f"expected exactly one d{sides} token, got {len(matching)} "
                f"in {breakdown!r}"]
    count, _sides, rolls_s, subtotal = matching[0]
    if count not in allowed_counts:
        fails.append(f"d{sides} count {count} not in allowed {sorted(allowed_counts)} "
                     f"({breakdown!r})")
    rolls = [int(x) for x in rolls_s.split(",") if x != ""]
    if len(rolls) != count:
        fails.append(f"d{sides} shows {len(rolls)} dice but count is {count} "
                     f"({breakdown!r})")
    for r in rolls:
        if not (1 <= r <= sides):
            fails.append(f"d{sides} roll {r} out of [1,{sides}] ({breakdown!r})")
    if sum(rolls) != subtotal:
        fails.append(f"d{sides} dice {rolls} sum to {sum(rolls)} != subtotal "
                     f"{subtotal} ({breakdown!r})")
    gm = _GRAND_TOTAL.search(breakdown or "")
    if not gm:
        fails.append(f"no grand total in breakdown {breakdown!r}")
    else:
        grand = int(gm.group(1))
        if grand != reported_total:
            fails.append(f"grand total {grand} != reported rolled {reported_total} "
                         f"({breakdown!r})")
        # The grand total must be the subtotal plus any flat modifier; for
        # a single-die-group damage expr the flat is grand - subtotal and
        # must be >= 0 (our spells add at most a small flat, never subtract).
        flat = grand - subtotal
        if flat < 0:
            fails.append(f"implied flat modifier {flat} is negative ({breakdown!r})")
    return fails


async def _seed_dice(gm_client, seed) -> None:
    await gm_client.post("/api/test/dice/seed", json={"seed": seed})


async def _seed_low_ac_bandit(gm_client) -> str:
    """One very-high-HP, low-AC NPC so attack-roll spells reliably hit
    and successive casts never drop it."""
    templates = (await gm_client.get(f"/api/campaign/{CAMPAIGN_ID}/templates")).json()
    bandit = next(t for t in templates if "bandit" in t["name"].lower())
    cid = "tok_exactdmg_target"
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={
            "combatants": [{
                "id": cid, "char_id": None,
                "token_template_id": bandit["id"],
                "name": "Exact Damage Target",
                "initiative": 5, "hp_current": 999999, "hp_max": 999999,
                "ac": 1,
                "buffs": [],
                "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0},
            }],
            "turn_index": 0, "round": 1, "active": True,
        },
    )
    return cid


async def test_exact_damage_breakdown_is_self_consistent_across_shapes(gm_client, roster):
    """Seed the RNG and assert every damage shape's breakdown is exactly
    self-consistent (shown dice sum to the reported total) with the exact
    catalog dice expression — attack-roll, multi-beam, save-for-half, and
    auto-hit all covered."""
    caster = roster[_SCRATCH_CASTER]
    cid = caster["id"]

    snap = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{cid}/sheet-json",
    )
    sheet = (snap.json() or {}).get("sheet") or {}
    orig_spells = sheet.get("spells") or []
    orig_slots = sheet.get("spell_slots") or {}

    spells = load_all_spells()
    entries = _all_entries(spells)
    idx_by_slug = {e["_slug"]: i for i, e in enumerate(entries)}

    patch = await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{cid}/sheet-fields",
        json={"spells": entries, "spell_slots": _abundant_slots()},
    )
    assert patch.status_code == 200, patch.text

    orig_flag = bool((await gm_client.post(
        f"/api/test/campaign/{CAMPAIGN_ID}/flags", json={},
    )).json()["auto_apply_damage"])
    await gm_client.post(
        f"/api/test/campaign/{CAMPAIGN_ID}/flags",
        json={"auto_apply_damage": True},
    )

    failures: list[str] = []
    shapes_checked = 0
    try:
        target_id = await _seed_low_ac_bandit(gm_client)

        async def _cast(slug, slot):
            await _seed_dice(gm_client, 4242)
            return await gm_client.post(
                f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
                json={
                    "character_id": cid,
                    "spell_index": idx_by_slug[slug],
                    "slot_level": slot,
                    "class_slug": _SCRATCH_CLASS,
                    "target_combatant_id": target_id,
                    "target_combatant_ids": [target_id],
                    "target_name": "Exact Damage Target",
                    "override": True,
                },
            )

        # --- attack-roll: Fire Bolt 2d10 (4d10 on crit). Loop seeds for a hit.
        hit_data = None
        for s in range(200):
            await _seed_dice(gm_client, 7000 + s)
            r = await gm_client.post(
                f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
                json={"character_id": cid, "spell_index": idx_by_slug["fire-bolt"],
                      "slot_level": 0, "class_slug": _SCRATCH_CLASS,
                      "target_combatant_id": target_id,
                      "target_name": "Exact Damage Target", "override": True},
            )
            d = r.json()
            if r.status_code == 200 and d.get("auto_attack_hit"):
                hit_data = d
                break
        if hit_data is None:
            failures.append("fire-bolt: no hit found in 200 seeds")
        else:
            bd = hit_data.get("auto_attack_damage_breakdown") or ""
            rolled = int(hit_data.get("auto_attack_damage_rolled") or 0)
            crit = bool(hit_data.get("auto_attack_crit"))
            counts = {4} if crit else {2}
            fails = _check_breakdown(bd, sides=10, allowed_counts=counts,
                                     reported_total=rolled)
            failures += [f"fire-bolt: {m}" for m in fails]
            shapes_checked += 1

        # --- multi-beam: Scorching Ray 3×2d6. Loop seeds for >=1 hitting beam.
        beam_hit = None
        for s in range(200):
            await _seed_dice(gm_client, 8000 + s)
            r = await gm_client.post(
                f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
                json={"character_id": cid, "spell_index": idx_by_slug["scorching-ray"],
                      "slot_level": 2, "class_slug": _SCRATCH_CLASS,
                      "target_combatant_id": target_id,
                      "target_name": "Exact Damage Target", "override": True},
            )
            d = r.json()
            beams = d.get("auto_attack_beams") or []
            hitting = [b for b in beams if b.get("hit")]
            if r.status_code == 200 and hitting:
                beam_hit = hitting[0]
                break
        if beam_hit is None:
            failures.append("scorching-ray: no hitting beam found in 200 seeds")
        else:
            bd = beam_hit.get("damage_breakdown") or beam_hit.get("breakdown") or ""
            rolled = int(beam_hit.get("damage_rolled") or beam_hit.get("total") or 0)
            counts = {4} if beam_hit.get("crit") else {2}
            fails = _check_breakdown(bd, sides=6, allowed_counts=counts,
                                     reported_total=rolled)
            failures += [f"scorching-ray: {m}" for m in fails]
            shapes_checked += 1

        # --- save-for-half: Fireball 8d6 (no crit).
        r = await _cast("fireball", 3)
        d = r.json()
        if r.status_code != 200:
            failures.append(f"fireball: HTTP {r.status_code} {r.text[:120]}")
        else:
            bd = d.get("auto_save_damage_breakdown") or ""
            rolled = int(d.get("auto_save_damage_rolled") or 0)
            fails = _check_breakdown(bd, sides=6, allowed_counts={8},
                                     reported_total=rolled)
            failures += [f"fireball: {m}" for m in fails]
            shapes_checked += 1

        # --- auto-hit: Magic Missile, 3 darts of 1d4+1 each.
        r = await _cast("magic-missile", 1)
        d = r.json()
        if r.status_code != 200:
            failures.append(f"magic-missile: HTTP {r.status_code} {r.text[:120]}")
        else:
            darts = d.get("auto_hit_targets") or []
            if not darts:
                failures.append(f"magic-missile: no auto_hit_targets: {d.get('auto_hit_targets')!r}")
            else:
                for i, dart in enumerate(darts):
                    bd = dart.get("breakdown") or ""
                    rolled = int(dart.get("rolled") or 0)
                    fails = _check_breakdown(bd, sides=4, allowed_counts={1},
                                             reported_total=rolled)
                    failures += [f"magic-missile dart {i}: {m}" for m in fails]
                    # 1d4+1 → exact band [2,5].
                    if not (2 <= rolled <= 5):
                        failures.append(f"magic-missile dart {i}: rolled {rolled} not in [2,5]")
                shapes_checked += 1
    finally:
        await _seed_dice(gm_client, None)
        await gm_client.post(
            f"/api/test/campaign/{CAMPAIGN_ID}/flags",
            json={"auto_apply_damage": orig_flag},
        )
        await gm_client.patch(
            f"/api/campaign/{CAMPAIGN_ID}/character/{cid}/sheet-fields",
            json={"spells": orig_spells, "spell_slots": orig_slots},
        )

    assert shapes_checked == 4, (
        f"only checked {shapes_checked}/4 damage shapes; a representative "
        f"spell may have dropped out of the catalog."
    )
    assert not failures, (
        f"{len(failures)} exact-damage breakdown failures:\n  " + "\n  ".join(failures)
    )
