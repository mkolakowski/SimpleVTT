"""v2.99.282 — Glory Paladin: Aura of Alacrity (H.2 depth).

H.2 depth ship — Glory's Lv 7 speed aura. RAW XGE p.37: your
walking speed +10 ft permanently. Allies starting their turn
within 5 ft (10 ft at Lv 18+) get +10 ft walking speed until
end of turn.

v1 announce-only. CLOSES the H.2 Lv 7 aura batch (5/5 oaths).

Note: radius is 5 ft (10 ft at Lv 18), distinct from the
10/30 ft pattern of the other H.2 oath auras.

Caelan Lv 7 → radius 5, speed_bonus 10.
Tests PATCH his subclass to "Oath of Glory".

Tests:
  - Lv 7 happy → radius 5, speed_bonus 10.
  - Lv 18 happy → radius 10 (RAW upgrade).
  - Wrong subclass → 409.
  - Level gate (Lv 6) → 409.
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


def _aoa_broadcasts(gm_ws, character_id):
    return [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "aura-of-alacrity"
        and (m.get("data") or {}).get("character_id") == character_id
    ]


@pytest_asyncio.fixture
async def caelan_glory_lv7(gm_client, roster):
    """PATCH Caelan to Glory. Default Lv 7 already qualifies."""
    caelan = roster["Sir Caelan Lightbringer"]
    await _patch_sheet(
        gm_client, caelan["id"],
        {"subclass": "Oath of Glory"},
        class_slug="paladin",
    )
    try:
        yield caelan
    finally:
        await _patch_sheet(
            gm_client, caelan["id"],
            {"subclass": "Oath of Devotion", "level": 7},
            class_slug="paladin",
        )


async def test_use_aoa_happy_lv7(
    gm_client, gm_ws, caelan_glory_lv7,
):
    """Lv 7 Glory → radius 5, speed_bonus 10."""
    caelan = caelan_glory_lv7
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_aura_of_alacrity",
        json={"character_id": caelan["id"]},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["radius_ft"] == 5
    assert data["speed_bonus_ft"] == 10
    assert data["paladin_level"] == 7
    await asyncio.sleep(0.3)
    feats = _aoa_broadcasts(gm_ws, caelan["id"])
    assert feats


async def test_use_aoa_lv18_radius_upgrade(
    gm_client, caelan_glory_lv7,
):
    """Lv 18 → radius 10 (RAW upgrade — note 5→10 ft, not 10→30)."""
    caelan = caelan_glory_lv7
    await _patch_sheet(
        gm_client, caelan["id"], {"level": 18},
        class_slug="paladin",
    )
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_aura_of_alacrity",
        json={"character_id": caelan["id"]},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["radius_ft"] == 10
    assert data["speed_bonus_ft"] == 10
    assert data["paladin_level"] == 18


async def test_use_aoa_wrong_subclass(
    gm_client, roster,
):
    """Default Caelan (Devotion) → 409."""
    caelan = roster["Sir Caelan Lightbringer"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_aura_of_alacrity",
        json={"character_id": caelan["id"]},
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "wrong_subclass_or_level"


async def test_use_aoa_level_gate(
    gm_client, roster,
):
    """Glory Caelan at Lv 6 → 409."""
    caelan = roster["Sir Caelan Lightbringer"]
    await _patch_sheet(
        gm_client, caelan["id"],
        {"subclass": "Oath of Glory", "level": 6},
        class_slug="paladin",
    )
    try:
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/use_aura_of_alacrity",
            json={"character_id": caelan["id"]},
        )
        assert r.status_code == 409, r.text
        data = r.json()
        assert data.get("error") == "wrong_subclass_or_level"
    finally:
        await _patch_sheet(
            gm_client, caelan["id"],
            {"subclass": "Oath of Devotion", "level": 7},
            class_slug="paladin",
        )
