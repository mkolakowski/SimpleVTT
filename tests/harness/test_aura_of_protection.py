"""v2.53.0 — Aura of Protection (Paladin Lv 6+) ally-conferred save bonus.

When a Paladin Lv 6+ is in the active battle's init tracker, every
PC making a save (including the paladin themselves) gets +CHA mod
to their save roll. Caelan has CHA 16 (+3 mod), so saves land as
``+3`` appended to ``base_expression`` when he's in init.

Server-side helper ``_aura_of_protection_bonus`` does the walk:
- Iterates the battle's combatants
- For each PC combatant, checks Paladin Lv 6+ via `_paladin_level_from_sheet`
- Returns (max_cha_mod, paladin_char) across all qualifying paladins
- Returns (0, None) when the saver isn't in battle OR no paladin qualifies

Wired into:
  - `/place_aoe` PC branch (server-rolled save expr — appends +N)
  - `/cast_spell` single-target PC save roll_request creation
    (base_expression carries the +N alongside the d20 shape)
  - `/cast_spell` AoE PC save roll_request creation

Broadcasts a `feature_used(source="aura-of-protection")` event
naming the paladin as the source character.

Tests:
  - happy path: Caelan in init, Thalindra casts Fireball at Pip →
    base_expression carries "+3" + feature_used(source=aura-of-protection)
    with Caelan's char_id.
  - control without paladin: same setup but Caelan NOT in init →
    base_expression is plain "1d20" (no +N) + no Aura broadcast.
  - paladin's own aura: Thalindra casts Fireball at Caelan →
    his base_expression carries "+3" (RAW: paladin's own aura
    applies to themselves).
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID


FIREBALL_INDEX = 10  # Fireball, DEX save (stored-sheet index; 7 drifted to
                     # Web — see test_cast_spell_aoe.py).


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
        json={"combatants": combatants, "turn_index": 0, "round": 1, "active": True},
    )


def _aura_broadcasts(gm_ws, paladin_char_id: int) -> list:
    return [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "aura-of-protection"
        and (m.get("data") or {}).get("character_id") == paladin_char_id
    ]


def _roll_request_broadcast(gm_ws):
    msgs = gm_ws.buffered("roll_request")
    return msgs[-1] if msgs else None


def _make_combatant(name, char_id, init=10, hp=40):
    return {
        "id": f"tok_aop_{char_id}",
        "char_id": char_id,
        "name": name,
        "initiative": init,
        "hp_current": hp, "hp_max": hp,
        "buffs": [],
        "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0},
    }


async def test_aura_of_protection_grants_bonus_to_ally_save(
    gm_client, gm_ws, roster, thalindra_rested,
):
    """Caelan (Paladin Lv 6, CHA 16 → +3 mod) is in init.
    Thalindra casts Fireball at Pip → Pip's save roll_request
    broadcast carries base_expression containing "+3", AND a
    feature_used(source=aura-of-protection) broadcast fires with
    Caelan's char_id as the source.
    """
    thal = thalindra_rested
    caelan = roster["Sir Caelan Lightbringer"]
    pip = roster["Pip Quickfingers"]
    await _seed_battle(gm_client, [
        _make_combatant(thal["name"], thal["id"], init=12),
        _make_combatant(caelan["name"], caelan["id"], init=10),
        _make_combatant(pip["name"], pip["id"], init=8),
    ])
    gm_ws.mark()
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
        json={
            "character_id": thal["id"],
            "spell_index": FIREBALL_INDEX,
            "slot_level": 3,
            "class_slug": "wizard",
            "target_combatant_id": f"tok_aop_{pip['id']}",
            "target_character_id": pip["id"],
            "target_name": pip["name"],
            "override": True,
        },
    )
    assert resp.status_code == 200, resp.text

    rr = _roll_request_broadcast(gm_ws)
    assert rr is not None, "expected a roll_request broadcast for Pip"
    # Pip is a Rogue Lv 7 with Evasion (not Danger Sense), so
    # base_expression is just "1d20" + the aura bonus, not "2d20kh1".
    assert rr["data"]["base_expression"] == "1d20+3", (
        f"Pip's Fireball save should carry base_expression=1d20+3 "
        f"(Aura of Protection from Caelan); got {rr['data']['base_expression']!r}"
    )
    aura_msgs = _aura_broadcasts(gm_ws, caelan["id"])
    assert aura_msgs, (
        f"expected feature_used(source=aura-of-protection) named Caelan; "
        f"buffered: {[(m.get('type'), (m.get('data') or {}).get('source')) for m in gm_ws.buffered()]}"
    )


async def test_aura_skips_when_paladin_absent(
    gm_client, gm_ws, roster, thalindra_rested,
):
    """Control: Caelan is NOT in init. Pip's save roll_request
    base_expression is plain "1d20" (no aura bonus) and no Aura
    broadcast fires.
    """
    thal = thalindra_rested
    pip = roster["Pip Quickfingers"]
    await _seed_battle(gm_client, [
        _make_combatant(thal["name"], thal["id"], init=12),
        _make_combatant(pip["name"], pip["id"], init=8),
    ])
    gm_ws.mark()
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
        json={
            "character_id": thal["id"],
            "spell_index": FIREBALL_INDEX,
            "slot_level": 3,
            "class_slug": "wizard",
            "target_combatant_id": f"tok_aop_{pip['id']}",
            "target_character_id": pip["id"],
            "target_name": pip["name"],
            "override": True,
        },
    )
    assert resp.status_code == 200, resp.text

    rr = _roll_request_broadcast(gm_ws)
    assert rr is not None
    assert rr["data"]["base_expression"] == "1d20", (
        f"with no Lv 6+ paladin in init, base_expression should stay 1d20; "
        f"got {rr['data']['base_expression']!r}"
    )
    # Caelan's id is the would-be aura source — confirm no broadcast.
    aura_msgs = [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "aura-of-protection"
    ]
    assert not aura_msgs, (
        f"Aura broadcast should NOT fire without a paladin in init: {aura_msgs}"
    )


async def test_paladin_own_aura_applies_to_self(
    gm_client, gm_ws, roster, thalindra_rested,
):
    """RAW: "you and friendly creatures within 10 ft of you" — the
    paladin's own aura applies to themselves. Cast Fireball at
    Caelan → his save base_expression carries +3 and the broadcast
    still names Caelan as the source (he's both the paladin AND the
    saver).
    """
    thal = thalindra_rested
    caelan = roster["Sir Caelan Lightbringer"]
    await _seed_battle(gm_client, [
        _make_combatant(thal["name"], thal["id"], init=12),
        _make_combatant(caelan["name"], caelan["id"], init=10),
    ])
    gm_ws.mark()
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
        json={
            "character_id": thal["id"],
            "spell_index": FIREBALL_INDEX,
            "slot_level": 3,
            "class_slug": "wizard",
            "target_combatant_id": f"tok_aop_{caelan['id']}",
            "target_character_id": caelan["id"],
            "target_name": caelan["name"],
            "override": True,
        },
    )
    assert resp.status_code == 200, resp.text

    rr = _roll_request_broadcast(gm_ws)
    assert rr is not None
    assert rr["data"]["base_expression"] == "1d20+3", (
        f"Caelan's own aura should apply to himself; expected base_expression=1d20+3, "
        f"got {rr['data']['base_expression']!r}"
    )
    aura_msgs = _aura_broadcasts(gm_ws, caelan["id"])
    assert aura_msgs, (
        f"expected aura broadcast naming Caelan (self-aura); "
        f"buffered: {[(m.get('type'), (m.get('data') or {}).get('source')) for m in gm_ws.buffered()]}"
    )
