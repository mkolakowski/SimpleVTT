"""See Invisibility target-side — invisible-target disadvantage + its
sees_invisible negation. Phase 2 #43 follow-up of
``docs/plans/cast-and-broadcast-tail.md``.

v2.514.0 — RAW PHB p.291: "attack rolls against [an invisible] creature
have disadvantage." This is the auto-read target-side intercept the
v2.499.0 Greater Invisibility comment described but that had been left
to the manual `attacker_cant_see_target` body field. New
`_target_is_invisible` hub-read folds it into the PC `/attack` (both
branches) and NPC `/npc_attack` pipelines, negated when the attacker
can see invisible creatures (`_attacker_sees_invisible` /
`_npc_attacker_sees_invisible`, the See Invisibility v2.509.0 flag).

Seeding: invisible target carries `{"key": "invisible"}`; a
See-Invisibility attacker carries `{"effects": {"sees_invisible": true}}`
— both on the combatant.buffs list via PUT /battle (hub-read, no cast).

Tests:
  - PC attacks an invisible target → disadvantage_target_invisible.
  - PC with sees_invisible attacks the same target → not target_invisible.
  - NPC attacks an invisible PC → disadvantage_target_invisible.
  - NPC with sees_invisible attacks the same PC → not target_invisible.
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID


@pytest_asyncio.fixture
async def pip_full(gm_client, roster):
    pip = roster["Pip Quickfingers"]
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{pip['id']}/rest",
        json={"type": "long"},
    )
    return pip


@pytest_asyncio.fixture(autouse=True)
async def _clear_invisible_after(gm_client, roster):
    """These tests seed combatants carrying an `invisible` buff (the
    target is often Pip). Both the realtime hub AND the character-sheet
    `_buffs_active` mirror persist that state across requests, so a stray
    `invisible` left behind would pollute a later same-session attack
    test (a no-target Pip swing would inherit advantage). Strip the
    invisibility/see-invisible buffs from every character these tests
    touch via /end_buff (clears hub + sheet mirror), then reset the
    battle, so the file is order-independent."""
    yield
    for name in ("Pip Quickfingers", "Krieger Stonefist"):
        ch = roster.get(name)
        if not ch:
            continue
        for key in ("invisible", "see-invisibility"):
            await gm_client.post(
                f"/api/campaign/{CAMPAIGN_ID}/end_buff",
                json={"character_id": ch["id"], "key": key},
            )
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": [], "turn_index": 0, "round": 1,
              "active": False},
    )


async def _seed_battle(gm_client, combatants):
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": combatants, "turn_index": 0,
              "round": 1, "active": True},
    )


def _mkc(cid, char_id=None, hp_cur=40, hp_max=40, name="X", buffs=None,
         init=10, template_id=None):
    out = {
        "id": cid,
        "char_id": char_id,
        "name": name,
        "initiative": init,
        "hp_current": hp_cur,
        "hp_max": hp_max,
        "buffs": buffs or [],
        "economy": {"action": False, "bonus": False,
                    "reaction": False, "movement": 0},
    }
    if template_id is not None:
        out["token_template_id"] = template_id
    return out


_INVIS = [{"key": "invisible", "name": "Invisible"}]
_SEES = [{"key": "see-invisibility", "name": "See Invisibility",
          "effects": {"sees_invisible": True}}]


async def test_pc_attacks_invisible_target_gets_disadvantage(
    gm_client, pip_full, roster,
):
    """Pip attacks an invisible Krieger → 2d20kl1 +
    roll_state_applied = 'disadvantage_target_invisible'."""
    pip = pip_full
    krieger = roster["Krieger Stonefist"]
    pip_cid = f"tok_invtgt_pip_{pip['id']}"
    krieger_cid = f"tok_invtgt_krg_{krieger['id']}"
    await _seed_battle(gm_client, [
        _mkc(pip_cid, pip["id"], name=pip["name"], init=20),
        _mkc(krieger_cid, krieger["id"], name=krieger["name"],
             hp_cur=60, hp_max=60, buffs=list(_INVIS)),
    ])
    a = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/attack",
        json={
            "character_id": pip["id"],
            "attack_index": 0,
            "target_combatant_id": krieger_cid,
            "override": True,
        },
    )
    assert a.status_code == 200, a.text
    state = a.json().get("roll_state_applied") or ""
    assert "disadvantage" in state and "target_invisible" in state, (
        f"expected disadvantage_target_invisible; got {state!r}"
    )


async def test_pc_with_see_invisibility_no_disadvantage(
    gm_client, pip_full, roster,
):
    """Pip carrying sees_invisible attacks the invisible Krieger → the
    target_invisible disadvantage is negated."""
    pip = pip_full
    krieger = roster["Krieger Stonefist"]
    pip_cid = f"tok_invtgt2_pip_{pip['id']}"
    krieger_cid = f"tok_invtgt2_krg_{krieger['id']}"
    await _seed_battle(gm_client, [
        _mkc(pip_cid, pip["id"], name=pip["name"], init=20,
             buffs=list(_SEES)),
        _mkc(krieger_cid, krieger["id"], name=krieger["name"],
             hp_cur=60, hp_max=60, buffs=list(_INVIS)),
    ])
    a = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/attack",
        json={
            "character_id": pip["id"],
            "attack_index": 0,
            "target_combatant_id": krieger_cid,
            "override": True,
        },
    )
    assert a.status_code == 200, a.text
    state = a.json().get("roll_state_applied") or ""
    assert "target_invisible" not in state, (
        f"See Invisibility should negate the invisible-target "
        f"disadvantage; got {state!r}"
    )


async def test_npc_attacks_invisible_pc_gets_disadvantage(
    gm_client, pip_full,
):
    """An NPC attacks an invisible PC → 2d20kl1 +
    roll_state_applied = 'disadvantage_target_invisible'."""
    pip = pip_full
    pip_cid = f"tok_invtgt_npcpip_{pip['id']}"
    bandit_cid = "npc_invtgt_1"
    await _seed_battle(gm_client, [
        _mkc(bandit_cid, hp_cur=11, hp_max=11, name="Stalker",
             template_id=1),
        _mkc(pip_cid, pip["id"], name=pip["name"], hp_cur=33, hp_max=33,
             buffs=list(_INVIS)),
    ])
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/npc_attack",
        json={
            "combatant_id": bandit_cid,
            "action_name": "Scimitar",
            "attack_bonus": "+3",
            "damage": "1d6+1",
            "damage_type": "slashing",
            "target_combatant_id": pip_cid,
        },
    )
    assert resp.status_code == 200, resp.text
    state = resp.json().get("roll_state_applied") or ""
    assert "disadvantage" in state and "target_invisible" in state, (
        f"expected disadvantage_target_invisible; got {state!r}"
    )


async def test_npc_with_see_invisibility_no_disadvantage(
    gm_client, pip_full,
):
    """An NPC carrying sees_invisible attacks an invisible PC → the
    target_invisible disadvantage is negated."""
    pip = pip_full
    pip_cid = f"tok_invtgt2_npcpip_{pip['id']}"
    bandit_cid = "npc_invtgt_2"
    await _seed_battle(gm_client, [
        _mkc(bandit_cid, hp_cur=11, hp_max=11, name="Seer", template_id=1,
             buffs=list(_SEES)),
        _mkc(pip_cid, pip["id"], name=pip["name"], hp_cur=33, hp_max=33,
             buffs=list(_INVIS)),
    ])
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/npc_attack",
        json={
            "combatant_id": bandit_cid,
            "action_name": "Bite",
            "attack_bonus": "+5",
            "damage": "1d8+3",
            "damage_type": "piercing",
            "target_combatant_id": pip_cid,
        },
    )
    assert resp.status_code == 200, resp.text
    state = resp.json().get("roll_state_applied") or ""
    assert "target_invisible" not in state, (
        f"See Invisibility should negate the invisible-target "
        f"disadvantage; got {state!r}"
    )
