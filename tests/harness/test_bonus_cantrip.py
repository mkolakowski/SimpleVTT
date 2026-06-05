"""v2.99.313 — Land Druid: Bonus Cantrip (E.4 Druid opener, Lv 2+).

E.4 Druid subclass batch opener. RAW PHB p.68: +1 druid
cantrip of your choice.

v1 announce-only — actual cantrip addition is via the
existing spellcasting flow; this endpoint declares which.
No chip — passive list addition.

Mira Greenleaf is Lv 5 Moon Druid — PATCH'd to Land for testing.

Tests:
  - Lv 5 Land happy with cantrip name → 200, announced.
  - Default cantrip_name missing → fallback string.
  - Default Mira (Moon) → 409.
  - Land Lv 1 → 409.
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


def _bc_broadcasts(gm_ws, character_id):
    return [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "bonus-cantrip"
        and (m.get("data") or {}).get("character_id") == character_id
    ]


@pytest_asyncio.fixture
async def mira_land(gm_client, roster):
    """PATCH Mira to Circle of the Land."""
    mira = roster["Mira Greenleaf"]
    await _patch_sheet(
        gm_client, mira["id"],
        {"subclass": "Circle of the Land"},
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


async def test_use_bc_happy_lv5(
    gm_client, gm_ws, mira_land,
):
    """Lv 5 Land Druid with explicit cantrip → 200, announced."""
    mira = mira_land
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_bonus_cantrip",
        json={"character_id": mira["id"], "cantrip_name": "Shillelagh"},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["cantrip_name"] == "Shillelagh"
    assert data["added_cantrip_count"] == 1
    assert data["druid_level"] == 5
    await asyncio.sleep(0.3)
    feats = _bc_broadcasts(gm_ws, mira["id"])
    assert feats


async def test_use_bc_default_name(
    gm_client, mira_land,
):
    """Missing cantrip_name → fallback string."""
    mira = mira_land
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_bonus_cantrip",
        json={"character_id": mira["id"]},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert "unspecified" in data["cantrip_name"]


async def test_use_bc_wrong_subclass(
    gm_client, roster,
):
    """Default Mira (Moon) → 409."""
    mira = roster["Mira Greenleaf"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_bonus_cantrip",
        json={"character_id": mira["id"]},
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "wrong_subclass_or_level"


async def test_use_bc_level_gate(
    gm_client, roster,
):
    """Land Mira at Lv 1 → 409."""
    mira = roster["Mira Greenleaf"]
    await _patch_sheet(
        gm_client, mira["id"],
        {"subclass": "Circle of the Land", "level": 1},
        class_slug="druid",
    )
    try:
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/use_bonus_cantrip",
            json={"character_id": mira["id"]},
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
