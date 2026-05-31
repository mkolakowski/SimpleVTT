"""v2.99.7 — Monster init-tracker sheet contract.

Phase 1.5 follow-up filed by v2.99.7. Codifies the three wiring
points that the v2.99.7 commit added so a future regression that
breaks any of them fails CI instead of silently regressing manual
verification.

Coverage:

1. ``test_monster_sheet_page_exposes_globals`` — GET
   ``/campaign/{cid}/monster-template/{tid}/sheet?combatant_id=...``
   returns 200 + HTML containing the three v2.99.7 JS globals
   (``IS_MONSTER_SHEET`` / ``MONSTER_NAME`` / ``MONSTER_COMBATANT_ID``).
   These globals drive the click-through routing for
   ability/save/skill rolls and Strike attacks; if any goes missing,
   the click handlers silently fall through to the PC pipeline and
   404 or mis-attribute.

2. ``test_monster_roll_attributes_to_actor_name`` — POST
   ``/api/campaign/{cid}/roll`` with ``skip_roll_state: True`` +
   ``actor_name: <name>`` (the body shape the v2.99.7 monster-mode
   branch sends from ``wireDnd5eRollButtons``) → the ``roll``
   broadcast carries ``no_char_attribution: True`` + ``actor_name``
   so the roll log attributes to the monster name instead of the
   GM's first owned PC.

3. ``test_monster_sheet_strike_routes_to_npc_attack`` — POST
   ``/api/campaign/{cid}/npc_attack`` with the body shape the
   v2.99.7 ``.atk-strike`` monster-mode branch sends (combatant_id
   + action_name + attack_bonus + damage + damage_type + range
   + target_combatant_id) → 200 + ``weapon_attack`` broadcast with
   ``is_npc_attack: True``. (Cross-checks against test_npc_attack
   which already covers the /npc_attack endpoint's general shape;
   this test specifically asserts the v2.99.7 Strike-handler body
   shape lands cleanly.)
"""
import httpx

from .conftest import CAMPAIGN_ID
from .helpers import BASE_URL


def _mkc(cid, char_id=None, hp_cur=30, hp_max=30, name="X", template_id=None):
    out = {
        "id": cid,
        "char_id": char_id,
        "name": name,
        "initiative": 10,
        "hp_current": hp_cur,
        "hp_max": hp_max,
        "buffs": [],
        "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0},
    }
    if template_id is not None:
        out["token_template_id"] = template_id
    return out


async def _seed_battle(gm_client, combatants):
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": combatants, "turn_index": 0, "round": 1, "active": True},
    )


async def _bandit_template_id(gm_client) -> int:
    r = await gm_client.get(f"/api/campaign/{CAMPAIGN_ID}/templates")
    templates = r.json()
    bandit = next(
        (t for t in templates
         if "bandit" in (t.get("name") or "").lower()
         and "captain" not in (t.get("name") or "").lower()),
        None,
    )
    assert bandit is not None, (
        f"No Bandit template in demo seed; got {[t['name'] for t in templates]}"
    )
    return int(bandit["id"])


async def test_monster_sheet_page_exposes_globals(gm_client):
    """Sheet page HTML contains the three v2.99.7 globals."""
    tid = await _bandit_template_id(gm_client)
    combatant_id = "tok_monster_sheet_test"
    url = (
        f"/campaign/{CAMPAIGN_ID}/monster-template/{tid}/sheet"
        f"?combatant_id={combatant_id}"
    )
    resp = await gm_client.get(url)
    assert resp.status_code == 200, resp.text
    body = resp.text
    assert "window.IS_MONSTER_SHEET = true;" in body, (
        "v2.99.7 IS_MONSTER_SHEET global missing from monster sheet "
        "page — Strike + roll click handlers will fall through to PC "
        "pipeline and 404"
    )
    # Bandit is the template name; MONSTER_NAME holds it.
    assert '"Bandit"' in body or "'Bandit'" in body, (
        "v2.99.7 MONSTER_NAME global doesn't appear to be populated "
        "from the template name"
    )
    assert "window.MONSTER_COMBATANT_ID" in body, (
        "v2.99.7 MONSTER_COMBATANT_ID global missing — Strike clicks "
        "without it surface a toast instead of firing /npc_attack"
    )


async def test_monster_roll_attributes_to_actor_name(gm_client, gm_ws):
    """v2.99.7 monster-mode /roll branch attributes to actor_name."""
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/roll",
        json={
            "expression": "1d20+3",
            "visibility": "public",
            "note": "STR check",
            "skip_roll_state": True,
            "actor_name": "Test Bandit Mob",
        },
    )
    assert resp.status_code == 200, resp.text

    msg = await gm_ws.wait_for("roll")
    data = msg["data"]
    assert data.get("no_char_attribution") is True, (
        "v2.99.7 contract: skip_roll_state + no character_id should "
        "flip no_char_attribution so the client renders the actor_name "
        "instead of falling through to USER_CHAR_NAMES"
    )
    assert data.get("actor_name") == "Test Bandit Mob"
    assert data.get("char_name") is None


async def test_monster_sheet_strike_routes_to_npc_attack(
    gm_client, gm_ws, roster,
):
    """v2.99.7 monster-mode .atk-strike branch routes to /npc_attack
    with the structured attack fields the sheet's renderAttacks parses
    out of the projected monster sheet."""
    pip = roster["Pip Quickfingers"]
    tid = await _bandit_template_id(gm_client)
    bandit_cid = "tok_monster_sheet_strike"
    pip_cid = f"tok_monster_sheet_strike_pip_{pip['id']}"
    await _seed_battle(gm_client, [
        _mkc(bandit_cid, hp_cur=11, hp_max=11,
             name="Bandit", template_id=tid),
        _mkc(pip_cid, pip["id"], hp_cur=30, hp_max=30, name=pip["name"]),
    ])
    # Body shape mirrors what the v2.99.7 monster-mode .atk-strike
    # branch sends — attack_bonus comes from a.attack_bonus
    # (post-renderAttacks parse fallback that now includes atk_bonus).
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/npc_attack",
        json={
            "combatant_id": bandit_cid,
            "action_id": "scimitar",
            "action_name": "Scimitar",
            "attack_bonus": "+3",
            "damage": "1d6+1",
            "damage_type": "slashing",
            "range": "5 ft",
            "target_combatant_id": pip_cid,
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["ok"] is True
    assert data["is_npc_attack"] is True

    msg = await gm_ws.wait_for("weapon_attack")
    bd = msg["data"]
    assert bd["caster_char_name"] == "Bandit"
    assert bd["caster_char_id"] is None
    assert bd["caster_combatant_id"] == bandit_cid
    assert bd["is_npc_attack"] is True
