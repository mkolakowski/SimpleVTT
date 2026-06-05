"""v2.99.349 — The Fiend Warlock: Dark One's Blessing (G Warlock batch OPEN, Lv 1+, PHB).

Phase G Warlock patron subclass batch ship #1 — opens the Warlock
patron batch.
RAW PHB p.109: when you reduce a hostile creature to 0 HP, you
gain temporary HP equal to your Charisma modifier + your warlock
level (minimum of 1).

v1 announce-only — the kill trigger + temp-HP application are
GM-tracked. The temp-HP amount is computed server-side. No action
cost.

Magnus Hexbinder (Warlock The Fiend Lv 5) is the demo fixture.

Tests:
  - Lv 5 happy: temp_hp = max(1, cha_mod + 5), broadcast fires.
  - Wrong subclass (The Archfey) → 409.
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


def _dob_broadcasts(gm_ws, character_id):
    return [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "dark-ones-blessing"
        and (m.get("data") or {}).get("character_id") == character_id
    ]


async def test_use_dob_happy_lv5(
    gm_client, gm_ws, roster,
):
    """Lv 5 The Fiend Warlock → temp_hp = max(1, cha_mod + 5)."""
    magnus = roster["Magnus Hexbinder"]
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_dark_ones_blessing",
        json={"character_id": magnus["id"]},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["feature"] == "dark-ones-blessing"
    assert data["warlock_level"] == 5
    assert data["temp_hp"] == max(1, data["cha_mod"] + data["warlock_level"])
    assert data["temp_hp"] >= 1
    await asyncio.sleep(0.3)
    feats = _dob_broadcasts(gm_ws, magnus["id"])
    assert feats
    assert feats[-1]["data"]["temp_hp"] == data["temp_hp"]


async def test_use_dob_wrong_subclass(
    gm_client, roster,
):
    """Magnus PATCHed to The Archfey → 409."""
    magnus = roster["Magnus Hexbinder"]
    await _patch_sheet(
        gm_client, magnus["id"],
        {"subclass": "The Archfey"},
        class_slug="warlock",
    )
    try:
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/use_dark_ones_blessing",
            json={"character_id": magnus["id"]},
        )
        assert r.status_code == 409, r.text
        data = r.json()
        assert data.get("error") == "wrong_subclass_or_level"
    finally:
        await _patch_sheet(
            gm_client, magnus["id"],
            {"subclass": "The Fiend"},
            class_slug="warlock",
        )


async def test_use_dob_wrong_class(
    gm_client, roster,
):
    """Caelan (Paladin) → 409."""
    caelan = roster["Sir Caelan Lightbringer"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_dark_ones_blessing",
        json={"character_id": caelan["id"]},
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "wrong_subclass_or_level"
