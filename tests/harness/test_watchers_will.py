"""v2.99.383 — Oath of the Watchers Paladin: Watcher's Will (G Paladin oath sweep, Lv 3+, TCE).

Phase G Paladin oath sweep — rounds out the non-Devotion oaths
beyond the H.2 batch (Ancients, Vengeance, Conquest, Redemption,
Glory).
RAW TCE p.56 (Channel Divinity): as an action, choose up to
CHA-modifier creatures within 30 ft; for 1 minute you and they
gain advantage on INT, WIS, and CHA saving throws.

v1 announce-only — the targeting + save advantage + Channel
Divinity uses are GM-tracked. The number of creatures is computed
server-side. Action chip.

Sir Caelan Lightbringer (Paladin, PATCHed to Oath of the Watchers
Lv 7) is the demo fixture.

Tests:
  - Lv 7 happy: num_creatures >= 1, INT/WIS/CHA advantage.
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


def _ww_broadcasts(gm_ws, character_id):
    return [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "watchers-will"
        and (m.get("data") or {}).get("character_id") == character_id
    ]


@pytest_asyncio.fixture
async def caelan_watchers(gm_client, roster):
    """PATCH Caelan to Oath of the Watchers; restore to Devotion."""
    caelan = roster["Sir Caelan Lightbringer"]
    await _patch_sheet(
        gm_client, caelan["id"],
        {"subclass": "Oath of the Watchers"},
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


async def test_use_ww_happy_lv7(
    gm_client, gm_ws, caelan_watchers,
):
    """Lv 7 Watchers → num_creatures >= 1, INT/WIS/CHA advantage."""
    caelan = caelan_watchers
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_watchers_will",
        json={"character_id": caelan["id"], "override": True},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["feature"] == "watchers-will"
    assert data["num_creatures"] >= 1
    assert data["range_ft"] == 30
    assert data["advantage_saves"] == ["int", "wis", "cha"]
    assert data["duration_minutes"] == 1
    assert data["paladin_level"] == 7
    await asyncio.sleep(0.3)
    feats = _ww_broadcasts(gm_ws, caelan["id"])
    assert feats
    assert feats[-1]["data"]["num_creatures"] == data["num_creatures"]


async def test_use_ww_wrong_subclass(
    gm_client, roster,
):
    """Default Caelan (Oath of Devotion) → 409."""
    caelan = roster["Sir Caelan Lightbringer"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_watchers_will",
        json={"character_id": caelan["id"], "override": True},
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "wrong_subclass_or_level"


async def test_use_ww_wrong_class(
    gm_client, roster,
):
    """Krieger (Barbarian) → 409."""
    krieger = roster["Krieger Stonefist"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_watchers_will",
        json={"character_id": krieger["id"], "override": True},
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "wrong_subclass_or_level"
