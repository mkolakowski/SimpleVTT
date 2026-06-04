"""v2.99.228 — Wild Magic Sorcerer: Wild Magic Surge auto-roll (Phase 2).

Phase E.6 Phase 2 of the v2.99.193 phased completion plan. RAW
PHB p.103: "When you cast a sorcerer spell of 1st level or
higher, the DM can have you roll a d20 immediately after. If you
roll a 1, roll on the Wild Magic Surge table to create a random
magical effect."

v1 ships:
  - /cast_spell post-cast hook: on every Lv 1+ sorcerer-class
    cast by a Wild Magic Sorcerer, roll d20. On 1: roll d100,
    map to table entry, broadcast `wild_magic_surge` + refill
    `sheet.tides_of_chaos_uses` to 1 (RAW: surge before regaining
    Tides also refills Tides).

The harness uses the TEST_MODE-only `_force_surge_d20` body
override on /cast_spell to deterministically force the d20 roll
without seed-discovery dance.

Tests:
  - Wild Magic Sorcerer + Lv 1 sorcerer spell + forced d20=1
    → wild_magic_surge broadcast with table entry.
  - Tides of Chaos refilled after surge triggers.
  - Forced d20=20 → no surge.
  - Cantrip (spell_level 0) doesn't trigger even with forced d20=1.
  - Non-Wild-Magic Sorcerer cast doesn't trigger.

Zara Emberfire (Sorcerer Draconic Bloodline Lv 5 default) is
the demo fixture. Tests PATCH her subclass to "Wild Magic".
Magic Missile at index 7, Fire Bolt at 0 (cantrip).
"""
import asyncio
import pytest_asyncio

from .conftest import CAMPAIGN_ID


ZARA_FIRE_BOLT_INDEX = 0       # cantrip
ZARA_MAGIC_MISSILE_INDEX = 7   # Lv 1


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
async def zara_wild_magic_lv5(gm_client, roster):
    """PATCH Zara's subclass to 'Wild Magic'. Restore on teardown."""
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


async def test_wild_magic_surge_fires_on_d20_one(
    gm_client, gm_ws, zara_wild_magic_lv5,
):
    """Wild Magic Zara casts Magic Missile (Lv 1) with forced
    d20=1 → wild_magic_surge broadcast with table entry."""
    zara = zara_wild_magic_lv5
    await _patch_sheet(
        gm_client, zara["id"], {"tides_of_chaos_uses": 0},
    )
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
    assert feats, "expected wild_magic_surge broadcast; saw none"
    surge = feats[-1]["data"]
    assert surge.get("slug")
    assert surge.get("name")
    assert surge.get("desc")
    assert 1 <= int(surge.get("d100") or 0) <= 100
    assert surge.get("tides_refilled") is True


async def test_wild_magic_surge_refills_tides_of_chaos(
    gm_client, zara_wild_magic_lv5,
):
    """After surge fires, sheet.tides_of_chaos_uses == 1 even if
    it was 0 pre-cast (RAW: surge before regaining Tides also
    refills Tides)."""
    zara = zara_wild_magic_lv5
    await _patch_sheet(
        gm_client, zara["id"], {"tides_of_chaos_uses": 0},
    )
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
    await asyncio.sleep(0.3)
    # /use_tides_of_chaos should succeed (counter refilled to 1).
    use = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_tides_of_chaos",
        json={"character_id": zara["id"]},
    )
    assert use.status_code == 200, use.text


async def test_wild_magic_no_surge_on_d20_high(
    gm_client, gm_ws, zara_wild_magic_lv5,
):
    """Forced d20=20 → no surge broadcast (only nat-1 triggers)."""
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
            "_force_surge_d20": 20,
        },
    )
    assert r.status_code == 200, r.text
    await asyncio.sleep(0.3)
    feats = _surge_broadcasts(gm_ws, zara["id"])
    assert not feats, "d20=20 should not trigger surge"


async def test_wild_magic_cantrip_no_surge(
    gm_client, gm_ws, zara_wild_magic_lv5,
):
    """Cantrip (spell_level 0) doesn't trigger even with forced
    d20=1 (RAW: only "1st level or higher" sorcerer spells)."""
    zara = zara_wild_magic_lv5
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
        json={
            "character_id": zara["id"],
            "spell_index": ZARA_FIRE_BOLT_INDEX,
            "slot_level": 0,
            "class_slug": "sorcerer",
            "override": True,
            "_force_surge_d20": 1,
        },
    )
    assert r.status_code == 200, r.text
    await asyncio.sleep(0.3)
    feats = _surge_broadcasts(gm_ws, zara["id"])
    assert not feats, "cantrip should not trigger surge"


async def test_wild_magic_non_subclass_no_surge(
    gm_client, gm_ws, roster,
):
    """Default Draconic Bloodline Zara — no surge even with
    forced d20=1."""
    zara = roster["Zara Emberfire"]
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
    await asyncio.sleep(0.3)
    feats = _surge_broadcasts(gm_ws, zara["id"])
    assert not feats, "non-Wild-Magic sorcerer should not trigger surge"
