"""v2.99.318 — Wildfire Druid: Summon Wildfire Spirit (E.4 batch, Lv 2+, TCE).

E.4 Druid ship #6 (Wildfire, TCE). RAW TCE p.38: action +
Wild Shape (default) or Lv 2+ spell slot to summon Wildfire
Spirit companion for 1 hour. Once per long rest unless a
spell slot is used.

v1 announce-only — Wild Shape / slot consumption and spirit
persistence GM-tracked. Costs action chip.

Tests:
  - Lv 2+ happy default → resource "wild-shape", 60 min.
  - slot_level 3 → resource "spell-slot", slot_level 3.
  - Wrong subclass → 409.
  - Lv 1 gate → 409.
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


def _ws_broadcasts(gm_ws, character_id):
    return [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "summon-wildfire-spirit"
        and (m.get("data") or {}).get("character_id") == character_id
    ]


@pytest_asyncio.fixture
async def mira_wildfire(gm_client, roster):
    """PATCH Mira to Wildfire."""
    mira = roster["Mira Greenleaf"]
    await _patch_sheet(
        gm_client, mira["id"],
        {"subclass": "Circle of Wildfire"},
        class_slug="druid",
    )
    try:
        yield mira
    finally:
        await _patch_sheet(
            gm_client, mira["id"],
            {"subclass": "Circle of the Moon", "level": 5},
            class_slug="druid",
        )


async def test_use_ws_happy_lv5_default(
    gm_client, gm_ws, mira_wildfire,
):
    """Lv 5 Wildfire default → wild-shape, 60 min."""
    mira = mira_wildfire
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_summon_wildfire_spirit",
        json={"character_id": mira["id"], "override": True},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["resource_used"] == "wild-shape"
    assert data["slot_level"] is None
    assert data["duration_minutes"] == 60
    assert data["druid_level"] == 5
    await asyncio.sleep(0.3)
    feats = _ws_broadcasts(gm_ws, mira["id"])
    assert feats


async def test_use_ws_slot_variant(
    gm_client, mira_wildfire,
):
    """slot_level 3 → resource 'spell-slot'."""
    mira = mira_wildfire
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_summon_wildfire_spirit",
        json={"character_id": mira["id"], "slot_level": 3, "override": True},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["resource_used"] == "spell-slot"
    assert data["slot_level"] == 3


async def test_use_ws_wrong_subclass(
    gm_client, roster,
):
    """Default Mira (Moon) → 409."""
    mira = roster["Mira Greenleaf"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_summon_wildfire_spirit",
        json={"character_id": mira["id"], "override": True},
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "wrong_subclass_or_level"


async def test_use_ws_level_gate(
    gm_client, roster,
):
    """Wildfire Mira at Lv 1 → 409."""
    mira = roster["Mira Greenleaf"]
    await _patch_sheet(
        gm_client, mira["id"],
        {"subclass": "Circle of Wildfire", "level": 1},
        class_slug="druid",
    )
    try:
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/use_summon_wildfire_spirit",
            json={"character_id": mira["id"], "override": True},
        )
        assert r.status_code == 409, r.text
        data = r.json()
        assert data.get("error") == "wrong_subclass_or_level"
    finally:
        await _patch_sheet(
            gm_client, mira["id"],
            {"subclass": "Circle of the Moon", "level": 5},
            class_slug="druid",
        )
