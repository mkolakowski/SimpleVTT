"""v2.99.365 — Path of the Zealot Barbarian: Divine Fury (G Barbarian batch #2, Lv 3+, XGE).

Phase G Barbarian Paths subclass batch ship #2 — Path of the
Zealot opens.
RAW XGE p.11: while raging, the first creature you hit each turn
with a weapon attack takes extra damage = 1d6 + half your
barbarian level, of a chosen type (necrotic or radiant).

v1 announce-only — the on-hit application + first-hit-per-turn
limit are GM-tracked. The bonus damage is rolled server-side. No
action cost.

Krieger Stonefist (Barbarian, PATCHed to Path of the Zealot Lv 7)
is the demo fixture (half level = 3).

Tests:
  - Lv 7 happy (default radiant): bonus = 1d6 + 3, type radiant.
  - Lv 7 happy (necrotic): damage_type echoes "necrotic".
  - Wrong subclass (default Berserker) → 409.
  - Invalid damage_type → 400.
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


def _df_broadcasts(gm_ws, character_id):
    return [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "divine-fury"
        and (m.get("data") or {}).get("character_id") == character_id
    ]


@pytest_asyncio.fixture
async def krieger_zealot(gm_client, roster):
    """PATCH Krieger to Path of the Zealot; restore to Berserker."""
    krieger = roster["Krieger Stonefist"]
    await _patch_sheet(
        gm_client, krieger["id"],
        {"subclass": "Path of the Zealot"},
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


async def test_use_df_happy_radiant(
    gm_client, gm_ws, krieger_zealot,
):
    """Lv 7 Zealot, default → radiant, bonus = 1d6 + 3 in [4,9]."""
    krieger = krieger_zealot
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_divine_fury",
        json={"character_id": krieger["id"]},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["feature"] == "divine-fury"
    assert data["damage_type"] == "radiant"
    assert data["half_level"] == 3
    assert 1 <= data["die_roll"] <= 6
    assert data["bonus_damage"] == data["die_roll"] + 3
    assert data["barbarian_level"] == 7
    await asyncio.sleep(0.3)
    feats = _df_broadcasts(gm_ws, krieger["id"])
    assert feats
    assert feats[-1]["data"]["bonus_damage"] == data["bonus_damage"]


async def test_use_df_happy_necrotic(
    gm_client, krieger_zealot,
):
    """damage_type=necrotic echoes through."""
    krieger = krieger_zealot
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_divine_fury",
        json={"character_id": krieger["id"], "damage_type": "necrotic"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["damage_type"] == "necrotic"


async def test_use_df_wrong_subclass(
    gm_client, roster,
):
    """Default Krieger (Berserker) → 409."""
    krieger = roster["Krieger Stonefist"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_divine_fury",
        json={"character_id": krieger["id"]},
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "wrong_subclass_or_level"


async def test_use_df_invalid_type(
    gm_client, krieger_zealot,
):
    """Invalid damage_type → 400."""
    krieger = krieger_zealot
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_divine_fury",
        json={"character_id": krieger["id"], "damage_type": "fire"},
    )
    assert r.status_code == 400, r.text
