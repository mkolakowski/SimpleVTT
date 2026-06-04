"""v2.99.230 — Wild Magic Sorcerer: Controlled Chaos (Phase 4).

Phase E.6 Phase 4 of the v2.99.193 phased completion plan. RAW
PHB p.103: "At 14th level, you gain a measure of control over
the surges of your wild magic. Whenever you roll on the Wild
Magic Surge table, you can roll twice and use either number."

v1 ships:
  - /cast_spell post-cast surge hook (v2.99.228): when caster is
    Wild Magic Lv 14+, roll the d100 surge table twice; broadcast
    `wild_magic_surge` with `controlled_chaos: true` +
    `alternatives: [entry1, entry2]`. The first entry remains the
    "primary" slug/name/desc for backward compat.
  - Below Lv 14, the broadcast carries
    `controlled_chaos: false` + `alternatives: [single_entry]`.

Uses the TEST_MODE-only `_force_surge_d20: 1` body override on
/cast_spell so the d20 lands on 1 deterministically.

Tests:
  - Lv 14 Wild Magic Zara → broadcast `controlled_chaos: true`
    + alternatives length 2.
  - Lv 5 Wild Magic Zara (regression) → broadcast
    `controlled_chaos: false` + alternatives length 1.
"""
import asyncio
import pytest_asyncio

from .conftest import CAMPAIGN_ID


ZARA_MAGIC_MISSILE_INDEX = 7


async def _patch_sheet(gm_client, char_id, fields, class_slug=None):
    body = dict(fields)
    if class_slug:
        body["class_slug"] = class_slug
    r = await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-fields",
        json=body,
    )
    assert r.status_code == 200, r.text


def _surge_broadcasts(gm_ws, character_id):
    return [
        m for m in gm_ws.buffered("wild_magic_surge")
        if (m.get("data") or {}).get("character_id") == character_id
    ]


@pytest_asyncio.fixture
async def zara_wild_magic_lv14(gm_client, roster):
    """PATCH Zara to Wild Magic + Lv 14 for Controlled Chaos."""
    zara = roster["Zara Emberfire"]
    await _patch_sheet(
        gm_client, zara["id"],
        {"subclass": "Wild Magic", "level": 14},
        class_slug="sorcerer",
    )
    try:
        yield zara
    finally:
        await _patch_sheet(
            gm_client, zara["id"],
            {"subclass": "Draconic Bloodline", "level": 5},
            class_slug="sorcerer",
        )


@pytest_asyncio.fixture
async def zara_wild_magic_lv5(gm_client, roster):
    """PATCH Zara to Wild Magic + default Lv 5 (no Controlled Chaos)."""
    zara = roster["Zara Emberfire"]
    await _patch_sheet(
        gm_client, zara["id"],
        {"subclass": "Wild Magic"},
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


async def test_controlled_chaos_rolls_twice_at_lv14(
    gm_client, gm_ws, zara_wild_magic_lv14,
):
    """Lv 14 Wild Magic Zara casts Magic Missile with forced
    d20=1 → broadcast carries controlled_chaos: true +
    alternatives length 2."""
    zara = zara_wild_magic_lv14
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
        json={
            "character_id": zara["id"],
            "spell_index": ZARA_MAGIC_MISSILE_INDEX,
            "slot_level": 1,
            "class_slug": "sorcerer",
            "override": True,
            "_force_surge_d20": 1,
        },
    )
    assert r.status_code == 200, r.text
    await asyncio.sleep(0.4)
    feats = _surge_broadcasts(gm_ws, zara["id"])
    assert feats, "expected wild_magic_surge broadcast"
    data = feats[-1]["data"]
    assert data.get("controlled_chaos") is True
    alts = data.get("alternatives") or []
    assert len(alts) == 2, alts
    for entry in alts:
        assert entry.get("slug")
        assert entry.get("name")
        assert 1 <= int(entry.get("d100") or 0) <= 100


async def test_controlled_chaos_single_entry_at_lv5(
    gm_client, gm_ws, zara_wild_magic_lv5,
):
    """Lv 5 Wild Magic Zara → broadcast carries
    controlled_chaos: false + alternatives length 1.
    Regression for the v2.99.230 backward-compat shape."""
    zara = zara_wild_magic_lv5
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
        json={
            "character_id": zara["id"],
            "spell_index": ZARA_MAGIC_MISSILE_INDEX,
            "slot_level": 1,
            "class_slug": "sorcerer",
            "override": True,
            "_force_surge_d20": 1,
        },
    )
    assert r.status_code == 200, r.text
    await asyncio.sleep(0.4)
    feats = _surge_broadcasts(gm_ws, zara["id"])
    assert feats, "expected wild_magic_surge broadcast"
    data = feats[-1]["data"]
    assert data.get("controlled_chaos") is False
    alts = data.get("alternatives") or []
    assert len(alts) == 1, alts
