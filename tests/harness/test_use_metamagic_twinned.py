"""v2.99.33 — Metamagic Twinned Spell (Sorcerer Lv 3+).

RAW (PHB p.102): "When you Cast a Spell that targets only one
creature and doesn't have a range of self, you can spend a number
of sorcery points equal to the spell's level to target a second
creature in range with the same spell (1 sorcery point if the
spell is a cantrip)."

v1 announce-only ship — matches the Quickened Spell precedent
(v2.6.0). Server decrements SP by `max(1, spell_level)` + broadcasts
the trigger. The actual second-target cast is performed manually
by the player via a second /cast_spell. Auto-route is filed for
a future commit.

Tests:
- happy L1 spell (Magic Missile): SP cost = 1, decrements + broadcast.
- happy L3 spell (Fireball): SP cost = 3.
- happy cantrip (Fire Bolt): spell_level=0 → SP cost = 1.
- error: not enough SP for the spell level.
- error: wrong class.
- error: level too low (Sorcerer Lv 1-2 can't use metamagic).
- error: spell_level out of range.
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID


@pytest_asyncio.fixture
async def zara_rested(gm_client, roster):
    zara = roster["Zara Emberfire"]
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{zara['id']}/rest",
        json={"type": "long"},
    )
    return zara


async def test_twinned_l1_costs_1_sp(gm_client, gm_ws, zara_rested):
    """Zara arms Twinned for an L1 spell. SP cost = 1. Decrements
    + broadcasts feature_used + resource_update.
    """
    zara = zara_rested
    gm_ws.mark()
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_metamagic_twinned_spell",
        json={"character_id": zara["id"], "spell_level": 1},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["sp_cost"] == 1
    assert data["spell_level"] == 1
    assert data["sp_max"] == data["sp_remaining"] + 1, (
        f"expected sp_remaining = sp_max - 1; got {data}"
    )

    import asyncio as _asy
    await _asy.sleep(0.2)
    msgs = gm_ws.buffered("feature_used")
    twinned = [
        m for m in msgs
        if (m.get("data") or {}).get("source") == "metamagic-twinned-spell"
        and (m.get("data") or {}).get("character_id") == zara["id"]
    ]
    assert twinned, (
        f"expected feature_used(source=metamagic-twinned-spell); "
        f"buffered: {[(m.get('type'), (m.get('data') or {}).get('source')) for m in gm_ws.buffered()]}"
    )


async def test_twinned_l3_costs_3_sp(gm_client, gm_ws, zara_rested):
    """Twinned at L3 → SP cost = 3."""
    zara = zara_rested
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_metamagic_twinned_spell",
        json={"character_id": zara["id"], "spell_level": 3},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["sp_cost"] == 3
    assert data["spell_level"] == 3


async def test_twinned_cantrip_costs_1_sp(gm_client, gm_ws, zara_rested):
    """Twinned at cantrip (spell_level=0) → SP cost = 1 (RAW)."""
    zara = zara_rested
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_metamagic_twinned_spell",
        json={"character_id": zara["id"], "spell_level": 0},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["sp_cost"] == 1
    assert data["spell_level"] == 0


async def test_twinned_not_enough_points(gm_client, zara_rested):
    """Zara has 5 SP at Lv 5. Asking for Twinned at L5 → costs 5.
    Then asking for another at L1 → not enough SP. 409.
    """
    zara = zara_rested
    # Drain to 0 SP.
    for _ in range(5):
        resp = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/use_metamagic_empowered_spell",
            json={"character_id": zara["id"]},
        )
        if resp.status_code != 200:
            break
    # Now ask for Twinned at L1.
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_metamagic_twinned_spell",
        json={"character_id": zara["id"], "spell_level": 1},
    )
    assert resp.status_code == 409, resp.text
    body = resp.json()
    assert body["error"] == "not_enough_points"
    assert body["required"] == 1


async def test_twinned_wrong_class(gm_client, roster):
    """Tavik (Cleric) → 409 wrong_class."""
    tavik = roster["Brother Tavik Stonebrow"]
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_metamagic_twinned_spell",
        json={"character_id": tavik["id"], "spell_level": 1},
    )
    assert resp.status_code == 409, resp.text
    body = resp.json()
    assert body["error"] == "wrong_class"


async def test_twinned_spell_level_out_of_range(gm_client, zara_rested):
    """spell_level > 5 → 400."""
    zara = zara_rested
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_metamagic_twinned_spell",
        json={"character_id": zara["id"], "spell_level": 6},
    )
    assert resp.status_code == 400, resp.text
