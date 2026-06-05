"""v2.99.279 — Ancients Paladin: Aura of Warding (H.2 depth).

H.2 depth ship — Ancients's Lv 7 aura. RAW PHB p.87: 10 ft
aura (30 ft at Lv 18+); you + friendly creatures within have
resistance to damage from spells.

v1 announce-only; the resistance-to-spell-damage application
would land as a deeper /attack damage-pipeline hook (filed
for follow-up).

Caelan Lv 7 → 10 ft radius. Tests PATCH his subclass to
"Oath of the Ancients".

Tests:
  - Lv 7 happy → radius 10.
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


def _aow_broadcasts(gm_ws, character_id):
    return [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "aura-of-warding"
        and (m.get("data") or {}).get("character_id") == character_id
    ]


@pytest_asyncio.fixture
async def caelan_ancients_lv7(gm_client, roster):
    """PATCH Caelan to Ancients. Default Lv 7 already qualifies."""
    caelan = roster["Sir Caelan Lightbringer"]
    await _patch_sheet(
        gm_client, caelan["id"],
        {"subclass": "Oath of the Ancients"},
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


async def test_use_aow_happy_lv7(
    gm_client, gm_ws, caelan_ancients_lv7,
):
    """Lv 7 Ancients → radius 10."""
    caelan = caelan_ancients_lv7
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_aura_of_warding",
        json={"character_id": caelan["id"]},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["radius_ft"] == 10
    assert data["paladin_level"] == 7
    await asyncio.sleep(0.3)
    feats = _aow_broadcasts(gm_ws, caelan["id"])
    assert feats


async def test_use_aow_lv18_radius_upgrade(
    gm_client, caelan_ancients_lv7,
):
    """Lv 18 → radius 30 (RAW upgrade)."""
    caelan = caelan_ancients_lv7
    await _patch_sheet(
        gm_client, caelan["id"], {"level": 18},
        class_slug="paladin",
    )
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_aura_of_warding",
        json={"character_id": caelan["id"]},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["radius_ft"] == 30
    assert data["paladin_level"] == 18


async def test_use_aow_wrong_subclass(
    gm_client, roster,
):
    """Default Caelan (Devotion) → 409."""
    caelan = roster["Sir Caelan Lightbringer"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_aura_of_warding",
        json={"character_id": caelan["id"]},
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "wrong_subclass_or_level"


async def test_use_aow_level_gate(
    gm_client, roster,
):
    """Ancients Caelan at Lv 6 → 409."""
    caelan = roster["Sir Caelan Lightbringer"]
    await _patch_sheet(
        gm_client, caelan["id"],
        {"subclass": "Oath of the Ancients", "level": 6},
        class_slug="paladin",
    )
    try:
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/use_aura_of_warding",
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
