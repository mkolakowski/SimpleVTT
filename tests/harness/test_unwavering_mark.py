"""v2.99.375 — Cavalier Fighter: Unwavering Mark (G Fighter sweep #6, Lv 3+, XGE).

Phase G Fighter martial archetype sweep ship #6 — Cavalier opens.
RAW XGE p.30: when you hit a creature with a melee weapon attack,
mark it until the end of your next turn — while within 5 ft it has
disadvantage on attacks not aimed at you, and if it harms an ally
you can make a bonus-action melee attack against it with
advantage, dealing extra damage = half your fighter level.

v1 announce-only — the mark tracking, disadvantage, and punishing
attack are GM-tracked. The punish bonus is computed server-side.
No separate action cost.

Garrik Ironside (Fighter, PATCHed to Cavalier Lv 9) is the demo
fixture (punish bonus = 4).

Tests:
  - Lv 9 happy: disadvantage flag True, punish bonus 4.
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


def _um_broadcasts(gm_ws, character_id):
    return [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "unwavering-mark"
        and (m.get("data") or {}).get("character_id") == character_id
    ]


@pytest_asyncio.fixture
async def garrik_cavalier(gm_client, roster):
    """PATCH Garrik to Cavalier; restore to Champion on teardown."""
    garrik = roster["Garrik Ironside"]
    await _patch_sheet(
        gm_client, garrik["id"],
        {"subclass": "Cavalier"},
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


async def test_use_um_happy_lv9(
    gm_client, gm_ws, garrik_cavalier,
):
    """Lv 9 Cavalier → disadvantage flag + punish bonus 4."""
    garrik = garrik_cavalier
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_unwavering_mark",
        json={"character_id": garrik["id"]},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["feature"] == "unwavering-mark"
    assert data["target_attack_disadvantage"] is True
    assert data["punish_bonus_damage"] == 4  # half fighter level 9
    assert data["fighter_level"] == 9
    await asyncio.sleep(0.3)
    feats = _um_broadcasts(gm_ws, garrik["id"])
    assert feats
    assert feats[-1]["data"]["punish_bonus_damage"] == 4


async def test_use_um_wrong_subclass(
    gm_client, roster,
):
    """Default Garrik (Champion) → 409."""
    garrik = roster["Garrik Ironside"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_unwavering_mark",
        json={"character_id": garrik["id"]},
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "wrong_subclass_or_level"


async def test_use_um_wrong_class(
    gm_client, roster,
):
    """Caelan (Paladin) → 409."""
    caelan = roster["Sir Caelan Lightbringer"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_unwavering_mark",
        json={"character_id": caelan["id"]},
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "wrong_subclass_or_level"
