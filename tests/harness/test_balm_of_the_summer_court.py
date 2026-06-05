"""v2.99.319 — Dreams Druid: Balm of the Summer Court (E.4 batch, Lv 2+, XGE).

E.4 Druid ship #6 (Dreams, XGE). RAW XGE p.23: bonus action
spend d6 from pool (max=druid_lv, half-druid-lv dice per use)
→ ally within 120 ft heals total + 1 temp HP per die.

v1 announce-only — actual HP/temp HP application GM-tracked.
Costs bonus chip. Auto-bootstraps balm-of-summer-court-dice
resource (max=druid_lv, reset=long).

Mira Lv 5 → pool 5, half-level 2 (max dice per use).

Tests:
  - Lv 5 happy default 1 die → heal in [1, 6], temp HP 1.
  - dice_spent 2 → heal in [2, 12], temp HP 2.
  - dice_spent clamped to half-level 2.
  - Wrong subclass → 409.
  - Lv 1 gate → 409.
  - Pool exhaustion → 409 no_uses_left.
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


def _bsc_broadcasts(gm_ws, character_id):
    return [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "balm-of-the-summer-court"
        and (m.get("data") or {}).get("character_id") == character_id
    ]


@pytest_asyncio.fixture
async def mira_dreams(gm_client, roster):
    """PATCH Mira to Dreams + long-rest to refill pool."""
    mira = roster["Mira Greenleaf"]
    await _patch_sheet(
        gm_client, mira["id"],
        {"subclass": "Circle of Dreams"},
        class_slug="druid",
    )
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{mira['id']}/rest",
        json={"type": "long"},
    )
    try:
        yield mira
    finally:
        await _patch_sheet(
            gm_client, mira["id"],
            {"subclass": "Circle of the Moon", "level": 5},
            class_slug="druid",
        )


async def test_use_bsc_happy_lv5_one_die(
    gm_client, gm_ws, mira_dreams,
):
    """Lv 5 Dreams 1 die → heal in [1, 6], temp HP 1."""
    mira = mira_dreams
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_balm_of_the_summer_court",
        json={"character_id": mira["id"], "override": True},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["dice_spent"] == 1
    assert 1 <= data["heal_amount"] <= 6
    assert data["temp_hp"] == 1
    assert data["max_range_ft"] == 120
    assert data["dice_remaining"] == 4  # 5 - 1
    assert data["druid_level"] == 5
    await asyncio.sleep(0.3)
    feats = _bsc_broadcasts(gm_ws, mira["id"])
    assert feats


async def test_use_bsc_two_dice(
    gm_client, mira_dreams,
):
    """dice_spent 2 → heal in [2, 12], temp HP 2."""
    mira = mira_dreams
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_balm_of_the_summer_court",
        json={"character_id": mira["id"], "dice_spent": 2, "override": True},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["dice_spent"] == 2
    assert 2 <= data["heal_amount"] <= 12
    assert data["temp_hp"] == 2


async def test_use_bsc_dice_clamp(
    gm_client, mira_dreams,
):
    """Request 99 dice → clamped to half-druid-level 2."""
    mira = mira_dreams
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_balm_of_the_summer_court",
        json={"character_id": mira["id"], "dice_spent": 99, "override": True},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["dice_spent"] == 2  # half of 5 = 2 (int div)


async def test_use_bsc_wrong_subclass(
    gm_client, roster,
):
    """Default Mira (Moon) → 409."""
    mira = roster["Mira Greenleaf"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_balm_of_the_summer_court",
        json={"character_id": mira["id"], "override": True},
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "wrong_subclass_or_level"


async def test_use_bsc_level_gate(
    gm_client, roster,
):
    """Dreams Mira at Lv 1 → 409."""
    mira = roster["Mira Greenleaf"]
    await _patch_sheet(
        gm_client, mira["id"],
        {"subclass": "Circle of Dreams", "level": 1},
        class_slug="druid",
    )
    try:
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/use_balm_of_the_summer_court",
            json={"character_id": mira["id"], "override": True},
        )
        assert r.status_code == 409, r.text
        data = r.json()
        assert data.get("error") == "wrong_subclass_or_level"
    finally:
        await _patch_sheet(
            gm_client, mira["id"],
            {"subclass": "Circle of the Moon", "level": 5},
            class_slug="druid",
        )
