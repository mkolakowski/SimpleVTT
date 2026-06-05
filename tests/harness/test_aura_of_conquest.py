"""v2.99.273 — Conquest Paladin: Aura of Conquest (H.2 depth).

H.2 depth ship — Conquest's Lv 7 aura. Per RAW XGE, Conquest
has only Conquering Presence as a Lv 3 CD; the depth ship is
Aura of Conquest at Lv 7.

RAW (XGE p.37): 10 ft aura (30 ft at Lv 18+); frightened
creatures in aura have speed 0 + take half-paladin-level
psychic damage at turn start.

v1 announce-only.

Caelan Lv 7 → half-level 3 psychic damage + 10 ft radius.
Tests PATCH his subclass to "Oath of Conquest".

Tests:
  - Lv 7 happy → radius 10, psychic_damage 3.
  - Lv 18 happy → radius 30 (RAW upgrade).
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


def _aoc_broadcasts(gm_ws, character_id):
    return [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "aura-of-conquest"
        and (m.get("data") or {}).get("character_id") == character_id
    ]


@pytest_asyncio.fixture
async def caelan_conquest_lv7(gm_client, roster):
    """PATCH Caelan to Conquest. Default Lv 7 already qualifies."""
    caelan = roster["Sir Caelan Lightbringer"]
    await _patch_sheet(
        gm_client, caelan["id"],
        {"subclass": "Oath of Conquest"},
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


async def test_use_aoc_happy_lv7(
    gm_client, gm_ws, caelan_conquest_lv7,
):
    """Lv 7 Conquest → radius 10, psychic_damage 3."""
    caelan = caelan_conquest_lv7
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_aura_of_conquest",
        json={"character_id": caelan["id"]},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["radius_ft"] == 10
    assert data["psychic_damage"] == 3  # 7 // 2
    assert data["paladin_level"] == 7
    await asyncio.sleep(0.3)
    feats = _aoc_broadcasts(gm_ws, caelan["id"])
    assert feats


async def test_use_aoc_lv18_radius_upgrade(
    gm_client, caelan_conquest_lv7,
):
    """Lv 18 → radius 30 (RAW upgrade)."""
    caelan = caelan_conquest_lv7
    await _patch_sheet(
        gm_client, caelan["id"], {"level": 18},
        class_slug="paladin",
    )
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_aura_of_conquest",
        json={"character_id": caelan["id"]},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["radius_ft"] == 30
    assert data["psychic_damage"] == 9  # 18 // 2


async def test_use_aoc_wrong_subclass(
    gm_client, roster,
):
    """Default Caelan (Devotion) → 409."""
    caelan = roster["Sir Caelan Lightbringer"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_aura_of_conquest",
        json={"character_id": caelan["id"]},
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "wrong_subclass_or_level"


async def test_use_aoc_level_gate(
    gm_client, roster,
):
    """Conquest Caelan at Lv 6 → 409."""
    caelan = roster["Sir Caelan Lightbringer"]
    await _patch_sheet(
        gm_client, caelan["id"],
        {"subclass": "Oath of Conquest", "level": 6},
        class_slug="paladin",
    )
    try:
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/use_aura_of_conquest",
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
