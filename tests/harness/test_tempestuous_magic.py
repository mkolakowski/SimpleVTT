"""v2.99.339 — Storm Sorcery: Tempestuous Magic (G.2 batch open, Lv 1+, PHB).

G.2 Sorcerer subclass batch ship #1 — opens the Sorcerer batch.
RAW PHB p.137: bonus action on your turn to fly up to 10 ft
without provoking opportunity attacks, immediately after casting
a Lv 1+ sorcerer spell. Must be on the ground when casting.

v1 announce-only — recent-cast requirement + on-ground gate +
OA-free movement GM-tracked. Bonus chip.

Tests:
  - Lv 5 happy: fly_distance 10, oa_free True.
  - Wrong subclass (default Zara Draconic) → 409.
  - Wrong class (Caelan paladin) → 409.
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


def _tm_broadcasts(gm_ws, character_id):
    return [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "tempestuous-magic"
        and (m.get("data") or {}).get("character_id") == character_id
    ]


@pytest_asyncio.fixture
async def zara_storm(gm_client, roster):
    """PATCH Zara to Storm Sorcery."""
    zara = roster["Zara Emberfire"]
    await _patch_sheet(
        gm_client, zara["id"],
        {"subclass": "Storm Sorcery"},
        class_slug="sorcerer",
    )
    try:
        yield zara
    finally:
        await _patch_sheet(
            gm_client, zara["id"],
            {"subclass": "Draconic Bloodline"},
            class_slug="sorcerer",
        )


async def test_use_tm_happy_lv5(
    gm_client, gm_ws, zara_storm,
):
    """Lv 5 Storm Sorcery → fly_distance 10, oa_free True."""
    zara = zara_storm
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_tempestuous_magic",
        json={"character_id": zara["id"], "override": True},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["feature"] == "tempestuous-magic"
    assert data["fly_distance"] == 10
    assert data["oa_free"] is True
    assert data["sorcerer_level"] == 5
    await asyncio.sleep(0.3)
    feats = _tm_broadcasts(gm_ws, zara["id"])
    assert feats


async def test_use_tm_wrong_subclass(
    gm_client, roster,
):
    """Default Zara (Draconic Bloodline) → 409."""
    zara = roster["Zara Emberfire"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_tempestuous_magic",
        json={"character_id": zara["id"], "override": True},
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "wrong_subclass_or_level"


async def test_use_tm_wrong_class(
    gm_client, roster,
):
    """Caelan (Paladin) → 409."""
    caelan = roster["Sir Caelan Lightbringer"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_tempestuous_magic",
        json={"character_id": caelan["id"], "override": True},
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "wrong_subclass_or_level"
