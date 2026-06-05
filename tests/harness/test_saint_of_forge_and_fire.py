"""v2.99.299 — Forge Domain Cleric: Saint of Forge and Fire (H.1 deeper, Lv 17).

H.1 Lv 17 Forge ship. RAW XGE p.18: immunity to fire damage;
while wearing heavy armor, resistance to bludgeoning, piercing,
slashing from nonmagical attacks.

v1 announce-only — fire immunity + BPS resistance are
GM-tracked. No chip — passive permanent.

Tests:
  - Lv 17 happy → fire_immunity True, BPS resistance True.
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


def _sff_broadcasts(gm_ws, character_id):
    return [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "saint-of-forge-and-fire"
        and (m.get("data") or {}).get("character_id") == character_id
    ]


@pytest_asyncio.fixture
async def tavik_forge_lv17(gm_client, roster):
    """PATCH Tavik to Forge Domain Lv 17."""
    tavik = roster["Brother Tavik Stonebrow"]
    await _patch_sheet(
        gm_client, tavik["id"],
        {"subclass": "Forge Domain", "level": 17},
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


async def test_use_sff_happy_lv17(
    gm_client, gm_ws, tavik_forge_lv17,
):
    """Lv 17 Forge → fire immune + heavy-armor BPS resist."""
    tavik = tavik_forge_lv17
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_saint_of_forge_and_fire",
        json={"character_id": tavik["id"]},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["fire_immunity"] is True
    assert data["heavy_armor_bps_resistance"] is True
    assert "bludgeoning" in data["resistance_types"]
    assert data["resistance_nonmagical_only"] is True
    assert data["cleric_level"] == 17
    await asyncio.sleep(0.3)
    feats = _sff_broadcasts(gm_ws, tavik["id"])
    assert feats


async def test_use_sff_wrong_subclass(
    gm_client, roster,
):
    """Default Tavik (Life Domain) → 409."""
    tavik = roster["Brother Tavik Stonebrow"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_saint_of_forge_and_fire",
        json={"character_id": tavik["id"]},
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "wrong_subclass_or_level"


async def test_use_sff_level_gate(
    gm_client, roster,
):
    """Forge Tavik at Lv 16 → 409."""
    tavik = roster["Brother Tavik Stonebrow"]
    await _patch_sheet(
        gm_client, tavik["id"],
        {"subclass": "Forge Domain", "level": 16},
        class_slug="cleric",
    )
    try:
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/use_saint_of_forge_and_fire",
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
