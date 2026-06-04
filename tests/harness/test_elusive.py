"""v2.99.207 — Elusive (Rogue Lv 18+).

Phase F.4 final of the v2.99.193 phased completion plan. RAW
PHB p.96: "Beginning at 18th level, you are so evasive that
attackers rarely gain the upper hand against you. No attack roll
has advantage against you while you aren't incapacitated."

v1 ships:
  - `_pc_has_elusive(sheet)` — Rogue Lv 18+ gate.
  - `_target_has_elusive(campaign_id, target_combatant_id)` —
    look up the target combatant's char_id, read the Character
    sheet, gate on the helper.
  - /attack advantage resolution suppresses `has_adv` when the
    target has Elusive.

v1 simplification skips the "while you aren't incapacitated"
gate (the incapacitated condition isn't consistently mirrored to
the sheet today). Filed.

Tests:
  - Happy: Krieger raging (advantage on STR attacks) attacks Pip
    Lv 18 → attack_roll_state_applied == "elusive_suppressed".
  - Control: Krieger raging attacks Pip Lv 7 → advantage_rage.
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID


async def _patch_sheet(gm_client, char_id, fields, class_slug=None):
    body = dict(fields)
    if class_slug:
        body["class_slug"] = class_slug
    r = await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-fields",
        json=body,
    )
    assert r.status_code == 200, r.text


async def _seed_battle_with_raging_krieger(gm_client, krieger, pip):
    """Krieger seeded with active rage buff; Pip is the target."""
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": [
            {"id": f"tok_el_kr_{krieger['id']}",
             "char_id": krieger["id"], "name": krieger["name"],
             "initiative": 12, "hp_current": 75, "hp_max": 75,
             "buffs": [{
                 "key": "rage", "name": "Rage",
                 "concentration": False,
                 "duration_rounds": 10, "duration_max": 10,
                 "effects": {
                     "advantage_on": ["str_attack"],
                     "resistance_to": ["bludgeoning", "piercing",
                                       "slashing"],
                 },
             }],
             "economy": {"action": False, "bonus": False,
                         "reaction": False, "movement": 0}},
            {"id": f"tok_el_pip_{pip['id']}",
             "char_id": pip["id"], "name": pip["name"],
             "initiative": 10, "hp_current": 47, "hp_max": 47,
             "buffs": [],
             "economy": {"action": False, "bonus": False,
                         "reaction": False, "movement": 0}},
        ], "turn_index": 0, "round": 1, "active": True},
    )


async def test_elusive_suppresses_advantage_at_lv18(
    gm_client, roster,
):
    """Krieger raging (advantage on str_attack) attacks Pip Lv 18
    → attack_roll_state_applied == "elusive_suppressed".
    """
    krieger = roster["Krieger Stonefist"]
    pip = roster["Pip Quickfingers"]
    pre_level = 7
    await _patch_sheet(
        gm_client, pip["id"], {"level": 18},
        class_slug="rogue",
    )
    try:
        await _seed_battle_with_raging_krieger(gm_client, krieger, pip)
        pip_tok = f"tok_el_pip_{pip['id']}"
        # Greataxe (attack_index=0) is STR-based melee.
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/attack",
            json={
                "character_id": krieger["id"],
                "attack_index": 0,
                "target_combatant_id": pip_tok,
                "override": True,
            },
        )
        assert r.status_code == 200, r.text
        data = r.json()
        rsa = data.get("roll_state_applied") or ""
        assert "elusive" in rsa, (
            f"v2.99.207: Elusive should suppress advantage; "
            f"got roll_state_applied={rsa!r}"
        )
    finally:
        await _patch_sheet(
            gm_client, pip["id"], {"level": pre_level},
            class_slug="rogue",
        )


async def test_elusive_skips_below_lv18(
    gm_client, roster,
):
    """Control: Krieger raging attacks Pip Lv 7 → advantage_rage
    fires (Elusive doesn't suppress).
    """
    krieger = roster["Krieger Stonefist"]
    pip = roster["Pip Quickfingers"]
    await _seed_battle_with_raging_krieger(gm_client, krieger, pip)
    pip_tok = f"tok_el_pip_{pip['id']}"
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/attack",
        json={
            "character_id": krieger["id"],
            "attack_index": 0,
            "target_combatant_id": pip_tok,
            "override": True,
        },
    )
    assert r.status_code == 200, r.text
    data = r.json()
    rsa = data.get("roll_state_applied") or ""
    assert "elusive" not in rsa, (
        f"v2.99.207: Elusive shouldn't fire at Lv 7; "
        f"got roll_state_applied={rsa!r}"
    )
    # Rage advantage should still fire.
    assert "advantage" in rsa or "rage" in rsa, (
        f"v2.99.207: expected rage advantage to fire at Lv 7; "
        f"got roll_state_applied={rsa!r}"
    )
