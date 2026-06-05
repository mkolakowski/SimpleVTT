"""v2.99.233 — Battle Master Fighter: Combat Superiority + Trip Attack (Phase 1).

Phase E.1 Phase 1 of the v2.99.193 phased completion plan. RAW
PHB p.74: Battle Master Lv 3+ "When you hit a creature with a
weapon attack, you can expend one superiority die to attempt to
knock the target down. You add the superiority die to the
attack's damage roll, and if the target is Large or smaller, it
must make a Strength saving throw. On a failed save, you knock
the target prone."

v1 ships:
  - /use_trip_attack: validates Battle Master Lv 3+ + has
    superiority-dice resource with current >= 1; decrements
    counter; rolls 1d<size> via sheet.superiority_die_size
    (default d8); computes Maneuver DC = 8 + prof + max(STR,
    DEX) mod; broadcasts feature_used (source trip-attack) with
    (extra_damage, save_dc, die_size, dice_remaining).

Garrik Ironside is the demo fixture; tests PATCH his subclass
to "Battle Master" + seed a superiority-dice resource via
sheet.resources PATCH.

Tests:
  - Happy path Lv 3 d8 → extra in 1..8, DC computed, dice 4→3.
  - Out-of-dice (current 0) → 409 out_of_uses.
  - Wrong subclass (default Champion) → 409.
  - Level gate (Lv 2) → 409.
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


def _trip_broadcasts(gm_ws, character_id):
    return [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "trip-attack"
        and (m.get("data") or {}).get("character_id") == character_id
    ]


def _superiority_dice_block(current: int, maximum: int) -> dict:
    return {
        "key": "superiority-dice",
        "name": "Superiority Dice",
        "current": current, "max": maximum, "reset": "short",
        "source": "fighter Lv 3 / Combat Superiority",
        "class_slug": "fighter",
        "desc": "Battle Master maneuvers. Refreshes on short or long rest.",
        "manual": False,
    }


@pytest_asyncio.fixture
async def garrik_battle_master(gm_client, roster):
    """PATCH Garrik to Battle Master + seed superiority-dice
    resource with d8 die size. Teardown restores Champion."""
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


async def test_use_trip_attack_happy(
    gm_client, gm_ws, garrik_battle_master,
):
    """Lv 9 Garrik (Battle Master) → extra in 1..8, DC computed,
    dice 4 → 3, broadcast fired."""
    garrik = garrik_battle_master
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_trip_attack",
        json={"character_id": garrik["id"]},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["die_size"] == "d8"
    assert 1 <= data["extra_damage"] <= 8
    # Garrik: prof +4, STR mod +4, DEX mod +2 → max = 4 → DC = 16.
    assert data["save_dc"] == 16, data
    assert data["dice_remaining"] == 3
    await asyncio.sleep(0.3)
    feats = _trip_broadcasts(gm_ws, garrik["id"])
    assert feats


async def test_use_trip_attack_out_of_dice(
    gm_client, garrik_battle_master,
):
    """current=0 → 409 out_of_uses."""
    garrik = garrik_battle_master
    await _patch_sheet(
        gm_client, garrik["id"],
        {"resources": [_superiority_dice_block(0, 4)]},
    )
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_trip_attack",
        json={"character_id": garrik["id"]},
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "out_of_uses"


async def test_use_trip_attack_wrong_subclass(
    gm_client, roster,
):
    """Default Garrik (Champion) → 409 wrong_subclass_or_level."""
    garrik = roster["Garrik Ironside"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_trip_attack",
        json={"character_id": garrik["id"]},
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "wrong_subclass_or_level"


async def test_use_trip_attack_level_gate(
    gm_client, roster,
):
    """Battle Master at Lv 2 (not 3+) → 409."""
    garrik = roster["Garrik Ironside"]
    await _patch_sheet(
        gm_client, garrik["id"],
        {
            "subclass": "Battle Master",
            "level": 2,
            "resources": [_superiority_dice_block(4, 4)],
        },
        class_slug="fighter",
    )
    try:
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/use_trip_attack",
            json={"character_id": garrik["id"]},
        )
        assert r.status_code == 409, r.text
        data = r.json()
        assert data.get("error") == "wrong_subclass_or_level"
    finally:
        await _patch_sheet(
            gm_client, garrik["id"],
            {"subclass": "Champion", "level": 9, "resources": []},
            class_slug="fighter",
        )
