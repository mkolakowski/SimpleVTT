"""v2.99.280 — Vengeance Paladin: Relentless Avenger (H.2 depth).

H.2 depth ship — Vengeance's Lv 7 OA-rider feature. RAW PHB
p.88: when you hit a creature with an opportunity attack, you
can move up to half your speed immediately after the attack
and as part of the same reaction; this movement doesn't
provoke opportunity attacks.

v1 announce-only. The actual half-speed-without-provoke move
application is GM-tracked.

Caelan Lv 7 (speed 30 ft) → bonus_move_ft 15.
Tests PATCH his subclass to "Oath of Vengeance".

Tests:
  - Lv 7 happy → bonus_move_ft 15, base_speed 30.
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


def _ra_broadcasts(gm_ws, character_id):
    return [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "relentless-avenger"
        and (m.get("data") or {}).get("character_id") == character_id
    ]


@pytest_asyncio.fixture
async def caelan_vengeance_lv7(gm_client, roster):
    """PATCH Caelan to Vengeance. Default Lv 7 already qualifies."""
    caelan = roster["Sir Caelan Lightbringer"]
    await _patch_sheet(
        gm_client, caelan["id"],
        {"subclass": "Oath of Vengeance"},
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


async def test_use_ra_happy_lv7(
    gm_client, gm_ws, caelan_vengeance_lv7,
):
    """Lv 7 Vengeance, speed 30 → bonus_move_ft 15."""
    caelan = caelan_vengeance_lv7
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_relentless_avenger",
        json={"character_id": caelan["id"]},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["bonus_move_ft"] == 15
    assert data["base_speed"] == 30
    assert data["paladin_level"] == 7
    await asyncio.sleep(0.3)
    feats = _ra_broadcasts(gm_ws, caelan["id"])
    assert feats


async def test_use_ra_wrong_subclass(
    gm_client, roster,
):
    """Default Caelan (Devotion) → 409."""
    caelan = roster["Sir Caelan Lightbringer"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_relentless_avenger",
        json={"character_id": caelan["id"]},
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "wrong_subclass_or_level"


async def test_use_ra_level_gate(
    gm_client, roster,
):
    """Vengeance Caelan at Lv 6 → 409."""
    caelan = roster["Sir Caelan Lightbringer"]
    await _patch_sheet(
        gm_client, caelan["id"],
        {"subclass": "Oath of Vengeance", "level": 6},
        class_slug="paladin",
    )
    try:
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/use_relentless_avenger",
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
