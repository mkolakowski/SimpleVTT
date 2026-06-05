"""v2.99.297 — Death Domain Cleric: Improved Reaper (H.1 deeper, Lv 17).

H.1 Lv 17 Death ship. RAW DMG p.97: 1st-5th level necromancy
spells that target one creature can target two creatures
within range + within 5 ft of each other.

v1 announce-only — the dual-target option is GM-tracked via
the player invoking the spell with two targets. No chip —
passive permanent.

Tests:
  - Lv 17 happy → max_targets 2, school necromancy, spell
    levels 1-5.
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


def _ir_broadcasts(gm_ws, character_id):
    return [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "improved-reaper"
        and (m.get("data") or {}).get("character_id") == character_id
    ]


@pytest_asyncio.fixture
async def tavik_death_lv17(gm_client, roster):
    """PATCH Tavik to Death Domain Lv 17."""
    tavik = roster["Brother Tavik Stonebrow"]
    await _patch_sheet(
        gm_client, tavik["id"],
        {"subclass": "Death Domain", "level": 17},
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


async def test_use_ir_happy_lv17(
    gm_client, gm_ws, tavik_death_lv17,
):
    """Lv 17 Death → necromancy Lv 1-5 → 2 targets, 5 ft apart."""
    tavik = tavik_death_lv17
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_improved_reaper",
        json={"character_id": tavik["id"]},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["max_targets"] == 2
    assert data["max_target_separation_ft"] == 5
    assert data["school"] == "necromancy"
    assert data["min_spell_level"] == 1
    assert data["max_spell_level"] == 5
    assert data["cleric_level"] == 17
    await asyncio.sleep(0.3)
    feats = _ir_broadcasts(gm_ws, tavik["id"])
    assert feats


async def test_use_ir_wrong_subclass(
    gm_client, roster,
):
    """Default Tavik (Life Domain) → 409."""
    tavik = roster["Brother Tavik Stonebrow"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_improved_reaper",
        json={"character_id": tavik["id"]},
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "wrong_subclass_or_level"


async def test_use_ir_level_gate(
    gm_client, roster,
):
    """Death Tavik at Lv 16 → 409."""
    tavik = roster["Brother Tavik Stonebrow"]
    await _patch_sheet(
        gm_client, tavik["id"],
        {"subclass": "Death Domain", "level": 16},
        class_slug="cleric",
    )
    try:
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/use_improved_reaper",
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
