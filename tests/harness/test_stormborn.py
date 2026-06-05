"""v2.99.294 — Tempest Domain Cleric: Stormborn (H.1 deeper, Lv 17).

H.1 Lv 17 Tempest ship. RAW PHB p.63: fly speed = walking
speed when not underground or indoors.

v1 announce-only — outdoor/indoor gating is GM-tracked.
No chip cost — passive permanent feature.

Tavik PATCH'd to Tempest Lv 17. Tavik is a dwarf (walking 25)
→ fly 25.

Tests:
  - Lv 17 happy → fly 25 (=walking), outdoor_only True.
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


def _sb_broadcasts(gm_ws, character_id):
    return [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "stormborn"
        and (m.get("data") or {}).get("character_id") == character_id
    ]


@pytest_asyncio.fixture
async def tavik_tempest_lv17(gm_client, roster):
    """PATCH Tavik to Tempest Lv 17."""
    tavik = roster["Brother Tavik Stonebrow"]
    await _patch_sheet(
        gm_client, tavik["id"],
        {"subclass": "Tempest Domain", "level": 17},
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


async def test_use_sb_happy_lv17(
    gm_client, gm_ws, tavik_tempest_lv17,
):
    """Lv 17 Tempest → fly = walking (dwarf 25)."""
    tavik = tavik_tempest_lv17
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_stormborn",
        json={"character_id": tavik["id"]},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["walking_speed_ft"] == 25
    assert data["fly_speed_ft"] == 25
    assert data["outdoor_only"] is True
    assert data["cleric_level"] == 17
    await asyncio.sleep(0.3)
    feats = _sb_broadcasts(gm_ws, tavik["id"])
    assert feats


async def test_use_sb_wrong_subclass(
    gm_client, roster,
):
    """Default Tavik (Life Domain) → 409."""
    tavik = roster["Brother Tavik Stonebrow"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_stormborn",
        json={"character_id": tavik["id"]},
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "wrong_subclass_or_level"


async def test_use_sb_level_gate(
    gm_client, roster,
):
    """Tempest Tavik at Lv 16 → 409."""
    tavik = roster["Brother Tavik Stonebrow"]
    await _patch_sheet(
        gm_client, tavik["id"],
        {"subclass": "Tempest Domain", "level": 16},
        class_slug="cleric",
    )
    try:
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/use_stormborn",
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
