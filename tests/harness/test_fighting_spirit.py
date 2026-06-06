"""v2.99.370 — Samurai Fighter: Fighting Spirit (G Fighter sweep OPEN, Lv 3+, XGE).

Phase G Fighter martial archetype sweep — Samurai is the first new
archetype beyond Champion / Battle Master / Eldritch Knight.
RAW XGE p.31: as a bonus action, give yourself advantage on weapon
attack rolls until the end of the turn and gain temp HP (5, rising
to 10 at Lv 10, 15 at Lv 15). 3 uses per long rest.

v1 announce-only — the advantage + temp-HP application + 3-per-
long-rest limit are GM-tracked. Bonus chip.

Garrik Ironside (Fighter, PATCHed to Samurai Lv 9) is the demo
fixture (temp HP 5 below Lv 10).

Tests:
  - Lv 9 happy: advantage flag True, temp_hp 5.
  - Wrong subclass (default Champion) → 409.
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


def _fs_broadcasts(gm_ws, character_id):
    return [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "fighting-spirit"
        and (m.get("data") or {}).get("character_id") == character_id
    ]


@pytest_asyncio.fixture
async def garrik_samurai(gm_client, roster):
    """PATCH Garrik to Samurai; restore to Champion on teardown."""
    garrik = roster["Garrik Ironside"]
    await _patch_sheet(
        gm_client, garrik["id"],
        {"subclass": "Samurai"},
        class_slug="fighter",
    )
    try:
        yield garrik
    finally:
        await _patch_sheet(
            gm_client, garrik["id"],
            {"subclass": "Champion"},
            class_slug="fighter",
        )


async def test_use_fs_happy_lv9(
    gm_client, gm_ws, garrik_samurai,
):
    """Lv 9 Samurai → advantage on weapon attacks + 5 temp HP."""
    garrik = garrik_samurai
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_fighting_spirit",
        json={"character_id": garrik["id"], "override": True},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["feature"] == "fighting-spirit"
    assert data["advantage_on_weapon_attacks"] is True
    assert data["temp_hp"] == 5
    assert data["fighter_level"] == 9
    await asyncio.sleep(0.3)
    feats = _fs_broadcasts(gm_ws, garrik["id"])
    assert feats
    assert feats[-1]["data"]["temp_hp"] == 5


async def test_use_fs_wrong_subclass(
    gm_client, roster,
):
    """Default Garrik (Champion) → 409."""
    garrik = roster["Garrik Ironside"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_fighting_spirit",
        json={"character_id": garrik["id"], "override": True},
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "wrong_subclass_or_level"


async def test_use_fs_wrong_class(
    gm_client, roster,
):
    """Caelan (Paladin) → 409."""
    caelan = roster["Sir Caelan Lightbringer"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_fighting_spirit",
        json={"character_id": caelan["id"], "override": True},
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "wrong_subclass_or_level"
