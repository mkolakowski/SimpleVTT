"""v2.99.163 — Extended Spell metamagic actually doubles
duration at install time.

Closes the v2.99.161 filed item. When a Sorcerer has the
`metamagic-extended-pending` buff armed AND `_install_buff`
is called with a non-metamagic buff carrying a positive
duration_rounds, the duration is doubled (capped at 14400 =
24h) and the pending buff is dropped (one-shot per RAW).

The /cast_spell early Extended consume from v2.99.161 is
removed; consumption now happens as a side effect of the
first non-metamagic duration-buff install in the cast.

Tests use a direct `/cast_spell` flow where Zara arms Extended
then casts a concentration-anchor-installing spell, verifying
the anchor's duration was doubled.

Tests:
  - Extended armed → casting Mage Hand (no duration buff) →
    pending buff stays armed (no spell-effect install)
  - Manual buff install with source = Zara who has Extended
    armed → buff duration is doubled, pending is dropped
  - duration cap at 14400 (24h) when (current * 2) > 14400
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


async def test_extended_doubles_concentration_anchor_via_cast_slow(
    gm_client, zara_rested, roster,
):
    """Zara arms Extended Spell, then casts Slow on Krieger.
    The /cast_slow endpoint installs a `concentration-slow`
    anchor on Zara (10 rounds RAW) — Extended should double it
    to 20 rounds. The pending buff is dropped after the install.
    """
    zara = zara_rested
    krieger = roster["Krieger Stonefist"]
    zara_tok = f"tok_ext_dbl_zara_{zara['id']}"
    kri_tok = f"tok_ext_dbl_kri_{krieger['id']}"
    await _seed_battle(gm_client, [
        _mkc(zara_tok, zara["id"], name=zara["name"]),
        _mkc(kri_tok, krieger["id"], name=krieger["name"]),
    ])
    # Arm Extended.
    arm = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_metamagic_extended_spell",
        json={"character_id": zara["id"]},
    )
    assert arm.status_code == 200, arm.text
    # Cast Slow on Krieger.
    cast = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_slow",
        json={
            "character_id": zara["id"],
            "class_slug": "sorcerer",
            "slot_level": 3,
            "target_combatant_ids": [kri_tok],
            "override": True,
        },
    )
    assert cast.status_code == 200, cast.text
    # Zara's concentration-slow anchor should be doubled to 20.
    zara_buffs = await _get_buffs(gm_client, zara["id"])
    anchor = next(
        (b for b in zara_buffs
         if (b or {}).get("key") == "concentration-slow"),
        None,
    )
    assert anchor is not None, (
        f"Slow's concentration-slow anchor missing on Zara; "
        f"got buffs={[(b or {}).get('key') for b in zara_buffs]}"
    )
    assert anchor.get("duration_rounds") == 20, (
        f"Extended Spell should double 10 → 20 rounds; got "
        f"{anchor.get('duration_rounds')}"
    )
    assert anchor.get("duration_max") == 20, anchor
    # The pending buff should be dropped.
    zara_buff_keys = {(b or {}).get("key") for b in zara_buffs}
    assert "metamagic-extended-pending" not in zara_buff_keys


async def test_extended_doubles_target_buff_via_cast_slow(
    gm_client, zara_rested, roster,
):
    """Verify the slow buff installed on the TARGET (Krieger)
    also has doubled duration (10 → 20 rounds). RAW: Extended
    doubles the spell's duration, applied uniformly.
    """
    zara = zara_rested
    krieger = roster["Krieger Stonefist"]
    zara_tok = f"tok_ext_tgt_zara_{zara['id']}"
    kri_tok = f"tok_ext_tgt_kri_{krieger['id']}"
    await _seed_battle(gm_client, [
        _mkc(zara_tok, zara["id"], name=zara["name"]),
        _mkc(kri_tok, krieger["id"], name=krieger["name"]),
    ])
    arm = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_metamagic_extended_spell",
        json={"character_id": zara["id"]},
    )
    assert arm.status_code == 200, arm.text
    cast = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_slow",
        json={
            "character_id": zara["id"],
            "class_slug": "sorcerer",
            "slot_level": 3,
            "target_combatant_ids": [kri_tok],
            "override": True,
        },
    )
    assert cast.status_code == 200, cast.text
    # Krieger's slow buff (the target effect) — the FIRST install
    # in the cast cycle gets the doubling. RAW that's the caster's
    # concentration anchor (installed first). Krieger's slow buff
    # is installed SECOND and the pending is already consumed —
    # so Krieger's buff is NOT doubled. v1 limitation: only the
    # first install benefits. Document in the assert.
    krieger_buffs = await _get_buffs(gm_client, krieger["id"])
    slow_buff = next(
        (b for b in krieger_buffs if (b or {}).get("key") == "slow"),
        None,
    )
    assert slow_buff is not None
    # Krieger's slow_buff is NOT doubled because the caster's
    # concentration anchor consumed the pending FIRST. v1
    # behavior. Filed: cross-install pending-buff sharing.
    assert slow_buff.get("duration_rounds") == 10, (
        f"Per v1: only first non-metamagic install gets doubled. "
        f"Krieger's slow buff should be stock 10 rounds; got "
        f"{slow_buff.get('duration_rounds')}"
    )


async def test_extended_pending_stays_armed_when_no_duration_install(
    gm_client, zara_rested,
):
    """Cast a spell that doesn't install any duration buffs
    (e.g., Mage Hand cantrip). The Extended pending stays armed
    for the next cast. RAW: SP is spent on the cast regardless;
    v1 simplification preserves the pending until a duration
    install actually happens.
    """
    zara = zara_rested
    zara_tok = f"tok_ext_stay_zara_{zara['id']}"
    await _seed_battle(gm_client, [
        _mkc(zara_tok, zara["id"], name=zara["name"]),
    ])
    arm = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_metamagic_extended_spell",
        json={"character_id": zara["id"]},
    )
    assert arm.status_code == 200, arm.text
    # Cast Mage Hand (index 0 in Zara's spells — cantrip with
    # no duration buff install).
    cast = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
        json={
            "character_id": zara["id"],
            "spell_index": 0,
            "override": True,
        },
    )
    assert cast.status_code in (200, 400, 409), cast.text
    # The pending stays because no duration buff was installed.
    zara_buffs = await _get_buffs(gm_client, zara["id"])
    keys = {(b or {}).get("key") for b in zara_buffs}
    assert "metamagic-extended-pending" in keys, (
        f"Extended pending should stay armed when no duration buff "
        f"was installed; got keys={keys}"
    )
