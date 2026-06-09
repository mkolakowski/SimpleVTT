"""Phase 2d — NPC condition-driven disadvantage on save d20s.

Phase 2a/2b/2c covered PC attacks, PC saves+checks, and NPC attacks.
The last symmetry gap is NPC saves: when a PC casts a DEX-save spell
(e.g. Fireball) at a Restrained NPC target, the server rolls the
NPC's save d20 inline — and prior to v2.155.0 didn't honor RAW PHB
Appendix A's "Restrained → DEX save disadvantage."

The new `_npc_save_condition_disadvantage(target_combatant, stat_key)`
helper reads the NPC combatant's `buffs` list directly (NPCs don't
have a sheet mirror) and returns the matching condition key when the
save type qualifies. Six NPC-save construction sites are wired:
  - `/cast_spell` single-target NPC (PC caster)
  - `/place_aoe` NPC save
  - shared save-resolution helper (PC caster path)
  - PC-caster spell sites
  - `/use_open_hand_technique` NPC save
  - `/npc_cast_spell` NPC-target save

Test: Thalindra casts Fireball (DEX save) at a single Restrained
bandit via `/cast_spell` single-target path. The response's
`auto_save_breakdown` should carry `2d20kl1` instead of the bare
1d20+mod expression. The bandit's Restrained buff is seeded via
PUT /battle — no sheet mirror needed since NPCs use combatant.buffs
directly.
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID


FIREBALL_INDEX = 10  # Demo Thalindra's spell list — Fireball is a DEX
                     # save spell at index 10 (per test_cast_spell_aoe.py).


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
        json={
            "combatants": combatants,
            "turn_index": 0, "round": 1, "active": True,
        },
    )


async def _bandit_tmpl(gm_client):
    r = await gm_client.get(f"/api/campaign/{CAMPAIGN_ID}/templates")
    templates = r.json()
    return next(t for t in templates if "bandit" in t["name"].lower())


async def test_restrained_npc_dex_save_imposes_disadvantage(
    gm_client, thalindra_rested,
):
    """Thalindra casts Fireball at a Restrained bandit → the server's
    NPC DEX-save d20 expression becomes 2d20kl1+mod per Phase 2d. The
    `auto_save_breakdown` field on the /cast_spell response carries
    the resolved dice form, which should start with 2d20kl1 (RAW PHB
    Appendix A: Restrained → DEX save disadvantage).
    """
    thal = thalindra_rested
    tmpl = await _bandit_tmpl(gm_client)
    bandit_cid = "tok_p2d_restrained_bandit"
    await _seed_battle(gm_client, [
        {"id": f"tok_p2d_{thal['id']}", "char_id": thal["id"],
         "name": thal["name"], "initiative": 10,
         "hp_current": 24, "hp_max": 24, "buffs": [],
         "economy": {"action": False, "bonus": False,
                     "reaction": False, "movement": 0}},
        {"id": bandit_cid, "char_id": None,
         "token_template_id": tmpl["id"],
         "name": "Bandit", "initiative": 7,
         "hp_current": 50, "hp_max": 50,
         "buffs": [{"key": "restrained", "name": "Restrained"}],
         "economy": {"action": False, "bonus": False,
                     "reaction": False, "movement": 0}},
    ])
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
        json={
            "character_id": thal["id"],
            "spell_index": FIREBALL_INDEX,
            "slot_level": 3,
            "class_slug": "wizard",
            "target_combatant_id": bandit_cid,
            "target_name": "Bandit",
            "override": True,
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["auto_save_target_kind"] == "npc"
    breakdown = data.get("auto_save_breakdown") or ""
    assert "2d20kl1" in breakdown, (
        f"Restrained bandit's DEX save d20 should be 2d20kl1 per Phase 2d; "
        f"got auto_save_breakdown={breakdown!r}"
    )


async def test_non_restrained_npc_dex_save_unchanged(
    gm_client, thalindra_rested,
):
    """Control: a bandit WITHOUT the Restrained buff rolls a normal
    1d20 DEX save (no Phase 2d disadvantage). Catches a regression that
    would auto-disadvantage every NPC save."""
    thal = thalindra_rested
    tmpl = await _bandit_tmpl(gm_client)
    bandit_cid = "tok_p2d_clean_bandit"
    await _seed_battle(gm_client, [
        {"id": f"tok_p2d_ctrl_{thal['id']}", "char_id": thal["id"],
         "name": thal["name"], "initiative": 10,
         "hp_current": 24, "hp_max": 24, "buffs": [],
         "economy": {"action": False, "bonus": False,
                     "reaction": False, "movement": 0}},
        {"id": bandit_cid, "char_id": None,
         "token_template_id": tmpl["id"],
         "name": "Bandit", "initiative": 7,
         "hp_current": 50, "hp_max": 50, "buffs": [],
         "economy": {"action": False, "bonus": False,
                     "reaction": False, "movement": 0}},
    ])
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
        json={
            "character_id": thal["id"],
            "spell_index": FIREBALL_INDEX,
            "slot_level": 3,
            "class_slug": "wizard",
            "target_combatant_id": bandit_cid,
            "target_name": "Bandit",
            "override": True,
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    breakdown = data.get("auto_save_breakdown") or ""
    assert "2d20kl1" not in breakdown, (
        f"Non-restrained bandit should roll a straight 1d20 DEX save; "
        f"got auto_save_breakdown={breakdown!r}"
    )
