"""v2.158.51 — Relentless Avenger read site (Phase 2).

Relentless Avenger (Vengeance Paladin Lv 7+, PHB p.88): "When you hit
a creature with an opportunity attack, you can move up to half your
speed immediately after the attack and as part of the same reaction.
This movement doesn't provoke opportunity attacks."

The v2.149.0 install (`/use_relentless_avenger`) lands a 1-round
`relentless-avenger-bonus-move` buff carrying
`free_movement_remaining_ft` (= half walking speed) +
`oa_immune_during_move: True`. Until now nothing read it — the
half-speed-without-provoke movement was GM-tracked.

This commit wires the read into `/token/move`:
  - OA triggers the drag would raise are suppressed (no provocation,
    no `oa_confirmation_required` 409).
  - Up to `free_movement_remaining_ft` of the drag is exempted from
    the over-speed cap (the bonus move is separate from normal speed).
  - The buff is consumed (single-use) after the move — a `buff_update`
    broadcast removes it.

Seeding strategy mirrors test_opportunity_attack.py — the buff goes on
the mover's combatant `buffs` list at PUT /battle; `_get_buffs` reads
combatant buffs by `char_id`, so no extra install call is needed. We
use Sir Caelan (the demo Paladin) as the mover for RAW flavor, though
the read site keys on the buff, not the class.

Demo grid: 70 px / cell, 5 ft / cell.

Tests:
  - RA buff + move out of a watcher's reach → 200, empty triggers,
    relentless_avenger_applied True, buff_update consumes the buff.
  - Control (no buff): same move → 409 oa_confirmation_required.
  - RA buff exempts the free move from the over-speed cap → 200 where
    the same over-cap drag without the buff 409s `over_speed_cap`.
"""
import asyncio
import pytest_asyncio

from .conftest import CAMPAIGN_ID


_RA_BUFF = {
    "key": "relentless-avenger-bonus-move",
    "name": "🏃 Relentless Avenger (free move)",
    "icon": "🏃",
    "duration_rounds": 1,
    "effects": {
        "free_movement_remaining_ft": 15,
        "oa_immune_during_move": True,
    },
}


def _make_combatant(name, char_id, init=10, hp=40, buffs=None, economy=None):
    return {
        "id": f"tok_ra_{char_id}",
        "char_id": char_id,
        "name": name,
        "initiative": init,
        "hp_current": hp, "hp_max": hp,
        "buffs": buffs or [],
        "economy": economy or {
            "action": False, "bonus": False, "reaction": False, "movement": 0,
        },
    }


async def _seed_battle(gm_client, combatants):
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={
            "combatants": combatants,
            "turn_index": 0,
            "round": 1,
            "active": True,
        },
    )


async def _place_token(gm_client, char_id, x, y):
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/place-token",
        json={"x": float(x), "y": float(y)},
    )
    assert r.status_code == 200, r.text
    return r.json()


async def _get_token_for_char(gm_client, char_id):
    r = await gm_client.get(f"/api/campaign/{CAMPAIGN_ID}/tokens")
    assert r.status_code == 200, r.text
    for t in r.json()["tokens"]:
        if t.get("character_id") == char_id:
            return t
    return None


def _ra_buff_updates(gm_ws):
    return [
        m for m in gm_ws.buffered("buff_update")
        if (m.get("data") or {}).get("removed_key")
        == "relentless-avenger-bonus-move"
    ]


async def test_relentless_avenger_suppresses_oa_and_consumes_buff(
    gm_client, gm_ws, roster,
):
    """Caelan carries the `relentless-avenger-bonus-move` buff and
    moves out of Tavik's 5 ft reach. Even WITHOUT `oa_confirmed`, the
    move succeeds (200) with NO opportunity_attack_triggers, because
    Relentless Avenger suppresses them — and the buff is consumed
    (a buff_update broadcast removes it)."""
    caelan = roster["Sir Caelan Lightbringer"]
    tavik = roster["Brother Tavik Stonebrow"]

    await _seed_battle(gm_client, [
        _make_combatant(caelan["name"], caelan["id"], init=10,
                        buffs=[dict(_RA_BUFF)]),
        _make_combatant(tavik["name"], tavik["id"], init=8),
    ])
    await _place_token(gm_client, caelan["id"], 350.0, 350.0)
    await _place_token(gm_client, tavik["id"], 420.0, 350.0)
    ca_tok = await _get_token_for_char(gm_client, caelan["id"])
    assert ca_tok, "Caelan token must exist"
    await asyncio.sleep(0.15)
    gm_ws.mark()

    # Move out of reach WITHOUT oa_confirmed — RA should suppress the
    # provocation so there's no 409.
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/token/{ca_tok['id']}/move",
        json={"x": 700.0, "y": 350.0},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data.get("relentless_avenger_applied") is True, (
        f"expected relentless_avenger_applied True; got {data!r}"
    )
    assert not (data.get("opportunity_attack_triggers") or []), (
        f"RA should suppress OA triggers; got "
        f"{data.get('opportunity_attack_triggers')}"
    )

    await asyncio.sleep(0.2)
    consumed = _ra_buff_updates(gm_ws)
    assert consumed, (
        "expected a buff_update removing relentless-avenger-bonus-move; "
        f"buffered: {[m.get('type') for m in gm_ws.buffered()]}"
    )


async def test_move_provokes_oa_without_relentless_avenger(
    gm_client, gm_ws, roster,
):
    """Control: same geometry, but Caelan has NO buff → moving out of
    Tavik's reach without `oa_confirmed` returns 409
    oa_confirmation_required (proves the move WOULD provoke)."""
    caelan = roster["Sir Caelan Lightbringer"]
    tavik = roster["Brother Tavik Stonebrow"]

    await _seed_battle(gm_client, [
        _make_combatant(caelan["name"], caelan["id"], init=10),
        _make_combatant(tavik["name"], tavik["id"], init=8),
    ])
    await _place_token(gm_client, caelan["id"], 350.0, 350.0)
    await _place_token(gm_client, tavik["id"], 420.0, 350.0)
    ca_tok = await _get_token_for_char(gm_client, caelan["id"])
    assert ca_tok, "Caelan token must exist"
    await asyncio.sleep(0.15)

    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/token/{ca_tok['id']}/move",
        json={"x": 700.0, "y": 350.0},
    )
    assert resp.status_code == 409, (
        f"expected 409 oa_confirmation_required without RA; got "
        f"{resp.status_code} {resp.text}"
    )
    assert resp.json().get("error") == "oa_confirmation_required", resp.text


async def test_relentless_avenger_exempts_free_move_from_speed_cap(
    gm_client, roster,
):
    """RA's bonus move is separate from normal speed, so it's exempt
    from the over-speed cap. Caelan's combatant is preloaded at his
    30 ft cap (`economy.movement = 30`); a +5 ft drag would normally
    409 `over_speed_cap`, but the RA free budget (15 ft) exempts it →
    200. The control (no buff) 409s on the identical over-cap drag."""
    caelan = roster["Sir Caelan Lightbringer"]

    # With the buff: at-cap + 5 ft drag is exempted.
    await _seed_battle(gm_client, [
        _make_combatant(
            caelan["name"], caelan["id"], init=10,
            buffs=[dict(_RA_BUFF)],
            economy={"action": False, "bonus": False,
                     "reaction": False, "movement": 30},
        ),
    ])
    await _place_token(gm_client, caelan["id"], 350.0, 350.0)
    ca_tok = await _get_token_for_char(gm_client, caelan["id"])
    assert ca_tok, "Caelan token must exist"
    await asyncio.sleep(0.15)

    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/token/{ca_tok['id']}/move",
        json={"x": 420.0, "y": 350.0},  # +1 cell = 5 ft
    )
    assert resp.status_code == 200, (
        f"RA free move should be exempt from the speed cap; got "
        f"{resp.status_code} {resp.text}"
    )
    assert resp.json().get("relentless_avenger_applied") is True, resp.text

    # Control: identical over-cap drag with NO buff → 409.
    await _seed_battle(gm_client, [
        _make_combatant(
            caelan["name"], caelan["id"], init=10,
            economy={"action": False, "bonus": False,
                     "reaction": False, "movement": 30},
        ),
    ])
    await _place_token(gm_client, caelan["id"], 350.0, 350.0)
    ca_tok = await _get_token_for_char(gm_client, caelan["id"])
    await asyncio.sleep(0.15)

    resp2 = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/token/{ca_tok['id']}/move",
        json={"x": 420.0, "y": 350.0},
    )
    assert resp2.status_code == 409, (
        f"over-cap drag without RA should 409 over_speed_cap; got "
        f"{resp2.status_code} {resp2.text}"
    )
    assert resp2.json().get("error") == "over_speed_cap", resp2.text
