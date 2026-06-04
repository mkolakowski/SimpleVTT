"""v2.99.196 — Dragonborn ancestry → damage resistance helper.

Phase A.3 of the v2.99.193 phased completion plan. v2.99.20 ships
Magnus Hexbinder (Bronze Dragonborn) with `damage_resistances:
["lightning"]` hand-typed on the sheet — the existing
`_resistance_halve` reads the explicit list. v2.99.196 adds a
helper `_dragonborn_ancestry_resistance(sheet)` that derives the
damage type from `sheet.dragonborn_ancestry` per the PHB p.34
table (Bronze → lightning, Red → fire, etc.). `_resistance_halve`
gains a fallback that fires when (a) the explicit list doesn't
match the type and (b) the ancestry-derived type does.

Future Dragonborn PCs ship just the `dragonborn_ancestry` field;
the resistance auto-derives. Existing hand-typed PCs keep working
through the explicit-list branch.

Tests:
  - Bronze ancestry derived: clear Rowan's explicit
    damage_resistances + set dragonborn_ancestry="bronze" → lightning
    damage halved via the fallback. PATCH restored.
  - Red ancestry → fire resistance auto-derives. Demonstrates the
    helper is ancestry-keyed, not hand-typed.
  - Non-Dragonborn PC: setting dragonborn_ancestry doesn't apply
    (Tavik is a Dwarf; the gate `_race_slug_from_sheet != "dragonborn"`
    short-circuits).
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID


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
        f"/campaign/{CAMPAIGN_ID}/settings", data=form, follow_redirects=False,
    )


@pytest_asyncio.fixture
async def auto_apply_on(gm_client):
    await _set_auto_apply(gm_client, True)
    yield
    await _set_auto_apply(gm_client, False)


async def _patch_sheet(gm_client, char_id, fields: dict):
    r = await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-fields",
        json=fields,
    )
    assert r.status_code == 200, r.text


async def _seed_battle(gm_client, combatants):
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": combatants, "turn_index": 0,
              "round": 1, "active": True},
    )


def _tok(char):
    return {
        "id": f"tok_dbar_{char['id']}",
        "char_id": char["id"],
        "name": char["name"],
        "initiative": 10,
        "hp_current": 30, "hp_max": 30,
        "buffs": [],
        "economy": {"action": False, "bonus": False,
                    "reaction": False, "movement": 0},
    }


async def test_bronze_ancestry_derives_lightning_resistance(
    gm_client, roster, auto_apply_on,
):
    """Rowan: clear `damage_resistances` + set
    `dragonborn_ancestry="bronze"` → lightning damage to Rowan via
    /attack still halves (v2.99.196 fallback fires).
    """
    rowan = roster["Magnus Hexbinder"]
    # Magnus's seed values (per app/demo_seed.py): damage_resistances
    # = ["lightning"], no dragonborn_ancestry field. Restore on exit.
    pre_resists = ["lightning"]
    pre_ancestry = ""
    try:
        # Clear explicit list + set ancestry only.
        await _patch_sheet(gm_client, rowan["id"], {
            "damage_resistances": [],
            "dragonborn_ancestry": "bronze",
        })
        rowan_tok = f"tok_dbar_{rowan['id']}"
        npc_tok = "tok_dbar_caster"
        await _seed_battle(gm_client, [
            _tok(rowan),
            {"id": npc_tok, "name": "Lightning Elemental",
             "initiative": 12, "hp_current": 40, "hp_max": 40,
             "buffs": [],
             "economy": {"action": False, "bonus": False,
                         "reaction": False, "movement": 0}},
        ])
        # Use /npc_attack with lightning damage; verify the damage
        # halves through the v2.99.196 fallback.
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/npc_attack",
            json={
                "combatant_id": npc_tok,
                "action_id": "shock",
                "action_name": "Shock",
                "attack_bonus": "+50",  # always hit
                "damage": "1d1+19",  # flat 20 damage for clean halving math
                "damage_type": "lightning",
                "range": "5 ft",
                "target_combatant_id": rowan_tok,
            },
        )
        assert r.status_code == 200, r.text
        data = r.json()
        # /npc_attack response carries `auto_attack_damage_applied`
        # — should be 10 (20 halved by Bronze Dragonborn lightning
        # resistance via the v2.99.196 ancestry fallback).
        applied = data.get("damage_applied")
        assert applied is not None and applied == 10, (
            f"v2.99.196: Bronze Dragonborn ancestry should halve "
            f"20 lightning damage to 10 via ancestry-derived "
            f"resistance; got {applied}"
        )
    finally:
        await _patch_sheet(gm_client, rowan["id"], {
            "damage_resistances": pre_resists,
            "dragonborn_ancestry": pre_ancestry,
        })


async def test_red_ancestry_derives_fire_resistance(
    gm_client, roster, auto_apply_on,
):
    """Rowan: PATCH to Red ancestry → fire damage halves via the
    ancestry-derived fallback. Demonstrates the helper isn't
    hand-typed for Bronze.
    """
    rowan = roster["Magnus Hexbinder"]
    # Magnus's seed values (per app/demo_seed.py): damage_resistances
    # = ["lightning"], no dragonborn_ancestry field. Restore on exit.
    pre_resists = ["lightning"]
    pre_ancestry = ""
    try:
        await _patch_sheet(gm_client, rowan["id"], {
            "damage_resistances": [],
            "dragonborn_ancestry": "red",
        })
        rowan_tok = f"tok_dbar_{rowan['id']}"
        npc_tok = "tok_dbar_fire"
        await _seed_battle(gm_client, [
            _tok(rowan),
            {"id": npc_tok, "name": "Fire Elemental",
             "initiative": 12, "hp_current": 40, "hp_max": 40,
             "buffs": [],
             "economy": {"action": False, "bonus": False,
                         "reaction": False, "movement": 0}},
        ])
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/npc_attack",
            json={
                "combatant_id": npc_tok,
                "action_id": "scorch",
                "action_name": "Scorch",
                "attack_bonus": "+50",
                "damage": "1d1+19",
                "damage_type": "fire",
                "range": "5 ft",
                "target_combatant_id": rowan_tok,
            },
        )
        assert r.status_code == 200, r.text
        data = r.json()
        applied = data.get("damage_applied")
        assert applied is not None and applied == 10, (
            f"v2.99.196: Red Dragonborn ancestry should halve 20 "
            f"fire damage to 10; got {applied}"
        )
    finally:
        await _patch_sheet(gm_client, rowan["id"], {
            "damage_resistances": pre_resists,
            "dragonborn_ancestry": pre_ancestry,
        })


async def test_non_dragonborn_ignores_ancestry_field(
    gm_client, roster, auto_apply_on,
):
    """Control: Tavik (Hill Dwarf) PATCH'd with dragonborn_ancestry="red"
    → fire damage NOT halved (the gate
    `_race_slug_from_sheet != "dragonborn"` short-circuits).
    """
    tavik = roster["Brother Tavik Stonebrow"]
    pre_ancestry = ""  # Tavik's seed has no dragonborn_ancestry field
    try:
        await _patch_sheet(gm_client, tavik["id"], {
            "dragonborn_ancestry": "red",
        })
        tavik_tok = f"tok_dbar_{tavik['id']}"
        npc_tok = "tok_dbar_ne_fire"
        await _seed_battle(gm_client, [
            _tok(tavik),
            {"id": npc_tok, "name": "Mephit",
             "initiative": 12, "hp_current": 40, "hp_max": 40,
             "buffs": [],
             "economy": {"action": False, "bonus": False,
                         "reaction": False, "movement": 0}},
        ])
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/npc_attack",
            json={
                "combatant_id": npc_tok,
                "action_id": "flame",
                "action_name": "Flame",
                "attack_bonus": "+50",
                "damage": "1d1+19",
                "damage_type": "fire",
                "range": "5 ft",
                "target_combatant_id": tavik_tok,
            },
        )
        assert r.status_code == 200, r.text
        data = r.json()
        applied = data.get("damage_applied")
        # No halving — Tavik (Hill Dwarf) takes full 20 fire damage.
        # If applied isn't 20, surface the response for diagnosis.
        assert applied == 20, (
            f"v2.99.196: dragonborn_ancestry on a non-Dragonborn "
            f"PC should not derive resistance; full response={data}"
        )
    finally:
        await _patch_sheet(gm_client, tavik["id"], {
            "dragonborn_ancestry": pre_ancestry,
        })
