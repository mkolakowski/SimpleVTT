"""v2.158.74 — magic-items-automation Phase 1a wiring for Cloak of
Protection (uncommon wondrous item, attunement: +1 AC, +1 saving
throws).

Two read sites wired this commit:

  - ``_read_target_ac`` — adds the ``_equipped_item_effects`` walker's
    ``ac_bonus`` alongside the v2.97.39 buff walk and v2.99.95 Defense
    style. A PC wearing an equipped+attuned Cloak shows
    ``target_ac = base + 1`` at attack hit-determination time.

  - ``/api/campaign/{cid}/roll`` — for ``stat_key.endswith("_save")``
    rolls, the walker's ``save_bonus`` is appended to the expression
    (``1d20+X`` → ``1d20+X+1``) and the breakdown is annotated with
    the source item name.

Demo fixture: Thalindra Moonwhisper (Wizard 7) carries a permanent
Cloak of Protection (equipped + attuned) in her inventory; she's the
canary because she has no armor (base AC 12) so the +1 cloak bonus
shows up cleanly without the Defense Fighting Style mask the Fighter
PCs have. Her INT is saving-throw-proficient (Wizard RAW) so the save
test exercises a meaningful save expression.

Phase 1b will add Ring of Protection (same +1/+1) and Bracers of
Defense (+2 AC, no-armor + no-shield gate). Phase 2 will gate this
hook on the ``attuned: True`` field via a sheet UI checkbox + the
3-item server-side cap.
"""
import pytest

from .conftest import CAMPAIGN_ID


async def _seed_battle_with(gm_client, char_specs: list[dict]) -> None:
    """Mirror of the helper in test_buff_attack_hooks.py — drops the
    listed PCs into a fresh battle as combatants with empty buffs."""
    combatants = []
    for spec in char_specs:
        combatants.append({
            "id": spec["tok_id"],
            "char_id": spec["id"],
            "name": spec["name"],
            "initiative": spec.get("initiative", 10),
            "hp_current": spec.get("hp_max", 40),
            "hp_max": spec.get("hp_max", 40),
            "buffs": [],
            "economy": {
                "action": False, "bonus": False, "reaction": False,
                "movement": 0,
            },
        })
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={
            "combatants": combatants, "turn_index": 0, "round": 1,
            "active": True,
        },
    )


async def test_cloak_of_protection_grants_ac_bonus(gm_client, roster):
    """v2.158.74 Phase 1a AC half. Thalindra wears an equipped +
    attuned Cloak of Protection from the demo seed. Krieger swings
    his greataxe at her; the response's ``target_ac`` should report
    her base AC (12) plus the Cloak's +1 = 13. Asserting on
    target_ac directly rather than the hit verdict avoids dice
    flakiness."""
    krieger = roster["Krieger Stonefist"]
    thalindra = roster["Thalindra Moonwhisper"]
    thalindra_tok = f"tok_cloak_ac_thalindra_{thalindra['id']}"
    await _seed_battle_with(gm_client, [
        {"id": krieger["id"], "name": krieger["name"],
         "tok_id": f"tok_cloak_ac_krieger_{krieger['id']}",
         "hp_max": 55, "initiative": 14},
        {"id": thalindra["id"], "name": thalindra["name"],
         "tok_id": thalindra_tok, "hp_max": 37, "initiative": 8},
    ])

    atk = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/attack",
        json={
            "character_id": krieger["id"],
            "attack_index": 0,
            "target_combatant_id": thalindra_tok,
            "target_character_id": thalindra["id"],
            "target_name": thalindra["name"],
            "override": True,
        },
    )
    assert atk.status_code == 200, atk.text
    target_ac = atk.json().get("target_ac")
    # Thalindra base AC 12 + Cloak of Protection +1 = 13.
    assert target_ac == 13, (
        f"expected target_ac=13 (12 base + 1 Cloak of Protection), "
        f"got {target_ac}; response={atk.json()}"
    )


async def test_cloak_of_protection_grants_save_bonus(gm_client, roster):
    """v2.158.74 Phase 1a save half. Thalindra rolls an INT save
    (her INT is wizard-proficient: +3 mod + 3 prof = +6). The /roll
    endpoint detects ``stat_key='int_save'``, walks her equipped
    items via ``_equipped_item_effects``, finds the Cloak (+1 saves)
    and appends ``+1`` to the expression. The breakdown picks up the
    "Cloak of Protection" attribution."""
    thalindra = roster["Thalindra Moonwhisper"]
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/roll",
        json={
            "expression": "1d20+6",
            "stat_key": "int_save",
            "character_id": thalindra["id"],
            "note": "INT save (test)",
            "visibility": "public",
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    breakdown = data.get("breakdown", "")
    # The /roll endpoint annotates the breakdown with the source item.
    assert "Cloak of Protection" in breakdown, (
        f"expected 'Cloak of Protection' in breakdown, got: {breakdown!r}"
    )
    # And the +1 should be present in the breakdown annotation.
    assert "+1" in breakdown, (
        f"expected '+1' bonus annotation in breakdown, got: {breakdown!r}"
    )


async def test_cloak_of_protection_save_skipped_for_non_save_rolls(
    gm_client, roster,
):
    """v2.158.74 Phase 1a save-hook guard: the +1 save_bonus rewrite
    ONLY fires when ``stat_key.endswith("_save")``. An ability check
    (``stat_key="int_check"``) with the same expression must NOT get
    the cloak's +1 attribution in the breakdown — saves and checks
    are different RAW surfaces."""
    thalindra = roster["Thalindra Moonwhisper"]
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/roll",
        json={
            "expression": "1d20+3",
            "stat_key": "int_check",
            "character_id": thalindra["id"],
            "note": "INT check (test)",
            "visibility": "public",
        },
    )
    assert resp.status_code == 200, resp.text
    breakdown = resp.json().get("breakdown", "")
    assert "Cloak of Protection" not in breakdown, (
        f"Cloak save_bonus must not fire on stat_key='int_check'; "
        f"got breakdown={breakdown!r}"
    )
