"""v2.99.259 — Battle Master maneuver 9: Feinting Attack.

Phase E.1 Phase 3 (maneuver 9 of 16). RAW PHB p.74: bonus
action; pick target within 5 ft; advantage on your next attack
roll vs that target this turn + die added to damage on hit.

First per-maneuver endpoint to gate on a Phase 4 BONUS chip
(prior 8 maneuvers are part of the Attack action).

Tests:
  - Happy d8 → next_attack_advantage True, extra_damage_on_hit 1..8.
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


def _fa_broadcasts(gm_ws, character_id):
    return [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "feinting-attack"
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


async def test_use_fa_happy(
    gm_client, gm_ws, garrik_battle_master,
):
    """Lv 9 Garrik d8 → advantage + +1..8 damage on hit."""
    garrik = garrik_battle_master
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_feinting_attack",
        json={
            "character_id": garrik["id"],
            "target_name": "Bandit Alpha",
            "override": True,
        },
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["next_attack_advantage"] is True
    assert 1 <= data["extra_damage_on_hit"] <= 8
    assert data["target_name"] == "Bandit Alpha"
    assert data["dice_remaining"] == 3
    await asyncio.sleep(0.3)
    feats = _fa_broadcasts(gm_ws, garrik["id"])
    assert feats


async def test_use_fa_out_of_dice(
    gm_client, garrik_battle_master,
):
    """current=0 → 409."""
    garrik = garrik_battle_master
    await _patch_sheet(
        gm_client, garrik["id"],
        {"resources": [_superiority_dice_block(0, 4)]},
    )
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_feinting_attack",
        json={"character_id": garrik["id"], "override": True},
    )
    assert r.status_code == 409, r.text


async def test_use_fa_wrong_subclass(
    gm_client, roster,
):
    """Default Garrik (Champion) → 409."""
    garrik = roster["Garrik Ironside"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_feinting_attack",
        json={"character_id": garrik["id"], "override": True},
    )
    assert r.status_code == 409, r.text
