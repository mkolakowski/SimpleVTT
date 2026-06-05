"""v2.99.353 — The Celestial Warlock: Healing Light (G Warlock batch #5, Lv 1+, XGE).

Phase G Warlock patron subclass batch ship #5 — The Celestial
opens.
RAW XGE p.54: pool of d6s = 1 + warlock level. As a bonus action,
heal one creature within 60 ft, spending up to CHA-mod dice (min
1) at once. Regain all dice on a long rest.

v1 — the heal dice are rolled server-side and the pool is tracked
on a `healing-light-dice` resource (reset=long); target HP
application is GM-tracked. Bonus chip.

Magnus Hexbinder (Warlock, PATCHed to The Celestial Lv 5) is the
demo fixture (pool max = 1 + 5 = 6).

Tests:
  - Lv 5 happy (1 die): heal in [1,6], max_dice 6, dice_remaining 5.
  - Wrong subclass (default The Fiend) → 409.
  - Wrong class (Caelan paladin) → 409.
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


def _hl_broadcasts(gm_ws, character_id):
    return [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "healing-light"
        and (m.get("data") or {}).get("character_id") == character_id
    ]


@pytest_asyncio.fixture
async def magnus_celestial(gm_client, roster):
    """PATCH Magnus to The Celestial + long-rest (full pool);
    restore to The Fiend on teardown."""
    magnus = roster["Magnus Hexbinder"]
    await _patch_sheet(
        gm_client, magnus["id"],
        {"subclass": "The Celestial"},
        class_slug="warlock",
    )
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{magnus['id']}/rest",
        json={"type": "long"},
    )
    try:
        yield magnus
    finally:
        await _patch_sheet(
            gm_client, magnus["id"],
            {"subclass": "The Fiend"},
            class_slug="warlock",
        )


async def test_use_hl_happy_lv5(
    gm_client, gm_ws, magnus_celestial,
):
    """Lv 5 Celestial, 1 die → heal in [1,6], pool 6 → 5."""
    magnus = magnus_celestial
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_healing_light",
        json={"character_id": magnus["id"], "dice_spent": 1,
              "override": True},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["feature"] == "healing-light"
    assert data["dice_spent"] == 1
    assert 1 <= data["heal_amount"] <= 6
    assert data["max_dice"] == 6  # 1 + warlock level 5
    assert data["dice_remaining"] == data["max_dice"] - 1
    assert data["max_range_ft"] == 60
    assert data["warlock_level"] == 5
    await asyncio.sleep(0.3)
    feats = _hl_broadcasts(gm_ws, magnus["id"])
    assert feats
    assert feats[-1]["data"]["heal_amount"] == data["heal_amount"]


async def test_use_hl_wrong_subclass(
    gm_client, roster,
):
    """Default Magnus (The Fiend) → 409."""
    magnus = roster["Magnus Hexbinder"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_healing_light",
        json={"character_id": magnus["id"], "override": True},
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "wrong_subclass_or_level"


async def test_use_hl_wrong_class(
    gm_client, roster,
):
    """Caelan (Paladin) → 409."""
    caelan = roster["Sir Caelan Lightbringer"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_healing_light",
        json={"character_id": caelan["id"], "override": True},
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "wrong_subclass_or_level"
