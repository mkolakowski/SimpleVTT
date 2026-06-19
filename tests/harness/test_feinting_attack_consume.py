"""v2.451.0 — Feinting Attack opts into the v2.449.0
buff-consume-on-attack contract.

The existing v2.99.259 Feinting Attack endpoint broadcasts
`next_attack_advantage: True` in the chat card but leaves the
actual advantage as GM-narrated. v2.451.0 adds an optional
`target_combatant_id` body param: when supplied, the endpoint
installs a `feinting-attack` buff carrying both
`attack_advantage_vs_target_combatant_id` (for the v2.158.53
/attack advantage read) AND `consume_on_attack: True` (for the
v2.449.0 walker that drops the buff after the first /attack).

Tests:
  - Without target_combatant_id, the legacy GM-narrated path runs
    (no buff installed; broadcast carries buff_installed: False).
  - With target_combatant_id, the buff installs with both flags
    (broadcast carries buff_installed: True + the target id).
  - After /attack, the buff is consumed by the v2.449.0 walker.

Caster: Garrik Ironside (Fighter Lv 9 in demo seed). Garrik
ships as Champion by default — the `garrik_battle_master`
fixture PATCHes subclass to Battle Master + adds a
`superiority-dice` resource row, then restores on teardown.
Mirrors `tests/harness/test_feinting_attack.py:52-71`.
"""
import asyncio

import pytest_asyncio

from .conftest import CAMPAIGN_ID


async def _patch_sheet(gm_client, char_id, fields, class_slug=None):
    body = dict(fields)
    if class_slug:
        body["class_slug"] = class_slug
    r = await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-fields",
        json=body,
    )
    assert r.status_code == 200, r.text


def _superiority_dice_block(current: int, maximum: int) -> dict:
    return {
        "key": "superiority-dice",
        "name": "Superiority Dice",
        "current": current, "max": maximum, "reset": "short",
        "source": "fighter Lv 3 / Combat Superiority",
        "class_slug": "fighter",
        "desc": "Battle Master maneuvers.",
        "manual": False,
    }


@pytest_asyncio.fixture
async def garrik_battle_master(gm_client, roster):
    """PATCH Garrik to Battle Master + superiority dice; restore
    to Champion + cleared resources on teardown. Same shape as
    `test_feinting_attack.py`'s fixture."""
    garrik = roster["Garrik Ironside"]
    await _patch_sheet(
        gm_client, garrik["id"],
        {
            "subclass": "Battle Master",
            "superiority_die_size": "d8",
            "resources": [_superiority_dice_block(4, 4)],
        },
        class_slug="fighter",
    )
    try:
        yield garrik
    finally:
        await _patch_sheet(
            gm_client, garrik["id"],
            {"subclass": "Champion", "resources": []},
            class_slug="fighter",
        )


async def _seed_battle(gm_client, caster, target_combatant_id):
    pc_cb = {
        "id": f"tok_fa_{caster['id']}",
        "char_id": caster["id"],
        "name": caster["name"],
        "initiative": 15,
        "hp_current": 30, "hp_max": 30,
        "buffs": [],
        "economy": {"action": False, "bonus": False,
                    "reaction": False, "movement": 0},
    }
    target_cb = {
        "id": target_combatant_id, "char_id": None, "name": "FA Target",
        "initiative": 10,
        "hp_current": 50, "hp_max": 50,
        "buffs": [],
        "economy": {"action": False, "bonus": False,
                    "reaction": False, "movement": 0},
    }
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": [pc_cb, target_cb], "turn_index": 0,
              "round": 1, "active": True},
    )


async def _get_buffs(gm_client, char_id):
    r = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/buffs",
    )
    assert r.status_code == 200, r.text
    return r.json().get("buffs") or []


def _fa_broadcasts(gm_ws, character_id):
    return [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "feinting-attack"
        and (m.get("data") or {}).get("character_id") == character_id
    ]


async def test_feinting_attack_without_target_combatant_no_buff(
    gm_client, gm_ws, garrik_battle_master,
):
    """Legacy GM-narrated path: omit target_combatant_id → endpoint
    succeeds, response + broadcast carry buff_installed: False, and
    no feinting-attack buff is installed on Garrik."""
    fighter = garrik_battle_master
    await _seed_battle(gm_client, fighter, "tok_fa_target_noopt")
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_feinting_attack",
        json={
            "character_id": fighter["id"],
            "target_name": "FA Target",
            "override": True,
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
    assert body["next_attack_advantage"] is True
    assert body.get("buff_installed") is False
    assert body.get("target_combatant_id") is None

    await asyncio.sleep(0.3)
    feats = _fa_broadcasts(gm_ws, fighter["id"])
    assert feats, "feature_used broadcast missing"
    data = feats[-1]["data"]
    assert data["buff_installed"] is False
    assert data["next_attack_advantage"] is True
    assert data.get("target_combatant_id") is None

    buffs = await _get_buffs(gm_client, fighter["id"])
    assert not any(
        b.get("key") == "feinting-attack" for b in buffs
    ), f"no buff expected on legacy path; got buffs={buffs}"


async def test_feinting_attack_with_target_installs_buff(
    gm_client, gm_ws, garrik_battle_master,
):
    """v2.451.0 path: supply target_combatant_id → buff installs with
    both attack_advantage_vs_target_combatant_id AND consume_on_attack.
    Broadcast mirrors buff_installed: True + the target id."""
    fighter = garrik_battle_master
    target_combatant_id = "tok_fa_target_opt"
    await _seed_battle(gm_client, fighter, target_combatant_id)
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_feinting_attack",
        json={
            "character_id": fighter["id"],
            "target_name": "FA Target",
            "target_combatant_id": target_combatant_id,
            "override": True,
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["buff_installed"] is True
    assert body["target_combatant_id"] == target_combatant_id

    await asyncio.sleep(0.3)
    feats = _fa_broadcasts(gm_ws, fighter["id"])
    assert feats, "feature_used broadcast missing"
    data = feats[-1]["data"]
    assert data["buff_installed"] is True
    assert data["target_combatant_id"] == target_combatant_id

    buffs = await _get_buffs(gm_client, fighter["id"])
    fa_buff = next(
        (b for b in buffs if b.get("key") == "feinting-attack"), None,
    )
    assert fa_buff is not None, (
        f"feinting-attack buff missing; got buffs={buffs}"
    )
    effects = fa_buff.get("effects") or {}
    assert effects.get("attack_advantage_vs_target_combatant_id") == (
        target_combatant_id
    )
    assert effects.get("consume_on_attack") is True


async def test_feinting_attack_buff_consumed_after_attack(
    gm_client, garrik_battle_master,
):
    """After /attack, the v2.449.0 walker drops the feinting-attack
    buff from the fighter's combatant. Garrik fires his Greatsword
    (attack_index 0 per demo seed) vs the marked target."""
    fighter = garrik_battle_master
    target_combatant_id = "tok_fa_target_consume"
    await _seed_battle(gm_client, fighter, target_combatant_id)
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_feinting_attack",
        json={
            "character_id": fighter["id"],
            "target_name": "FA Target",
            "target_combatant_id": target_combatant_id,
            "override": True,
        },
    )
    assert r.status_code == 200, r.text
    assert r.json()["buff_installed"] is True

    # Verify buff present before attack.
    buffs_before = await _get_buffs(gm_client, fighter["id"])
    assert any(
        b.get("key") == "feinting-attack" for b in buffs_before
    ), f"expected buff before /attack; got {buffs_before}"

    # Garrik attacks with his Greatsword (attack_index 0). The
    # v2.449.0 walker drops the feinting-attack buff post-resolution.
    atk = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/attack",
        json={
            "character_id": fighter["id"],
            "attack_index": 0,
            "target_combatant_id": target_combatant_id,
            "override": True,
        },
    )
    assert atk.status_code == 200, atk.text

    buffs_after = await _get_buffs(gm_client, fighter["id"])
    assert not any(
        b.get("key") == "feinting-attack" for b in buffs_after
    ), (
        f"feinting-attack buff should be consumed by the first /attack; "
        f"got buffs={buffs_after}"
    )
