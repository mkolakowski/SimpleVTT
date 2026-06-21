"""Antilife Shell — movement barrier (Phase 3 of
``docs/plans/aura-geometry-enforcement.md``).

v2.518.0 — RAW PHB p.213: the shell "prevents an affected creature from
passing or reaching through." New `_move_crosses_antilife_shell` hub-read
folded into `/token/{id}/move` as a 409 `barrier_blocks_move` gate: a
move that carries the mover from outside to inside the holder's moving
10-ft radius is rejected. The holder moves freely (the shell follows it);
`override_barrier: true` bypasses (the RAW undead/construct exception +
edge cases are GM-narrated).

Grid: demo map is 70 px / cell, 5 ft / cell; the shell radius is 10 ft.

Tests:
  - A mover crossing from outside (25 ft) to inside (~2 ft) → 409
    barrier_blocks_move.
  - A move that stays outside → allowed (200).
  - `override_barrier: true` lets the mover cross in (200).
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID


def _find_druid(roster):
    return roster.get("Mira Greenleaf")


def _tok(char, init=10, hp=40):
    return {
        "id": f"tok_als_bar_{char['id']}",
        "char_id": char["id"],
        "name": char["name"],
        "initiative": init,
        "hp_current": hp, "hp_max": hp,
        "buffs": [],
        "economy": {"action": False, "bonus": False,
                    "reaction": False, "movement": 0},
    }


async def _put_battle(gm_client, combatants):
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": combatants, "turn_index": 0,
              "round": 1, "active": True},
    )


async def _tokens_by_char(gm_client):
    r = await gm_client.get(f"/api/campaign/{CAMPAIGN_ID}/tokens")
    assert r.status_code == 200, r.text
    return {t["character_id"]: t for t in r.json()["tokens"]
            if t.get("character_id")}


async def _place(gm_client, char_id, x, y):
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/place-token",
        json={"x": float(x), "y": float(y)},
    )
    assert r.status_code == 200, r.text


async def _move(gm_client, token_id, x, y, override_barrier=False):
    body = {"x": float(x), "y": float(y),
            "over_speed_confirmed": True, "oa_confirmed": True}
    if override_barrier:
        body["override_barrier"] = True
    return await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/token/{token_id}/move",
        json=body,
    )


@pytest_asyncio.fixture
async def shell_setup(gm_client, roster):
    """Mira (Druid) raises Antilife Shell at (350,350); the mover
    (Krieger) starts outside at (700,350) = 25 ft. Yields
    (mover_token_id, druid). Teardown clears the buff + battle."""
    import pytest
    druid = _find_druid(roster)
    mover = roster.get("Krieger Stonefist")
    if not (druid and mover):
        pytest.skip("demo roster missing Mira/Krieger")
    await _put_battle(gm_client, [_tok(druid, init=20), _tok(mover, init=10)])
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_antilife_shell",
        json={"character_id": druid["id"]},
    )
    assert r.status_code == 200, r.text
    await _place(gm_client, druid["id"], 350.0, 350.0)
    await _place(gm_client, mover["id"], 700.0, 350.0)
    toks = await _tokens_by_char(gm_client)
    mover_tok_id = toks[mover["id"]]["id"]
    try:
        yield mover_tok_id, druid, mover
    finally:
        await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/end_buff",
            json={"character_id": druid["id"], "key": "antilife-shell"},
        )
        await gm_client.put(
            f"/api/campaign/{CAMPAIGN_ID}/battle",
            json={"combatants": [], "turn_index": 0, "round": 1,
                  "active": False},
        )


async def test_move_into_shell_blocked(gm_client, shell_setup):
    """A mover crossing from outside (25 ft) to inside (~2 ft) → 409
    barrier_blocks_move."""
    mover_tok_id, druid, mover = shell_setup
    r = await _move(gm_client, mover_tok_id, 380.0, 350.0)  # ~2 ft from holder
    assert r.status_code == 409, r.text
    body = r.json()
    assert body["error"] == "barrier_blocks_move", body
    assert body["barrier"] == "antilife-shell"


async def test_move_staying_outside_allowed(gm_client, shell_setup):
    """A move that stays outside the 10-ft radius is allowed."""
    mover_tok_id, druid, mover = shell_setup
    r = await _move(gm_client, mover_tok_id, 770.0, 350.0)  # still ~30 ft out
    assert r.status_code == 200, r.text


async def test_override_barrier_bypasses(gm_client, shell_setup):
    """override_barrier: true lets the mover cross into the shell (the
    GM escape hatch for edge cases)."""
    mover_tok_id, druid, mover = shell_setup
    r = await _move(gm_client, mover_tok_id, 380.0, 350.0, override_barrier=True)
    assert r.status_code == 200, r.text


async def _has_shell(gm_client, char_id):
    r = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/buffs",
    )
    assert r.status_code == 200, r.text
    return any(b.get("key") == "antilife-shell" for b in (r.json().get("buffs") or []))


async def _setup_emitter_move(gm_client, roster):
    """Battle [Mira(shell), Krieger@15ft outside]; both placed. Returns
    (mira_token_id, druid, mover). Caller moves Mira."""
    import pytest
    druid = _find_druid(roster)
    mover = roster.get("Krieger Stonefist")
    if not (druid and mover):
        pytest.skip("demo roster missing Mira/Krieger")
    await _put_battle(gm_client, [_tok(druid, init=20), _tok(mover, init=10)])
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_antilife_shell",
        json={"character_id": druid["id"]},
    )
    assert r.status_code == 200, r.text
    await _place(gm_client, druid["id"], 350.0, 350.0)
    await _place(gm_client, mover["id"], 560.0, 350.0)  # 15 ft, outside
    toks = await _tokens_by_char(gm_client)
    return toks[druid["id"]]["id"], druid, mover


async def _teardown_shell(gm_client, druid):
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/end_buff",
        json={"character_id": druid["id"], "key": "antilife-shell"},
    )
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": [], "turn_index": 0, "round": 1, "active": False},
    )


async def test_emitter_sweeps_creature_ends_shell(gm_client, roster):
    """v2.520.0 — the holder moves so a living creature (outside → inside)
    is forced through the barrier → the shell ends (RAW PHB p.213)."""
    mira_tok_id, druid, mover = await _setup_emitter_move(gm_client, roster)
    try:
        assert await _has_shell(gm_client, druid["id"])  # precondition
        # Move Mira to (490,350): 5 ft from Krieger(560) — sweeps the
        # shell over him (was 15 ft away).
        r = await _move(gm_client, mira_tok_id, 490.0, 350.0)
        assert r.status_code == 200, r.text  # the move stands
        assert not await _has_shell(gm_client, druid["id"]), (
            "the Antilife Shell should end when the holder sweeps it over "
            "an affected creature"
        )
    finally:
        await _teardown_shell(gm_client, druid)


async def test_emitter_move_no_sweep_keeps_shell(gm_client, roster):
    """Control: the holder moves but no creature crosses the barrier →
    the shell persists."""
    mira_tok_id, druid, mover = await _setup_emitter_move(gm_client, roster)
    try:
        # Move Mira a hair (10 px ≈ <1 ft); Krieger stays 15 ft+ away.
        r = await _move(gm_client, mira_tok_id, 360.0, 350.0)
        assert r.status_code == 200, r.text
        assert await _has_shell(gm_client, druid["id"]), (
            "the shell should persist when no creature is swept through"
        )
    finally:
        await _teardown_shell(gm_client, druid)


async def test_undead_mover_passes_freely(gm_client, roster):
    """v2.519.0 — RAW: undead/constructs are NOT hedged out. A mover whose
    combatant carries `creature_type: "undead"` crosses the shell freely
    (no override needed)."""
    import pytest
    druid = _find_druid(roster)
    mover = roster.get("Krieger Stonefist")
    if not (druid and mover):
        pytest.skip("demo roster missing Mira/Krieger")
    # Seed the mover's combatant with an undead creature-type override.
    mover_tok = _tok(mover, init=10)
    mover_tok["creature_type"] = "undead"
    await _put_battle(gm_client, [_tok(druid, init=20), mover_tok])
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_antilife_shell",
        json={"character_id": druid["id"]},
    )
    assert r.status_code == 200, r.text
    await _place(gm_client, druid["id"], 350.0, 350.0)
    await _place(gm_client, mover["id"], 700.0, 350.0)
    toks = await _tokens_by_char(gm_client)
    mover_tok_id = toks[mover["id"]]["id"]
    try:
        # Crossing into the shell (~2 ft) is allowed for an undead mover.
        r = await _move(gm_client, mover_tok_id, 380.0, 350.0)
        assert r.status_code == 200, r.text
    finally:
        await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/end_buff",
            json={"character_id": druid["id"], "key": "antilife-shell"},
        )
        await gm_client.put(
            f"/api/campaign/{CAMPAIGN_ID}/battle",
            json={"combatants": [], "turn_index": 0, "round": 1,
                  "active": False},
        )
