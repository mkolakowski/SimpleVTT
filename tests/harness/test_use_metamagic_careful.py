"""v2.99.38 — Metamagic Careful Spell (Sorcerer Lv 3+).

RAW (PHB p.102): "When you Cast a Spell that forces other creatures
to make a saving throw, you can protect some of those creatures from
the spell's full force. To do so, you spend 1 sorcery point and
choose a number of those creatures up to your Charisma modifier
(minimum of one creature). A chosen creature automatically succeeds
on its saving throw against the spell."

SECOND mechanical metamagic ship that intercepts the save-roll
construction (after v2.99.35 Heightened). Endpoint takes
`protected_combatant_ids: list[str]` (length-checked against CHA-mod)
+ arms a `metamagic-careful-pending` buff on the caster carrying the
protected list. The 3 save-roll construction sites read the buff via
`_caster_has_careful_pending_buff` + `_combatant_is_careful_protected`
BEFORE rolling, swap the target's d20 → "1d20+99" (auto-pass), and
the buff drops at END of cast — distinct from Heightened's RAW "ONE
TARGET" semantic. Multiple protected targets all benefit.

Tests:
- happy arm: 1 SP decrement + feature_used(armed) broadcast +
  buff installed with `effects.protected_combatant_ids`.
- error: not enough SP.
- error: wrong class (Tavik, Cleric).
- error: too many protected (len > CHA-mod).
- consume: Zara arms Careful protecting Pip, casts Hold Person at
  Pip → Pip's save base_expression = 1d20+99 + protected broadcast
  + buff dropped at end of cast.
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID


# Zara's spell list — Hold Person at index 13 (matches the v2.99.35
# Heightened test's HOLD_PERSON_ZARA_INDEX).
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
        "id": f"tok_cf_{char['id']}",
        "char_id": char["id"],
        "name": char["name"],
        "initiative": 10,
        "hp_current": 30,
        "hp_max": 30,
        "buffs": [],
        "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0},
    }


async def test_careful_arms_buff_and_decrements_sp(
    gm_client, gm_ws, zara_rested, roster,
):
    """Zara declares Careful Spell protecting Pip. 1 SP decrement +
    buff installed with the protected list + armed broadcast.
    """
    zara = zara_rested
    pip = roster["Pip Quickfingers"]
    await _seed_battle(gm_client, [_tok(zara), _tok(pip)])
    gm_ws.mark()
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_metamagic_careful_spell",
        json={
            "character_id": zara["id"],
            "protected_combatant_ids": [f"tok_cf_{pip['id']}"],
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["sp_cost"] == 1
    assert data["sp_remaining"] == data["sp_max"] - 1
    assert data["protected_count"] == 1

    # Buff installed on the caster with the protected list.
    zara_buffs = (await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{zara['id']}/buffs"
    )).json().get("buffs", [])
    cf = next(
        (b for b in zara_buffs if (b or {}).get("key") == "metamagic-careful-pending"),
        None,
    )
    assert cf is not None, (
        f"expected metamagic-careful-pending buff on Zara; got {zara_buffs}"
    )
    protected = (cf.get("effects") or {}).get("protected_combatant_ids") or []
    assert f"tok_cf_{pip['id']}" in protected, (
        f"expected Pip's combatant_id in protected list; got {protected}"
    )


async def test_careful_not_enough_points(gm_client, zara_rested, roster):
    """Drain Zara's 5 SP via Empowered (1 SP each × 5). Then Careful
    → 409 not_enough_points.
    """
    zara = zara_rested
    pip = roster["Pip Quickfingers"]
    await _seed_battle(gm_client, [_tok(zara), _tok(pip)])
    for _ in range(5):
        await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/use_metamagic_empowered_spell",
            json={"character_id": zara["id"]},
        )
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_metamagic_careful_spell",
        json={
            "character_id": zara["id"],
            "protected_combatant_ids": [f"tok_cf_{pip['id']}"],
        },
    )
    assert resp.status_code == 409, resp.text
    body = resp.json()
    assert body["error"] == "not_enough_points"


async def test_careful_wrong_class(gm_client, roster):
    """Tavik (Cleric) → 409 wrong_class."""
    tavik = roster["Brother Tavik Stonebrow"]
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_metamagic_careful_spell",
        json={
            "character_id": tavik["id"],
            "protected_combatant_ids": ["tok_dummy"],
        },
    )
    assert resp.status_code == 409, resp.text
    body = resp.json()
    assert body["error"] == "wrong_class"


async def test_careful_too_many_protected(
    gm_client, zara_rested, roster,
):
    """Zara's CHA = 17 → CHA-mod = 3. Pass 4 protected ids →
    409 too_many_protected with max_allowed = 3.
    """
    zara = zara_rested
    pip = roster["Pip Quickfingers"]
    await _seed_battle(gm_client, [_tok(zara), _tok(pip)])
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_metamagic_careful_spell",
        json={
            "character_id": zara["id"],
            "protected_combatant_ids": [
                "tok_a", "tok_b", "tok_c", "tok_d",
            ],
        },
    )
    assert resp.status_code == 409, resp.text
    body = resp.json()
    assert body["error"] == "too_many_protected"
    assert body["max_allowed"] == 3
    assert body["requested"] == 4


async def test_careful_auto_pass_on_save_swaps_to_force_pass(
    gm_client, gm_ws, zara_rested, roster,
):
    """Zara arms Careful protecting Pip, then casts Hold Person at
    Pip. Pip's save roll_request carries `base_expression="1d20+99"`
    (auto-pass) AND a protected broadcast fires for Zara. Buff is
    dropped at end of cast.
    """
    zara = zara_rested
    pip = roster["Pip Quickfingers"]
    await _seed_battle(gm_client, [_tok(zara), _tok(pip)])
    # Arm Careful Spell protecting Pip (1 SP).
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_metamagic_careful_spell",
        json={
            "character_id": zara["id"],
            "protected_combatant_ids": [f"tok_cf_{pip['id']}"],
        },
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
            "target_combatant_id": f"tok_cf_{pip['id']}",
            "target_character_id": pip["id"],
            "target_name": pip["name"],
            "override": True,
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["auto_save_ability"] == "WIS"

    # roll_request broadcast — base_expression should be 1d20+99
    # (Careful auto-pass).
    rr_msgs = gm_ws.buffered("roll_request")
    rr = rr_msgs[-1] if rr_msgs else None
    assert rr is not None, "expected a roll_request broadcast for Pip's Wis save"
    assert rr["data"]["base_expression"] == "1d20+99", (
        f"Careful should set base_expression to 1d20+99 (auto-pass); "
        f"got {rr['data']['base_expression']!r}"
    )

    # Protected broadcast — feature_used(source=metamagic-careful-spell).
    import asyncio as _asy
    await _asy.sleep(0.2)
    fu_msgs = gm_ws.buffered("feature_used")
    protected = [
        m for m in fu_msgs
        if (m.get("data") or {}).get("source") == "metamagic-careful-spell"
        and (m.get("data") or {}).get("character_id") == zara["id"]
    ]
    assert protected, (
        f"expected feature_used(source=metamagic-careful-spell) protected "
        f"broadcast; buffered: {[(m.get('type'), (m.get('data') or {}).get('source')) for m in gm_ws.buffered()]}"
    )

    # Buff dropped at end of cast.
    zara_buffs_post = (await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{zara['id']}/buffs"
    )).json().get("buffs", [])
    assert not any(
        (b or {}).get("key") == "metamagic-careful-pending"
        for b in zara_buffs_post
    ), f"Careful buff should be dropped post-cast; got {zara_buffs_post}"
