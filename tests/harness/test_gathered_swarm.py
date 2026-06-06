"""v2.99.380 — Swarmkeeper Ranger: Gathered Swarm (G Ranger conclave #4, Lv 3+, TCE).

Phase G Ranger conclave subclass batch ship #4 — Swarmkeeper opens.
RAW TCE p.59: once per turn on a hit, call on your swarm — the
target takes +1d6 force, OR is moved 15 ft, OR you are moved 5 ft
without provoking opportunity attacks.

v1 announce-only — the on-hit application + forced movement are
GM-tracked. For `damage` the 1d6 force is rolled server-side. No
separate action cost.

Rowan Quickbow (Ranger, PATCHed to Swarmkeeper Lv 5) is the demo
fixture.

Tests:
  - Lv 5 happy (default damage): +1d6 force in [1,6].
  - Lv 5 happy (move_target): 15-ft target move.
  - Wrong subclass (default Hunter) → 409.
  - Invalid mode → 400.
"""
import asyncio
import pytest_asyncio

from .conftest import CAMPAIGN_ID


def _mkc(cid, char_id=None, name="X"):
    return {
        "id": cid, "char_id": char_id, "name": name,
        "initiative": 10, "hp_current": 50, "hp_max": 50,
        "buffs": [], "speed_walk": 30,
        "economy": {"action": False, "bonus": False, "reaction": False,
                    "movement": 0},
    }


async def _patch_sheet(gm_client, char_id, fields, class_slug=None):
    body = dict(fields)
    if class_slug:
        body["class_slug"] = class_slug
    r = await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-fields",
        json=body,
    )
    assert r.status_code == 200, r.text


def _gs_broadcasts(gm_ws, character_id):
    return [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "gathered-swarm"
        and (m.get("data") or {}).get("character_id") == character_id
    ]


@pytest_asyncio.fixture
async def rowan_swarm(gm_client, roster):
    """PATCH Rowan to Swarmkeeper; restore to Hunter on teardown."""
    rowan = roster["Rowan Quickbow"]
    await _patch_sheet(
        gm_client, rowan["id"],
        {"subclass": "Swarmkeeper"},
        class_slug="ranger",
    )
    try:
        yield rowan
    finally:
        await _patch_sheet(
            gm_client, rowan["id"],
            {"subclass": "Hunter"},
            class_slug="ranger",
        )


async def test_use_gs_happy_damage(
    gm_client, gm_ws, rowan_swarm,
):
    """Lv 5 Swarmkeeper, default → +1d6 force in [1,6]."""
    rowan = rowan_swarm
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_gathered_swarm",
        json={"character_id": rowan["id"]},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["feature"] == "gathered-swarm"
    assert data["mode"] == "damage"
    assert data["bonus_damage_die"] == "1d6"
    assert data["damage_type"] == "force"
    assert 1 <= data["bonus_damage"] <= 6
    assert data["ranger_level"] == 5
    await asyncio.sleep(0.3)
    feats = _gs_broadcasts(gm_ws, rowan["id"])
    assert feats
    assert feats[-1]["data"]["bonus_damage"] == data["bonus_damage"]


async def test_use_gs_happy_move_target(
    gm_client, rowan_swarm,
):
    """mode=move_target → 15-ft target move."""
    rowan = rowan_swarm
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_gathered_swarm",
        json={"character_id": rowan["id"], "mode": "move_target"},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["mode"] == "move_target"
    assert data["move_distance_ft"] == 15
    assert data["move_subject"] == "target"


async def test_use_gs_wrong_subclass(
    gm_client, roster,
):
    """Default Rowan (Hunter) → 409."""
    rowan = roster["Rowan Quickbow"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_gathered_swarm",
        json={"character_id": rowan["id"]},
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "wrong_subclass_or_level"


async def test_use_gs_invalid_mode(
    gm_client, rowan_swarm,
):
    """Invalid mode → 400."""
    rowan = rowan_swarm
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_gathered_swarm",
        json={"character_id": rowan["id"], "mode": "fly"},
    )
    assert r.status_code == 400, r.text


async def test_gs_damage_mode_installs_rider_buff(
    gm_client, gm_ws, rowan_swarm,
):
    """v2.99.398 — the damage mode installs a 1-round non-target
    once-per-turn rider buff (1d6 force). Verified via buff_update."""
    rowan = rowan_swarm
    rowan_cid = f"tok_gs_rw_{rowan['id']}"
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": [
            _mkc(rowan_cid, rowan["id"], name=rowan["name"]),
        ], "turn_index": 0, "round": 1, "active": True},
    )
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_gathered_swarm",
        json={"character_id": rowan["id"], "mode": "damage"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["buff_installed"] is True

    bu = await gm_ws.wait_for("buff_update")
    buffs = bu["data"]["buffs"]
    gs = next((b for b in buffs if b.get("key") == "gathered-swarm"), None)
    assert gs is not None, buffs
    eff = gs.get("effects") or {}
    assert eff.get("weapon_hit_bonus_dice") == "1d6"
    assert eff.get("weapon_hit_bonus_damage_type") == "force"
    assert eff.get("weapon_hit_once_per_turn") is True
    assert "weapon_hit_bonus_target_combatant_id" not in eff


async def test_gs_move_mode_no_rider_buff(
    gm_client, rowan_swarm,
):
    """The move modes don't install an on-hit rider (Phase 6 work)."""
    rowan = rowan_swarm
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_gathered_swarm",
        json={"character_id": rowan["id"], "mode": "move_target"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["buff_installed"] is False
