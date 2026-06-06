"""v2.99.383 — Oath of the Watchers Paladin: Watcher's Will (G Paladin oath sweep, Lv 3+, TCE).

Phase G Paladin oath sweep — rounds out the non-Devotion oaths
beyond the H.2 batch (Ancients, Vengeance, Conquest, Redemption,
Glory).
RAW TCE p.56 (Channel Divinity): as an action, choose up to
CHA-modifier creatures within 30 ft; for 1 minute you and they
gain advantage on INT, WIS, and CHA saving throws.

v2.99.392 — Phase 1 of docs/plans/full-feature-automation.md: the
Channel Divinity cost is now server-tracked — `/use_watchers_will`
spends a use from the shared `channel-divinity` resource pool
(decrements, 409 `out_of_uses` when depleted, refilled by the
generic /rest resource loop). The save-advantage application stays
GM-tracked pending the Phase 4 roll-bonus engine. Action chip.

Sir Caelan Lightbringer (Paladin, PATCHed to Oath of the Watchers
Lv 7; Channel Divinity max 1) is the demo fixture.

Tests:
  - Lv 7 happy: INT/WIS/CHA advantage, Channel Divinity 1→0.
  - Exhausted Channel Divinity (second use) → 409 out_of_uses.
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
    """PATCH Caelan to Oath of the Watchers + long-rest (refill Channel
    Divinity); restore to Devotion on teardown."""
    caelan = roster["Sir Caelan Lightbringer"]
    await _patch_sheet(
        gm_client, caelan["id"],
        {"subclass": "Oath of the Watchers"},
        class_slug="paladin",
    )
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{caelan['id']}/rest",
        json={"type": "long"},
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
    """Lv 7 Watchers → INT/WIS/CHA advantage, Channel Divinity 1→0."""
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
    assert data["cd_max"] == 1  # Paladin Channel Divinity
    assert data["cd_remaining"] == 0
    assert data["paladin_level"] == 7
    await asyncio.sleep(0.3)
    feats = _ww_broadcasts(gm_ws, caelan["id"])
    assert feats
    assert feats[-1]["data"]["cd_remaining"] == 0


async def test_use_ww_out_of_channel_divinity(
    gm_client, caelan_watchers,
):
    """A second Watcher's Will with no Channel Divinity left → 409
    out_of_uses (the shared CD pool is depleted by the first use)."""
    caelan = caelan_watchers
    url = f"/api/campaign/{CAMPAIGN_ID}/use_watchers_will"
    # First use spends the single CD charge (override bypasses the
    # action gate so the CD pool is the binding constraint).
    r1 = await gm_client.post(url, json={
        "character_id": caelan["id"], "override": True})
    assert r1.status_code == 200, r1.text
    assert r1.json()["cd_remaining"] == 0
    # Second use → CD depleted → 409 out_of_uses.
    r2 = await gm_client.post(url, json={
        "character_id": caelan["id"], "override": True})
    assert r2.status_code == 409, r2.text
    assert r2.json().get("error") == "out_of_uses"


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
