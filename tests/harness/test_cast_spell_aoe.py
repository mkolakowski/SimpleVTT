"""Phase T.5 — /cast_spell AoE multi-target dispatch.

v2.44.0: spells with ``area.shape == "sphere"`` accept a list of
combatants via ``target_combatant_ids`` (in addition to the existing
single-target ``target_combatant_id``). The endpoint loops save +
damage application per target and returns a per-target outcome list
in ``auto_save_targets``.

Tests:
  - Thalindra casts Fireball at 3 bandits with auto_apply_damage on:
    response carries ``auto_save_targets`` with 3 entries, each with
    rolled / passed / damage_applied; each bandit's HP dropped.
  - Single-target fallback: ``target_combatant_id`` (no list) still
    works unchanged.
  - PC target in AoE list is recorded as ``pc_skipped: True`` — v1
    doesn't auto-roll PC AoE saves; the GM still resolves manually.
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID


FIREBALL_INDEX = 7  # Demo Thalindra's spell list (app/demo_seed.py): 0 Fire Bolt,
                    # 1 Mage Hand, 2 Prestidigitation, 3 Magic Missile, 4 Shield,
                    # 5 Misty Step, 6 Scorching Ray, 7 Fireball, 8 Counterspell.


@pytest_asyncio.fixture
async def thalindra_rested(gm_client, roster):
    thal = roster["Thalindra Moonwhisper"]
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{thal['id']}/rest",
        json={"type": "long"},
    )
    return thal


async def _set_auto_apply(gm_client, on: bool) -> None:
    form = {
        "name": "Demo Campaign",
        "description": "demo",
        "game_system": "dnd5e",
        "gm_tab_color": "",
        "font_override": "",
        "default_encounter_id": "",
        "hp_threshold_1": "",
        "hp_threshold_2": "",
        "hp_threshold_3": "",
        "hp_threshold_4": "",
        "auto_play_playlist_id": "",
        "auto_play_mode": "order",
        "auto_play_initial_volume": "0.7",
    }
    if on:
        form["auto_apply_damage"] = "on"
    await gm_client.post(
        f"/campaign/{CAMPAIGN_ID}/settings", data=form,
        follow_redirects=False,
    )


async def _seed_battle(gm_client, combatants):
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": combatants, "turn_index": 0, "round": 1, "active": True},
    )


async def _bandit_tmpl(gm_client):
    r = await gm_client.get(f"/api/campaign/{CAMPAIGN_ID}/templates")
    templates = r.json()
    return next(t for t in templates if "bandit" in t["name"].lower())


async def test_fireball_hits_three_bandits(gm_client, gm_ws, roster, thalindra_rested):
    """Thalindra casts Fireball at 3 bandits — server loops the save
    + damage path 3 times, response includes 3 auto_save_targets.
    """
    thal = thalindra_rested
    tmpl = await _bandit_tmpl(gm_client)
    await _set_auto_apply(gm_client, on=True)
    await _seed_battle(gm_client, [
        {"id": f"tok_aoe_{thal['id']}", "char_id": thal["id"],
         "name": thal["name"], "initiative": 10, "hp_current": 24, "hp_max": 24,
         "buffs": [],
         "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0}},
        {"id": "tok_aoe_b1", "char_id": None,
         "token_template_id": tmpl["id"],
         "name": "Bandit Alpha", "initiative": 7, "hp_current": 50, "hp_max": 50,
         "buffs": [],
         "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0}},
        {"id": "tok_aoe_b2", "char_id": None,
         "token_template_id": tmpl["id"],
         "name": "Bandit Beta", "initiative": 6, "hp_current": 50, "hp_max": 50,
         "buffs": [],
         "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0}},
        {"id": "tok_aoe_b3", "char_id": None,
         "token_template_id": tmpl["id"],
         "name": "Bandit Gamma", "initiative": 5, "hp_current": 50, "hp_max": 50,
         "buffs": [],
         "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0}},
    ])

    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
        json={
            "character_id": thal["id"],
            "spell_index": FIREBALL_INDEX,
            "slot_level": 3,
            "class_slug": "wizard",
            "target_combatant_ids": ["tok_aoe_b1", "tok_aoe_b2", "tok_aoe_b3"],
            "override": True,
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    targets = data.get("auto_save_targets") or []
    assert len(targets) == 3, (
        f"expected 3 per-target outcomes, got {len(targets)}: {targets}"
    )
    names = {t["target_name"] for t in targets}
    assert names == {"Bandit Alpha", "Bandit Beta", "Bandit Gamma"}, (
        f"unexpected target names: {names}"
    )
    for t in targets:
        assert "rolled" in t and isinstance(t["rolled"], int)
        assert "passed" in t and isinstance(t["passed"], bool)
        # 8d6 fire damage — every bandit should have taken at least 1 HP
        # of damage (half on save, full on fail; both are > 0 for 8d6).
        assert t["damage_applied"] > 0, (
            f"bandit {t['target_name']} took 0 damage: {t}"
        )
        assert t["damage_type"] == "fire"


async def test_single_target_fallback_unchanged(gm_client, gm_ws, roster, thalindra_rested):
    """Casting with the old single-target ``target_combatant_id`` and
    no ``target_combatant_ids`` list still works — the response
    carries the existing auto_save_* headline fields AND
    auto_save_targets with exactly 1 entry (the canonical target).
    """
    thal = thalindra_rested
    tmpl = await _bandit_tmpl(gm_client)
    await _set_auto_apply(gm_client, on=True)
    await _seed_battle(gm_client, [
        {"id": f"tok_solo_{thal['id']}", "char_id": thal["id"],
         "name": thal["name"], "initiative": 10, "hp_current": 24, "hp_max": 24,
         "buffs": [],
         "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0}},
        {"id": "tok_solo_bandit", "char_id": None,
         "token_template_id": tmpl["id"],
         "name": "Bandit", "initiative": 7, "hp_current": 50, "hp_max": 50,
         "buffs": [],
         "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0}},
    ])

    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
        json={
            "character_id": thal["id"],
            "spell_index": FIREBALL_INDEX,
            "slot_level": 3,
            "class_slug": "wizard",
            # Old field — no list.
            "target_combatant_id": "tok_solo_bandit",
            "target_name": "Bandit",
            "override": True,
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    # Headline single-target fields populated as before.
    assert data["auto_save_target_kind"] == "npc"
    assert data["auto_save_target_name"] == "Bandit"
    assert isinstance(data["auto_save_rolled"], int)
    # auto_save_targets seeded with the single target for client uniformity.
    targets = data.get("auto_save_targets") or []
    assert len(targets) == 1, f"expected 1 target, got {len(targets)}: {targets}"
    assert targets[0]["target_name"] == "Bandit"


async def test_aoe_list_with_pc_target_marks_pc_skipped(
    gm_client, gm_ws, roster, thalindra_rested,
):
    """When an AoE list includes a PC token, the server doesn't auto-
    roll the PC's save (that needs a roll_request per target). The
    entry is appended with ``pc_skipped: True`` so the client can
    still show "Pip — save prompt pending" on the card.
    """
    thal = thalindra_rested
    pip = roster["Pip Quickfingers"]
    tmpl = await _bandit_tmpl(gm_client)
    await _set_auto_apply(gm_client, on=True)
    await _seed_battle(gm_client, [
        {"id": f"tok_mixed_{thal['id']}", "char_id": thal["id"],
         "name": thal["name"], "initiative": 10, "hp_current": 24, "hp_max": 24,
         "buffs": [],
         "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0}},
        {"id": "tok_mixed_bandit", "char_id": None,
         "token_template_id": tmpl["id"],
         "name": "Bandit", "initiative": 7, "hp_current": 50, "hp_max": 50,
         "buffs": [],
         "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0}},
        {"id": f"tok_mixed_{pip['id']}", "char_id": pip["id"],
         "name": pip["name"], "initiative": 8, "hp_current": 24, "hp_max": 24,
         "buffs": [],
         "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0}},
    ])

    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
        json={
            "character_id": thal["id"],
            "spell_index": FIREBALL_INDEX,
            "slot_level": 3,
            "class_slug": "wizard",
            "target_combatant_ids": ["tok_mixed_bandit", f"tok_mixed_{pip['id']}"],
            "override": True,
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    targets = data.get("auto_save_targets") or []
    # 2 entries: bandit (NPC, auto-resolved) + pip (PC, skipped).
    assert len(targets) == 2, f"expected 2 targets, got {len(targets)}: {targets}"
    bandit_entry = next(t for t in targets if t["target_name"] == "Bandit")
    pip_entry = next(t for t in targets if t["target_name"] == pip["name"])
    assert isinstance(bandit_entry["rolled"], int)
    assert bandit_entry["damage_applied"] > 0
    # PC was skipped — no auto-roll, no auto-damage. The card will
    # show a save-prompt pending state for the player to roll.
    assert pip_entry.get("pc_skipped") is True
    assert pip_entry["rolled"] is None
    assert pip_entry["damage_applied"] == 0
