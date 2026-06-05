"""v2.99.304 — Arcana Domain Cleric: Arcane Mastery (H.1 deeper, Lv 17).

H.1 Lv 17 Arcana ship (TCE/SCAG extension; extends batch to
12/13 domains). RAW SCAG p.125: add 4 spells (one each of
Lv 6/7/8/9) from any class's spell list as domain spells —
always prepared, count as cleric spells.

v1 announce-only — actual cross-class spell selection is
GM-tracked. No chip — passive list addition.

Tests:
  - Lv 17 happy → added_spell_count 4, levels [6,7,8,9].
  - Wrong subclass → 409.
  - Level gate (Lv 16) → 409.
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


def _am_broadcasts(gm_ws, character_id):
    return [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "arcane-mastery"
        and (m.get("data") or {}).get("character_id") == character_id
    ]


@pytest_asyncio.fixture
async def tavik_arcana_lv17(gm_client, roster):
    """PATCH Tavik to Arcana Domain Lv 17."""
    tavik = roster["Brother Tavik Stonebrow"]
    await _patch_sheet(
        gm_client, tavik["id"],
        {"subclass": "Arcana Domain", "level": 17},
        class_slug="cleric",
    )
    try:
        yield tavik
    finally:
        await _patch_sheet(
            gm_client, tavik["id"],
            {"subclass": "Life Domain", "level": 6},
            class_slug="cleric",
        )


async def test_use_am_happy_lv17(
    gm_client, gm_ws, tavik_arcana_lv17,
):
    """Lv 17 Arcana → 4 spells, Lv 6/7/8/9, any class."""
    tavik = tavik_arcana_lv17
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_arcane_mastery",
        json={"character_id": tavik["id"]},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["added_spell_count"] == 4
    assert data["added_spell_levels"] == [6, 7, 8, 9]
    assert data["source_class"] == "any"
    assert data["cleric_level"] == 17
    await asyncio.sleep(0.3)
    feats = _am_broadcasts(gm_ws, tavik["id"])
    assert feats


async def test_use_am_wrong_subclass(
    gm_client, roster,
):
    """Default Tavik (Life Domain) → 409."""
    tavik = roster["Brother Tavik Stonebrow"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_arcane_mastery",
        json={"character_id": tavik["id"]},
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "wrong_subclass_or_level"


async def test_use_am_level_gate(
    gm_client, roster,
):
    """Arcana Tavik at Lv 16 → 409."""
    tavik = roster["Brother Tavik Stonebrow"]
    await _patch_sheet(
        gm_client, tavik["id"],
        {"subclass": "Arcana Domain", "level": 16},
        class_slug="cleric",
    )
    try:
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/use_arcane_mastery",
            json={"character_id": tavik["id"]},
        )
        assert r.status_code == 409, r.text
        data = r.json()
        assert data.get("error") == "wrong_subclass_or_level"
    finally:
        await _patch_sheet(
            gm_client, tavik["id"],
            {"subclass": "Life Domain", "level": 6},
            class_slug="cleric",
        )
