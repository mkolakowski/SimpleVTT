"""v2.99.384 — Oath of the Crown Paladin: Champion Challenge (G Paladin oath sweep, Lv 3+, SCAG).

Phase G Paladin oath sweep — Oath of the Crown.
RAW SCAG p.131 (Channel Divinity): as a bonus action, each chosen
creature within 30 ft makes a WIS save (DC 8 + PB + CHA mod); on a
failure it can't willingly move more than 30 ft away from you.

v1 announce-only — the targeting + saves + movement restriction +
Channel Divinity uses are GM-tracked. The save DC is computed
server-side. Bonus chip.

Sir Caelan Lightbringer (Paladin, PATCHed to Oath of the Crown Lv
7) is the demo fixture.

Tests:
  - Lv 7 happy: WIS save DC >= 8, range 30, tether 30.
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


def _cc_broadcasts(gm_ws, character_id):
    return [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "champion-challenge"
        and (m.get("data") or {}).get("character_id") == character_id
    ]


@pytest_asyncio.fixture
async def caelan_crown(gm_client, roster):
    """PATCH Caelan to Oath of the Crown; restore to Devotion."""
    caelan = roster["Sir Caelan Lightbringer"]
    await _patch_sheet(
        gm_client, caelan["id"],
        {"subclass": "Oath of the Crown"},
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


async def test_use_cc_happy_lv7(
    gm_client, gm_ws, caelan_crown,
):
    """Lv 7 Crown → WIS save DC computed, range/tether 30."""
    caelan = caelan_crown
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_champion_challenge",
        json={"character_id": caelan["id"], "override": True},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["feature"] == "champion-challenge"
    assert data["save"] == "wis"
    assert data["save_dc"] >= 8
    assert data["range_ft"] == 30
    assert data["tether_ft"] == 30
    assert data["paladin_level"] == 7
    await asyncio.sleep(0.3)
    feats = _cc_broadcasts(gm_ws, caelan["id"])
    assert feats
    assert feats[-1]["data"]["save_dc"] == data["save_dc"]


async def test_use_cc_wrong_subclass(
    gm_client, roster,
):
    """Default Caelan (Oath of Devotion) → 409."""
    caelan = roster["Sir Caelan Lightbringer"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_champion_challenge",
        json={"character_id": caelan["id"], "override": True},
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "wrong_subclass_or_level"


async def test_use_cc_wrong_class(
    gm_client, roster,
):
    """Krieger (Barbarian) → 409."""
    krieger = roster["Krieger Stonefist"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_champion_challenge",
        json={"character_id": krieger["id"], "override": True},
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "wrong_subclass_or_level"
