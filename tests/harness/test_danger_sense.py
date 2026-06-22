"""v2.52.0 — Danger Sense (Barbarian Lv 2+) Dex-save advantage.

When a Barbarian Lv 2+ rolls a Dex save, the d20 rolls with
advantage (2d20kh1) instead of straight 1d20. RAW: "you have
advantage on Dexterity saving throws against effects that you can
see, such as traps and spells."

Server-side helper ``_pc_has_danger_sense_on_dex_save`` gates the
expression swap. Wired into:
  - `/place_aoe` PC branch (server-rolled save) — the expr passed to
    dice_mod.roll becomes ``2d20kh1+CON``
  - `/cast_spell` single-target PC Dex save — the roll_request's
    ``base_expression`` is set to ``2d20kh1`` (instead of ``1d20``)
    so the PC's own client-side roll uses advantage
  - `/cast_spell` AoE PC Dex save — same roll_request modification

When the helper fires, a ``feature_used`` broadcast with
``source: "danger-sense"`` surfaces the trigger.

Tests:
  - happy single-target: Tavik casts a Dex-save spell at Krieger
    (Barbarian 5) → roll_request broadcast carries
    base_expression="2d20kh1" + feature_used(source=danger-sense).
  - control non-barbarian: Tavik casts the same spell at Tavik's
    own party-mate Pip → base_expression="1d20" + no Danger Sense
    broadcast (Pip is Rogue 7, has Evasion but not Danger Sense).
  - non-DEX save: Tavik casts a WIS-save spell at Krieger →
    base_expression="1d20" + no broadcast (Danger Sense is Dex-only).
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID


# Thalindra's wizard spell list — see app/demo_seed.py and
# tests/harness/test_cast_spell_aoe.py.
FIREBALL_INDEX = 10        # Fireball (8d6 fire, DEX save) in Thalindra's
                           # *stored* sheet. Was 7, but the seed drifted and
                           # stored-index 7 is now Web — a DEX-save AoE that
                           # deals no damage, so this test passed for the
                           # wrong spell. Aligned with test_cast_spell_aoe.py.
HOLD_PERSON_TAVIK_INDEX = 8  # Tavik's cleric spell list — WIS save


@pytest_asyncio.fixture
async def thalindra_rested(gm_client, roster):
    thal = roster["Thalindra Moonwhisper"]
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{thal['id']}/rest",
        json={"type": "long"},
    )
    return thal


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


def _danger_sense_broadcasts(gm_ws, character_id: int) -> list:
    return [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "danger-sense"
        and (m.get("data") or {}).get("character_id") == character_id
    ]


def _roll_request_broadcast(gm_ws):
    msgs = gm_ws.buffered("roll_request")
    return msgs[-1] if msgs else None


async def test_danger_sense_advantage_on_dex_save(
    gm_client, gm_ws, roster, thalindra_rested,
):
    """Thalindra casts Fireball at Krieger (Barbarian 5) → the
    roll_request broadcast for Krieger's Dex save carries
    base_expression="2d20kh1" AND a feature_used(source=danger-sense)
    broadcast fires for him.
    """
    thal = thalindra_rested
    krieger = roster["Krieger Stonefist"]
    await _seed_battle(gm_client, [
        {"id": f"tok_ds_{thal['id']}", "char_id": thal["id"],
         "name": thal["name"], "initiative": 10, "hp_current": 24, "hp_max": 24,
         "buffs": [],
         "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0}},
        {"id": f"tok_ds_{krieger['id']}", "char_id": krieger["id"],
         "name": krieger["name"], "initiative": 8, "hp_current": 55, "hp_max": 55,
         "buffs": [],
         "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0}},
    ])
    gm_ws.mark()
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
        json={
            "character_id": thal["id"],
            "spell_index": FIREBALL_INDEX,
            "slot_level": 3,
            "class_slug": "wizard",
            "target_combatant_id": f"tok_ds_{krieger['id']}",
            "target_character_id": krieger["id"],
            "target_name": krieger["name"],
            "override": True,
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["auto_save_ability"] == "DEX"
    assert data["auto_save_target_kind"] == "pc"
    assert data["auto_save_prompted"] is True

    rr = _roll_request_broadcast(gm_ws)
    assert rr is not None, "expected a roll_request broadcast for Krieger's Dex save"
    assert rr["data"]["base_expression"] == "2d20kh1", (
        f"Danger Sense should set base_expression to 2d20kh1; "
        f"got {rr['data']['base_expression']!r}"
    )
    ds_msgs = _danger_sense_broadcasts(gm_ws, krieger["id"])
    assert ds_msgs, (
        f"expected feature_used(source=danger-sense) for Krieger; "
        f"buffered: {[(m.get('type'), (m.get('data') or {}).get('source')) for m in gm_ws.buffered()]}"
    )


async def test_danger_sense_skips_non_barbarian(
    gm_client, gm_ws, roster, thalindra_rested,
):
    """Control: Thalindra casts Fireball at Pip (Rogue Lv 7, has
    Evasion but not Danger Sense). roll_request base_expression
    stays "1d20" and no Danger Sense broadcast fires.
    """
    thal = thalindra_rested
    pip = roster["Pip Quickfingers"]
    await _seed_battle(gm_client, [
        {"id": f"tok_ds_{thal['id']}", "char_id": thal["id"],
         "name": thal["name"], "initiative": 10, "hp_current": 24, "hp_max": 24,
         "buffs": [],
         "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0}},
        {"id": f"tok_ds_{pip['id']}", "char_id": pip["id"],
         "name": pip["name"], "initiative": 8, "hp_current": 47, "hp_max": 47,
         "buffs": [],
         "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0}},
    ])
    gm_ws.mark()
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
        json={
            "character_id": thal["id"],
            "spell_index": FIREBALL_INDEX,
            "slot_level": 3,
            "class_slug": "wizard",
            "target_combatant_id": f"tok_ds_{pip['id']}",
            "target_character_id": pip["id"],
            "target_name": pip["name"],
            "override": True,
        },
    )
    assert resp.status_code == 200, resp.text

    rr = _roll_request_broadcast(gm_ws)
    assert rr is not None
    assert rr["data"]["base_expression"] == "1d20", (
        f"non-Barbarian PC should have base_expression=1d20; "
        f"got {rr['data']['base_expression']!r}"
    )
    ds_msgs = _danger_sense_broadcasts(gm_ws, pip["id"])
    assert not ds_msgs, (
        f"Danger Sense broadcast should NOT fire for Pip (Rogue): {ds_msgs}"
    )


async def test_danger_sense_skips_non_dex_save(
    gm_client, gm_ws, roster, tavik_rested,
):
    """Hold Person is a WIS save. Even though Krieger has Danger
    Sense, it's a Dex-only feature — base_expression stays "1d20"
    and no broadcast fires.
    """
    tavik = tavik_rested
    krieger = roster["Krieger Stonefist"]
    await _seed_battle(gm_client, [
        {"id": f"tok_ds_{tavik['id']}", "char_id": tavik["id"],
         "name": tavik["name"], "initiative": 10, "hp_current": 30, "hp_max": 30,
         "buffs": [],
         "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0}},
        {"id": f"tok_ds_{krieger['id']}", "char_id": krieger["id"],
         "name": krieger["name"], "initiative": 8, "hp_current": 55, "hp_max": 55,
         "buffs": [],
         "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0}},
    ])
    gm_ws.mark()
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
        json={
            "character_id": tavik["id"],
            "spell_index": HOLD_PERSON_TAVIK_INDEX,
            "slot_level": 2,
            "class_slug": "cleric",
            "target_combatant_id": f"tok_ds_{krieger['id']}",
            "target_character_id": krieger["id"],
            "target_name": krieger["name"],
            "override": True,
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["auto_save_ability"] == "WIS"

    rr = _roll_request_broadcast(gm_ws)
    assert rr is not None
    assert rr["data"]["base_expression"] == "1d20", (
        f"Wis save should NOT get Danger Sense advantage; "
        f"got base_expression={rr['data']['base_expression']!r}"
    )
    ds_msgs = _danger_sense_broadcasts(gm_ws, krieger["id"])
    assert not ds_msgs, (
        f"Danger Sense broadcast should NOT fire for Wis save: {ds_msgs}"
    )
