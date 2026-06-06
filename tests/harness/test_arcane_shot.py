"""v2.99.374 — Arcane Archer Fighter: Arcane Shot (G Fighter sweep #5, Lv 3+, XGE).

Phase G Fighter martial archetype sweep ship #5 — Arcane Archer
opens.
RAW XGE p.28: once per turn when you fire an arrow as part of the
Attack action, apply an Arcane Shot option (Banishing, Beguiling,
Bursting, Enfeebling, Grasping, Piercing, Seeking, Shadow). Save
DC = 8 + proficiency bonus + DEX modifier. 2 uses per short/long
rest.

v1 announce-only — the attack/save resolution + 2-uses-per-rest
limit are GM-tracked. The bonus damage + save DC are computed
server-side. No separate action cost (a rider on the attack).

Garrik Ironside (Fighter, PATCHed to Arcane Archer Lv 9) is the
demo fixture.

Tests:
  - Lv 9 happy (default bursting): 2d6 force, save DC computed.
  - Lv 9 happy (banishing): no damage dice, CHA save.
  - Wrong subclass (default Champion) → 409.
  - Invalid arrow → 400.
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


def _as_broadcasts(gm_ws, character_id):
    return [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "arcane-shot"
        and (m.get("data") or {}).get("character_id") == character_id
    ]


@pytest_asyncio.fixture
async def garrik_arcane_archer(gm_client, roster):
    """PATCH Garrik to Arcane Archer; restore to Champion on teardown."""
    garrik = roster["Garrik Ironside"]
    await _patch_sheet(
        gm_client, garrik["id"],
        {"subclass": "Arcane Archer"},
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


async def test_use_as_happy_bursting(
    gm_client, gm_ws, garrik_arcane_archer,
):
    """Lv 9 Arcane Archer, default → Bursting Arrow, 2d6 force."""
    garrik = garrik_arcane_archer
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_arcane_shot",
        json={"character_id": garrik["id"]},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["feature"] == "arcane-shot"
    assert data["arrow"] == "bursting"
    assert data["damage_dice"] == "2d6"
    assert data["damage_type"] == "force"
    assert 2 <= data["bonus_damage"] <= 12
    assert data["save_dc"] >= 8
    assert data["fighter_level"] == 9
    await asyncio.sleep(0.3)
    feats = _as_broadcasts(gm_ws, garrik["id"])
    assert feats
    assert feats[-1]["data"]["arrow"] == "bursting"


async def test_use_as_happy_banishing(
    gm_client, garrik_arcane_archer,
):
    """Banishing Arrow → no damage dice, CHA save."""
    garrik = garrik_arcane_archer
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_arcane_shot",
        json={"character_id": garrik["id"], "arrow": "banishing"},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["arrow"] == "banishing"
    assert data["damage_dice"] is None
    assert data["bonus_damage"] == 0
    assert data["save"] == "cha"


async def test_use_as_wrong_subclass(
    gm_client, roster,
):
    """Default Garrik (Champion) → 409."""
    garrik = roster["Garrik Ironside"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_arcane_shot",
        json={"character_id": garrik["id"]},
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "wrong_subclass_or_level"


async def test_use_as_invalid_arrow(
    gm_client, garrik_arcane_archer,
):
    """Invalid arrow → 400."""
    garrik = garrik_arcane_archer
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_arcane_shot",
        json={"character_id": garrik["id"], "arrow": "explosive"},
    )
    assert r.status_code == 400, r.text
