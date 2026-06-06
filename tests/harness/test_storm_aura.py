"""v2.99.367 — Path of the Storm Herald Barbarian: Storm Aura (G Barbarian #4, Lv 3+, XGE).

Phase G Barbarian Paths subclass batch ship #4 — Path of the Storm
Herald opens.
RAW XGE p.10: a 10-ft aura while raging. Desert (each other
creature in the aura takes fire damage), Sea (one creature makes a
DEX save or takes lightning), or Tundra (one creature gains temp
HP). Magnitudes scale at Lv 10/15/20.

v1 announce-only — the aura targeting + saves + HP/damage
application are GM-tracked. The Sea lightning is rolled
server-side. No action cost.

Krieger Stonefist (Barbarian, PATCHed to Path of the Storm Herald
Lv 7) is the demo fixture (base magnitudes — no tier bumps).

Tests:
  - Lv 7 happy (default desert): fire 2, aura 10 ft.
  - Lv 7 happy (sea): lightning 1d6 in [1,6], DEX save.
  - Wrong subclass (default Berserker) → 409.
  - Invalid environment → 400.
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


def _sa_broadcasts(gm_ws, character_id):
    return [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "storm-aura"
        and (m.get("data") or {}).get("character_id") == character_id
    ]


@pytest_asyncio.fixture
async def krieger_storm(gm_client, roster):
    """PATCH Krieger to Path of the Storm Herald; restore to Berserker."""
    krieger = roster["Krieger Stonefist"]
    await _patch_sheet(
        gm_client, krieger["id"],
        {"subclass": "Path of the Storm Herald"},
        class_slug="barbarian",
    )
    try:
        yield krieger
    finally:
        await _patch_sheet(
            gm_client, krieger["id"],
            {"subclass": "Path of the Berserker"},
            class_slug="barbarian",
        )


async def test_use_sa_happy_desert(
    gm_client, gm_ws, krieger_storm,
):
    """Lv 7 Storm Herald, default → desert, 2 fire, 10-ft aura."""
    krieger = krieger_storm
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_storm_aura",
        json={"character_id": krieger["id"]},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["feature"] == "storm-aura"
    assert data["environment"] == "desert"
    assert data["aura_radius_ft"] == 10
    assert data["fire_damage"] == 2
    assert data["barbarian_level"] == 7
    await asyncio.sleep(0.3)
    feats = _sa_broadcasts(gm_ws, krieger["id"])
    assert feats
    assert feats[-1]["data"]["fire_damage"] == 2


async def test_use_sa_happy_sea(
    gm_client, krieger_storm,
):
    """Lv 7 sea → 1d6 lightning in [1,6], DEX save."""
    krieger = krieger_storm
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_storm_aura",
        json={"character_id": krieger["id"], "environment": "sea"},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["environment"] == "sea"
    assert data["lightning_dice"] == "1d6"
    assert 1 <= data["lightning_damage"] <= 6
    assert data["save"] == "dex"


async def test_use_sa_wrong_subclass(
    gm_client, roster,
):
    """Default Krieger (Berserker) → 409."""
    krieger = roster["Krieger Stonefist"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_storm_aura",
        json={"character_id": krieger["id"]},
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "wrong_subclass_or_level"


async def test_use_sa_invalid_environment(
    gm_client, krieger_storm,
):
    """Invalid environment → 400."""
    krieger = krieger_storm
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_storm_aura",
        json={"character_id": krieger["id"], "environment": "jungle"},
    )
    assert r.status_code == 400, r.text
