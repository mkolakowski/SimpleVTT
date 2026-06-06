"""v2.99.423 — Phase 4.4: buff-level save advantage.

docs/plans/temp-hp-and-bonuses.md P4.4 — `_buff_grants_save_advantage`
reads `effects.save_advantage` off the saver's buffs and is wired at the
spell-save construction sites alongside `_race_grants_save_advantage`, so
a buff can grant advantage on saves (the saver's d20 → 2d20kh1).

`save_advantage: True` covers every save; a list (e.g. ["STR"]) covers
only those abilities. Verified on the single-target PC save path: Tavik
casts Hold Person (WIS save) at Pip, whose combatant carries a synthetic
ward buff. The roll-request's base_expression reflects the advantage.

Tests:
  - Buff `save_advantage: True` → WIS save prompt is 2d20kh1.
  - Buff `save_advantage: ["STR"]` → WIS save prompt stays 1d20 (the
    list doesn't cover WIS).
"""
from .conftest import CAMPAIGN_ID

HOLD_PERSON_INDEX = 8  # Tavik's cleric spell list (see test_cast_spell_save).


async def _cast_hold_person_at_pip(gm_client, gm_ws, tavik, pip, save_adv):
    """Seed Pip's combatant with a ward buff carrying the given
    save_advantage value, then have Tavik cast Hold Person at Pip.
    Returns the roll_request broadcast data (or None)."""
    tavik_tok = f"tok_bsa_tavik_{tavik['id']}"
    pip_tok = f"tok_bsa_pip_{pip['id']}"
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": [
            {"id": tavik_tok, "char_id": tavik["id"], "name": tavik["name"],
             "initiative": 12, "hp_current": 55, "hp_max": 55, "buffs": [],
             "economy": {"action": False, "bonus": False,
                         "reaction": False, "movement": 0}},
            {"id": pip_tok, "char_id": pip["id"], "name": pip["name"],
             "initiative": 8, "hp_current": 47, "hp_max": 47,
             "buffs": [{
                 "key": "test-ward", "name": "Test Ward",
                 "duration_rounds": 10, "duration_max": 10,
                 "concentration": False,
                 "effects": {"save_advantage": save_adv},
             }],
             "economy": {"action": False, "bonus": False,
                         "reaction": False, "movement": 0}},
        ], "turn_index": 0, "round": 1, "active": True},
    )
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
        json={"character_id": tavik["id"], "spell_index": HOLD_PERSON_INDEX,
              "slot_level": 2, "class_slug": "cleric",
              "target_combatant_id": pip_tok,
              "target_character_id": pip["id"],
              "override": True, "override_range": True},
    )
    assert r.status_code == 200, r.text
    return await gm_ws.wait_for("roll_request")


async def test_buff_save_advantage_true_grants_kh1(
    gm_client, gm_ws, roster,
):
    """A buff with save_advantage=True makes the WIS save prompt 2d20kh1."""
    tavik = roster["Brother Tavik Stonebrow"]
    pip = roster["Pip Quickfingers"]
    rr = await _cast_hold_person_at_pip(gm_client, gm_ws, tavik, pip, True)
    assert rr["data"]["base_expression"].startswith("2d20kh1"), rr["data"]


async def test_buff_save_advantage_list_non_match_stays_1d20(
    gm_client, gm_ws, roster,
):
    """A buff with save_advantage=["STR"] does NOT grant advantage on a
    WIS save — the prompt stays 1d20."""
    tavik = roster["Brother Tavik Stonebrow"]
    pip = roster["Pip Quickfingers"]
    rr = await _cast_hold_person_at_pip(gm_client, gm_ws, tavik, pip, ["STR"])
    assert not rr["data"]["base_expression"].startswith("2d20kh1"), rr["data"]
