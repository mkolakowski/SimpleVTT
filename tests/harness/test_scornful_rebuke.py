"""v2.99.285 — Conquest Paladin: Scornful Rebuke (H.2 deeper, Lv 15).

H.2 Lv 15 Conquest ship. RAW XGE p.37: when a creature hits
you with an attack, that creature takes psychic damage equal
to your CHA modifier (minimum 1) if you're not incapacitated.

v1 announce-only — actual psychic-damage application to the
attacker is GM-tracked. Passive — no chip cost.

Caelan default CHA 16 → mod 3 → psychic_damage 3 (max(1, 3)).

Tests:
  - Lv 15 happy → psychic_damage 3, broadcast.
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


def _sr_broadcasts(gm_ws, character_id):
    return [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "scornful-rebuke"
        and (m.get("data") or {}).get("character_id") == character_id
    ]


@pytest_asyncio.fixture
async def caelan_conquest_lv15(gm_client, roster):
    """PATCH Caelan to Conquest Lv 15."""
    caelan = roster["Sir Caelan Lightbringer"]
    await _patch_sheet(
        gm_client, caelan["id"],
        {"subclass": "Oath of Conquest", "level": 15},
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


async def test_use_sr_happy_lv15(
    gm_client, gm_ws, caelan_conquest_lv15,
):
    """Lv 15 Conquest, CHA 16 → psychic_damage 3."""
    caelan = caelan_conquest_lv15
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_scornful_rebuke",
        json={"character_id": caelan["id"]},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["psychic_damage"] == 3
    assert data["paladin_level"] == 15
    await asyncio.sleep(0.3)
    feats = _sr_broadcasts(gm_ws, caelan["id"])
    assert feats


async def test_use_sr_wrong_subclass(
    gm_client, roster,
):
    """Default Caelan (Devotion Lv 7) → 409."""
    caelan = roster["Sir Caelan Lightbringer"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_scornful_rebuke",
        json={"character_id": caelan["id"]},
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "wrong_subclass_or_level"


async def test_use_sr_level_gate(
    gm_client, roster,
):
    """Conquest Caelan at Lv 14 → 409."""
    caelan = roster["Sir Caelan Lightbringer"]
    await _patch_sheet(
        gm_client, caelan["id"],
        {"subclass": "Oath of Conquest", "level": 14},
        class_slug="paladin",
    )
    try:
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/use_scornful_rebuke",
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
