"""v2.99.167 — Twinned Spell second-target metadata + audit.

Pre-v2.99.167 the v2.99.160 pending-buff scaffold accepted no
second-target info. v2.99.167 extends `/use_metamagic_twinned_spell`
to accept an optional `target_combatant_id_2` body field. When
provided, the field is:
  - Validated via `_lookup_combatant`
  - Stored on the pending buff's `effects.target_combatant_id_2`
    + `effects.target_combatant_name_2`
  - Surfaced in /cast_spell's consume broadcast as a "Twinned to
    {name}" feature_used audit

What's still NOT in this commit (filed):
  - Auto-install of the same buff on the second target inside
    the same /cast_spell call. The player still follows up
    manually with a second /cast_spell at the second target.

Tests:
  - declaring Twinned without target_combatant_id_2 (existing
    behavior) → pending buff has effects.target_combatant_id_2
    = None
  - declaring Twinned WITH target_combatant_id_2 → pending buff
    carries the target id + name
  - /cast_spell consume emits the "Twinned to {name}" broadcast
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


async def _get_buffs(gm_client, char_id):
    resp = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/buffs",
    )
    return resp.json().get("buffs") or []


@pytest_asyncio.fixture
async def zara_rested(gm_client, roster):
    """Long-rest Zara so SP is fresh."""
    zara = roster["Zara Emberfire"]
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{zara['id']}/rest",
        json={"type": "long"},
    )
    return zara


async def test_twinned_pending_without_second_target_unchanged(
    gm_client, zara_rested,
):
    """Backward-compatibility: declaring Twinned without
    target_combatant_id_2 produces a pending buff with
    effects.target_combatant_id_2 = None.
    """
    zara = zara_rested
    zara_tok = f"tok_tw2_none_{zara['id']}"
    await _seed_battle(gm_client, [
        _mkc(zara_tok, zara["id"], name=zara["name"]),
    ])
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_metamagic_twinned_spell",
        json={"character_id": zara["id"], "spell_level": 1},
    )
    assert resp.status_code == 200, resp.text
    zara_buffs = await _get_buffs(gm_client, zara["id"])
    pending = next(
        (b for b in zara_buffs
         if (b or {}).get("key") == "metamagic-twinned-pending"),
        None,
    )
    assert pending is not None
    effects = pending.get("effects") or {}
    assert effects.get("target_combatant_id_2") is None
    assert effects.get("target_combatant_name_2") is None


async def test_twinned_pending_stores_second_target(
    gm_client, zara_rested, roster,
):
    """Declaring Twinned WITH target_combatant_id_2 → pending
    buff's effects carry the target id + name.
    """
    zara = zara_rested
    krieger = roster["Krieger Stonefist"]
    zara_tok = f"tok_tw2_set_zara_{zara['id']}"
    kri_tok = f"tok_tw2_set_kri_{krieger['id']}"
    await _seed_battle(gm_client, [
        _mkc(zara_tok, zara["id"], name=zara["name"]),
        _mkc(kri_tok, krieger["id"], name=krieger["name"]),
    ])
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_metamagic_twinned_spell",
        json={
            "character_id": zara["id"],
            "spell_level": 1,
            "target_combatant_id_2": kri_tok,
        },
    )
    assert resp.status_code == 200, resp.text
    zara_buffs = await _get_buffs(gm_client, zara["id"])
    pending = next(
        (b for b in zara_buffs
         if (b or {}).get("key") == "metamagic-twinned-pending"),
        None,
    )
    assert pending is not None
    effects = pending.get("effects") or {}
    assert effects.get("target_combatant_id_2") == kri_tok
    assert effects.get("target_combatant_name_2") == krieger["name"]


async def test_twinned_consume_emits_second_target_broadcast(
    gm_client, gm_ws, zara_rested, roster,
):
    """When the pending buff has a second target, /cast_spell
    consume emits a feature_used(source=
    metamagic-twinned-spell-second-target) naming the target.
    """
    zara = zara_rested
    krieger = roster["Krieger Stonefist"]
    zara_tok = f"tok_tw2_bcast_zara_{zara['id']}"
    kri_tok = f"tok_tw2_bcast_kri_{krieger['id']}"
    await _seed_battle(gm_client, [
        _mkc(zara_tok, zara["id"], name=zara["name"]),
        _mkc(kri_tok, krieger["id"], name=krieger["name"]),
    ])
    # Arm Twinned with Krieger as second target.
    arm = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_metamagic_twinned_spell",
        json={
            "character_id": zara["id"],
            "spell_level": 1,
            "target_combatant_id_2": kri_tok,
        },
    )
    assert arm.status_code == 200, arm.text
    gm_ws.mark()
    cast = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
        json={
            "character_id": zara["id"],
            "spell_index": 0,
            "override": True,
        },
    )
    assert cast.status_code in (200, 400, 409), cast.text
    import asyncio as _asy
    await _asy.sleep(0.2)
    msgs = gm_ws.buffered("feature_used")
    second_target = [
        m for m in msgs
        if (m.get("data") or {}).get("source") == "metamagic-twinned-spell-second-target"
    ]
    assert second_target, (
        f"expected feature_used(source=metamagic-twinned-spell-second-target); "
        f"got: {[(m.get('type'), (m.get('data') or {}).get('source')) for m in gm_ws.buffered()]}"
    )
    bd = second_target[0].get("data") or {}
    assert bd.get("target_combatant_id_2") == kri_tok
    assert bd.get("target_combatant_name_2") == krieger["name"]
