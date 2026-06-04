"""v2.99.231 — Wild Magic Sorcerer: Spell Bombardment (Phase 5).

Phase E.6 Phase 5 (FINAL) of the v2.99.193 phased completion
plan. RAW PHB p.103: "Beginning at 18th level, the harmful
energy of your spells intensifies. When you roll damage for a
spell and roll the highest number possible on any of the dice,
choose one of those dice, roll it again and add that roll to
the damage. You can use the feature only once per turn."

v1 ships:
  - /use_spell_bombardment: validates Wild Magic Lv 18+ + once-
    per-turn flag (combatant economy `spell_bombardment_used`,
    mirror of Colossus Slayer's flag); rolls 1d<die_size>;
    marks flag; broadcasts.

Zara Emberfire (Sorcerer Draconic Bloodline Lv 5 default).
Tests PATCH her subclass to "Wild Magic" + level to 18 and seed
her in a battle so the economy flag has a home.

Tests:
  - Happy path d8 → roll in 1..8, broadcast fired.
  - Once-per-turn flag: second invocation same turn → 409.
  - Bad die_size (5) → 400.
  - Wrong subclass (Draconic) → 409.
  - Level gate (Lv 17) → 409.
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


def _sb_broadcasts(gm_ws, character_id):
    return [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "spell-bombardment"
        and (m.get("data") or {}).get("character_id") == character_id
    ]


@pytest_asyncio.fixture
async def zara_wild_magic_lv18(gm_client, roster):
    """PATCH Zara to Wild Magic + Lv 18 + seed in a fresh battle
    so the per-turn flag has somewhere to live."""
    zara = roster["Zara Emberfire"]
    await _patch_sheet(
        gm_client, zara["id"],
        {"subclass": "Wild Magic", "level": 18},
        class_slug="sorcerer",
    )
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": [
            {"id": f"tok_sb_{zara['id']}",
             "char_id": zara["id"], "name": zara["name"],
             "initiative": 12, "hp_current": 90, "hp_max": 90,
             "buffs": [],
             "economy": {"action": False, "bonus": False,
                         "reaction": False, "movement": 0}},
        ], "turn_index": 0, "round": 1, "active": True},
    )
    try:
        yield zara
    finally:
        await _patch_sheet(
            gm_client, zara["id"],
            {"subclass": "Draconic Bloodline", "level": 5},
            class_slug="sorcerer",
        )


async def test_use_spell_bombardment_happy(
    gm_client, gm_ws, zara_wild_magic_lv18,
):
    """Lv 18 Wild Magic Zara → 1d8 reroll in 1..8 + broadcast."""
    zara = zara_wild_magic_lv18
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_spell_bombardment",
        json={"character_id": zara["id"], "die_size": 8},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["die_size"] == 8
    assert 1 <= data["extra_damage"] <= 8
    await asyncio.sleep(0.3)
    feats = _sb_broadcasts(gm_ws, zara["id"])
    assert feats


async def test_use_spell_bombardment_once_per_turn(
    gm_client, zara_wild_magic_lv18,
):
    """First call succeeds; second call same turn → 409."""
    zara = zara_wild_magic_lv18
    r1 = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_spell_bombardment",
        json={"character_id": zara["id"], "die_size": 10},
    )
    assert r1.status_code == 200, r1.text
    r2 = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_spell_bombardment",
        json={"character_id": zara["id"], "die_size": 10},
    )
    assert r2.status_code == 409, r2.text
    data = r2.json()
    assert data.get("error") == "once_per_turn"


async def test_use_spell_bombardment_bad_die_size(
    gm_client, zara_wild_magic_lv18,
):
    """die_size=5 → 400."""
    zara = zara_wild_magic_lv18
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_spell_bombardment",
        json={"character_id": zara["id"], "die_size": 5},
    )
    assert r.status_code == 400, r.text


async def test_use_spell_bombardment_wrong_subclass(
    gm_client, roster,
):
    """Default Draconic Bloodline → 409."""
    zara = roster["Zara Emberfire"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_spell_bombardment",
        json={"character_id": zara["id"], "die_size": 8},
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "wrong_subclass_or_level"


async def test_use_spell_bombardment_level_gate(
    gm_client, roster,
):
    """Wild Magic at Lv 17 (not 18+) → 409."""
    zara = roster["Zara Emberfire"]
    await _patch_sheet(
        gm_client, zara["id"],
        {"subclass": "Wild Magic", "level": 17},
        class_slug="sorcerer",
    )
    try:
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/use_spell_bombardment",
            json={"character_id": zara["id"], "die_size": 8},
        )
        assert r.status_code == 409, r.text
        data = r.json()
        assert data.get("error") == "wrong_subclass_or_level"
    finally:
        await _patch_sheet(
            gm_client, zara["id"],
            {"subclass": "Draconic Bloodline", "level": 5},
            class_slug="sorcerer",
        )
