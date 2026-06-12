"""Phase 4 — Magic Missile deep-dive (the auto-hit multi-dart contract).

Magic Missile (PHB p.257) is the catalog's one true *auto-hit* attack:
"three glowing darts of magical force … Each dart hits a creature of
your choice that you can see within range … you can direct them to hit
one creature or several." No save, no attack roll — the darts simply
land. The engine models this in the `/cast_spell` auto-hit branch
(tabletop_routes.py:20551-20616): when a spell has ``damage`` but
neither ``save_ability`` nor ``attack_roll``, it rolls one damage die
*per target combatant id* in the cast body's ``target_combatant_ids``
list and surfaces each in ``auto_hit_targets`` (``rolled`` /
``breakdown`` / ``damage_applied`` / ``damage_type``) — but only when
``campaign.auto_apply_damage`` is on.

Where Phase 2A's `test_spell_catalog_autohit.py` checks the matrix shape
(3 darts at one target, each a 1d4+1 force roll in band), this file owns
Magic Missile's bespoke story — the part that distinguishes it from
Eldritch Blast's per-beam *attack rolls*:

  - the darts split across *several distinct* targets ("one creature or
    several"), each its own combatant id, roll, and applied damage;
  - the darts *auto-hit* — there is no attack-roll path, so the response
    carries ``auto_hit_targets`` and **not** ``auto_attack_beams``, and
    every dart applies non-zero damage on every dice seed (no dart ever
    misses — the contrast with Eldritch Blast, whose beams can whiff);
  - the aggregate applied damage is exactly the sum of the per-dart
    rolls — each a single 1d4+1 (2-5) force die, no rider on the
    auto-hit path (the Evoker's Empowered Evocation +INT lives on the
    weapon/attack pipeline, not the `/cast_spell` auto-hit branch).

Caster: Thalindra Moonwhisper (demo Wizard L7) — has Magic Missile
prepared + L1 slots natively, so no scratch-injection; the spell index
is resolved from the live sheet to stay robust to seed drift.
"""
from __future__ import annotations

import pytest_asyncio

from .conftest import CAMPAIGN_ID
from .spell_catalog import load_all_spells

_CASTER = "Thalindra Moonwhisper"
_CASTER_CLASS = "wizard"
_SLUG = "magic-missile"
_PER_DART = (2, 5)  # 1d4+1 force, inclusive band
_DTYPE = "force"


async def _set_auto_apply(gm_client, on: bool) -> bool:
    """Flip the campaign auto-apply flag via the TEST_MODE endpoint;
    return the prior value so the caller can restore it."""
    prior = bool((await gm_client.post(
        f"/api/test/campaign/{CAMPAIGN_ID}/flags", json={},
    )).json()["auto_apply_damage"])
    await gm_client.post(
        f"/api/test/campaign/{CAMPAIGN_ID}/flags",
        json={"auto_apply_damage": on},
    )
    return prior


async def _bandit_tmpl(gm_client):
    r = await gm_client.get(f"/api/campaign/{CAMPAIGN_ID}/templates")
    return next(t for t in r.json() if "bandit" in t["name"].lower())


async def _sheet(gm_client, char_id) -> dict:
    return (await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-json")
    ).json().get("sheet") or {}


async def _spell_index(gm_client, char_id) -> int:
    sheet = await _sheet(gm_client, char_id)
    for i, e in enumerate(sheet.get("spells") or []):
        if (e.get("_slug") or "") == _SLUG:
            return i
    raise AssertionError(f"{_SLUG} not on {char_id}'s sheet")


async def _seed_targets(gm_client, caster, target_ids):
    """Seed a battle with the caster + one high-HP bandit per target id
    so darts split across distinct combatants without killing any."""
    bandit = await _bandit_tmpl(gm_client)
    combatants = [
        {"id": f"tok_mm_{caster['id']}", "char_id": caster["id"],
         "name": caster["name"], "initiative": 10, "hp_current": 30, "hp_max": 30,
         "buffs": [], "economy": {"action": False, "bonus": False,
                                  "reaction": False, "movement": 0}},
    ]
    for n, tid in enumerate(target_ids):
        combatants.append(
            {"id": tid, "char_id": None, "token_template_id": bandit["id"],
             "name": f"Dart Target {n + 1}", "initiative": 7 - n,
             "hp_current": 999999, "hp_max": 999999, "buffs": [],
             "economy": {"action": False, "bonus": False,
                         "reaction": False, "movement": 0}},
        )
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": combatants, "turn_index": 0, "round": 1, "active": True},
    )


async def _cast(gm_client, caster, idx, target_ids):
    return await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
        json={"character_id": caster["id"], "spell_index": idx,
              "slot_level": 1, "class_slug": _CASTER_CLASS,
              "target_combatant_ids": list(target_ids),
              "override": True, "override_range": True},
    )


async def _seed_dice(gm_client, seed) -> None:
    await gm_client.post("/api/test/dice/seed", json={"seed": seed})


async def _long_rest(gm_client, char_id) -> None:
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/rest",
        json={"type": "long"},
    )


@pytest_asyncio.fixture
async def mm_caster(gm_client, roster):
    """Long-rest Thalindra, resolve the live spell index, enable
    auto-apply. Restores the auto-apply flag + clears the battle +
    resets the dice seed on teardown."""
    caster = roster[_CASTER]
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{caster['id']}/rest",
        json={"type": "long"},
    )
    idx = await _spell_index(gm_client, caster["id"])
    prior_flag = await _set_auto_apply(gm_client, True)
    try:
        yield {"caster": caster, "idx": idx}
    finally:
        await _set_auto_apply(gm_client, prior_flag)
        await _seed_dice(gm_client, None)
        await gm_client.put(
            f"/api/campaign/{CAMPAIGN_ID}/battle",
            json={"combatants": [], "turn_index": 0, "round": 1, "active": False},
        )


async def test_magic_missile_present_in_catalog():
    """Catalog anchor — Magic Missile present as a no-save / no-attack
    force-damage spell whose action documents the dart-count scaling
    (``aoe_targets`` 3 base + ``extra_targets_per_slot_above_base`` 1).
    A dropped scaling field silently changes the dart contract — caught
    here before the behavioural tests run."""
    by_slug = {(s.get("slug") or ""): s for s in load_all_spells()}
    assert _SLUG in by_slug, "magic-missile absent from catalog"
    spell = by_slug[_SLUG]
    action = next(a for a in spell["actions"] if a.get("damage"))
    assert not action.get("save_ability"), "magic-missile unexpectedly has a save"
    assert not action.get("attack_roll"), "magic-missile unexpectedly has an attack roll"
    assert (action.get("damage_type") or "").lower() == _DTYPE, action
    assert int(action.get("aoe_targets") or 0) == 3, action
    assert int(action.get("extra_targets_per_slot_above_base") or 0) == 1, action


async def test_three_darts_split_across_distinct_targets(gm_client, gm_ws, mm_caster):
    """The three darts can be directed at *several* creatures: cast at
    three distinct targets → three ``auto_hit_targets`` entries with
    three distinct combatant ids, each a 1d4+1 (2-5) force roll that
    applied non-zero damage."""
    mm = mm_caster
    target_ids = ["tok_mm_d1", "tok_mm_d2", "tok_mm_d3"]
    await _seed_targets(gm_client, mm["caster"], target_ids)

    r = await _cast(gm_client, mm["caster"], mm["idx"], target_ids)
    assert r.status_code == 200, r.text
    darts = r.json().get("auto_hit_targets") or []
    assert len(darts) == 3, f"expected 3 darts; got {len(darts)}: {darts}"
    assert {d["combatant_id"] for d in darts} == set(target_ids), darts
    for d in darts:
        lo, hi = _PER_DART
        assert lo <= int(d["rolled"]) <= hi, f"dart out of 1d4+1 band: {d}"
        assert (d.get("damage_type") or "").lower() == _DTYPE, d
        assert int(d["damage_applied"]) > 0, f"dart applied no damage: {d}"


async def test_darts_auto_hit_with_no_attack_roll(gm_client, gm_ws, mm_caster):
    """Magic Missile darts auto-hit: the response carries
    ``auto_hit_targets`` and **not** ``auto_attack_beams`` (no spell-
    attack path), and every dart applies non-zero damage on every dice
    seed — no dart ever misses. This is the contrast with Eldritch
    Blast, whose per-beam attack rolls can whiff."""
    mm = mm_caster
    target_ids = ["tok_mm_h1", "tok_mm_h2", "tok_mm_h3"]
    await _seed_targets(gm_client, mm["caster"], target_ids)

    for seed in range(1, 7):
        # Long-rest each iteration so Thalindra's finite L1 slots never
        # deplete mid-loop (override bypasses the economy gate but still
        # spends the slot).
        await _long_rest(gm_client, mm["caster"]["id"])
        await _seed_dice(gm_client, seed)
        r = await _cast(gm_client, mm["caster"], mm["idx"], target_ids)
        assert r.status_code == 200, r.text
        data = r.json()
        assert not data.get("auto_attack_beams"), (
            f"seed {seed}: Magic Missile took an attack-roll path: {data.get('auto_attack_beams')}"
        )
        darts = data.get("auto_hit_targets") or []
        assert len(darts) == 3, f"seed {seed}: expected 3 darts; got {darts}"
        for d in darts:
            assert int(d["damage_applied"]) > 0, (
                f"seed {seed}: a dart missed (applied 0): {d}"
            )


async def test_aggregate_is_exact_sum_of_darts(gm_client, gm_ws, mm_caster):
    """The total applied damage is exactly the sum of the per-dart rolls
    — each a single 1d4+1 (2-5) force die with no rider on the auto-hit
    path (the Evoker's Empowered Evocation +INT does not touch the
    `/cast_spell` auto-hit branch). Seeded for determinism."""
    mm = mm_caster
    target_ids = ["tok_mm_s1", "tok_mm_s2", "tok_mm_s3"]
    await _seed_targets(gm_client, mm["caster"], target_ids)
    await _seed_dice(gm_client, 7)

    r = await _cast(gm_client, mm["caster"], mm["idx"], target_ids)
    assert r.status_code == 200, r.text
    darts = r.json().get("auto_hit_targets") or []
    assert len(darts) == 3, darts

    lo, hi = _PER_DART
    for d in darts:
        assert lo <= int(d["rolled"]) <= hi, f"dart out of 1d4+1 band: {d}"
        # full-HP targets, force damage, no resistance → applied == rolled
        assert int(d["damage_applied"]) == int(d["rolled"]), d
    assert sum(int(d["damage_applied"]) for d in darts) == sum(
        int(d["rolled"]) for d in darts
    ), darts
