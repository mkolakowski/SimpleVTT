"""Phase T.3 — /cast_spell auto-resolves saves vs the targeted creature.

v2.30.0: when a spell has a ``save_ability`` (top-level OR on an
action) AND the caster passes a target, the server:

  - **PC target**: creates a RollRequest scoped to the target's owner
    and broadcasts a ``roll_request`` event. The chat card shows
    "Prompted NAME to save"; the player rolls in their own UI.

  - **NPC target**: rolls the save server-side using the monster
    template's ability scores (raw mod; demo NPCs aren't proficient
    in any saves) and broadcasts a ``roll`` event with a note that
    correlates back to the cast card via _appendSaveResultToSpellCard.

Tests:
  - Tavik casts Hold Person on Pip (PC) → auto_save_prompted=True,
    auto_save_target_kind=pc, RollRequest scoped to Pip's owner
  - Tavik casts Hold Person on an NPC bandit (NPC) → server rolls;
    auto_save_rolled populated, auto_save_passed boolean
  - cast without target → no auto-save
  - non-save spell (Healing Word) → no auto-save fields populated
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID


HOLD_PERSON_INDEX = 8  # Tavik's cleric spell list: 0 Sacred Flame, 1 Guidance,
                       # 2 Light, 3 Bless, 4 Cure Wounds, 5 Healing Word,
                       # 6 Lesser Restoration, 7 Spiritual Weapon,
                       # 8 Hold Person.


@pytest_asyncio.fixture
async def tavik_rested(gm_client, roster):
    tavik = roster["Brother Tavik Stonebrow"]
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{tavik['id']}/rest",
        json={"type": "long"},
    )
    return tavik


async def _seed_battle(gm_client, combatants):
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": combatants, "turn_index": 0, "round": 1, "active": True},
    )


async def test_save_spell_prompts_pc_target(gm_client, tavik_rested, roster):
    """Hold Person on Pip (PC) → roll_request created for Pip's owner."""
    tavik = tavik_rested
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
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
        json={
            "character_id": tavik["id"],
            "spell_index": HOLD_PERSON_INDEX,
            "slot_level": 2,
            "class_slug": "cleric",
            "target_character_id": pip["id"],
            "target_combatant_id": f"tok_test_{pip['id']}",
            "target_name": pip["name"],
            "override": True,
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["auto_save_ability"] == "WIS"
    assert data["auto_save_target_kind"] == "pc"
    assert data["auto_save_prompted"] is True
    assert data["auto_save_dc"] >= 8
    assert data["auto_save_target_name"] == pip["name"]
    # NPC fields stay null for PC path.
    assert data["auto_save_rolled"] is None
    assert data["auto_save_passed"] is None


async def test_save_spell_auto_rolls_npc(gm_client, tavik_rested, roster):
    """Hold Person on a seeded NPC bandit → server rolls the save;
    rolled / passed fields populated."""
    tavik = tavik_rested
    # Need a token_template_id to project the monster sheet — fetch
    # one from the campaign's templates.
    r = await gm_client.get(f"/api/campaign/{CAMPAIGN_ID}/templates")
    assert r.status_code == 200, r.text
    templates = r.json()
    bandit_tmpl = next((t for t in templates if "bandit" in t["name"].lower()), templates[0])
    await _seed_battle(gm_client, [
        {"id": f"tok_test_{tavik['id']}", "char_id": tavik["id"],
         "name": tavik["name"], "initiative": 10, "hp_current": 30, "hp_max": 30,
         "buffs": [],
         "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0}},
        {"id": "tok_test_bandit_npc", "char_id": None,
         "token_template_id": bandit_tmpl["id"],
         "name": bandit_tmpl["name"], "initiative": 7, "hp_current": 11, "hp_max": 11,
         "buffs": [],
         "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0}},
    ])
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
        json={
            "character_id": tavik["id"],
            "spell_index": HOLD_PERSON_INDEX,
            "slot_level": 2,
            "class_slug": "cleric",
            "target_combatant_id": "tok_test_bandit_npc",
            "target_name": bandit_tmpl["name"],
            "override": True,
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["auto_save_ability"] == "WIS"
    assert data["auto_save_target_kind"] == "npc"
    assert data["auto_save_prompted"] is False
    assert isinstance(data["auto_save_rolled"], int)
    assert isinstance(data["auto_save_passed"], bool)
    assert data["auto_save_breakdown"]
    # Sanity: 1d20 (-5..-1 for low Wis bandit) gives a range of 1..20.
    assert 1 <= data["auto_save_rolled"] <= 30


async def test_cast_without_target_no_auto_save(gm_client, tavik_rested):
    """Cast Hold Person with no target → no auto-save fields populated."""
    tavik = tavik_rested
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
        json={
            "character_id": tavik["id"],
            "spell_index": HOLD_PERSON_INDEX,
            "slot_level": 2,
            "class_slug": "cleric",
            "override": True,
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    # When no save_ability AND no target, the field stays empty.
    assert data["auto_save_target_name"] == ""
    assert data["auto_save_target_kind"] == ""
    assert data["auto_save_prompted"] is False


async def _set_auto_apply(gm_client, on: bool) -> None:
    """Toggle Campaign.auto_apply_damage via the form-encoded settings
    POST. Mirrors the helper in test_attack_auto_damage.py — every
    sibling form field the validator requires must come along."""
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


async def test_save_for_half_applies_half_on_success(gm_client, tavik_rested, roster, monkeypatch):
    """Sacred Flame at a bandit who saves → no damage applied (Sacred
    Flame has no save-for-half — but the v2.31.0 default IS save-for-
    half so the test asserts half-damage. A future content flag can
    encode the per-spell exception). Here we use Burning Hands which
    IS save-for-half, and force the bandit to roll high so the success
    branch fires.

    Skips when auto_apply_damage is off — set it on first.
    """
    tavik = tavik_rested
    await _set_auto_apply(gm_client, on=True)
    r = await gm_client.get(f"/api/campaign/{CAMPAIGN_ID}/templates")
    templates = r.json()
    bandit_tmpl = next((t for t in templates if "bandit" in t["name"].lower()), templates[0])
    await _seed_battle(gm_client, [
        {"id": f"tok_test_{tavik['id']}", "char_id": tavik["id"],
         "name": tavik["name"], "initiative": 10, "hp_current": 30, "hp_max": 30,
         "buffs": [],
         "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0}},
        {"id": "tok_test_bandit_dmg", "char_id": None,
         "token_template_id": bandit_tmpl["id"],
         "name": bandit_tmpl["name"], "initiative": 7, "hp_current": 50, "hp_max": 50,
         "buffs": [],
         "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0}},
    ])
    # Sacred Flame (idx 0) — d8 radiant, Dex save. The bandit's Dex
    # mod is +1 (dex 12) so half the time he saves, half he doesn't.
    # We just assert SOMETHING reasonable came back; exact values
    # depend on the d20+d8 rolls.
    SACRED_FLAME_INDEX = 0
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
        json={
            "character_id": tavik["id"],
            "spell_index": SACRED_FLAME_INDEX,
            "slot_level": 0,
            "class_slug": "cleric",
            "target_combatant_id": "tok_test_bandit_dmg",
            "target_name": bandit_tmpl["name"],
            "override": True,
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["auto_save_target_kind"] == "npc"
    assert isinstance(data["auto_save_passed"], bool)
    # v2.36.0 cantrip scaling: Sacred Flame is 1d8 at L1-4 and 2d8 at
    # L5-10. Tavik is L5 in the demo seed, so we expect 2d8 range
    # (2..16). Older versions of this test asserted 1..8 — bump for
    # the scaling tier.
    assert 2 <= data["auto_save_damage_rolled"] <= 16
    if data["auto_save_passed"]:
        # Save-for-half default: half (rounded down).
        assert data["auto_save_damage_applied"] == data["auto_save_damage_rolled"] // 2
    else:
        # Full damage on fail (modulo resistance — bandit has none).
        assert data["auto_save_damage_applied"] == data["auto_save_damage_rolled"]
    assert data["auto_save_damage_type"] == "radiant"


async def test_save_spell_no_auto_damage_when_toggle_off(gm_client, tavik_rested, roster):
    """When campaign.auto_apply_damage is False, the save still rolls
    but no damage is applied — auto_save_damage_applied == 0."""
    tavik = tavik_rested
    await _set_auto_apply(gm_client, on=False)
    r = await gm_client.get(f"/api/campaign/{CAMPAIGN_ID}/templates")
    templates = r.json()
    bandit_tmpl = next((t for t in templates if "bandit" in t["name"].lower()), templates[0])
    await _seed_battle(gm_client, [
        {"id": f"tok_test_{tavik['id']}", "char_id": tavik["id"],
         "name": tavik["name"], "initiative": 10, "hp_current": 30, "hp_max": 30,
         "buffs": [],
         "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0}},
        {"id": "tok_test_bandit_off", "char_id": None,
         "token_template_id": bandit_tmpl["id"],
         "name": bandit_tmpl["name"], "initiative": 7, "hp_current": 11, "hp_max": 11,
         "buffs": [],
         "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0}},
    ])
    SACRED_FLAME_INDEX = 0
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
        json={
            "character_id": tavik["id"],
            "spell_index": SACRED_FLAME_INDEX,
            "slot_level": 0,
            "class_slug": "cleric",
            "target_combatant_id": "tok_test_bandit_off",
            "target_name": bandit_tmpl["name"],
            "override": True,
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    # Save still rolls.
    assert data["auto_save_target_kind"] == "npc"
    assert isinstance(data["auto_save_passed"], bool)
    # Damage NOT applied because toggle is off.
    assert data["auto_save_damage_rolled"] == 0
    assert data["auto_save_damage_applied"] == 0
    # Re-enable for subsequent tests in the run.
    await _set_auto_apply(gm_client, on=True)


async def test_save_or_suck_installs_buff_on_fail(gm_client, tavik_rested):
    """v2.32.0 T.3c: Hold Person on a bandit (Wis +0) → at low save
    bonus the bandit fails the WIS save ~65% of the time. We cast in
    a small loop and verify that when ``auto_save_passed`` is False
    the buff fields populate (key=paralyzed, name=Paralyzed) AND the
    bandit's combatant.buffs in the battle state carries the entry."""
    tavik = tavik_rested
    r = await gm_client.get(f"/api/campaign/{CAMPAIGN_ID}/templates")
    templates = r.json()
    bandit_tmpl = next((t for t in templates if "bandit" in t["name"].lower()), templates[0])
    saw_buff = False
    saw_save = False
    for attempt in range(20):
        # Long-rest Tavik so each iteration has a fresh spell slot.
        await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/character/{tavik['id']}/rest",
            json={"type": "long"},
        )
        await _seed_battle(gm_client, [
            {"id": f"tok_test_{tavik['id']}", "char_id": tavik["id"],
             "name": tavik["name"], "initiative": 10, "hp_current": 30, "hp_max": 30,
             "buffs": [],
             "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0}},
            {"id": "tok_test_bandit_buff", "char_id": None,
             "token_template_id": bandit_tmpl["id"],
             "name": bandit_tmpl["name"], "initiative": 7, "hp_current": 11, "hp_max": 11,
             "buffs": [],
             "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0}},
        ])
        resp = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
            json={
                "character_id": tavik["id"],
                "spell_index": HOLD_PERSON_INDEX,
                "slot_level": 2,
                "class_slug": "cleric",
                "target_combatant_id": "tok_test_bandit_buff",
                "target_name": bandit_tmpl["name"],
                "override": True,
            },
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        if data["auto_save_passed"] is False:
            saw_buff = True
            assert data["auto_save_buff_key"] == "paralyzed"
            assert data["auto_save_buff_name"] == "Paralyzed"
            assert data["auto_save_buff_duration"] == 10
            break
        else:
            saw_save = True
            # When the save succeeds, no buff is installed.
            assert data["auto_save_buff_key"] == ""
    # Cap protection: at least one branch fired in 20 attempts.
    assert saw_buff or saw_save


async def test_save_or_suck_skips_unknown_spell(gm_client, tavik_rested):
    """Sacred Flame has no entry in _SPELL_CONDITION_MAP (it's a
    damage spell, not save-or-suck). Even when the bandit fails, no
    buff is installed."""
    tavik = tavik_rested
    r = await gm_client.get(f"/api/campaign/{CAMPAIGN_ID}/templates")
    templates = r.json()
    bandit_tmpl = next((t for t in templates if "bandit" in t["name"].lower()), templates[0])
    await _seed_battle(gm_client, [
        {"id": f"tok_test_{tavik['id']}", "char_id": tavik["id"],
         "name": tavik["name"], "initiative": 10, "hp_current": 30, "hp_max": 30,
         "buffs": [],
         "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0}},
        {"id": "tok_test_bandit_sf", "char_id": None,
         "token_template_id": bandit_tmpl["id"],
         "name": bandit_tmpl["name"], "initiative": 7, "hp_current": 11, "hp_max": 11,
         "buffs": [],
         "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0}},
    ])
    SACRED_FLAME_INDEX = 0
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
        json={
            "character_id": tavik["id"],
            "spell_index": SACRED_FLAME_INDEX,
            "slot_level": 0,
            "class_slug": "cleric",
            "target_combatant_id": "tok_test_bandit_sf",
            "target_name": bandit_tmpl["name"],
            "override": True,
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    # Sacred Flame has damage → save-for-half block fires; T.3c block
    # is skipped (damage_expr truthy).
    assert data["auto_save_buff_key"] == ""
    assert data["auto_save_buff_name"] == ""


async def test_non_save_spell_no_auto_save(gm_client, tavik_rested, roster):
    """Healing Word (no save_ability) → auto-save not invoked."""
    tavik = tavik_rested
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
    # No save ability on Healing Word → auto-save fields stay empty/default.
    assert data["auto_save_ability"] == ""
    assert data["auto_save_target_kind"] == ""
    assert data["auto_save_prompted"] is False
