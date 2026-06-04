"""v2.99.160 — Twinned Spell metamagic pending-buff wiring.

Pre-v2.99.160 /use_metamagic_twinned_spell was announce-only —
the SP was decremented + a feature_used broadcast fired, but
the second-target cast was GM-adjudicated manually.

v2.99.160 layers the pending-buff scaffolding on top (mirror of
v2.99.159 Distant Spell):
  - The endpoint installs a `metamagic-twinned-pending` buff on
    the caster (effects.twin_targets=True + spell_level +
    sp_paid).
  - /cast_spell consumes the buff one-shot at the start of the
    cast cycle.

What's NOT in this commit (filed):
  - Auto-routing to the second target with the same damage roll
    + save DC. v1 still requires the player to follow up with a
    second /cast_spell call manually.

Tests:
  - declaring Twinned Spell installs the pending buff on Zara
  - the pending buff is consumed when /cast_spell fires
  - endpoint return shape (sp_cost matches spell_level, cast_id
    present) preserved end-to-end
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID


def _mkc(cid, char_id=None, name="X"):
    return {
        "id": cid,
        "char_id": char_id,
        "name": name,
        "initiative": 10,
        "hp_current": 50, "hp_max": 50,
        "buffs": [],
        "economy": {"action": False, "bonus": False, "reaction": False,
                    "movement": 0},
    }


async def _seed_battle(gm_client, combatants):
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": combatants, "turn_index": 0, "round": 1,
              "active": True},
    )


async def _get_buff_keys(gm_client, char_id):
    resp = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/buffs",
    )
    return {(b or {}).get("key") for b in resp.json().get("buffs") or []}


@pytest_asyncio.fixture
async def zara_rested(gm_client, roster):
    """Long-rest Zara so SP is fresh."""
    zara = roster["Zara Emberfire"]
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{zara['id']}/rest",
        json={"type": "long"},
    )
    return zara


async def test_twinned_spell_installs_pending_buff(
    gm_client, zara_rested,
):
    """Calling /use_metamagic_twinned_spell for a L2 spell
    installs the `metamagic-twinned-pending` buff on Zara's
    combatant. Needs a battle for the buff install to land.
    """
    zara = zara_rested
    zara_tok = f"tok_tw_install_{zara['id']}"
    await _seed_battle(gm_client, [
        _mkc(zara_tok, zara["id"], name=zara["name"]),
    ])
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_metamagic_twinned_spell",
        json={"character_id": zara["id"], "spell_level": 2},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["sp_cost"] == 2  # L2 spell → 2 SP
    keys = await _get_buff_keys(gm_client, zara["id"])
    assert "metamagic-twinned-pending" in keys


async def test_twinned_pending_consumed_by_cast_spell(
    gm_client, zara_rested,
):
    """After declaring Twinned Spell, the next /cast_spell call
    consumes the pending buff. The cast itself may succeed or
    fail; we just verify the buff is dropped.
    """
    zara = zara_rested
    zara_tok = f"tok_tw_consume_{zara['id']}"
    await _seed_battle(gm_client, [
        _mkc(zara_tok, zara["id"], name=zara["name"]),
    ])
    # Arm Twinned Spell for a cantrip (1 SP).
    arm = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_metamagic_twinned_spell",
        json={"character_id": zara["id"], "spell_level": 0},
    )
    assert arm.status_code == 200, arm.text
    pre = await _get_buff_keys(gm_client, zara["id"])
    assert "metamagic-twinned-pending" in pre
    # Cast a spell — the buff is consumed regardless of cast outcome.
    cast = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
        json={
            "character_id": zara["id"],
            "spell_index": 0,
            "override": True,
        },
    )
    assert cast.status_code in (200, 400, 409), cast.text
    post = await _get_buff_keys(gm_client, zara["id"])
    assert "metamagic-twinned-pending" not in post


async def test_twinned_endpoint_shape_preserved(
    gm_client, zara_rested,
):
    """Backward-compatibility check: existing announce-only
    response fields (sp_cost, sp_remaining, sp_max, spell_level,
    cast_id) are still present and accurate.
    """
    zara = zara_rested
    zara_tok = f"tok_tw_shape_{zara['id']}"
    await _seed_battle(gm_client, [
        _mkc(zara_tok, zara["id"], name=zara["name"]),
    ])
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_metamagic_twinned_spell",
        json={"character_id": zara["id"], "spell_level": 3},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["sp_cost"] == 3  # L3 → 3 SP
    assert data["spell_level"] == 3
    assert "cast_id" in data
    assert data["sp_remaining"] == data["sp_max"] - 3
