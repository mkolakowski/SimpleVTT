"""Phase 4 — Spirit Guardians deep-dive (the concentration-aura contract).

Spirit Guardians (PHB p.278) is a 3rd-level Cleric spell that fills a
15-ft sphere centred on the caster with damaging spirits for the
duration (Concentration, up to 10 minutes). It is the catalog's
canonical *self-anchored concentration AoE*: the engine models it as a
``self_sphere`` whose placed marker tracks the caster's token and rolls
a Wisdom save (3d8 radiant, save-for-half) against each creature in the
area.

Where the catalog matrix (Phases 1-3) only checks Spirit Guardians'
damage/save fields in isolation, this file owns its bespoke story across
the live cast → place → persist path:

  - the cast (no targets) lands as a *pending self-sphere placement* and
    the response flags it as a concentration spell — Spirit Guardians is
    Concentration RAW (the catalog ``concentration`` flag was corrected
    from ``false`` to ``true`` alongside this test; the cast path already
    treated it as concentration via the "Up to ..." duration fallback,
    but the ``spell_concentration`` response field read the raw flag);
  - ``/place_aoe`` dispatches the Wisdom save against every NPC in the
    sphere, applying 3d8 *radiant* save-for-half damage;
  - the placement persists as a *self-anchored* concentration marker
    (``is_self_anchored: True``) so the aura follows the caster;
  - that self-anchored marker is *not movable* via ``/move_aoe`` (409
    ``not_movable``) — Spirit Guardians tracks the caster's token, it
    can't be repositioned like Web/Moonbeam.

Caster: Tavik Stormhand (Cleric) — has Spirit Guardians prepared + L3
slots natively in the demo seed, so no scratch-injection is needed; the
spell index is resolved from the live sheet to stay robust to seed drift.
"""
from __future__ import annotations

import asyncio

import pytest_asyncio

from .conftest import CAMPAIGN_ID
from .spell_catalog import load_all_spells

_CASTER = "Brother Tavik Stonebrow"
_CASTER_CLASS = "cleric"
_SLUG = "spirit-guardians"


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


async def _spell_index(gm_client, char_id) -> int:
    sheet = (await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-json")
    ).json().get("sheet") or {}
    for i, e in enumerate(sheet.get("spells") or []):
        if (e.get("_slug") or "") == _SLUG:
            return i
    raise AssertionError(f"{_SLUG} not on {char_id}'s sheet")


async def _seed_battle(gm_client, caster, bandits):
    combatants = [
        {"id": f"tok_sg_{caster['id']}", "char_id": caster["id"],
         "name": caster["name"], "initiative": 10, "hp_current": 60, "hp_max": 60,
         "buffs": [], "economy": {"action": False, "bonus": False,
                                  "reaction": False, "movement": 0}},
    ]
    combatants.extend(bandits)
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": combatants, "turn_index": 0, "round": 1, "active": True},
    )


@pytest_asyncio.fixture
async def sg_caster(gm_client, roster):
    """Long-rest Tavik (refills the L3 slot) and resolve the live spell
    index. Clears the battle on teardown so the marker + combatants don't
    leak into the next test."""
    caster = roster[_CASTER]
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{caster['id']}/rest",
        json={"type": "long"},
    )
    idx = await _spell_index(gm_client, caster["id"])
    try:
        yield {"caster": caster, "idx": idx}
    finally:
        await gm_client.put(
            f"/api/campaign/{CAMPAIGN_ID}/battle",
            json={"combatants": [], "turn_index": 0, "round": 1, "active": False},
        )


async def test_spirit_guardians_present_in_catalog():
    """Catalog anchor — a rename/removal trips here before the
    behavioural tests run, and confirms the corrected concentration flag
    is now true in the shipped JSON."""
    by_slug = {(s.get("slug") or ""): s for s in load_all_spells()}
    assert _SLUG in by_slug, "spirit-guardians absent from catalog"
    assert by_slug[_SLUG].get("concentration") is True, (
        "Spirit Guardians is Concentration RAW — catalog flag must be true"
    )


async def test_cast_marks_concentration_and_pending_self_sphere(
    gm_client, gm_ws, sg_caster,
):
    """Casting Spirit Guardians without targets lands a pending
    self-sphere placement (15-ft `self_sphere`), and the `spell_cast`
    broadcast flags it as a concentration spell — the field the catalog
    `concentration` flag fix corrects (the broadcast carries the full
    cast payload; the HTTP response is a curated subset that omits it)."""
    sg = sg_caster
    bandit = await _bandit_tmpl(gm_client)
    await _seed_battle(gm_client, sg["caster"], [
        {"id": "tok_sg_b1", "char_id": None, "token_template_id": bandit["id"],
         "name": "Aura Bandit", "initiative": 7, "hp_current": 50, "hp_max": 50,
         "buffs": [], "economy": {"action": False, "bonus": False,
                                  "reaction": False, "movement": 0}},
    ])

    gm_ws.mark()
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
        json={"character_id": sg["caster"]["id"], "spell_index": sg["idx"],
              "slot_level": 3, "class_slug": _CASTER_CLASS, "override": True},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["pending_aoe_placement"] is True, data
    assert data["area_shape"] == "self_sphere", data
    assert data["area_size_ft"] == 15, data

    bcast = await gm_ws.wait_for("spell_cast", timeout=3.0)
    assert bcast["data"].get("spell_concentration") is True, (
        f"Spirit Guardians must broadcast as a concentration spell; got "
        f"spell_concentration={bcast['data'].get('spell_concentration')}"
    )


async def test_place_dispatches_radiant_saves(gm_client, gm_ws, sg_caster):
    """/place_aoe rolls the Wisdom save against every NPC in the sphere
    and applies 3d8 radiant save-for-half damage."""
    sg = sg_caster
    bandit = await _bandit_tmpl(gm_client)
    await _set_auto_apply(gm_client, on=True)
    await _seed_battle(gm_client, sg["caster"], [
        {"id": "tok_sg_r1", "char_id": None, "token_template_id": bandit["id"],
         "name": "Radiant Bandit A", "initiative": 7, "hp_current": 50, "hp_max": 50,
         "buffs": [], "economy": {"action": False, "bonus": False,
                                  "reaction": False, "movement": 0}},
        {"id": "tok_sg_r2", "char_id": None, "token_template_id": bandit["id"],
         "name": "Radiant Bandit B", "initiative": 6, "hp_current": 50, "hp_max": 50,
         "buffs": [], "economy": {"action": False, "bonus": False,
                                  "reaction": False, "movement": 0}},
    ])

    cast = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
        json={"character_id": sg["caster"]["id"], "spell_index": sg["idx"],
              "slot_level": 3, "class_slug": _CASTER_CLASS, "override": True},
    )
    assert cast.status_code == 200, cast.text
    cast_id = cast.json()["id"]

    place = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/place_aoe",
        json={"cast_id": cast_id, "target_combatant_ids": ["tok_sg_r1", "tok_sg_r2"]},
    )
    assert place.status_code == 200, place.text
    targets = place.json().get("auto_save_targets") or []
    assert len(targets) == 2, f"expected 2 per-target outcomes, got {targets}"
    assert {t["target_name"] for t in targets} == {"Radiant Bandit A", "Radiant Bandit B"}
    for t in targets:
        assert isinstance(t["rolled"], int)
        assert isinstance(t["passed"], bool)
        assert t["damage_type"] == "radiant", t
        assert t["damage_applied"] > 0, f"bandit took 0 radiant damage: {t}"


async def test_place_creates_self_anchored_concentration_marker(
    gm_client, gm_ws, sg_caster,
):
    """Placing Spirit Guardians persists a self-anchored concentration
    marker that follows the caster (`is_self_anchored: True`)."""
    sg = sg_caster
    bandit = await _bandit_tmpl(gm_client)
    await _seed_battle(gm_client, sg["caster"], [
        {"id": "tok_sg_m1", "char_id": None, "token_template_id": bandit["id"],
         "name": "Marker Bandit", "initiative": 7, "hp_current": 50, "hp_max": 50,
         "buffs": [], "economy": {"action": False, "bonus": False,
                                  "reaction": False, "movement": 0}},
    ])

    cast = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
        json={"character_id": sg["caster"]["id"], "spell_index": sg["idx"],
              "slot_level": 3, "class_slug": _CASTER_CLASS, "override": True},
    )
    assert cast.status_code == 200, cast.text
    cast_id = cast.json()["id"]

    gm_ws.mark()
    place = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/place_aoe",
        json={"cast_id": cast_id, "target_combatant_ids": ["tok_sg_m1"]},
    )
    assert place.status_code == 200, place.text

    upd = await gm_ws.wait_for("concentration_aoe_update", timeout=3.0)
    marker = next((m for m in upd["data"]["markers"]
                   if m.get("spell_slug") == _SLUG), None)
    assert marker is not None, f"no Spirit Guardians marker; got {upd['data']}"
    assert marker["is_self_anchored"] is True, marker
    assert marker["shape"] == "self_sphere", marker
    assert int(marker["caster_char_id"]) == int(sg["caster"]["id"]), marker


async def test_self_anchored_marker_not_movable(gm_client, gm_ws, sg_caster):
    """A self-anchored Spirit Guardians marker can't be repositioned —
    /move_aoe returns 409 not_movable (the aura tracks the caster)."""
    sg = sg_caster
    bandit = await _bandit_tmpl(gm_client)
    await _seed_battle(gm_client, sg["caster"], [
        {"id": "tok_sg_n1", "char_id": None, "token_template_id": bandit["id"],
         "name": "Anchor Bandit", "initiative": 7, "hp_current": 50, "hp_max": 50,
         "buffs": [], "economy": {"action": False, "bonus": False,
                                  "reaction": False, "movement": 0}},
    ])

    cast = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
        json={"character_id": sg["caster"]["id"], "spell_index": sg["idx"],
              "slot_level": 3, "class_slug": _CASTER_CLASS, "override": True},
    )
    assert cast.status_code == 200, cast.text
    cast_id = cast.json()["id"]

    gm_ws.mark()
    place = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/place_aoe",
        json={"cast_id": cast_id, "target_combatant_ids": ["tok_sg_n1"]},
    )
    assert place.status_code == 200, place.text
    upd = await gm_ws.wait_for("concentration_aoe_update", timeout=3.0)
    marker = next((m for m in upd["data"]["markers"]
                   if m.get("spell_slug") == _SLUG), None)
    assert marker is not None, f"no Spirit Guardians marker; got {upd['data']}"

    mv = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/move_aoe",
        json={"marker_id": marker["id"], "center_x": 999.0, "center_y": 888.0},
    )
    assert mv.status_code == 409, mv.text
    assert mv.json().get("error") == "not_movable", mv.text
