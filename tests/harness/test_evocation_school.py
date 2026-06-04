"""v2.99.225 — Evocation Wizard features: Sculpt Spells + Empowered Evocation.

Phase E.7 of the v2.99.193 phased completion plan. RAW PHB
p.117:
  - Sculpt Spells (Lv 2): on evocation cast, protect 1 + spell
    level chosen creatures from save-half damage.
  - Empowered Evocation (Lv 10): add INT mod to one damage roll
    of a wizard evocation spell.

v1 ships:
  - /use_sculpt_spells: announce, returns protected_count =
    1 + spell_level.
  - /use_empowered_evocation: announce, returns INT mod.

Thalindra Moonwhisper (Wizard School of Evocation Lv 7) is the
demo fixture. The Empowered Evocation test PATCHes her Lv 7 → 10.

Tests:
  - Sculpt Spells Lv 2 happy path (Thalindra at Lv 7 ≥ 2).
  - Sculpt Spells bad spell_level (0) → 400.
  - Sculpt Spells wrong-subclass gate (Magnus / Conjuration would
    work but he isn't a wizard — use Krieger, wrong class).
  - Empowered Evocation at Lv 10 happy path.
  - Empowered Evocation level gate (Lv 7).
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


def _sculpt_broadcasts(gm_ws, character_id):
    return [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "sculpt-spells"
        and (m.get("data") or {}).get("character_id") == character_id
    ]


def _empowered_broadcasts(gm_ws, character_id):
    return [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "empowered-evocation"
        and (m.get("data") or {}).get("character_id") == character_id
    ]


async def test_use_sculpt_spells_lv3_fireball(
    gm_client, gm_ws, roster,
):
    """Thalindra Lv 7, level-3 evocation → protected = 4 + broadcast."""
    thal = roster["Thalindra Moonwhisper"]
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_sculpt_spells",
        json={
            "character_id": thal["id"],
            "spell_level": 3,
        },
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["protected_count"] == 4
    assert data["spell_level"] == 3
    await asyncio.sleep(0.3)
    feats = _sculpt_broadcasts(gm_ws, thal["id"])
    assert feats
    assert feats[-1]["data"]["protected_count"] == 4


async def test_use_sculpt_spells_bad_level(
    gm_client, roster,
):
    """spell_level 0 → 400."""
    thal = roster["Thalindra Moonwhisper"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_sculpt_spells",
        json={
            "character_id": thal["id"],
            "spell_level": 0,
        },
    )
    assert r.status_code == 400, r.text


async def test_use_sculpt_spells_wrong_class(
    gm_client, roster,
):
    """Krieger (Barbarian) → 409 wrong_subclass_or_level."""
    krieger = roster["Krieger Stonefist"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_sculpt_spells",
        json={
            "character_id": krieger["id"],
            "spell_level": 3,
        },
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "wrong_subclass_or_level"


async def test_use_empowered_evocation_at_lv10(
    gm_client, gm_ws, roster,
):
    """Thalindra PATCH'd to Lv 10 → +INT mod broadcast."""
    thal = roster["Thalindra Moonwhisper"]
    pre_level = 7
    await _patch_sheet(
        gm_client, thal["id"], {"level": 10},
        class_slug="wizard",
    )
    try:
        gm_ws.mark()
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/use_empowered_evocation",
            json={"character_id": thal["id"]},
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["int_mod"] == 3  # INT 16 → +3
        await asyncio.sleep(0.3)
        feats = _empowered_broadcasts(gm_ws, thal["id"])
        assert feats
        assert feats[-1]["data"]["int_mod"] == 3
    finally:
        await _patch_sheet(
            gm_client, thal["id"], {"level": pre_level},
            class_slug="wizard",
        )


async def test_use_empowered_evocation_level_gate(
    gm_client, roster,
):
    """Control: Thalindra at Lv 7 → 409 wrong_subclass_or_level."""
    thal = roster["Thalindra Moonwhisper"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_empowered_evocation",
        json={"character_id": thal["id"]},
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "wrong_subclass_or_level"
