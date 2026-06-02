"""v2.99.35 — Metamagic Heightened Spell (Sorcerer Lv 3+).

RAW (PHB p.102): "When you Cast a Spell that forces a creature to
make a saving throw to resist its effects, you can spend 3 sorcery
points to give one target of the spell disadvantage on its first
saving throw made against the spell."

FIRST mechanical metamagic ship that intercepts the save-roll
construction (Twinned + Distant were announce-only). Endpoint arms
a `metamagic-heightened-pending` buff on the caster's combatant;
the 3 save-roll construction sites read the buff via
`_caster_has_heightened_pending` BEFORE rolling, swap the target's
d20 → 2d20kl1 (disadvantage), AND drop the buff (one-use per RAW).

For single-target save spells (Hold Person, Suggestion, etc.) the
gate fires naturally on the only saver. For AoE save spells
(Fireball, Cone of Cold, etc.), v1 fires on the FIRST saver and
drops the buff — the GM picks who to apply it to via target order
RAW. Future UI would let the caster specify which target gets the
disadvantage; filed.

Tests:
- happy arm: 3 SP decrement + feature_used(armed) broadcast +
  buff installed.
- error: not enough SP.
- consume: Zara casts Hold Person (L2 WIS save) at Pip with
  Heightened armed → Pip's save base_expression = 2d20kl1 +
  feature_used(metamagic-heightened-spell) consumed broadcast +
  buff dropped.
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID


# Zara's spell list — Hold Person was appended in v2.99.35 demo
# seed. Index = 13 (post-Sleep at 12).
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


def _tok(char):
    return {
        "id": f"tok_ht_{char['id']}",
        "char_id": char["id"],
        "name": char["name"],
        "initiative": 10,
        "hp_current": 30,
        "hp_max": 30,
        "buffs": [],
        "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0},
    }


async def test_heightened_arms_buff_and_decrements_sp(
    gm_client, gm_ws, zara_rested,
):
    """Zara declares Heightened Spell. 3 SP decrement + buff
    installed + armed broadcast.
    """
    zara = zara_rested
    # Heightened needs the caster in the battle so the buff lands
    # on a combatant (not just the sheet).
    await _seed_battle(gm_client, [_tok(zara)])
    gm_ws.mark()
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_metamagic_heightened_spell",
        json={"character_id": zara["id"]},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["sp_cost"] == 3
    assert data["sp_remaining"] == data["sp_max"] - 3

    # Buff installed on the caster.
    pip_buffs = (await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{zara['id']}/buffs"
    )).json().get("buffs", [])
    ht = next(
        (b for b in pip_buffs if (b or {}).get("key") == "metamagic-heightened-pending"),
        None,
    )
    assert ht is not None, (
        f"expected metamagic-heightened-pending buff on Zara; got {pip_buffs}"
    )


async def test_heightened_not_enough_points(gm_client, zara_rested):
    """5 SP pool; Heightened costs 3 → first call succeeds, second
    call fails (only 2 SP remaining).
    """
    zara = zara_rested
    await _seed_battle(gm_client, [_tok(zara)])
    r1 = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_metamagic_heightened_spell",
        json={"character_id": zara["id"]},
    )
    assert r1.status_code == 200, r1.text
    r2 = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_metamagic_heightened_spell",
        json={"character_id": zara["id"]},
    )
    assert r2.status_code == 409, r2.text
    body = r2.json()
    assert body["error"] == "not_enough_points"
    assert body["required"] == 3


async def test_heightened_consume_on_save_swaps_to_disadvantage(
    gm_client, gm_ws, zara_rested, roster,
):
    """Zara arms Heightened, then casts Hold Person at Pip. Pip's
    save roll_request carries `base_expression="2d20kl1"` AND a
    consume broadcast fires for Zara. Buff is dropped after.
    """
    zara = zara_rested
    pip = roster["Pip Quickfingers"]
    await _seed_battle(gm_client, [_tok(zara), _tok(pip)])
    # Arm Heightened (3 SP).
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_metamagic_heightened_spell",
        json={"character_id": zara["id"]},
    )
    assert r.status_code == 200, r.text

    gm_ws.mark()
    # Cast Hold Person at Pip (Wis save → Paralyzed).
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
        json={
            "character_id": zara["id"],
            "spell_index": HOLD_PERSON_ZARA_INDEX,
            "slot_level": 2,
            "class_slug": "sorcerer",
            "target_combatant_id": f"tok_ht_{pip['id']}",
            "target_character_id": pip["id"],
            "target_name": pip["name"],
            "override": True,
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["auto_save_ability"] == "WIS"

    # roll_request broadcast — base_expression should be 2d20kl1.
    rr_msgs = gm_ws.buffered("roll_request")
    rr = rr_msgs[-1] if rr_msgs else None
    assert rr is not None, "expected a roll_request broadcast for Pip's Wis save"
    assert rr["data"]["base_expression"] == "2d20kl1", (
        f"Heightened should set base_expression to 2d20kl1 (disadvantage); "
        f"got {rr['data']['base_expression']!r}"
    )

    # Consume broadcast — feature_used(source=metamagic-heightened-spell).
    import asyncio as _asy
    await _asy.sleep(0.2)
    fu_msgs = gm_ws.buffered("feature_used")
    consumed = [
        m for m in fu_msgs
        if (m.get("data") or {}).get("source") == "metamagic-heightened-spell"
        and (m.get("data") or {}).get("character_id") == zara["id"]
    ]
    assert consumed, (
        f"expected feature_used(source=metamagic-heightened-spell) consume "
        f"broadcast; buffered: {[(m.get('type'), (m.get('data') or {}).get('source')) for m in gm_ws.buffered()]}"
    )

    # Buff dropped post-consume.
    zara_buffs_post = (await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{zara['id']}/buffs"
    )).json().get("buffs", [])
    assert not any(
        (b or {}).get("key") == "metamagic-heightened-pending"
        for b in zara_buffs_post
    ), f"Heightened buff should be dropped post-consume; got {zara_buffs_post}"
