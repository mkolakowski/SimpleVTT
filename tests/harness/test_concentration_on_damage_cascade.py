"""v2.99.118 — concentration-on-damage cascade end-to-end test.

The v2.99.109 `_install_caster_concentration_anchor` set up the
caster-side anchor + the v2.49.51 `_remove_buff` → cascade path
already existed for explicit /end_buff. v2.19.1's
`_maybe_concentration_save` already wires the damage → CON save
→ buff drop chain. This commit verifies the full third concentration
drop path: damage takes the caster → failed CON save → anchor
removed → cascade clears target buffs.

The PATCH /sheet-fields endpoint with hp_change_reason="damage" +
damage_amount fires `_maybe_concentration_save`. We force the save
to fail by applying massive damage (DC = max(10, damage // 2)).

Test:
  - Thalindra casts Slow on Krieger → both buffs present
  - Apply 100 damage to Thalindra (DC = 50 → impossible to pass)
  - Verify Thalindra's concentration-slow anchor is gone
  - Verify Krieger's slow buff is gone (cascade fired)
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID


def _mkc(cid, char_id=None, name="X", speed_walk=30):
    return {
        "id": cid,
        "char_id": char_id,
        "name": name,
        "initiative": 10,
        "hp_current": 50, "hp_max": 50,
        "speed_walk": speed_walk,
        "buffs": [],
        "economy": {"action": False, "bonus": False, "reaction": False,
                    "movement": 0, "dash_bonus_ft": 0},
    }


async def _seed_battle(gm_client, combatants):
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": combatants, "turn_index": 0,
              "round": 1, "active": True},
    )


async def _get_buff_keys(gm_client, char_id):
    resp = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/buffs",
    )
    assert resp.status_code == 200, resp.text
    return {(b or {}).get("key") for b in resp.json().get("buffs") or []}


async def test_damage_drops_concentration_and_cascades_to_target(
    gm_client, roster,
):
    """Thalindra casts Slow → both anchor + target buff present.
    Massive damage forces a failed CON save → cascade clears both.
    """
    thalindra = roster["Thalindra Moonwhisper"]
    krieger = roster["Krieger Stonefist"]
    th_tok = f"tok_cn_dmg_th_{thalindra['id']}"
    kr_tok = f"tok_cn_dmg_kr_{krieger['id']}"
    await _seed_battle(gm_client, [
        _mkc(th_tok, thalindra["id"], name=thalindra["name"], speed_walk=30),
        _mkc(kr_tok, krieger["id"], name=krieger["name"], speed_walk=40),
    ])

    # Long-rest Thalindra so her HP is full + spell slots ready.
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{thalindra['id']}/rest",
        json={"type": "long"},
    )

    cast_resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_slow",
        json={
            "character_id": thalindra["id"],
            "class_slug": "wizard",
            "slot_level": 3,
            "target_combatant_ids": [kr_tok],
            "override": True,
        },
    )
    assert cast_resp.status_code == 200, cast_resp.text

    # Both buffs present before damage.
    th_keys_before = await _get_buff_keys(gm_client, thalindra["id"])
    kr_keys_before = await _get_buff_keys(gm_client, krieger["id"])
    assert "concentration-slow" in th_keys_before, th_keys_before
    assert "slow" in kr_keys_before, kr_keys_before

    # Read Thalindra's current HP so we can compute the new value.
    # _maybe_concentration_save fires on the PATCH /sheet-fields path
    # when hp_change_reason="damage" + damage_amount > 0.
    DAMAGE = 100  # DC = max(10, 100 // 2) = 50 → impossible to pass
    # Thalindra's hp_max is 37 (Wizard Lv 7). HP can't go below 0.
    new_current = 0  # full overkill, doesn't matter for the save flow
    damage_resp = await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{thalindra['id']}/sheet-fields",
        json={
            "hp": {"current": new_current},
            "hp_change_reason": "damage",
            "damage_amount": DAMAGE,
        },
    )
    assert damage_resp.status_code == 200, damage_resp.text

    # After damage: anchor + target buff should both be cleared.
    th_keys_after = await _get_buff_keys(gm_client, thalindra["id"])
    kr_keys_after = await _get_buff_keys(gm_client, krieger["id"])
    assert "concentration-slow" not in th_keys_after, (
        f"Thalindra's anchor should drop on failed CON save; "
        f"got {th_keys_after}"
    )
    assert "slow" not in kr_keys_after, (
        f"Krieger's slow buff should cascade-clear; got {kr_keys_after}"
    )

    # Restore Thalindra's HP for subsequent tests.
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{thalindra['id']}/rest",
        json={"type": "long"},
    )
