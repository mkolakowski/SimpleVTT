"""v2.99.286 — Glory Paladin: Glorious Defense (H.2 deeper, Lv 15).

H.2 Lv 15 Glory ship. RAW XGE p.38: when you or another
creature within 10 ft is hit by an attack, use your reaction
to grant +CHA mod (min +1) AC against the attack. If it now
misses, you can make a weapon attack against the attacker as
part of the same reaction.

v1 announce-only — the AC-bonus application + follow-up weapon
attack is GM-tracked. Costs a reaction chip.

Caelan default CHA 16 → ac_bonus 3 (max(1, 3)).

Tests:
  - Lv 15 happy → ac_bonus 3, broadcast.
  - Wrong subclass → 409.
  - Level gate (Lv 14) → 409.
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


def _gd_broadcasts(gm_ws, character_id):
    return [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "glorious-defense"
        and (m.get("data") or {}).get("character_id") == character_id
    ]


@pytest_asyncio.fixture
async def caelan_glory_lv15(gm_client, roster):
    """PATCH Caelan to Glory Lv 15."""
    caelan = roster["Sir Caelan Lightbringer"]
    await _patch_sheet(
        gm_client, caelan["id"],
        {"subclass": "Oath of Glory", "level": 15},
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


async def test_use_gd_happy_lv15(
    gm_client, gm_ws, caelan_glory_lv15,
):
    """Lv 15 Glory, CHA 16 → ac_bonus 3."""
    caelan = caelan_glory_lv15
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_glorious_defense",
        json={"character_id": caelan["id"], "override": True},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["ac_bonus"] == 3
    assert data["paladin_level"] == 15
    await asyncio.sleep(0.3)
    feats = _gd_broadcasts(gm_ws, caelan["id"])
    assert feats


async def test_use_gd_wrong_subclass(
    gm_client, roster,
):
    """Default Caelan (Devotion Lv 7) → 409."""
    caelan = roster["Sir Caelan Lightbringer"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_glorious_defense",
        json={"character_id": caelan["id"], "override": True},
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "wrong_subclass_or_level"


async def test_use_gd_level_gate(
    gm_client, roster,
):
    """Glory Caelan at Lv 14 → 409."""
    caelan = roster["Sir Caelan Lightbringer"]
    await _patch_sheet(
        gm_client, caelan["id"],
        {"subclass": "Oath of Glory", "level": 14},
        class_slug="paladin",
    )
    try:
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/use_glorious_defense",
            json={"character_id": caelan["id"], "override": True},
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
