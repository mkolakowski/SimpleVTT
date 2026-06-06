"""v2.99.379 — Monster Slayer Ranger: Slayer's Prey (G Ranger conclave #3, Lv 3+, XGE).

Phase G Ranger conclave subclass batch ship #3 — Monster Slayer
opens.
RAW XGE p.43: as a bonus action, designate a creature within 60 ft
as your prey; the first weapon hit each turn deals +1d6 to it until
you rest or mark a new target.

v2.99.396 — Phase 2.2 of docs/plans/on-hit-riders.md: when a
`target_combatant_id` is supplied, the feature now **installs a
`slayers-prey` rider buff** keyed to the prey (weapon_hit_bonus_dice
1d6, once_per_turn) so the first weapon hit each turn auto-applies
+1d6 via the /attack pipeline (the rider-application mechanism itself
is covered by test_attack_rider_substrate.py). Without a target it
stays announce-only. Bonus chip.

Rowan Quickbow (Ranger, PATCHed to Monster Slayer Lv 5) is the demo
fixture.

Tests:
  - Lv 5 happy (no target): bonus damage 1d6, range 60, buff_installed False.
  - With a target: installs the slayers-prey rider buff (effects
    weapon_hit_bonus_dice 1d6, target-keyed, once-per-turn) — asserted
    via the buff_update broadcast.
  - Wrong subclass (default Hunter) → 409.
  - Wrong class (Caelan paladin) → 409.
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


def _sp_broadcasts(gm_ws, character_id):
    return [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "slayers-prey"
        and (m.get("data") or {}).get("character_id") == character_id
    ]


@pytest_asyncio.fixture
async def rowan_slayer(gm_client, roster):
    """PATCH Rowan to Monster Slayer; restore to Hunter on teardown."""
    rowan = roster["Rowan Quickbow"]
    await _patch_sheet(
        gm_client, rowan["id"],
        {"subclass": "Monster Slayer"},
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


async def test_use_sp_happy_lv5(
    gm_client, gm_ws, rowan_slayer,
):
    """Lv 5 Monster Slayer → +1d6 in [1,6], range 60."""
    rowan = rowan_slayer
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_slayers_prey",
        json={"character_id": rowan["id"], "override": True},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["feature"] == "slayers-prey"
    assert data["bonus_damage_die"] == "1d6"
    assert 1 <= data["bonus_damage"] <= 6
    assert data["range_ft"] == 60
    assert data["ranger_level"] == 5
    await asyncio.sleep(0.3)
    feats = _sp_broadcasts(gm_ws, rowan["id"])
    assert feats
    assert feats[-1]["data"]["bonus_damage"] == data["bonus_damage"]


async def test_use_sp_wrong_subclass(
    gm_client, roster,
):
    """Default Rowan (Hunter) → 409."""
    rowan = roster["Rowan Quickbow"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_slayers_prey",
        json={"character_id": rowan["id"], "override": True},
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "wrong_subclass_or_level"


async def test_use_sp_wrong_class(
    gm_client, roster,
):
    """Caelan (Paladin) → 409."""
    caelan = roster["Sir Caelan Lightbringer"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_slayers_prey",
        json={"character_id": caelan["id"], "override": True},
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "wrong_subclass_or_level"


async def test_sp_no_target_announce_only(
    gm_client, rowan_slayer,
):
    """Without a target_combatant_id the feature stays announce-only —
    buff_installed is False (back-compat)."""
    rowan = rowan_slayer
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_slayers_prey",
        json={"character_id": rowan["id"], "override": True},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["buff_installed"] is False
    assert data["bonus_damage_die"] == "1d6"


async def test_sp_installs_rider_buff(
    gm_client, gm_ws, rowan_slayer,
):
    """v2.99.396 — with a target, Slayer's Prey installs the on-hit rider
    buff (weapon_hit_bonus_dice 1d6, target-keyed, once-per-turn). Verified
    via the buff_update broadcast that _install_buff emits."""
    rowan = rowan_slayer
    rowan_cid = f"tok_sp_rw_{rowan['id']}"
    dummy_cid = "tok_sp_dummy"
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": [
            _mkc(rowan_cid, rowan["id"], name=rowan["name"]),
            _mkc(dummy_cid, None, name="Dummy"),
        ], "turn_index": 0, "round": 1, "active": True},
    )
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_slayers_prey",
        json={"character_id": rowan["id"],
              "target_combatant_id": dummy_cid, "override": True},
    )
    assert r.status_code == 200, r.text
    assert r.json()["buff_installed"] is True

    bu = await gm_ws.wait_for("buff_update")
    buffs = bu["data"]["buffs"]
    sp = next((b for b in buffs if b.get("key") == "slayers-prey"), None)
    assert sp is not None, buffs
    eff = sp.get("effects") or {}
    assert eff.get("weapon_hit_bonus_dice") == "1d6"
    assert eff.get("weapon_hit_bonus_target_combatant_id") == dummy_cid
    assert eff.get("weapon_hit_once_per_turn") is True
