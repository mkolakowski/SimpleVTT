"""v2.99.340 — Divine Soul: Favored by the Gods (G.2 batch ship #2, Lv 1+, XGE).

G.2 Sorcerer subclass batch ship #2 — Divine Soul opens.
RAW XGE p.50: if you fail a saving throw or miss with an attack
roll, roll 2d4 and add it to the total. Once per short or long
rest. Costs no action.

v1 — rolls the 2d4 server-side and broadcasts the total; the
once-per-rest limit is GM-tracked.

Tests:
  - Lv 5 happy: bonus_total in [2,8], two d4 dice, broadcast fires.
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


def _fbg_broadcasts(gm_ws, character_id):
    return [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "favored-by-the-gods"
        and (m.get("data") or {}).get("character_id") == character_id
    ]


@pytest_asyncio.fixture
async def zara_divine(gm_client, roster):
    """PATCH Zara to Divine Soul."""
    zara = roster["Zara Emberfire"]
    await _patch_sheet(
        gm_client, zara["id"],
        {"subclass": "Divine Soul"},
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


async def test_use_fbg_happy_lv5(
    gm_client, gm_ws, zara_divine,
):
    """Lv 5 Divine Soul → 2d4 bonus in [2,8], broadcast fires."""
    zara = zara_divine
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_favored_by_the_gods",
        json={"character_id": zara["id"]},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["feature"] == "favored-by-the-gods"
    assert len(data["dice"]) == 2
    assert all(1 <= d <= 4 for d in data["dice"])
    assert data["bonus_total"] == sum(data["dice"])
    assert 2 <= data["bonus_total"] <= 8
    assert data["sorcerer_level"] == 5
    await asyncio.sleep(0.3)
    feats = _fbg_broadcasts(gm_ws, zara["id"])
    assert feats
    assert feats[-1]["data"]["bonus_total"] == data["bonus_total"]


async def test_use_fbg_wrong_subclass(
    gm_client, roster,
):
    """Default Zara (Draconic Bloodline) → 409."""
    zara = roster["Zara Emberfire"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_favored_by_the_gods",
        json={"character_id": zara["id"]},
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "wrong_subclass_or_level"


async def test_use_fbg_wrong_class(
    gm_client, roster,
):
    """Caelan (Paladin) → 409."""
    caelan = roster["Sir Caelan Lightbringer"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_favored_by_the_gods",
        json={"character_id": caelan["id"]},
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "wrong_subclass_or_level"
