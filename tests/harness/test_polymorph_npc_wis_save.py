"""v2.99.180 — Polymorph WIS save for unwilling NPC targets.

Closes a v2.99.175 filed item. v2.99.175 rolled the WIS save
only for PC targets. v2.99.180 extends the logic to NPC targets
by reading the template's saving throws via
`_monster_template_to_sheet` + `_resolve_stat_modifier`.

The endpoint resolves the target combatant's source:
  - PC (char_id set): read sheet.abilities.WIS +
    sheet.proficiency_bonus + sheet.saving_throws.WIS
  - NPC (token_template_id set, no char_id): read the template's
    save mod via the v2.97.66 helper chain

Tests use a real NPC template fixture (Goblin) seeded in the
demo. The test combatant carries the template_id; the endpoint
looks it up and rolls the save.

Tests:
  - Unwilling NPC target → save rolled, response carries
    save_total + save_target_name (NPC's name from template)
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID


def _mkc(cid, char_id=None, token_template_id=None, name="X"):
    return {
        "id": cid,
        "char_id": char_id,
        "token_template_id": token_template_id,
        "name": name,
        "initiative": 10,
        "hp_current": 50, "hp_max": 50,
        "buffs": [],
        "economy": {"action": False, "bonus": False, "reaction": False,
                    "movement": 0},
    }


async def _seed_battle(gm_client, combatants):
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": combatants, "turn_index": 0, "round": 1,
              "active": True},
    )


@pytest_asyncio.fixture
async def thalindra_with_l4_slot(gm_client, roster):
    """PATCH Thalindra with a L4 slot + Polymorph."""
    thalindra = roster["Thalindra Moonwhisper"]
    stock_slots = {
        "1": {"total": 4, "used": 0},
        "2": {"total": 3, "used": 0},
        "3": {"total": 3, "used": 0},
        "4": {"total": 1, "used": 0},
    }
    await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{thalindra['id']}/sheet-fields",
        json={
            "spell_slots": {"wizard": stock_slots},
            "spells": [
                {"name": "Polymorph", "level": 4, "_slug": "polymorph",
                 "prepared": True, "casting_time": "1 action"},
            ],
        },
    )
    return thalindra


async def _find_token_template_id(gm_client, name_hint="goblin"):
    """Look up the first token template matching name_hint
    (case-insensitive substring). Returns the template id or
    None. v2.99.192 — endpoint is `/templates` (bare list
    response), not `/token-templates` (the pre-fix call 404'd
    so the test silently skipped).
    """
    r = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/templates",
    )
    if r.status_code != 200:
        return None
    payload = r.json()
    # Endpoint returns a bare list of {id, name, ...} dicts.
    items = payload if isinstance(payload, list) else (
        payload.get("templates") or []
    )
    for t in items:
        if name_hint.lower() in (t.get("name") or "").lower():
            return t.get("id")
    return None


async def test_unwilling_npc_target_save_rolled(
    gm_client, thalindra_with_l4_slot,
):
    """Thalindra polymorphs an unwilling NPC (Goblin template).
    Response carries save_rolled=True + save_total + save_dc +
    save_target_name (NPC name).
    """
    thalindra = thalindra_with_l4_slot
    tmpl_id = await _find_token_template_id(gm_client, "goblin")
    if tmpl_id is None:
        import pytest
        pytest.skip("No goblin template in demo — skipping NPC save test")
    th_tok = f"tok_pnws_th_{thalindra['id']}"
    npc_tok = f"tok_pnws_npc_goblin"
    await _seed_battle(gm_client, [
        _mkc(th_tok, char_id=thalindra["id"], name=thalindra["name"]),
        _mkc(npc_tok, token_template_id=tmpl_id, name="Goblin"),
    ])
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_polymorph",
        json={
            "character_id": thalindra["id"],
            "class_slug": "wizard",
            "slot_level": 4,
            "target_combatant_id": npc_tok,
            "unwilling": True,
            "override": True,
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["save_rolled"] is True, (
        f"Expected save rolled for NPC target; got data={data}"
    )
    assert isinstance(data["save_total"], int)
    assert isinstance(data["save_dc"], int)
    assert data["save_target_name"], data
