"""v2.1033.0 (B15) — SRD 5.1 bonus-action spell pairing rule.

RAW (SRD 5.1, Casting Time → Bonus Action): "You can't cast a spell
with your action and a spell with your bonus action in the same turn,
unless the spell you cast with your action is a cantrip with a casting
time of 1 action."

Note the constraint is on the **action** spell, not the bonus one —
a leveled bonus-action spell paired with an action *cantrip* is legal.
That asymmetry is the thing most likely to be implemented wrong (as a
symmetric "no two spells per turn"), so it gets its own test below.

Thalindra (Bob's wizard) is the fixture PC because she carries a
natural 1-bonus-action leveled spell — Misty Step — so the rule is
reachable without involving Sorcerer Quickened Spell. Casts run as
``bob_client``: the gate exempts the GM (rules authority), so a
gm_client cast would never trip it.

The gate reads hub battle state, so it only applies inside an active
battle — out of combat there are no turns to pair within.
"""
import asyncio

import pytest_asyncio

from .conftest import CAMPAIGN_ID


# Spells resolved BY NAME, not by hardcoded index. Other suites PATCH
# Thalindra's sheet (and a killed run leaves those patches in place), so
# index 0 is not reliably Fire Bolt — it has been observed as Acid Arrow.
# Same reasoning as CLAUDE.md's "look character ids up by name" rule.
FIRE_BOLT = "Fire Bolt"        # cantrip, 1 action
MAGIC_MISSILE = "Magic Missile"  # L1, 1 action
MISTY_STEP = "Misty Step"      # L2, 1 bonus action

_TOK = "tok_bap_thalindra"
_TOK_PIP = "tok_bap_pip"


async def _spell_index(gm_client, char_id: int, name: str) -> int:
    """Resolve a spell's sheet index by name."""
    r = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-json")
    assert r.status_code == 200, r.text
    body = r.json()
    spells = (body.get("sheet") or body).get("spells") or []
    for i, s in enumerate(spells):
        if (s.get("name") or "").strip().lower() == name.strip().lower():
            return i
    raise AssertionError(
        f"{name!r} not on character {char_id}'s sheet; "
        f"have: {[s.get('name') for s in spells]}"
    )


@pytest_asyncio.fixture
async def battle_with_thalindra(gm_client, roster):
    """Long-rest Thalindra (refill slots) and seed a 2-combatant battle
    with her active. Returns (thalindra, pip, idx) where ``idx`` maps
    spell name → sheet index, resolved live."""
    thalindra = roster["Thalindra Moonwhisper"]
    pip = roster["Pip Quickfingers"]
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{thalindra['id']}/rest",
        json={"type": "long"},
    )
    # Tear the previous battle down before seeding. Server-side pairing
    # provenance keys on (round, turn_index) and every battle starts at
    # (1, 0), so without an explicit teardown a marker from the previous
    # test would look like it belonged to this one. This mirrors how a
    # real fight starts — the GM clears init, then rolls a new battle.
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": [], "turn_index": 0, "round": 1,
              "active": False},
    )
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={
            "combatants": [
                {"id": _TOK, "char_id": thalindra["id"],
                 "name": thalindra["name"], "initiative": 20,
                 "hp_current": 30, "hp_max": 30, "buffs": [],
                 "economy": {"action": False, "bonus": False,
                             "reaction": False, "movement": 0}},
                {"id": _TOK_PIP, "char_id": pip["id"], "name": pip["name"],
                 "initiative": 10, "hp_current": 24, "hp_max": 24,
                 "buffs": [],
                 "economy": {"action": False, "bonus": False,
                             "reaction": False, "movement": 0}},
            ],
            "turn_index": 0, "round": 1, "active": True,
        },
    )
    idx = {
        FIRE_BOLT: await _spell_index(gm_client, thalindra['id'], FIRE_BOLT),
        MAGIC_MISSILE: await _spell_index(gm_client, thalindra['id'], MAGIC_MISSILE),
        MISTY_STEP: await _spell_index(gm_client, thalindra['id'], MISTY_STEP),
    }
    return thalindra, pip, idx


async def _cast(client, char_id, spell_index, slot_level, pip, **extra):
    body = {
        "character_id": char_id,
        "spell_index": spell_index,
        "class_slug": "wizard",
        "target_combatant_id": _TOK_PIP,
        "target_character_id": pip["id"],
        "target_name": pip["name"],
    }
    if slot_level:
        body["slot_level"] = slot_level
    body.update(extra)
    r = await client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_spell", json=body)
    await asyncio.sleep(0.1)
    return r


async def test_bonus_leveled_then_action_leveled_409(
    gm_client, bob_client, battle_with_thalindra,
):
    """Misty Step (bonus, leveled) then Magic Missile (action, leveled)
    → 409 bonus_action_spell_pairing. The core RAW gate."""
    thalindra, pip, idx = battle_with_thalindra
    first = await _cast(bob_client, thalindra["id"], idx[MISTY_STEP], 2, pip)
    assert first.status_code == 200, first.text

    second = await _cast(bob_client, thalindra["id"], idx[MAGIC_MISSILE], 1, pip)
    assert second.status_code == 409, second.text
    body = second.json()
    assert body["error"] == "bonus_action_spell_pairing", body
    assert body["slot"] == "action", body
    assert body["prior_slot"] == "bonus", body


async def test_bonus_leveled_then_action_cantrip_allowed(
    gm_client, bob_client, battle_with_thalindra,
):
    """Misty Step (bonus, leveled) then Fire Bolt (action, CANTRIP)
    → 200. This is the RAW exception, not an oversight."""
    thalindra, pip, idx = battle_with_thalindra
    first = await _cast(bob_client, thalindra["id"], idx[MISTY_STEP], 2, pip)
    assert first.status_code == 200, first.text

    second = await _cast(bob_client, thalindra["id"], idx[FIRE_BOLT], 0, pip)
    assert second.status_code == 200, (
        f"a 1-action cantrip after a bonus-action spell is legal per RAW; "
        f"got {second.status_code}: {second.text}"
    )


async def test_action_leveled_then_bonus_leveled_409(
    gm_client, bob_client, battle_with_thalindra,
):
    """Reverse order: Magic Missile (action, leveled) then Misty Step
    (bonus) → 409. The rule is order-independent."""
    thalindra, pip, idx = battle_with_thalindra
    first = await _cast(bob_client, thalindra["id"], idx[MAGIC_MISSILE], 1, pip)
    assert first.status_code == 200, first.text

    second = await _cast(bob_client, thalindra["id"], idx[MISTY_STEP], 2, pip)
    assert second.status_code == 409, second.text
    body = second.json()
    assert body["error"] == "bonus_action_spell_pairing", body
    assert body["slot"] == "bonus", body
    assert body["prior_slot"] == "action", body


async def test_action_cantrip_then_bonus_leveled_allowed(
    gm_client, bob_client, battle_with_thalindra,
):
    """**The asymmetry test.** Fire Bolt (action, cantrip) then Misty
    Step (bonus, leveled) → 200.

    RAW constrains the ACTION spell, not the bonus one: a cantrip cast
    with the action leaves a leveled bonus-action spell legal. A naive
    symmetric "one spell per turn" implementation would wrongly 409
    here, so this is the test that distinguishes correct from
    plausible-but-wrong.
    """
    thalindra, pip, idx = battle_with_thalindra
    first = await _cast(bob_client, thalindra["id"], idx[FIRE_BOLT], 0, pip)
    assert first.status_code == 200, first.text

    second = await _cast(bob_client, thalindra["id"], idx[MISTY_STEP], 2, pip)
    assert second.status_code == 200, (
        f"a leveled bonus-action spell after an action CANTRIP is legal "
        f"per RAW; got {second.status_code}: {second.text}"
    )


async def test_gm_bypasses_pairing_gate(
    gm_client, battle_with_thalindra,
):
    """The GM is the rules authority — the pairing gate doesn't apply
    to GM-driven casts, matching the over_budget gate's behaviour."""
    thalindra, pip, idx = battle_with_thalindra
    first = await _cast(gm_client, thalindra["id"], idx[MISTY_STEP], 2, pip)
    assert first.status_code == 200, first.text

    second = await _cast(gm_client, thalindra["id"], idx[MAGIC_MISSILE], 1, pip)
    assert second.status_code == 200, (
        f"GM casts bypass the pairing gate; got {second.text}"
    )


async def test_override_bypasses_pairing_gate(
    gm_client, bob_client, battle_with_thalindra,
):
    """A player who confirms through the modal (``override: true``)
    proceeds, same escape hatch the over_budget gate offers."""
    thalindra, pip, idx = battle_with_thalindra
    first = await _cast(bob_client, thalindra["id"], idx[MISTY_STEP], 2, pip)
    assert first.status_code == 200, first.text

    second = await _cast(
        bob_client, thalindra["id"], idx[MAGIC_MISSILE], 1, pip, override=True)
    assert second.status_code == 200, (
        f"override should bypass the pairing gate; got {second.text}"
    )


async def test_gate_survives_a_client_battle_push(
    gm_client, bob_client, battle_with_thalindra,
):
    """Regression pin for the bug that shaped the storage design.

    The client calls ``pushBattle()`` (a wholesale ``PUT /battle``) on
    many ordinary interactions, from a copy that has never seen any
    server-added per-turn key. An earlier implementation stamped the
    provenance onto ``combatant.economy`` — the same pattern Colossus
    Slayer and Spell Bombardment use — and a single client push wiped
    it, so the gate silently **failed open**.

    Provenance is now server-owned and keyed by (round, turn_index), so
    a push mid-turn can't clear it. This test replays that exact
    sequence: cast → client push → the gate must still fire.
    """
    thalindra, pip, idx = battle_with_thalindra
    first = await _cast(bob_client, thalindra["id"], idx[MISTY_STEP], 2, pip)
    assert first.status_code == 200, first.text

    # Wholesale re-push, exactly as the client does — note the payload
    # carries a fresh economy dict with no provenance key.
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={
            "combatants": [
                {"id": _TOK, "char_id": thalindra["id"],
                 "name": thalindra["name"], "initiative": 20,
                 "hp_current": 30, "hp_max": 30, "buffs": [],
                 "economy": {"action": False, "bonus": True,
                             "reaction": False, "movement": 0}},
                {"id": _TOK_PIP, "char_id": pip["id"], "name": pip["name"],
                 "initiative": 10, "hp_current": 24, "hp_max": 24,
                 "buffs": [],
                 "economy": {"action": False, "bonus": False,
                             "reaction": False, "movement": 0}},
            ],
            "turn_index": 0, "round": 1, "active": True,
        },
    )
    await asyncio.sleep(0.1)

    second = await _cast(bob_client, thalindra["id"], idx[MAGIC_MISSILE], 1, pip)
    assert second.status_code == 409, (
        f"a client battle push must not clear the pairing provenance "
        f"(the gate would fail open); got {second.status_code}: {second.text}"
    )
    assert second.json()["error"] == "bonus_action_spell_pairing"


async def test_turn_advance_clears_the_pairing_marker(
    gm_client, bob_client, battle_with_thalindra,
):
    """The marker is scoped to one turn: after the turn advances, a
    leveled action spell is legal again. Guards the opposite failure
    from the test above — provenance that never expires would block
    legal casts forever."""
    thalindra, pip, idx = battle_with_thalindra
    first = await _cast(bob_client, thalindra["id"], idx[MISTY_STEP], 2, pip)
    assert first.status_code == 200, first.text

    # Advance to Pip's turn and back around to a new round.
    for turn_index, rnd in ((1, 1), (0, 2)):
        await gm_client.put(
            f"/api/campaign/{CAMPAIGN_ID}/battle",
            json={
                "combatants": [
                    {"id": _TOK, "char_id": thalindra["id"],
                     "name": thalindra["name"], "initiative": 20,
                     "hp_current": 30, "hp_max": 30, "buffs": [],
                     "economy": {"action": False, "bonus": False,
                                 "reaction": False, "movement": 0}},
                    {"id": _TOK_PIP, "char_id": pip["id"],
                     "name": pip["name"], "initiative": 10,
                     "hp_current": 24, "hp_max": 24, "buffs": [],
                     "economy": {"action": False, "bonus": False,
                                 "reaction": False, "movement": 0}},
                ],
                "turn_index": turn_index, "round": rnd, "active": True,
            },
        )
        await asyncio.sleep(0.05)

    second = await _cast(bob_client, thalindra["id"], idx[MAGIC_MISSILE], 1, pip)
    assert second.status_code == 200, (
        f"the pairing marker must not outlive its turn; "
        f"got {second.status_code}: {second.text}"
    )


async def test_no_battle_no_pairing_gate(gm_client, bob_client, roster):
    """Out of combat there are no turns to pair within, so the gate is
    inert — two leveled casts back to back both succeed."""
    thalindra = roster["Thalindra Moonwhisper"]
    pip = roster["Pip Quickfingers"]
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{thalindra['id']}/rest",
        json={"type": "long"},
    )
    # Clear the battle so hub state carries no combatants.
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": [], "turn_index": 0, "round": 1,
              "active": False},
    )
    # This test doesn't use the battle fixture (it needs NO battle), so
    # it resolves the two spell indices itself.
    misty = await _spell_index(gm_client, thalindra["id"], MISTY_STEP)
    missile = await _spell_index(gm_client, thalindra["id"], MAGIC_MISSILE)
    first = await _cast(bob_client, thalindra["id"], misty, 2, pip)
    assert first.status_code == 200, first.text
    second = await _cast(bob_client, thalindra["id"], missile, 1, pip)
    assert second.status_code == 200, (
        f"no active battle → no pairing gate; got {second.text}"
    )
