"""Phase T.4b — /cast_spell auto-rolls spell ATTACK rolls (Fire Bolt etc.).

v2.34.0: spells with ``attack_roll: true`` on their action (Fire Bolt,
Eldritch Blast, Inflict Wounds, Ray of Frost, Scorching Ray, Chill
Touch, Vampiric Touch, Guiding Bolt, Acid Arrow, Produce Flame, …)
now resolve hit determination server-side, mirroring T.2's weapon-
attack flow. Spell attack bonus = caster proficiency + spellcasting
ability mod; roll vs target AC; natural 20 = crit (doubles damage
dice), natural 1 = miss. On hit, damage rolled + applied via the
shared ``_apply_damage_to_combatant`` helper (gated by
``Campaign.auto_apply_damage``).

Tests:
  - Fire Bolt on a bandit (NPC) → auto_attack_hit boolean, total,
    target_ac populated, damage rolled when hit + toggle on
  - cast without target → no auto-attack fields populated
  - non-attack spell (Healing Word) → no auto-attack
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID


FIRE_BOLT_INDEX = 0  # Thalindra's wizard cantrip list: 0 Fire Bolt.


@pytest_asyncio.fixture
async def thalindra_rested(gm_client, roster):
    thal = roster["Thalindra Moonwhisper"]
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{thal['id']}/rest",
        json={"type": "long"},
    )
    return thal


async def _seed_battle(gm_client, combatants):
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": combatants, "turn_index": 0, "round": 1, "active": True},
    )


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


async def test_fire_bolt_resolves_hit_vs_npc(gm_client, thalindra_rested):
    """Fire Bolt on a bandit → server rolls 1d20+spell-atk-mod and
    compares to bandit AC. Hit boolean populated, target_ac surfaced,
    damage rolled when hit."""
    thal = thalindra_rested
    await _set_auto_apply(gm_client, on=True)
    r = await gm_client.get(f"/api/campaign/{CAMPAIGN_ID}/templates")
    templates = r.json()
    bandit_tmpl = next((t for t in templates if "bandit" in t["name"].lower()), templates[0])
    await _seed_battle(gm_client, [
        {"id": f"tok_test_{thal['id']}", "char_id": thal["id"],
         "name": thal["name"], "initiative": 10, "hp_current": 30, "hp_max": 30,
         "buffs": [],
         "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0}},
        {"id": "tok_test_bandit_atk", "char_id": None,
         "token_template_id": bandit_tmpl["id"],
         "name": bandit_tmpl["name"], "initiative": 7, "hp_current": 50, "hp_max": 50,
         "buffs": [],
         "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0}},
    ])
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
        json={
            "character_id": thal["id"],
            "spell_index": FIRE_BOLT_INDEX,
            "slot_level": 0,
            "class_slug": "wizard",
            "target_combatant_id": "tok_test_bandit_atk",
            "target_name": bandit_tmpl["name"],
            "override": True,
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    # Attack-roll fields populated.
    assert isinstance(data["auto_attack_hit"], bool)
    assert data["auto_attack_total"] >= 1
    assert data["auto_attack_target_ac"] >= 8  # bandit has AC 12
    assert data["auto_attack_target_name"] == bandit_tmpl["name"]
    if data["auto_attack_hit"]:
        # Damage rolls when toggle on. d10 fire (1d10).
        assert data["auto_attack_damage_rolled"] >= 1
        assert data["auto_attack_damage_type"] == "fire"
    else:
        # Miss → no damage applied (still might have rolled
        # nothing — that's fine).
        assert data["auto_attack_damage_applied"] == 0


async def test_spell_attack_no_damage_when_toggle_off(gm_client, thalindra_rested):
    """When campaign.auto_apply_damage is False, the attack still
    rolls but damage_applied stays 0 (mirrors weapon attacks)."""
    thal = thalindra_rested
    await _set_auto_apply(gm_client, on=False)
    r = await gm_client.get(f"/api/campaign/{CAMPAIGN_ID}/templates")
    templates = r.json()
    bandit_tmpl = next((t for t in templates if "bandit" in t["name"].lower()), templates[0])
    await _seed_battle(gm_client, [
        {"id": f"tok_test_{thal['id']}", "char_id": thal["id"],
         "name": thal["name"], "initiative": 10, "hp_current": 30, "hp_max": 30,
         "buffs": [],
         "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0}},
        {"id": "tok_test_bandit_off", "char_id": None,
         "token_template_id": bandit_tmpl["id"],
         "name": bandit_tmpl["name"], "initiative": 7, "hp_current": 11, "hp_max": 11,
         "buffs": [],
         "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0}},
    ])
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
        json={
            "character_id": thal["id"],
            "spell_index": FIRE_BOLT_INDEX,
            "slot_level": 0,
            "class_slug": "wizard",
            "target_combatant_id": "tok_test_bandit_off",
            "target_name": bandit_tmpl["name"],
            "override": True,
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    # Attack still rolls.
    assert isinstance(data["auto_attack_hit"], bool)
    # Damage NOT applied because toggle is off.
    assert data["auto_attack_damage_rolled"] == 0
    assert data["auto_attack_damage_applied"] == 0
    # Re-enable for downstream tests.
    await _set_auto_apply(gm_client, on=True)


async def test_spell_attack_no_target_skips_block(gm_client, thalindra_rested):
    """Fire Bolt with no target → auto_attack fields stay default."""
    thal = thalindra_rested
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
        json={
            "character_id": thal["id"],
            "spell_index": FIRE_BOLT_INDEX,
            "slot_level": 0,
            "class_slug": "wizard",
            "override": True,
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["auto_attack_hit"] is None
    assert data["auto_attack_total"] == 0
    assert data["auto_attack_target_ac"] == 0


async def test_non_attack_spell_skips_attack_block(gm_client, roster):
    """Healing Word (no attack_roll) → auto_attack fields stay default."""
    tavik = roster["Brother Tavik Stonebrow"]
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{tavik['id']}/rest",
        json={"type": "long"},
    )
    pip = roster["Pip Quickfingers"]
    await _seed_battle(gm_client, [
        {"id": f"tok_test_{tavik['id']}", "char_id": tavik["id"],
         "name": tavik["name"], "initiative": 10, "hp_current": 30, "hp_max": 30,
         "buffs": [],
         "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0}},
        {"id": f"tok_test_{pip['id']}", "char_id": pip["id"],
         "name": pip["name"], "initiative": 8, "hp_current": 30, "hp_max": 30,
         "buffs": [],
         "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0}},
    ])
    HEALING_WORD_INDEX = 5
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
        json={
            "character_id": tavik["id"],
            "spell_index": HEALING_WORD_INDEX,
            "slot_level": 1,
            "class_slug": "cleric",
            "target_character_id": pip["id"],
            "target_combatant_id": f"tok_test_{pip['id']}",
            "override": True,
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    # No attack_roll on Healing Word → block skipped.
    assert data["auto_attack_hit"] is None
    assert data["auto_attack_total"] == 0
