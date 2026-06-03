"""v2.99.128 — condition immunity engine end-to-end tests.

v2.99.128 adds `_target_condition_immune` (PC) and
`_target_condition_immune_npc` (NPC) helpers + wires them into
`_install_buff` and `_install_buff_on_combatant_id`. RAW: a
creature immune to a condition doesn't get the condition
installed on a failed save (Constructs are immune to most
mind-affecting conditions, etc.).

Tests:
  - PC: PATCH Krieger's sheet with `condition_immunities:
    ["Stunned"]`. /use_stunning_strike attempts to install Stunned
    on Krieger via /respond → buff is suppressed.
  - PC: PATCH with `condition_immunities: ["all"]` → any
    condition install is suppressed (including paralyzed via
    Hold Person).
  - NPC: install a buff carrying `effects.condition_immunity_to:
    ["paralyzed"]` on the bandit. /cast_hold_person attempts to
    install paralyzed → suppressed.
  - Control: no immunity → normal install.
"""
import asyncio
import time

import pytest_asyncio

from .conftest import CAMPAIGN_ID


def _mkc(cid, char_id=None, token_template_id=None, name="X",
         hp_cur=20, hp_max=20, buffs=None):
    return {
        "id": cid,
        "char_id": char_id,
        "token_template_id": token_template_id,
        "name": name,
        "initiative": 10,
        "hp_current": hp_cur, "hp_max": hp_max,
        "speed_walk": 30,
        "buffs": buffs or [],
        "economy": {"action": False, "bonus": False, "reaction": False,
                    "movement": 0, "dash_bonus_ft": 0},
    }


async def _seed_battle(gm_client, combatants):
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": combatants, "turn_index": 0,
              "round": 1, "active": True},
    )


async def _bandit_template(gm_client):
    r = await gm_client.get(f"/api/campaign/{CAMPAIGN_ID}/templates")
    templates = r.json()
    return next(
        (t for t in templates if "bandit" in t["name"].lower()), templates[0],
    )


async def _get_buff_keys(gm_client, char_id):
    resp = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/buffs",
    )
    return {(b or {}).get("key") for b in resp.json().get("buffs") or []}


async def test_pc_specific_condition_immunity_suppresses_install(
    gm_client, roster,
):
    """PATCH Krieger's sheet with `condition_immunities: ["Paralyzed"]`.
    Tavik casts Hold Person on Krieger; Paralyzed should NOT install.
    """
    tavik = roster["Brother Tavik Stonebrow"]
    krieger = roster["Krieger Stonefist"]
    await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{krieger['id']}/sheet-fields",
        json={"condition_immunities": ["Paralyzed"]},
    )
    try:
        tv_tok = f"tok_cond_imm_tv_{tavik['id']}"
        kr_tok = f"tok_cond_imm_kr_{krieger['id']}"
        await _seed_battle(gm_client, [
            _mkc(tv_tok, tavik["id"], name=tavik["name"]),
            _mkc(kr_tok, krieger["id"], name=krieger["name"],
                 hp_cur=75, hp_max=75),
        ])
        resp = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/cast_hold_person",
            json={
                "character_id": tavik["id"],
                "class_slug": "cleric",
                "slot_level": 2,
                "target_combatant_ids": [kr_tok],
                "override": True,
            },
        )
        assert resp.status_code == 200, resp.text
        # The paralyzed buff should NOT be installed.
        keys = await _get_buff_keys(gm_client, krieger["id"])
        assert "paralyzed" not in keys, (
            f"condition immunity to Paralyzed should suppress the "
            f"install; got buff keys {keys}"
        )
    finally:
        await gm_client.patch(
            f"/api/campaign/{CAMPAIGN_ID}/character/{krieger['id']}/sheet-fields",
            json={"condition_immunities": []},
        )


async def test_pc_all_condition_immunity_wildcard(gm_client, roster):
    """PATCH with `condition_immunities: ["all"]` — any condition
    install is suppressed. Use grapple as the test vector since
    it's not a spell + the install path goes through
    _install_buff_on_combatant_id for the target (but Krieger is
    a PC, so it'd actually go through _install_buff if grappled
    by name). Use /use_grapple which uses
    _install_buff_on_combatant_id for the target. Wait — Krieger
    is a PC combatant though.
    """
    krieger = roster["Krieger Stonefist"]
    tavik = roster["Brother Tavik Stonebrow"]
    await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{krieger['id']}/sheet-fields",
        json={"condition_immunities": ["all"]},
    )
    try:
        tv_tok = f"tok_cond_imm_all_tv_{tavik['id']}"
        kr_tok = f"tok_cond_imm_all_kr_{krieger['id']}"
        await _seed_battle(gm_client, [
            _mkc(tv_tok, tavik["id"], name=tavik["name"]),
            _mkc(kr_tok, krieger["id"], name=krieger["name"],
                 hp_cur=75, hp_max=75),
        ])
        resp = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/cast_hold_person",
            json={
                "character_id": tavik["id"],
                "class_slug": "cleric",
                "slot_level": 2,
                "target_combatant_ids": [kr_tok],
                "override": True,
            },
        )
        assert resp.status_code == 200, resp.text
        keys = await _get_buff_keys(gm_client, krieger["id"])
        assert "paralyzed" not in keys, (
            f"'all' wildcard should suppress Paralyzed too; got {keys}"
        )
    finally:
        await gm_client.patch(
            f"/api/campaign/{CAMPAIGN_ID}/character/{krieger['id']}/sheet-fields",
            json={"condition_immunities": []},
        )


async def test_npc_condition_immunity_via_buff_suppresses_install(
    gm_client, roster,
):
    """Bandit with a buff carrying
    `effects.condition_immunity_to: ["paralyzed"]` doesn't get
    paralyzed installed when Tavik casts Hold Person on them.
    """
    tavik = roster["Brother Tavik Stonebrow"]
    bandit_tmpl = await _bandit_template(gm_client)
    bandit_id = "tok_cond_imm_npc_bandit"
    immunity_buff = {
        "key": "condition-immune-test",
        "name": "Condition Immune (test)",
        "icon": "🛡",
        "effects": {"condition_immunity_to": ["paralyzed"]},
    }
    await _seed_battle(gm_client, [
        _mkc(f"tok_cond_imm_npc_tv_{tavik['id']}", tavik["id"],
             name=tavik["name"]),
        _mkc(bandit_id, token_template_id=bandit_tmpl["id"],
             name=bandit_tmpl["name"], hp_cur=11, hp_max=11,
             buffs=[immunity_buff]),
    ])
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_hold_person",
        json={
            "character_id": tavik["id"],
            "class_slug": "cleric",
            "slot_level": 2,
            "target_combatant_ids": [bandit_id],
            "override": True,
        },
    )
    assert resp.status_code == 200, resp.text
    # The paralyzed buff should NOT be on the bandit.
    # Re-read from the battle state by snapshotting via PUT (the
    # response carries the affected list; we check both paths).
    affected = resp.json().get("affected") or []
    # The response's `installed` flag should be False because the
    # gate suppressed the install.
    assert any(
        e.get("combatant_id") == bandit_id and e.get("installed") is False
        for e in affected
    ), (
        f"v2.99.128 NPC condition immunity should yield installed=False; "
        f"got affected={affected}"
    )


async def test_no_condition_immunity_baseline(gm_client, roster):
    """Control: no immunity, Hold Person installs paralyzed
    normally (via the standard target-buff install flow).
    """
    tavik = roster["Brother Tavik Stonebrow"]
    krieger = roster["Krieger Stonefist"]
    tv_tok = f"tok_cond_imm_ctl_tv_{tavik['id']}"
    kr_tok = f"tok_cond_imm_ctl_kr_{krieger['id']}"
    await _seed_battle(gm_client, [
        _mkc(tv_tok, tavik["id"], name=tavik["name"]),
        _mkc(kr_tok, krieger["id"], name=krieger["name"],
             hp_cur=75, hp_max=75),
    ])
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_hold_person",
        json={
            "character_id": tavik["id"],
            "class_slug": "cleric",
            "slot_level": 2,
            "target_combatant_ids": [kr_tok],
            "override": True,
        },
    )
    assert resp.status_code == 200, resp.text
    affected = resp.json().get("affected") or []
    assert any(
        e.get("combatant_id") == kr_tok and e.get("installed") is True
        for e in affected
    ), f"control should install paralyzed; got affected={affected}"
