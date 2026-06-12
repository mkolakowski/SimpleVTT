"""Phase 4 — Eldritch Blast deep-dive (the multi-beam contract).

Eldritch Blast (PHB p.237) is the Warlock's signature cantrip: a ranged
spell attack for 1d10 force, that fires *additional beams* as the caster
levels — two at 5th, three at 11th, four at 17th, "make a separate attack
roll for each beam." The engine models this in the `/cast_spell`
spell-attack branch (tabletop_routes.py:19252-19349): the cantrip
``damage_scaling`` tier's ``extra_beams`` count drives ``total_beams``,
each beam rolls its own d20 + 1d10, and the per-beam detail surfaces in
``auto_attack_beams`` while the damage aggregates into a single
``_apply_damage_to_combatant`` call.

Where the catalog matrix (Phases 1-3) treats Eldritch Blast as just a
1d10 force attack cantrip, this file owns its bespoke story — the
multi-beam scaling:

  - at character level 5 the cast fires exactly 2 beams, each a separate
    attack roll surfaced in ``auto_attack_beams``;
  - the beam count tracks the caster's character level through the
    ``extra_beams`` scaling tiers (1 / 2 / 3 / 4 beams at L1 / L5 / L11 /
    L17);
  - the aggregate ``auto_attack_damage_rolled`` is exactly the sum of the
    per-beam rolls (no rider — Agonizing Blast's +CHA lives on the
    `/attack` weapon entry, not the `/cast_spell` path), every hit beam
    rolls a 1d10 (1-10) force die, and the damage type is ``force``.

Caster: Magnus Hexbinder (demo Warlock Lv 5 → 2 beams natively). The
level-scaling test PATCHes Magnus's sheet ``level`` to 11 / 17 / 1 and
restores it, so the ``extra_beams`` tiers are exercised end-to-end.
"""
from __future__ import annotations

import pytest_asyncio

from .conftest import CAMPAIGN_ID
from .spell_catalog import load_all_spells

_CASTER = "Magnus Hexbinder"
_CASTER_CLASS = "warlock"
_SLUG = "eldritch-blast"


async def _set_auto_apply(gm_client, on: bool) -> None:
    form = {
        "name": "Demo Campaign", "description": "demo", "game_system": "dnd5e",
        "gm_tab_color": "", "font_override": "", "default_encounter_id": "",
        "hp_threshold_1": "", "hp_threshold_2": "", "hp_threshold_3": "",
        "hp_threshold_4": "", "auto_play_playlist_id": "",
        "auto_play_mode": "order", "auto_play_initial_volume": "0.7",
    }
    if on:
        form["auto_apply_damage"] = "on"
    await gm_client.post(
        f"/campaign/{CAMPAIGN_ID}/settings", data=form, follow_redirects=False,
    )


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


async def _patch_level(gm_client, char_id, level: int) -> None:
    r = await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-fields",
        json={"level": level},
    )
    assert r.status_code == 200, r.text


async def _seed_battle(gm_client, caster, target_id):
    bandit = await _bandit_tmpl(gm_client)
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": [
            {"id": f"tok_eb_{caster['id']}", "char_id": caster["id"],
             "name": caster["name"], "initiative": 10, "hp_current": 30, "hp_max": 30,
             "buffs": [], "economy": {"action": False, "bonus": False,
                                      "reaction": False, "movement": 0}},
            {"id": target_id, "char_id": None, "token_template_id": bandit["id"],
             "name": "Blast Target", "initiative": 7, "hp_current": 200, "hp_max": 200,
             "buffs": [], "economy": {"action": False, "bonus": False,
                                      "reaction": False, "movement": 0}},
        ], "turn_index": 0, "round": 1, "active": True},
    )


async def _cast(gm_client, caster, idx, target_id):
    return await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
        json={"character_id": caster["id"], "spell_index": idx,
              "slot_level": 0, "class_slug": _CASTER_CLASS,
              "target_combatant_id": target_id, "target_name": "Blast Target",
              "override": True, "override_range": True},
    )


async def _seed_dice(gm_client, seed) -> None:
    await gm_client.post("/api/test/dice/seed", json={"seed": seed})


@pytest_asyncio.fixture
async def eb_caster(gm_client, roster):
    """Long-rest Magnus, resolve the live spell index, snapshot his level.
    Restores the level + clears the battle + resets the dice seed on
    teardown so a PATCHed level / seed can't leak to the next test."""
    caster = roster[_CASTER]
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{caster['id']}/rest",
        json={"type": "long"},
    )
    idx = await _spell_index(gm_client, caster["id"])
    orig_level = int((await _sheet(gm_client, caster["id"])).get("level") or 5)
    try:
        yield {"caster": caster, "idx": idx, "orig_level": orig_level}
    finally:
        await _patch_level(gm_client, caster["id"], orig_level)
        await _seed_dice(gm_client, None)
        await gm_client.put(
            f"/api/campaign/{CAMPAIGN_ID}/battle",
            json={"combatants": [], "turn_index": 0, "round": 1, "active": False},
        )


async def test_eldritch_blast_present_in_catalog():
    """Catalog anchor — Eldritch Blast present with the multi-beam
    ``extra_beams`` scaling tiers (L5 +1, L11 +2, L17 +3) that drive the
    beam count. A dropped/edited tier silently collapses the spell to a
    single beam — caught here before the behavioural tests run."""
    by_slug = {(s.get("slug") or ""): s for s in load_all_spells()}
    assert _SLUG in by_slug, "eldritch-blast absent from catalog"
    action = next(a for a in by_slug[_SLUG]["actions"] if a.get("damage"))
    tiers = {int(t["level"]): int(t.get("extra_beams") or 0)
             for t in (action.get("damage_scaling") or [])}
    assert tiers.get(5) == 1, tiers
    assert tiers.get(11) == 2, tiers
    assert tiers.get(17) == 3, tiers


async def test_cast_fires_two_beams_at_level_five(gm_client, gm_ws, eb_caster):
    """Magnus (Lv 5) casts Eldritch Blast → exactly 2 beams, each a
    separate attack roll surfaced in ``auto_attack_beams`` (numbered 1
    and 2, each with an int total + bool hit); the aggregate damage type
    is force."""
    eb = eb_caster
    target_id = "tok_eb_t5"
    await _seed_battle(gm_client, eb["caster"], target_id)

    r = await _cast(gm_client, eb["caster"], eb["idx"], target_id)
    assert r.status_code == 200, r.text
    data = r.json()
    beams = data.get("auto_attack_beams") or []
    assert len(beams) == 2, f"Lv 5 Warlock should fire 2 beams; got {len(beams)}: {beams}"
    assert [b["beam"] for b in beams] == [1, 2], beams
    for b in beams:
        assert isinstance(b["total"], int)
        assert isinstance(b["hit"], bool)
    assert data["auto_attack_damage_type"] == "force", data


async def test_beam_count_tracks_character_level(gm_client, gm_ws, eb_caster):
    """The beam count follows the caster's character level through the
    ``extra_beams`` scaling tiers: 1 beam at L1, 3 at L11, 4 at L17."""
    eb = eb_caster
    target_id = "tok_eb_lvl"
    await _seed_battle(gm_client, eb["caster"], target_id)

    for level, expected_beams in [(1, 1), (11, 3), (17, 4)]:
        await _patch_level(gm_client, eb["caster"]["id"], level)
        r = await _cast(gm_client, eb["caster"], eb["idx"], target_id)
        assert r.status_code == 200, r.text
        beams = r.json().get("auto_attack_beams") or []
        assert len(beams) == expected_beams, (
            f"Lv {level} should fire {expected_beams} beams; got {len(beams)}"
        )


async def test_aggregate_damage_is_sum_of_hit_beams(gm_client, gm_ws, eb_caster):
    """The aggregate ``auto_attack_damage_rolled`` is exactly the sum of
    the per-beam rolls; every hit beam rolls a 1d10 (1-10) force die (no
    rider on the cast path), and the damage type is force. Seeds the dice
    until at least one beam hits so the damage assertions exercise a real
    hit."""
    eb = eb_caster
    target_id = "tok_eb_dmg"
    await _set_auto_apply(gm_client, on=True)
    await _seed_battle(gm_client, eb["caster"], target_id)

    data = None
    for seed in range(1, 60):
        await _seed_dice(gm_client, seed)
        r = await _cast(gm_client, eb["caster"], eb["idx"], target_id)
        assert r.status_code == 200, r.text
        d = r.json()
        if d.get("auto_attack_hit"):
            data = d
            break
    assert data is not None, "no seed in 1..59 produced a beam hit — check attack math"

    beams = data.get("auto_attack_beams") or []
    assert len(beams) == 2, beams
    assert data["auto_attack_damage_type"] == "force", data
    assert data["auto_attack_damage_rolled"] == sum(
        int(b.get("damage_rolled") or 0) for b in beams
    ), data
    for b in beams:
        if b["hit"]:
            assert 1 <= int(b["damage_rolled"]) <= 10, (
                f"hit beam should roll a single 1d10 force die (1-10); got {b}"
            )
        else:
            assert int(b["damage_rolled"]) == 0, f"missed beam rolled damage: {b}"
