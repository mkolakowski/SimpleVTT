"""v2.99.34 — Metamagic Distant Spell (Sorcerer Lv 3+).

RAW (PHB p.102): "When you Cast a Spell that has a range of 5 feet
or greater, you can spend 1 sorcery point to double the range of
the spell. When you Cast a Spell that has a range of touch, you
can spend 1 sorcery point to make the range of the spell 30 feet."

v1 announce-only ship — matches Twinned (v2.99.33) + Quickened
(v2.6.0). Server decrements 1 SP + broadcasts the trigger. The
actual range extension is applied by the GM manually at the next
cast.

Tests:
- happy: SP cost 1, decrements + broadcast.
- error: not enough SP.
- error: wrong class.
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


async def test_distant_costs_1_sp_and_broadcasts(
    gm_client, gm_ws, zara_rested,
):
    """Zara declares Distant Spell. SP cost = 1. Resource decrements +
    feature_used(source=metamagic-distant-spell) broadcast fires.
    """
    zara = zara_rested
    gm_ws.mark()
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_metamagic_distant_spell",
        json={"character_id": zara["id"]},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["sp_cost"] == 1
    assert data["sp_remaining"] == data["sp_max"] - 1

    import asyncio as _asy
    await _asy.sleep(0.2)
    msgs = gm_ws.buffered("feature_used")
    distant = [
        m for m in msgs
        if (m.get("data") or {}).get("source") == "metamagic-distant-spell"
        and (m.get("data") or {}).get("character_id") == zara["id"]
    ]
    assert distant, (
        f"expected feature_used(source=metamagic-distant-spell); "
        f"buffered: {[(m.get('type'), (m.get('data') or {}).get('source')) for m in gm_ws.buffered()]}"
    )


async def test_distant_not_enough_points(gm_client, zara_rested):
    """Drain Zara's SP via Empowered (1 SP each, 5 SP pool). Then
    Distant returns 409 not_enough_points.
    """
    zara = zara_rested
    for _ in range(5):
        await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/use_metamagic_empowered_spell",
            json={"character_id": zara["id"]},
        )
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_metamagic_distant_spell",
        json={"character_id": zara["id"]},
    )
    assert resp.status_code == 409, resp.text
    body = resp.json()
    assert body["error"] == "not_enough_points"


async def test_distant_wrong_class(gm_client, roster):
    """Tavik (Cleric) → 409 wrong_class."""
    tavik = roster["Brother Tavik Stonebrow"]
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_metamagic_distant_spell",
        json={"character_id": tavik["id"]},
    )
    assert resp.status_code == 409, resp.text
    body = resp.json()
    assert body["error"] == "wrong_class"
