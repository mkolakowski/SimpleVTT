"""v2.99.262 — Battle Master maneuver 12: Riposte.

Phase E.1 Phase 3 (maneuver 12 of 16). RAW PHB p.74: reaction
when missed by melee; make a melee weapon attack vs the
attacker. If hit, die added to damage.

Tests:
  - Happy d8 → extra_damage_on_hit 1..8, dice 4→3.
  - Out of dice → 409.
  - Wrong subclass → 409.
"""
import asyncio
import pytest_asyncio

from .conftest import CAMPAIGN_ID


async def _patch_sheet(gm_client, char_id, fields, class_slug=None):
    body = dict(fields)
    if class_slug:
        body["class_slug"] = class_slug
    r = await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-fields",
        json=body,
    )
    assert r.status_code == 200, r.text


def _ri_broadcasts(gm_ws, character_id):
    return [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "riposte"
        and (m.get("data") or {}).get("character_id") == character_id
    ]


def _superiority_dice_block(current: int, maximum: int) -> dict:
    return {
        "key": "superiority-dice",
        "name": "Superiority Dice",
        "current": current, "max": maximum, "reset": "short",
        "source": "fighter Lv 3 / Combat Superiority",
        "class_slug": "fighter",
        "desc": "Battle Master maneuvers.",
        "manual": False,
    }


@pytest_asyncio.fixture
async def garrik_battle_master(gm_client, roster):
    garrik = roster["Garrik Ironside"]
    await _patch_sheet(
        gm_client, garrik["id"],
        {
            "subclass": "Battle Master",
            "superiority_die_size": "d8",
            "resources": [_superiority_dice_block(4, 4)],
        },
        class_slug="fighter",
    )
    try:
        yield garrik
    finally:
        await _patch_sheet(
            gm_client, garrik["id"],
            {"subclass": "Champion", "resources": []},
            class_slug="fighter",
        )


async def test_use_ri_happy(
    gm_client, gm_ws, garrik_battle_master,
):
    """Lv 9 Garrik d8 → extra_damage_on_hit 1..8."""
    garrik = garrik_battle_master
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_riposte",
        json={"character_id": garrik["id"], "override": True},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert 1 <= data["extra_damage_on_hit"] <= 8
    assert data["dice_remaining"] == 3
    await asyncio.sleep(0.3)
    feats = _ri_broadcasts(gm_ws, garrik["id"])
    assert feats


async def test_use_ri_out_of_dice(
    gm_client, garrik_battle_master,
):
    """current=0 → 409."""
    garrik = garrik_battle_master
    await _patch_sheet(
        gm_client, garrik["id"],
        {"resources": [_superiority_dice_block(0, 4)]},
    )
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_riposte",
        json={"character_id": garrik["id"], "override": True},
    )
    assert r.status_code == 409, r.text


async def test_use_ri_wrong_subclass(
    gm_client, roster,
):
    """Default Garrik (Champion) → 409."""
    garrik = roster["Garrik Ironside"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_riposte",
        json={"character_id": garrik["id"], "override": True},
    )
    assert r.status_code == 409, r.text
