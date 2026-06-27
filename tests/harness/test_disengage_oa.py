"""v2.698.0 — Disengage OA-read in /token/move (Phase 8 substrate gap).

Step of the Wind (Monk) and Drunken Technique (Way of the Drunken Master
Monk) already INSTALL a buff carrying `effects.disengage: True`, but until
now nothing read it — a "disengaged" mover still tripped opportunity-attack
prompts. This wires the read into `/token/move`:

  - A mover carrying any active buff with `effects.disengage: True` provokes
    NO opportunity attacks — the triggers a move out of reach would raise are
    dropped (no `oa_confirmation_required` 409).
  - Unlike the single-use free-move budget (Relentless Avenger / Skirmisher),
    the disengage flag is NOT consumed on the move — RAW the Disengage action
    lasts the whole turn, so a second move also provokes nothing while the
    buff persists.

Seeding mirrors test_relentless_avenger_move.py — the buff goes on the
mover's combatant `buffs` list at PUT /battle (`_get_buffs` reads combatant
buffs by char_id). The read keys on the buff's `effects.disengage`, not the
class, so any disengage source rides it.

Demo grid: 70 px / cell, 5 ft / cell.

Tests:
  - Disengage buff + move out of a watcher's reach → 200, no triggers,
    disengage_applied True.
  - The flag is NOT consumed: a second move out of reach also → 200.
  - Control (no buff): same move → 409 oa_confirmation_required.
"""
import asyncio
import pytest_asyncio

from .conftest import CAMPAIGN_ID


_DISENGAGE_BUFF = {
    "key": "step-of-the-wind-disengage",
    "name": "Step of the Wind (Disengage)",
    "icon": "💨",
    "duration_rounds": 1,
    "effects": {"disengage": True},
}


def _make_combatant(name, char_id, init=10, hp=40, buffs=None):
    return {
        "id": f"tok_dis_{char_id}",
        "char_id": char_id,
        "name": name,
        "initiative": init,
        "hp_current": hp, "hp_max": hp,
        "buffs": buffs or [],
        "economy": {
            "action": False, "bonus": False, "reaction": False, "movement": 0,
        },
    }


async def _seed_battle(gm_client, combatants):
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": combatants, "turn_index": 0,
              "round": 1, "active": True},
    )


async def _place_token(gm_client, char_id, x, y):
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/place-token",
        json={"x": float(x), "y": float(y)},
    )
    assert r.status_code == 200, r.text


async def _get_token_for_char(gm_client, char_id):
    r = await gm_client.get(f"/api/campaign/{CAMPAIGN_ID}/tokens")
    assert r.status_code == 200, r.text
    for t in r.json()["tokens"]:
        if t.get("character_id") == char_id:
            return t
    return None


async def test_disengage_suppresses_oa(gm_client, roster):
    """Mover with a `disengage` buff leaves a watcher's 5 ft reach — even
    WITHOUT `oa_confirmed`, the move succeeds (200) with NO triggers because
    Disengage suppresses provocation."""
    kael = roster["Kael Brightleaf"]   # Monk mover
    tavik = roster["Brother Tavik Stonebrow"]  # watcher in reach

    await _seed_battle(gm_client, [
        _make_combatant(kael["name"], kael["id"], init=10,
                        buffs=[dict(_DISENGAGE_BUFF)]),
        _make_combatant(tavik["name"], tavik["id"], init=8),
    ])
    await _place_token(gm_client, kael["id"], 350.0, 350.0)
    await _place_token(gm_client, tavik["id"], 420.0, 350.0)
    tok = await _get_token_for_char(gm_client, kael["id"])
    assert tok, "Kael token must exist"
    await asyncio.sleep(0.15)

    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/token/{tok['id']}/move",
        json={"x": 700.0, "y": 350.0},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data.get("disengage_applied") is True, data
    assert not (data.get("opportunity_attack_triggers") or []), data


async def test_disengage_not_consumed_second_move(gm_client, roster):
    """The disengage flag persists for the turn — a SECOND move out of reach
    also suppresses OAs (unlike the single-use free-move budget)."""
    kael = roster["Kael Brightleaf"]
    tavik = roster["Brother Tavik Stonebrow"]

    await _seed_battle(gm_client, [
        _make_combatant(kael["name"], kael["id"], init=10,
                        buffs=[dict(_DISENGAGE_BUFF)]),
        _make_combatant(tavik["name"], tavik["id"], init=8),
    ])
    await _place_token(gm_client, kael["id"], 350.0, 350.0)
    await _place_token(gm_client, tavik["id"], 420.0, 350.0)
    tok = await _get_token_for_char(gm_client, kael["id"])
    await asyncio.sleep(0.15)

    # First move away — disengaged.
    r1 = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/token/{tok['id']}/move",
        json={"x": 700.0, "y": 350.0},
    )
    assert r1.status_code == 200, r1.text
    assert r1.json().get("disengage_applied") is True

    # Move back into reach (forced-style re-position via a normal move; the
    # watcher doesn't get an OA on the inbound leg), then out again — still
    # disengaged because the buff was not consumed.
    await _place_token(gm_client, kael["id"], 350.0, 350.0)
    tok = await _get_token_for_char(gm_client, kael["id"])
    await asyncio.sleep(0.1)
    r2 = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/token/{tok['id']}/move",
        json={"x": 700.0, "y": 350.0},
    )
    assert r2.status_code == 200, r2.text
    assert r2.json().get("disengage_applied") is True, r2.text


async def test_move_provokes_oa_without_disengage(gm_client, roster):
    """Control: same geometry, no disengage buff → moving out of reach
    without `oa_confirmed` returns 409 oa_confirmation_required."""
    kael = roster["Kael Brightleaf"]
    tavik = roster["Brother Tavik Stonebrow"]

    await _seed_battle(gm_client, [
        _make_combatant(kael["name"], kael["id"], init=10),
        _make_combatant(tavik["name"], tavik["id"], init=8),
    ])
    await _place_token(gm_client, kael["id"], 350.0, 350.0)
    await _place_token(gm_client, tavik["id"], 420.0, 350.0)
    tok = await _get_token_for_char(gm_client, kael["id"])
    await asyncio.sleep(0.15)

    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/token/{tok['id']}/move",
        json={"x": 700.0, "y": 350.0},
    )
    assert resp.status_code == 409, resp.text
    assert resp.json().get("error") == "oa_confirmation_required", resp.text
