"""v2.99.385 — Oathbreaker Paladin: Control Undead (G Paladin oath sweep, Lv 3+, DMG).

Phase G Paladin oath sweep — Oathbreaker rounds out the oaths.
RAW DMG p.97 (Channel Divinity): as an action, target an undead
within 30 ft; it makes a CHA save (DC 8 + PB + CHA mod) or obeys
your commands for 24 hours. Undead with CR ≥ your level are immune.

v1 announce-only — the targeting + save + 24h control + Channel
Divinity uses are GM-tracked. The save DC + max CR are computed
server-side. Action chip.

Sir Caelan Lightbringer (Paladin, PATCHed to Oathbreaker Lv 7) is
the demo fixture (max CR 6).

Tests:
  - Lv 7 happy: CHA save DC >= 8, max_cr 6, 24h.
  - Wrong subclass (default Oath of Devotion) → 409.
  - Wrong class (Krieger barbarian) → 409.
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


def _cu_broadcasts(gm_ws, character_id):
    return [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "control-undead"
        and (m.get("data") or {}).get("character_id") == character_id
    ]


@pytest_asyncio.fixture
async def caelan_oathbreaker(gm_client, roster):
    """PATCH Caelan to Oathbreaker; restore to Devotion on teardown."""
    caelan = roster["Sir Caelan Lightbringer"]
    await _patch_sheet(
        gm_client, caelan["id"],
        {"subclass": "Oathbreaker"},
        class_slug="paladin",
    )
    try:
        yield caelan
    finally:
        await _patch_sheet(
            gm_client, caelan["id"],
            {"subclass": "Oath of Devotion"},
            class_slug="paladin",
        )


async def test_use_cu_happy_lv7(
    gm_client, gm_ws, caelan_oathbreaker,
):
    """Lv 7 Oathbreaker → CHA save DC computed, max CR 6, 24h."""
    caelan = caelan_oathbreaker
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_control_undead",
        json={"character_id": caelan["id"], "override": True},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["feature"] == "control-undead"
    assert data["save"] == "cha"
    assert data["save_dc"] >= 8
    assert data["max_cr"] == 6  # paladin level 7 - 1
    assert data["duration_hours"] == 24
    assert data["paladin_level"] == 7
    await asyncio.sleep(0.3)
    feats = _cu_broadcasts(gm_ws, caelan["id"])
    assert feats
    assert feats[-1]["data"]["max_cr"] == 6


async def test_use_cu_wrong_subclass(
    gm_client, roster,
):
    """Default Caelan (Oath of Devotion) → 409."""
    caelan = roster["Sir Caelan Lightbringer"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_control_undead",
        json={"character_id": caelan["id"], "override": True},
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "wrong_subclass_or_level"


async def test_use_cu_wrong_class(
    gm_client, roster,
):
    """Krieger (Barbarian) → 409."""
    krieger = roster["Krieger Stonefist"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_control_undead",
        json={"character_id": krieger["id"], "override": True},
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "wrong_subclass_or_level"
