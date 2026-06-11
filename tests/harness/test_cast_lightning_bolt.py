"""v2.159.14 — magic-items-automation Phase 8n: first SPELL wired
into the AoE-line substrate that v2.159.6-v2.159.13 built for items.

The substrate's spell side was already alive (the v2.44.0 cast_spell
multi-target loop has been working for Fireball since the sphere AoE
shipped); this commit proves the LINE shape also works through it by
exercising Lightning Bolt with 2 NPC targets. The UI now also drives
the v2.159.7 `_showAoEConfirmModal` between the AoE drag picker and
the /cast_spell POST — same per-target deselect power the Javelin has.

Tests:
  - Thalindra casts Lightning Bolt at 2 bandits → response carries
    `auto_save_targets` with 2 entries (one per target), each with
    `rolled` / `passed` / `damage_applied > 0` (8d6 is min 8, half =
    min 4), `damage_type == "lightning"`.
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID


LIGHTNING_BOLT_INDEX = 11  # Demo Thalindra's spell list (app/demo_seed.py):
                           # 0 Fire Bolt, 1 Mage Hand, 2 Prestidigitation,
                           # 3 Magic Missile, 4 Shield, 5 Misty Step,
                           # 6 Scorching Ray, 7 Web, 8 Hold Monster,
                           # 9 Flesh to Stone, 10 Fireball, 11 Lightning Bolt.


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
        json={"combatants": combatants, "turn_index": 0,
              "round": 1, "active": True},
    )


async def _bandit_tmpl(gm_client):
    r = await gm_client.get(f"/api/campaign/{CAMPAIGN_ID}/templates")
    templates = r.json()
    return next(t for t in templates if "bandit" in t["name"].lower())


async def test_lightning_bolt_hits_two_bandits(
    gm_client, gm_ws, roster, thalindra_rested,
):
    """v2.159.14 happy path. Thalindra casts Lightning Bolt at 2
    bandits via the multi-target cast_spell flow — response carries
    `auto_save_targets` with 2 entries, each carrying rolled/passed/
    damage_applied (>0 since 8d6 lightning is minimum 8 full / 4 half).
    """
    thal = thalindra_rested
    tmpl = await _bandit_tmpl(gm_client)
    await _set_auto_apply(gm_client, on=True)
    await _seed_battle(gm_client, [
        {"id": f"tok_lb_{thal['id']}", "char_id": thal["id"],
         "name": thal["name"], "initiative": 10,
         "hp_current": 24, "hp_max": 24, "buffs": [],
         "economy": {"action": False, "bonus": False,
                     "reaction": False, "movement": 0}},
        {"id": "tok_lb_b1", "char_id": None,
         "token_template_id": tmpl["id"],
         "name": "Bandit Alpha", "initiative": 7,
         "hp_current": 50, "hp_max": 50, "buffs": [],
         "economy": {"action": False, "bonus": False,
                     "reaction": False, "movement": 0}},
        {"id": "tok_lb_b2", "char_id": None,
         "token_template_id": tmpl["id"],
         "name": "Bandit Beta", "initiative": 6,
         "hp_current": 50, "hp_max": 50, "buffs": [],
         "economy": {"action": False, "bonus": False,
                     "reaction": False, "movement": 0}},
    ])

    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
        json={
            "character_id": thal["id"],
            "spell_index": LIGHTNING_BOLT_INDEX,
            "slot_level": 3,
            "class_slug": "wizard",
            "target_combatant_ids": ["tok_lb_b1", "tok_lb_b2"],
            "override": True,
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    targets = data.get("auto_save_targets") or []
    assert len(targets) == 2, (
        f"expected 2 per-target outcomes, got {len(targets)}: {targets}"
    )
    names = {t["target_name"] for t in targets}
    assert names == {"Bandit Alpha", "Bandit Beta"}, (
        f"unexpected target names: {names}"
    )
    for t in targets:
        assert "rolled" in t and isinstance(t["rolled"], int)
        assert "passed" in t and isinstance(t["passed"], bool)
        assert t["damage_applied"] > 0, (
            f"bandit {t['target_name']} took 0 damage: {t}"
        )
        assert t["damage_type"] == "lightning"
