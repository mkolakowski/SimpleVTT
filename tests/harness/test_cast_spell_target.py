"""Phase T.1 — /cast_spell accepts target body fields.

v2.22.0: targeting wiring. /cast_spell now accepts the same target
descriptors that /attack has accepted since Phase B (v2.20.0):
``target_combatant_id`` (preferred — stable hub combatant id),
``target_character_id`` (PC), and ``target_name`` (NPC fallback). The
endpoint resolves them via the existing _resolve_target_combatant
helper and adds them to the spell_cast WS broadcast + the response so
the chat card / sheet-side toast can name the target.

Tests:
  - happy path: Thalindra casts Magic Missile at Pip; spell_cast
    broadcast carries target_character_id + target_name
  - target_combatant_id wins when both forms passed
  - cast without target: broadcast still fires, fields empty
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID


@pytest_asyncio.fixture
async def thalindra_full(gm_client, roster):
    thal = roster["Thalindra Moonwhisper"]
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{thal['id']}/rest",
        json={"type": "long"},
    )
    return thal


async def _seed_battle(gm_client, char_entries):
    """``char_entries`` is a list of either ints (just char_id; name
    auto-filled as "PC {id}") or dicts ``{id, name}``."""
    combatants = []
    for e in char_entries:
        if isinstance(e, dict):
            cid = e["id"]
            name = e.get("name") or f"PC {cid}"
        else:
            cid = e
            name = f"PC {cid}"
        combatants.append({
            "id": f"tok_test_{cid}",
            "char_id": cid,
            "name": name,
            "initiative": 10,
            "hp_current": 30,
            "hp_max": 30,
            "buffs": [],
            "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0},
        })
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": combatants, "turn_index": 0, "round": 1, "active": True},
    )


def _find_spell_index(roster_char, slug):
    """Helper: look up a spell on a roster fixture entry. Tests can't
    fetch char.sheet directly so we rely on stable spell order in the
    demo seed factories. Magic Missile is wizard spell index 1 in
    _wizard_sheet (see app/demo_seed.py).
    """
    raise NotImplementedError("Use the literal index; the demo seed is stable.")


async def test_cast_spell_with_target_character_id(gm_client, gm_ws, thalindra_full, roster):
    """Thalindra casts a spell at Pip. spell_cast broadcast carries
    target_character_id + target_name."""
    thal = thalindra_full
    pip = roster["Pip Quickfingers"]
    await _seed_battle(gm_client, [
        {"id": thal["id"], "name": thal["name"]},
        {"id": pip["id"], "name": pip["name"]},
    ])

    # Magic Missile is index 1 in _wizard_sheet's spells list (after
    # Fire Bolt at index 0). L1 spell.
    gm_ws.mark()
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
        json={
            "character_id": thal["id"],
            "spell_index": 1,
            "slot_level": 1,
            "class_slug": "wizard",
            "target_character_id": pip["id"],
            "target_name": pip["name"],
            "override": True,
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["ok"] is True
    # Echoed target descriptors in the response.
    assert data["target_character_id"] == pip["id"]
    assert data["target_name"] == pip["name"]
    # combatant_id resolved because Pip is in the seeded battle.
    assert data["target_combatant_id"] == f"tok_test_{pip['id']}"

    # spell_cast broadcast also carries the target.
    msg = await gm_ws.wait_for("spell_cast")
    payload = msg["data"]
    assert payload["target_character_id"] == pip["id"]
    assert payload["target_name"] == pip["name"]
    assert payload["target_combatant_id"] == f"tok_test_{pip['id']}"
    assert payload["caster_char_id"] == thal["id"]


async def test_cast_spell_target_combatant_id_wins(gm_client, thalindra_full, roster):
    """When both target_combatant_id and target_character_id are
    passed, combatant_id wins (caller is being explicit about which
    init slot they meant).
    """
    thal = thalindra_full
    pip = roster["Pip Quickfingers"]
    await _seed_battle(gm_client, [thal["id"], pip["id"]])
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
        json={
            "character_id": thal["id"],
            "spell_index": 1,
            "slot_level": 1,
            "class_slug": "wizard",
            "target_combatant_id": "tok_test_explicit",  # not the resolved one
            "target_character_id": pip["id"],
            "override": True,
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    # Explicit combatant_id wins over the char_id resolution.
    assert data["target_combatant_id"] == "tok_test_explicit"


async def test_cast_spell_no_target(gm_client, thalindra_full):
    """No target — endpoint succeeds, fields empty / null."""
    thal = thalindra_full
    await _seed_battle(gm_client, [thal["id"]])
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
        json={
            "character_id": thal["id"],
            "spell_index": 1,
            "slot_level": 1,
            "class_slug": "wizard",
            "override": True,
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["ok"] is True
    assert data["target_combatant_id"] == ""
    assert data["target_character_id"] is None
    assert data["target_name"] == ""


async def test_cast_spell_target_npc_by_name(gm_client, thalindra_full):
    """Target an NPC via target_name only; combatant lookup happens
    server-side. We seed a battle with an NPC combatant whose name
    matches."""
    thal = thalindra_full
    # Seed battle with an NPC combatant (no char_id, name = "Vex").
    combatants = [
        {
            "id": f"tok_test_{thal['id']}",
            "char_id": thal["id"],
            "name": "Thalindra",
            "initiative": 10, "hp_current": 30, "hp_max": 30,
            "buffs": [],
            "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0},
        },
        {
            "id": "tok_vex_npc",
            "char_id": None,
            "name": "Vex",
            "initiative": 8, "hp_current": 65, "hp_max": 65,
            "buffs": [],
            "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0},
        },
    ]
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": combatants, "turn_index": 0, "round": 1, "active": True},
    )
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
        json={
            "character_id": thal["id"],
            "spell_index": 1,
            "slot_level": 1,
            "class_slug": "wizard",
            "target_name": "Vex",
            "override": True,
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["target_combatant_id"] == "tok_vex_npc"
    assert data["target_name"] == "Vex"
