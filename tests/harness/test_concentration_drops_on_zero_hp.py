"""Concentration breaks automatically at 0 HP (RAW PHB p.203).

v2.49.48 fix. Before this fix, ``_maybe_concentration_save`` rolled
the CON save and only dropped concentration on a failed save — so
a PC who took damage dropping to 0 HP could still pass the save
and stay concentrating. RAW says concentration ends AUTOMATICALLY
on incapacitation / death, no save involved.

Surfaced during the v2.49.41 / v2.49.46 audit trail (concentration
cleanup tests for the encounter-sim suite). The Phase 4
``test_drops_on_zero_hp`` had to inflate damage_amount to 65 to
guarantee an un-passable DC=32 — with the fix, the regular
damage flow drops concentration on 0 HP without dice gymnastics.

Tests:
  - Magnus casts Hex on Pip. Damage Magnus down to exactly 0 HP
    with a damage_amount where the DC could be passed.
    Concentration drops regardless (forced_drop_on_zero_hp=True).
  - Damage that DOESN'T drop to 0 still uses the normal save
    branch (forced_drop_on_zero_hp=False).
"""
import asyncio

from .conftest import CAMPAIGN_ID


async def _seed_battle_with(gm_client, char_ids: list[int]):
    """Seed minimal battle state with the given character ids in init."""
    combatants = [
        {
            "id": f"tok_zhd_{cid}",
            "char_id": cid,
            "name": f"PC {cid}",
            "initiative": 10 + i,
            "hp_current": 30,
            "hp_max": 30,
            "buffs": [],
            "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0},
        }
        for i, cid in enumerate(char_ids)
    ]
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": combatants, "turn_index": 0, "round": 1, "active": True},
    )


async def test_concentration_force_drops_at_zero_hp(gm_client, gm_ws, roster):
    """Magnus casts Hex on Pip, then takes damage to 0 HP. The
    concentration save's ``passed`` field is forced to False AND
    ``forced_drop_on_zero_hp`` is True regardless of the d20.
    """
    magnus = roster["Magnus Hexbinder"]
    pip = roster["Pip Quickfingers"]
    # Reset state.
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{magnus['id']}/rest",
        json={"type": "long"},
    )
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{magnus['id']}/death-save/override",
        json={"status": "alive", "successes": 0, "failures": 0},
    )

    await _seed_battle_with(gm_client, [magnus["id"], pip["id"]])

    # Install Hex.
    r1 = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_hex",
        json={
            "character_id": magnus["id"],
            "target_character_id": pip["id"],
            "ability": "STR",
            "override": True,
        },
    )
    assert r1.status_code == 200, r1.text
    gm_ws.mark()

    # Damage Magnus to exactly 0 HP via a moderate damage_amount. With
    # damage_amount=15, DC = max(10, 7) = 10 — a perfectly passable
    # save for Magnus's CON+2. Pre-fix Magnus could pass and keep
    # concentration despite being at 0 HP.
    resp = await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{magnus['id']}/sheet-fields",
        json={
            "hp": {"current": 0},
            "hp_change_reason": "damage",
            "damage_amount": 15,
        },
    )
    assert resp.status_code == 200, resp.text

    # concentration_save broadcast: passed=False AND forced flag.
    cs = await gm_ws.wait_for("concentration_save")
    assert cs["data"]["character_id"] == magnus["id"]
    assert cs["data"]["buff_key"] == "hex"
    assert cs["data"]["dc"] == 10
    assert cs["data"]["forced_drop_on_zero_hp"] is True, (
        f"PC at 0 HP should force-drop concentration regardless of save; "
        f"got {cs['data']}"
    )
    assert cs["data"]["passed"] is False, (
        f"forced_drop_on_zero_hp should set passed=False; got {cs['data']}"
    )
    assert cs["data"]["dropped_key"] == "hex"


async def test_concentration_normal_save_when_not_at_zero(gm_client, gm_ws, roster):
    """Damage that doesn't drop to 0 still goes through the normal
    save branch — ``forced_drop_on_zero_hp`` is False. The save may
    pass or fail by dice; we assert only the flag.
    """
    magnus = roster["Magnus Hexbinder"]
    pip = roster["Pip Quickfingers"]
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{magnus['id']}/rest",
        json={"type": "long"},
    )
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{magnus['id']}/death-save/override",
        json={"status": "alive", "successes": 0, "failures": 0},
    )

    await _seed_battle_with(gm_client, [magnus["id"], pip["id"]])

    r1 = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_hex",
        json={
            "character_id": magnus["id"],
            "target_character_id": pip["id"],
            "ability": "STR",
            "override": True,
        },
    )
    assert r1.status_code == 200, r1.text
    gm_ws.mark()

    # Damage Magnus to 20 HP (not 0). Should be the regular save path.
    resp = await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{magnus['id']}/sheet-fields",
        json={
            "hp": {"current": 20},
            "hp_change_reason": "damage",
            "damage_amount": 13,
        },
    )
    assert resp.status_code == 200, resp.text

    cs = await gm_ws.wait_for("concentration_save")
    assert cs["data"]["forced_drop_on_zero_hp"] is False
    # passed could be True or False depending on the d20 roll —
    # we only pin the flag here.
    assert isinstance(cs["data"]["passed"], bool)
