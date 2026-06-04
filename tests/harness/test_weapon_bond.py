"""v2.99.232 — Eldritch Knight Fighter: Weapon Bond (Phase 1).

Phase E.2 Phase 1 of the v2.99.193 phased completion plan. RAW
PHB p.74: Eldritch Knight Lv 3+ ritual that bonds up to 2
weapons. v1 ships persistence + announce; the "can't be
disarmed" half is filed (no disarm action in SimpleVTT today)
and the bonus-action summon is filed.

Garrik Ironside (Fighter Champion Lv 9 default) is the demo
fixture. Tests PATCH his subclass to "Eldritch Knight". Garrik's
inventory:
  index 0: Greatsword
  index 1: Handaxe
  index 2: Glaive
  index 3: Chain mail (not a weapon → 400 path)

Tests:
  - Happy path: bond Greatsword → bonded_weapons == ["greatsword"].
  - Second bond: Glaive → bonded_weapons length 2.
  - Cap reached: third weapon → 409 cap_reached.
  - Wrong subclass (default Champion) → 409.
  - Level gate (Lv 2) → 409.
  - Non-weapon inventory index (chain mail) → 400.
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


def _bond_broadcasts(gm_ws, character_id):
    return [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "weapon-bond"
        and (m.get("data") or {}).get("character_id") == character_id
    ]


@pytest_asyncio.fixture
async def garrik_eldritch_knight(gm_client, roster):
    """PATCH Garrik to Eldritch Knight + reset bonded_weapons."""
    garrik = roster["Garrik Ironside"]
    await _patch_sheet(
        gm_client, garrik["id"],
        {"subclass": "Eldritch Knight", "bonded_weapons": []},
        class_slug="fighter",
    )
    try:
        yield garrik
    finally:
        await _patch_sheet(
            gm_client, garrik["id"],
            {"subclass": "Champion", "bonded_weapons": []},
            class_slug="fighter",
        )


async def test_use_weapon_bond_happy(
    gm_client, gm_ws, garrik_eldritch_knight,
):
    """Bond Greatsword → bonded_weapons == ['greatsword'] +
    broadcast."""
    garrik = garrik_eldritch_knight
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_weapon_bond",
        json={"character_id": garrik["id"], "weapon_index": 0},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["weapon_slug"] == "greatsword"
    assert data["bonded_weapons"] == ["greatsword"]
    assert data["already_bonded"] is False
    await asyncio.sleep(0.3)
    feats = _bond_broadcasts(gm_ws, garrik["id"])
    assert feats


async def test_use_weapon_bond_second_weapon(
    gm_client, garrik_eldritch_knight,
):
    """Bond Greatsword then Glaive → bonded_weapons length 2."""
    garrik = garrik_eldritch_knight
    r1 = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_weapon_bond",
        json={"character_id": garrik["id"], "weapon_index": 0},
    )
    assert r1.status_code == 200, r1.text
    r2 = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_weapon_bond",
        json={"character_id": garrik["id"], "weapon_index": 2},
    )
    assert r2.status_code == 200, r2.text
    data = r2.json()
    assert data["bonded_weapons"] == ["greatsword", "glaive"]


async def test_use_weapon_bond_cap_reached(
    gm_client, garrik_eldritch_knight,
):
    """Two bonded → third attempt → 409 cap_reached."""
    garrik = garrik_eldritch_knight
    # Pre-bind two via PATCH.
    await _patch_sheet(
        gm_client, garrik["id"],
        {"bonded_weapons": ["greatsword", "handaxe"]},
    )
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_weapon_bond",
        json={"character_id": garrik["id"], "weapon_index": 2},
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "cap_reached"


async def test_use_weapon_bond_wrong_subclass(
    gm_client, roster,
):
    """Default Garrik (Champion) → 409 wrong_subclass_or_level."""
    garrik = roster["Garrik Ironside"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_weapon_bond",
        json={"character_id": garrik["id"], "weapon_index": 0},
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "wrong_subclass_or_level"


async def test_use_weapon_bond_level_gate(
    gm_client, roster,
):
    """Eldritch Knight at Lv 2 (not 3+) → 409."""
    garrik = roster["Garrik Ironside"]
    await _patch_sheet(
        gm_client, garrik["id"],
        {"subclass": "Eldritch Knight", "level": 2},
        class_slug="fighter",
    )
    try:
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/use_weapon_bond",
            json={"character_id": garrik["id"], "weapon_index": 0},
        )
        assert r.status_code == 409, r.text
        data = r.json()
        assert data.get("error") == "wrong_subclass_or_level"
    finally:
        await _patch_sheet(
            gm_client, garrik["id"],
            {"subclass": "Champion", "level": 9},
            class_slug="fighter",
        )


async def test_use_weapon_bond_non_weapon(
    gm_client, garrik_eldritch_knight,
):
    """Inventory index pointing at Chain mail (armor) → 400."""
    garrik = garrik_eldritch_knight
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_weapon_bond",
        json={"character_id": garrik["id"], "weapon_index": 3},
    )
    assert r.status_code == 400, r.text
