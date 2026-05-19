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
