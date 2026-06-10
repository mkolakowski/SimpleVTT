"""v2.158.54 — Eldritch Knight Fighter: Eldritch Strike Phase 2 read.

v2.99.268 shipped `/use_eldritch_strike`, which installs an
`eldritch-strike-target` buff on the struck creature carrying
`effects.save_disadvantage_against_caster_id` (the EK's char id) +
`consume_on_first_save: True`. RAW PHB p.74: "When you hit a
creature with a weapon attack, that creature has disadvantage on
the next saving throw it makes against a spell you cast before the
end of your next turn." But nothing read the flag — the
disadvantage was announce-only / GM-tracked (the last Phase-8
straggler from the v2.158.52 re-audit).

This wires the read into the single-target PC save-roll construction
site in `/cast_spell`: a new helper
`_saver_has_eldritch_strike_vs_caster` checks whether the saver
carries the buff naming the CURRENT caster; if so the save's
`base_expression` is swapped d20 → 2d20kl1 (disadvantage, with RAW
advantage-cancellation) and the one-use buff is dropped.

The read site is class-agnostic — it just matches the saver's buff
against the casting PC's id (the buff is only ever installed by a
real EK via the gated endpoint). So these tests seed the buff
directly on the saver's combatant and use Zara (who has Hold Person)
as the caster, avoiding the need for a Fighter with a save spell.

Tests:
  - Saver carries the mark naming the caster → save base_expression
    = "2d20kl1", consume broadcast fires, buff dropped.
  - Saver carries the mark naming a DIFFERENT caster → save stays
    "1d20", buff NOT dropped (per-caster guard).
"""
import asyncio
import pytest_asyncio

from .conftest import CAMPAIGN_ID


# Zara's spell list — Hold Person is index 13 (see
# test_use_metamagic_heightened.py).
HOLD_PERSON_ZARA_INDEX = 13


@pytest_asyncio.fixture
async def zara_rested(gm_client, roster):
    zara = roster["Zara Emberfire"]
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{zara['id']}/rest",
        json={"type": "long"},
    )
    return zara


async def _seed_battle(gm_client, combatants):
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": combatants, "turn_index": 0, "round": 1, "active": True},
    )


def _tok(char, buffs=None):
    return {
        "id": f"tok_es_{char['id']}",
        "char_id": char["id"],
        "name": char["name"],
        "initiative": 10,
        "hp_current": 30,
        "hp_max": 30,
        "buffs": buffs or [],
        "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0},
    }


def _es_buff(caster_char_id):
    return {
        "key": "eldritch-strike-target",
        "name": "Eldritch Strike",
        "icon": "🗡️",
        "effects": {
            "save_disadvantage_against_caster_id": caster_char_id,
            "consume_on_first_save": True,
        },
    }


async def test_eldritch_strike_imposes_save_disadvantage_and_consumes(
    gm_client, gm_ws, zara_rested, roster,
):
    """Pip's combatant carries `eldritch-strike-target` naming Zara as
    the caster. Zara casts Hold Person at Pip → Pip's save
    base_expression = 2d20kl1 (disadvantage), a consume broadcast fires
    (source `eldritch-strike`), and the buff is dropped."""
    zara = zara_rested
    pip = roster["Pip Quickfingers"]
    await _seed_battle(gm_client, [
        _tok(zara),
        _tok(pip, buffs=[_es_buff(zara["id"])]),
    ])
    gm_ws.mark()
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
        json={
            "character_id": zara["id"],
            "spell_index": HOLD_PERSON_ZARA_INDEX,
            "slot_level": 2,
            "class_slug": "sorcerer",
            "target_combatant_id": f"tok_es_{pip['id']}",
            "target_character_id": pip["id"],
            "target_name": pip["name"],
            "override": True,
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["auto_save_ability"] == "WIS"

    rr_msgs = gm_ws.buffered("roll_request")
    rr = rr_msgs[-1] if rr_msgs else None
    assert rr is not None, "expected a roll_request broadcast for Pip's Wis save"
    assert rr["data"]["base_expression"] == "2d20kl1", (
        f"Eldritch Strike should set base_expression to 2d20kl1; "
        f"got {rr['data']['base_expression']!r}"
    )

    await asyncio.sleep(0.2)
    fu_msgs = gm_ws.buffered("feature_used")
    consumed = [
        m for m in fu_msgs
        if (m.get("data") or {}).get("source") == "eldritch-strike"
        and (m.get("data") or {}).get("character_id") == zara["id"]
    ]
    assert consumed, (
        f"expected feature_used(source=eldritch-strike) consume broadcast; "
        f"buffered: {[(m.get('type'), (m.get('data') or {}).get('source')) for m in gm_ws.buffered()]}"
    )

    pip_buffs = (await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{pip['id']}/buffs"
    )).json().get("buffs", [])
    assert not any(
        (b or {}).get("key") == "eldritch-strike-target" for b in pip_buffs
    ), f"Eldritch Strike buff should be dropped post-consume; got {pip_buffs}"


async def test_eldritch_strike_no_disadvantage_for_other_caster(
    gm_client, gm_ws, zara_rested, roster,
):
    """Per-caster guard: Pip's mark names a DIFFERENT caster id, so
    Zara's Hold Person does NOT get the disadvantage → save stays
    1d20 and the buff is NOT consumed."""
    zara = zara_rested
    pip = roster["Pip Quickfingers"]
    await _seed_battle(gm_client, [
        _tok(zara),
        _tok(pip, buffs=[_es_buff(999999)]),
    ])
    gm_ws.mark()
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
        json={
            "character_id": zara["id"],
            "spell_index": HOLD_PERSON_ZARA_INDEX,
            "slot_level": 2,
            "class_slug": "sorcerer",
            "target_combatant_id": f"tok_es_{pip['id']}",
            "target_character_id": pip["id"],
            "target_name": pip["name"],
            "override": True,
        },
    )
    assert resp.status_code == 200, resp.text

    rr_msgs = gm_ws.buffered("roll_request")
    rr = rr_msgs[-1] if rr_msgs else None
    assert rr is not None, "expected a roll_request broadcast for Pip's Wis save"
    assert rr["data"]["base_expression"] == "1d20", (
        f"a mark for another caster should not impose disadvantage; "
        f"got {rr['data']['base_expression']!r}"
    )

    pip_buffs = (await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{pip['id']}/buffs"
    )).json().get("buffs", [])
    assert any(
        (b or {}).get("key") == "eldritch-strike-target" for b in pip_buffs
    ), f"a mark for another caster should NOT be consumed; got {pip_buffs}"
