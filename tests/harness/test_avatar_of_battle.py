"""v2.99.296 — War Domain Cleric: Avatar of Battle (H.1 deeper, Lv 17).

H.1 Lv 17 War ship. RAW PHB p.63: resistance to bludgeoning,
piercing, and slashing damage from nonmagical attacks.

v1 announce-only — the actual resistance vs nonmagical BPS
damage is GM-tracked. No chip cost — passive permanent.

Tests:
  - Lv 17 happy → resistance_types BPS, nonmagical_only True.
  - Wrong subclass → 409.
  - Level gate (Lv 16) → 409.
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


def _aob_broadcasts(gm_ws, character_id):
    return [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "avatar-of-battle"
        and (m.get("data") or {}).get("character_id") == character_id
    ]


@pytest_asyncio.fixture
async def tavik_war_lv17(gm_client, roster):
    """PATCH Tavik to War Domain Lv 17."""
    tavik = roster["Brother Tavik Stonebrow"]
    await _patch_sheet(
        gm_client, tavik["id"],
        {"subclass": "War Domain", "level": 17},
        class_slug="cleric",
    )
    try:
        yield tavik
    finally:
        await _patch_sheet(
            gm_client, tavik["id"],
            {"subclass": "Life Domain", "level": 6},
            class_slug="cleric",
        )


async def test_use_aob_happy_lv17(
    gm_client, gm_ws, tavik_war_lv17,
):
    """Lv 17 War → resistance to nonmagical BPS."""
    tavik = tavik_war_lv17
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_avatar_of_battle",
        json={"character_id": tavik["id"]},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert "bludgeoning" in data["resistance_types"]
    assert "piercing" in data["resistance_types"]
    assert "slashing" in data["resistance_types"]
    assert data["nonmagical_only"] is True
    assert data["cleric_level"] == 17
    await asyncio.sleep(0.3)
    feats = _aob_broadcasts(gm_ws, tavik["id"])
    assert feats


async def test_use_aob_wrong_subclass(
    gm_client, roster,
):
    """Default Tavik (Life Domain) → 409."""
    tavik = roster["Brother Tavik Stonebrow"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_avatar_of_battle",
        json={"character_id": tavik["id"]},
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "wrong_subclass_or_level"


async def test_use_aob_level_gate(
    gm_client, roster,
):
    """War Tavik at Lv 16 → 409."""
    tavik = roster["Brother Tavik Stonebrow"]
    await _patch_sheet(
        gm_client, tavik["id"],
        {"subclass": "War Domain", "level": 16},
        class_slug="cleric",
    )
    try:
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/use_avatar_of_battle",
            json={"character_id": tavik["id"]},
        )
        assert r.status_code == 409, r.text
        data = r.json()
        assert data.get("error") == "wrong_subclass_or_level"
    finally:
        await _patch_sheet(
            gm_client, tavik["id"],
            {"subclass": "Life Domain", "level": 6},
            class_slug="cleric",
        )
