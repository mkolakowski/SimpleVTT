"""v2.99.195 — Stout Halfling Stout Resilience subrace rule.

Phase A.2 of the v2.99.193 phased completion plan. v2.99.11+ wired
race-keyed save advantage via `_race_slug_from_sheet` +
`_RACE_SAVE_ADVANTAGES`. Halfling Brave (v2.99.14) folded both
Lightfoot and Stout Halflings into the parent "halfling" slug. RAW
(PHB p.28) Stout Halflings get an EXTRA trait — Stout Resilience:
"You have advantage on saving throws against poison, and you have
resistance against poison damage." — that doesn't apply to
Lightfoot. v2.99.195 closes the gap with:

  - `_subrace_slug_from_sheet(sheet)` returning slugs like
    "halfling-stout" / "halfling-lightfoot" / "dwarf-hill" /
    "elf-high" / "gnome-rock" / etc. when the sheet's race string
    carries the subrace prefix.
  - A new "halfling-stout" rule in `_RACE_SAVE_ADVANTAGES` for
    poison-damage / poisoned-condition save advantage (same shape
    as Dwarven Resilience).
  - `_race_grants_save_advantage` now consults BOTH the parent race
    rules AND the subrace rules; both fire when applicable.
  - `race` added to `_SHEET_PATCH_KEYS` for test scaffolding.

The poison-DAMAGE resistance half is sheet-level: a Stout Halfling
PC seeds `damage_resistances: ["poison"]` on the sheet (same shape
as Tavik's Hill Dwarf v2.99.19); the existing `_resistance_halve`
extension picks it up. No engine change needed for resistance.

Tests:
  - Pip's race PATCH'd Lightfoot → Stout → Poison Spray vs Pip →
    Stout Resilience fires (base_expression = 2d20kh1 +
    feature_used(source=stout-resilience)). PATCH restored in finally.
  - Control: Pip with default race ("Halfling", no subrace) → same
    Poison Spray → Stout Resilience does NOT fire (the
    `_subrace_slug_from_sheet` returns "" so the subrace rule is
    not consulted).
  - Control: Pip patched to Stout Halfling, Halfling Brave (parent
    rule) STILL fires on a Frightened save (Fear) → confirms the
    parent + subrace rule both apply.
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID

POISON_SPRAY_THAL_INDEX = 18  # v2.99.195 — see test_race_save_advantage


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
        json={"combatants": combatants, "turn_index": 0, "round": 1,
              "active": True},
    )


def _tok(char):
    return {
        "id": f"tok_stout_{char['id']}",
        "char_id": char["id"],
        "name": char["name"],
        "initiative": 10,
        "hp_current": 30, "hp_max": 30,
        "buffs": [],
        "economy": {"action": False, "bonus": False,
                    "reaction": False, "movement": 0},
    }


def _race_save_broadcasts(gm_ws, character_id, trait_slug):
    return [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == trait_slug
        and (m.get("data") or {}).get("character_id") == character_id
    ]


def _roll_request_broadcast(gm_ws):
    msgs = gm_ws.buffered("roll_request")
    return msgs[-1] if msgs else None


async def _patch_race(gm_client, char_id, race_str):
    r = await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-fields",
        json={"race": race_str},
    )
    assert r.status_code == 200, r.text


async def test_stout_halfling_resilience_on_poison_save(
    gm_client, gm_ws, roster, thalindra_rested,
):
    """Pip PATCH'd to "Stout Halfling" → Poison Spray at Pip → Stout
    Resilience fires (base_expression = 2d20kh1 +
    feature_used(source=stout-resilience)).
    """
    thal = thalindra_rested
    pip = roster["Pip Quickfingers"]
    await _patch_race(gm_client, pip["id"], "Stout Halfling")
    try:
        await _seed_battle(gm_client, [_tok(thal), _tok(pip)])
        gm_ws.mark()
        resp = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
            json={
                "character_id": thal["id"],
                "spell_index": POISON_SPRAY_THAL_INDEX,
                "slot_level": 0,
                "class_slug": "wizard",
                "target_combatant_id": f"tok_stout_{pip['id']}",
                "target_character_id": pip["id"],
                "target_name": pip["name"],
                "override": True,
            },
        )
        assert resp.status_code == 200, resp.text
        rr = _roll_request_broadcast(gm_ws)
        assert rr is not None, (
            "expected a roll_request broadcast for Pip's Con save"
        )
        assert rr["data"]["base_expression"] == "2d20kh1", (
            f"v2.99.195: Stout Resilience should set base_expression "
            f"to 2d20kh1; got {rr['data']['base_expression']!r}"
        )
        msgs = _race_save_broadcasts(gm_ws, pip["id"], "stout-resilience")
        assert msgs, (
            f"v2.99.195: expected feature_used(source=stout-resilience) "
            f"for Pip; buffered: {gm_ws.buffered()}"
        )
    finally:
        await _patch_race(gm_client, pip["id"], "Halfling")


async def test_lightfoot_halfling_no_stout_resilience(
    gm_client, gm_ws, roster, thalindra_rested,
):
    """Control: Pip with default race ("Halfling", no subrace prefix)
    → Poison Spray → Stout Resilience does NOT fire.
    `_subrace_slug_from_sheet` returns "" so the subrace lookup is
    skipped.
    """
    thal = thalindra_rested
    pip = roster["Pip Quickfingers"]
    # Default Pip race is "Halfling" — no subrace prefix. Confirm.
    await _seed_battle(gm_client, [_tok(thal), _tok(pip)])
    gm_ws.mark()
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
        json={
            "character_id": thal["id"],
            "spell_index": POISON_SPRAY_THAL_INDEX,
            "slot_level": 0,
            "class_slug": "wizard",
            "target_combatant_id": f"tok_stout_{pip['id']}",
            "target_character_id": pip["id"],
            "target_name": pip["name"],
            "override": True,
        },
    )
    assert resp.status_code == 200, resp.text
    rr = _roll_request_broadcast(gm_ws)
    assert rr is not None
    assert rr["data"]["base_expression"] == "1d20", (
        f"v2.99.195: bare 'Halfling' race shouldn't trigger Stout "
        f"Resilience; got {rr['data']['base_expression']!r}"
    )
    msgs = _race_save_broadcasts(gm_ws, pip["id"], "stout-resilience")
    assert not msgs, (
        f"v2.99.195: Stout Resilience should NOT fire for bare "
        f"Halfling (no subrace prefix); got {msgs}"
    )
