"""v2.99.287 — Redemption Paladin: Protective Spirit (H.2 deeper, Lv 15).

H.2 Lv 15 Redemption ship. CLOSES the H.2 Lv 15 batch (5/5
oaths). RAW XGE p.39: at end of turn, if at half HP or less
and not incapacitated, regain 1d6 + half-paladin-level HP.

v1 announce-only — actual HP application is GM-tracked (or a
follow-up /heal call). Server rolls the heal die and broadcasts.

Caelan Lv 15 → half_paladin_level 7. Heal range [1+7, 6+7] =
[8, 13]. v1 just asserts heal_amount is within the expected
range.

Tests:
  - Lv 15 happy → heal_amount in [8, 13], die_rolled in [1, 6].
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


def _ps_broadcasts(gm_ws, character_id):
    return [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "protective-spirit"
        and (m.get("data") or {}).get("character_id") == character_id
    ]


@pytest_asyncio.fixture
async def caelan_redemption_lv15(gm_client, roster):
    """PATCH Caelan to Redemption Lv 15."""
    caelan = roster["Sir Caelan Lightbringer"]
    await _patch_sheet(
        gm_client, caelan["id"],
        {"subclass": "Oath of Redemption", "level": 15},
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


async def test_use_ps_happy_lv15(
    gm_client, gm_ws, caelan_redemption_lv15,
):
    """Lv 15 Redemption → heal in [8, 13] (1d6 + 7)."""
    caelan = caelan_redemption_lv15
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_protective_spirit",
        json={"character_id": caelan["id"]},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert 1 <= data["die_rolled"] <= 6
    assert data["half_paladin_level"] == 7
    assert 8 <= data["heal_amount"] <= 13
    assert data["paladin_level"] == 15
    await asyncio.sleep(0.3)
    feats = _ps_broadcasts(gm_ws, caelan["id"])
    assert feats


async def test_use_ps_wrong_subclass(
    gm_client, roster,
):
    """Default Caelan (Devotion Lv 7) → 409."""
    caelan = roster["Sir Caelan Lightbringer"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_protective_spirit",
        json={"character_id": caelan["id"]},
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "wrong_subclass_or_level"


async def test_use_ps_level_gate(
    gm_client, roster,
):
    """Redemption Caelan at Lv 14 → 409."""
    caelan = roster["Sir Caelan Lightbringer"]
    await _patch_sheet(
        gm_client, caelan["id"],
        {"subclass": "Oath of Redemption", "level": 14},
        class_slug="paladin",
    )
    try:
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/use_protective_spirit",
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


async def test_protective_spirit_heals_caster(
    gm_client, caelan_redemption_lv15,
):
    """v2.99.458 — Protective Spirit restores the paladin's HP. Drop Caelan
    to 10/100 (headroom) → applied == heal_amount (1d6 + 7). Restore after."""
    caelan = caelan_redemption_lv15
    await _patch_sheet(
        gm_client, caelan["id"],
        {"hp": {"current": 10, "max": 100, "temp": 0}},
    )
    try:
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/use_protective_spirit",
            json={"character_id": caelan["id"]},
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert 8 <= data["heal_amount"] <= 13
        assert data["applied"] == data["heal_amount"]  # full heal, headroom
    finally:
        await _patch_sheet(
            gm_client, caelan["id"],
            {"hp": {"current": 100, "max": 100, "temp": 0}},
        )
