"""v2.99.316 — Stars Druid: Star Map (E.4 batch, Lv 2+, TCE).

E.4 Druid ship #4 (Stars, TCE). RAW TCE p.37: star chart
spellcasting focus. Guidance + Guiding Bolt always prepared.
Guiding Bolt is Lv 1 druid spell, castable WIS_mod times
(min 1) per long rest without slot.

v1 announce-only — actual prep + free-cast mechanics
GM-tracked. No chip — passive declaration.

Mira WIS 17 → mod 3 → 3 free Guiding Bolts.

Tests:
  - Lv 5 Stars happy → free_guiding_bolt_uses 3,
    always_prepared includes Guidance + Guiding Bolt.
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


def _sm_broadcasts(gm_ws, character_id):
    return [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "star-map"
        and (m.get("data") or {}).get("character_id") == character_id
    ]


@pytest_asyncio.fixture
async def mira_stars(gm_client, roster):
    """PATCH Mira to Stars Druid."""
    mira = roster["Mira Greenleaf"]
    await _patch_sheet(
        gm_client, mira["id"],
        {"subclass": "Circle of Stars"},
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


async def test_use_sm_happy_lv5(
    gm_client, gm_ws, mira_stars,
):
    """Lv 5 Stars (WIS 17 mod 3) → 3 free Guiding Bolts."""
    mira = mira_stars
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_star_map",
        json={"character_id": mira["id"]},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["free_guiding_bolt_uses"] == 3
    assert "Guidance" in data["always_prepared"]
    assert "Guiding Bolt" in data["always_prepared"]
    assert data["druid_level"] == 5
    await asyncio.sleep(0.3)
    feats = _sm_broadcasts(gm_ws, mira["id"])
    assert feats


async def test_use_sm_wrong_subclass(
    gm_client, roster,
):
    """Default Mira (Moon) → 409."""
    mira = roster["Mira Greenleaf"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_star_map",
        json={"character_id": mira["id"]},
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "wrong_subclass_or_level"


async def test_use_sm_level_gate(
    gm_client, roster,
):
    """Stars Mira at Lv 1 → 409."""
    mira = roster["Mira Greenleaf"]
    await _patch_sheet(
        gm_client, mira["id"],
        {"subclass": "Circle of Stars", "level": 1},
        class_slug="druid",
    )
    try:
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/use_star_map",
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
