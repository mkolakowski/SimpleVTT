"""v2.99.161 — Extended Spell metamagic pending-buff wiring.

Pre-v2.99.161 /use_metamagic_extended_spell was announce-only —
SP decremented + broadcast fired but duration extension was
GM-adjudicated.

v2.99.161 layers the pending-buff scaffolding on top (mirror of
v2.99.159 Distant + v2.99.160 Twinned):
  - The endpoint installs a `metamagic-extended-pending` buff on
    the caster (effects.extend_duration=True,
    effects.duration_multiplier=2,
    effects.duration_cap_rounds=14400).
  - /cast_spell consumes the buff one-shot at the start of the
    cast cycle.

What's NOT in this commit (filed):
  - Actual duration-doubling on the installed buff at cast time.
    Would need `_install_buff` to consult the source_char_id's
    pending buff before stamping duration_rounds / duration_max.

Tests:
  - declaring Extended Spell installs the pending buff on Zara
  - the pending buff is consumed when /cast_spell fires
  - endpoint return shape (sp_cost=1, sp_remaining, cast_id)
    preserved
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


async def test_extended_spell_installs_pending_buff(
    gm_client, zara_rested,
):
    """Calling /use_metamagic_extended_spell installs the
    `metamagic-extended-pending` buff on Zara's combatant.
    """
    zara = zara_rested
    zara_tok = f"tok_ext_install_{zara['id']}"
    await _seed_battle(gm_client, [
        _mkc(zara_tok, zara["id"], name=zara["name"]),
    ])
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_metamagic_extended_spell",
        json={"character_id": zara["id"]},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["sp_cost"] == 1
    keys = await _get_buff_keys(gm_client, zara["id"])
    assert "metamagic-extended-pending" in keys


async def test_extended_pending_consumed_by_cast_spell(
    gm_client, zara_rested,
):
    """After declaring Extended Spell, the next /cast_spell call
    consumes the pending buff.
    """
    zara = zara_rested
    zara_tok = f"tok_ext_consume_{zara['id']}"
    await _seed_battle(gm_client, [
        _mkc(zara_tok, zara["id"], name=zara["name"]),
    ])
    arm = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_metamagic_extended_spell",
        json={"character_id": zara["id"]},
    )
    assert arm.status_code == 200, arm.text
    pre = await _get_buff_keys(gm_client, zara["id"])
    assert "metamagic-extended-pending" in pre
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
    assert "metamagic-extended-pending" not in post


async def test_extended_endpoint_shape_preserved(
    gm_client, zara_rested,
):
    """Backward-compatibility: existing announce-only response
    fields (sp_cost, sp_remaining, sp_max, cast_id) preserved.
    """
    zara = zara_rested
    zara_tok = f"tok_ext_shape_{zara['id']}"
    await _seed_battle(gm_client, [
        _mkc(zara_tok, zara["id"], name=zara["name"]),
    ])
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_metamagic_extended_spell",
        json={"character_id": zara["id"]},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["sp_cost"] == 1
    assert "cast_id" in data
    assert data["sp_remaining"] == data["sp_max"] - 1
