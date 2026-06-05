"""v2.99.354 — The Fathomless Warlock: Tentacle of the Deeps (G Warlock batch #6, Lv 1+, TCE).

Phase G Warlock patron subclass batch ship #6 — The Fathomless
opens.
RAW TCE p.70: bonus action, summon a 10-ft spectral tentacle
within 60 ft and make a melee spell attack vs a creature within
10 ft. On a hit: 1d8 cold (2d8 at Lv 10) + speed -10 ft for 1 min.
Summonable PB times per long rest.

v1 announce-only — the attack roll resolution, target choice,
speed reduction, and uses-per-rest limit are GM-tracked. The cold
damage is rolled server-side; the spell-attack bonus is computed.
Bonus chip.

Magnus Hexbinder (Warlock, PATCHed to The Fathomless Lv 5) is the
demo fixture (1d8 cold below Lv 10).

Tests:
  - Lv 5 happy: cold in [1,8], 1d8 dice, reach 10, range 60.
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


def _td_broadcasts(gm_ws, character_id):
    return [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "tentacle-of-the-deeps"
        and (m.get("data") or {}).get("character_id") == character_id
    ]


@pytest_asyncio.fixture
async def magnus_fathomless(gm_client, roster):
    """PATCH Magnus to The Fathomless; restore to The Fiend."""
    magnus = roster["Magnus Hexbinder"]
    await _patch_sheet(
        gm_client, magnus["id"],
        {"subclass": "The Fathomless"},
        class_slug="warlock",
    )
    try:
        yield magnus
    finally:
        await _patch_sheet(
            gm_client, magnus["id"],
            {"subclass": "The Fiend"},
            class_slug="warlock",
        )


async def test_use_td_happy_lv5(
    gm_client, gm_ws, magnus_fathomless,
):
    """Lv 5 Fathomless → 1d8 cold in [1,8], reach 10, range 60."""
    magnus = magnus_fathomless
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_tentacle_of_the_deeps",
        json={"character_id": magnus["id"], "override": True},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["feature"] == "tentacle-of-the-deeps"
    assert data["damage_dice"] == "1d8"
    assert 1 <= data["cold_damage"] <= 8
    assert data["reach_ft"] == 10
    assert data["summon_range_ft"] == 60
    assert data["speed_reduction_ft"] == 10
    assert data["warlock_level"] == 5
    await asyncio.sleep(0.3)
    feats = _td_broadcasts(gm_ws, magnus["id"])
    assert feats
    assert feats[-1]["data"]["cold_damage"] == data["cold_damage"]


async def test_use_td_wrong_subclass(
    gm_client, roster,
):
    """Default Magnus (The Fiend) → 409."""
    magnus = roster["Magnus Hexbinder"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_tentacle_of_the_deeps",
        json={"character_id": magnus["id"], "override": True},
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "wrong_subclass_or_level"


async def test_use_td_wrong_class(
    gm_client, roster,
):
    """Caelan (Paladin) → 409."""
    caelan = roster["Sir Caelan Lightbringer"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_tentacle_of_the_deeps",
        json={"character_id": caelan["id"], "override": True},
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "wrong_subclass_or_level"
