"""v2.99.300 — Grave Domain Cleric: Keeper of Souls (H.1 deeper, Lv 17).

H.1 Lv 17 Grave ship. RAW XGE p.19: when an enemy within 60
ft dies, you (or creature of your choice within 60 ft) heal
HP = enemy's Hit Dice. 1/turn. Not while incapacitated.

v1 announce-only — actual HP application + 1/turn lockout
GM-tracked. No chip — passive trigger.

Tavik PATCH'd to Grave Lv 17.

Tests:
  - Lv 17 happy with enemy HD 5 → heal 5.
  - Default enemy_hit_dice missing → heal 1 (clamp).
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


def _ks_broadcasts(gm_ws, character_id):
    return [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "keeper-of-souls"
        and (m.get("data") or {}).get("character_id") == character_id
    ]


@pytest_asyncio.fixture
async def tavik_grave_lv17(gm_client, roster):
    """PATCH Tavik to Grave Domain Lv 17."""
    tavik = roster["Brother Tavik Stonebrow"]
    await _patch_sheet(
        gm_client, tavik["id"],
        {"subclass": "Grave Domain", "level": 17},
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


async def test_use_ks_happy_lv17(
    gm_client, gm_ws, tavik_grave_lv17,
):
    """Lv 17 Grave, enemy HD 5 → heal 5."""
    tavik = tavik_grave_lv17
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_keeper_of_souls",
        json={"character_id": tavik["id"], "enemy_hit_dice": 5},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["heal_amount"] == 5
    assert data["enemy_hit_dice"] == 5
    assert data["max_range_ft"] == 60
    assert data["cleric_level"] == 17
    await asyncio.sleep(0.3)
    feats = _ks_broadcasts(gm_ws, tavik["id"])
    assert feats


async def test_use_ks_default_hd_clamp(
    gm_client, tavik_grave_lv17,
):
    """Missing enemy_hit_dice → heal 1 (clamp)."""
    tavik = tavik_grave_lv17
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_keeper_of_souls",
        json={"character_id": tavik["id"]},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["heal_amount"] == 1
    assert data["enemy_hit_dice"] == 1


async def test_use_ks_wrong_subclass(
    gm_client, roster,
):
    """Default Tavik (Life Domain) → 409."""
    tavik = roster["Brother Tavik Stonebrow"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_keeper_of_souls",
        json={"character_id": tavik["id"], "enemy_hit_dice": 3},
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "wrong_subclass_or_level"


async def test_use_ks_level_gate(
    gm_client, roster,
):
    """Grave Tavik at Lv 16 → 409."""
    tavik = roster["Brother Tavik Stonebrow"]
    await _patch_sheet(
        gm_client, tavik["id"],
        {"subclass": "Grave Domain", "level": 16},
        class_slug="cleric",
    )
    try:
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/use_keeper_of_souls",
            json={"character_id": tavik["id"], "enemy_hit_dice": 3},
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
