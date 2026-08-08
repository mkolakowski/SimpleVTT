"""v2.1053.0 — NPC death saves (Phase 4a of docs/plans/death-saves.md).

A boss NPC flagged `rolls_death_saves` enters the *dying* state at 0 HP
instead of dropping inert-dead. State (`rolls_death_saves` +
`death_saves`) lives on the combatant dict in hub state; the toggle is
`POST /api/campaign/{cid}/set_npc_death_saves`.

Phase 4a covers the toggle + the 0-HP transition + the `npc_death_save`
broadcast. The turn-start auto-roll is Phase 4b.

Deterministic damage uses Magic Missile — the one auto-hit spell (no
attack roll, no save), so a single dart reliably drops a low-HP boss.

Tests:
  - Toggle sets + clears the flag/state; GM-only; rejects a PC; 404 unknown.
  - A flagged boss taking lethal damage → `dying` (not dead), and the
    `npc_death_save` event fires.
  - Control: an unflagged NPC still drops inert (no `death_saves`).
  - Damage to a dying boss ticks a failure.
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID

_CASTER = "Thalindra Moonwhisper"
_SLUG = "magic-missile"


async def _set_auto_apply(gm_client, on: bool) -> bool:
    prior = bool((await gm_client.post(
        f"/api/test/campaign/{CAMPAIGN_ID}/flags", json={},
    )).json()["auto_apply_damage"])
    await gm_client.post(
        f"/api/test/campaign/{CAMPAIGN_ID}/flags",
        json={"auto_apply_damage": on},
    )
    return prior


async def _bandit_tmpl(gm_client):
    r = await gm_client.get(f"/api/campaign/{CAMPAIGN_ID}/templates")
    return next(t for t in r.json() if "bandit" in t["name"].lower())


async def _spell_index(gm_client, char_id) -> int:
    sheet = (await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-json")
    ).json().get("sheet") or {}
    for i, e in enumerate(sheet.get("spells") or []):
        if (e.get("_slug") or "") == _SLUG:
            return i
    raise AssertionError(f"{_SLUG} not on {char_id}'s sheet")


async def _long_rest(gm_client, char_id) -> None:
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/rest",
        json={"type": "long"},
    )


def _boss(bid, tmpl_id, hp_current, hp_max, *, rolls=None, death_saves=None):
    c = {"id": bid, "char_id": None, "token_template_id": tmpl_id,
         "name": "Boss Ogre", "initiative": 5,
         "hp_current": hp_current, "hp_max": hp_max, "buffs": [],
         "economy": {"action": False, "bonus": False,
                     "reaction": False, "movement": 0}}
    if rolls is not None:
        c["rolls_death_saves"] = rolls
    if death_saves is not None:
        c["death_saves"] = death_saves
    return c


def _caster_combatant(caster):
    return {"id": f"tok_nds_c_{caster['id']}", "char_id": caster["id"],
            "name": caster["name"], "initiative": 10,
            "hp_current": 30, "hp_max": 30, "buffs": [],
            "economy": {"action": False, "bonus": False,
                        "reaction": False, "movement": 0}}


async def _seed(gm_client, caster, boss):
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": [_caster_combatant(caster), boss],
              "turn_index": 0, "round": 1, "active": True},
    )


async def _get_combatant(gm_client, bid):
    state = (await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/battle")).json().get("battle") or {}
    for c in (state.get("combatants") or []):
        if c.get("id") == bid:
            return c
    return None


async def _cast_mm(gm_client, caster, idx, target_id):
    return await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
        json={"character_id": caster["id"], "spell_index": idx,
              "slot_level": 1, "class_slug": "wizard",
              "target_combatant_ids": [target_id],
              "override": True, "override_range": True},
    )


async def _toggle(gm_client, bid, on):
    return await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/set_npc_death_saves",
        json={"combatant_id": bid, "rolls_death_saves": on},
    )


@pytest_asyncio.fixture
async def nds(gm_client, roster):
    caster = roster[_CASTER]
    await _long_rest(gm_client, caster["id"])
    idx = await _spell_index(gm_client, caster["id"])
    tmpl = await _bandit_tmpl(gm_client)
    prior = await _set_auto_apply(gm_client, True)
    try:
        yield {"caster": caster, "idx": idx, "tmpl": tmpl}
    finally:
        await _set_auto_apply(gm_client, prior)
        await gm_client.put(
            f"/api/campaign/{CAMPAIGN_ID}/battle",
            json={"combatants": [], "turn_index": 0, "round": 1,
                  "active": False},
        )


async def test_toggle_sets_and_clears(gm_client, nds):
    bid = "tok_nds_toggle"
    await _seed(gm_client, nds["caster"], _boss(bid, nds["tmpl"]["id"], 40, 40))
    r = await _toggle(gm_client, bid, True)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["rolls_death_saves"] is True
    assert d["death_saves"]["status"] == "alive"
    c = await _get_combatant(gm_client, bid)
    assert c["rolls_death_saves"] is True
    assert c["death_saves"]["status"] == "alive"
    # Toggle off clears the state.
    r = await _toggle(gm_client, bid, False)
    assert r.status_code == 200, r.text
    assert r.json()["rolls_death_saves"] is False
    c = await _get_combatant(gm_client, bid)
    assert c["rolls_death_saves"] is False
    assert "death_saves" not in c


async def test_toggle_gm_only(gm_client, alice_client, nds):
    bid = "tok_nds_gmonly"
    await _seed(gm_client, nds["caster"], _boss(bid, nds["tmpl"]["id"], 40, 40))
    r = await alice_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/set_npc_death_saves",
        json={"combatant_id": bid, "rolls_death_saves": True},
    )
    assert r.status_code == 403, r.text


async def test_toggle_rejects_pc(gm_client, nds):
    await _seed(gm_client, nds["caster"], _boss("tok_nds_pccase",
                                                nds["tmpl"]["id"], 40, 40))
    r = await _toggle(gm_client, f"tok_nds_c_{nds['caster']['id']}", True)
    assert r.status_code == 400, r.text


async def test_toggle_unknown_combatant(gm_client, nds):
    await _seed(gm_client, nds["caster"], _boss("tok_nds_unk",
                                                nds["tmpl"]["id"], 40, 40))
    r = await _toggle(gm_client, "tok_does_not_exist", True)
    assert r.status_code == 404, r.text


async def test_boss_enters_dying_at_zero(gm_client, gm_ws, nds):
    """A flagged boss dropped to 0 HP enters `dying`, not dead, and the
    `npc_death_save` event fires. hp_max 40 keeps it clear of the
    massive-damage instant-death rule."""
    bid = "tok_nds_dying"
    await _seed(gm_client, nds["caster"], _boss(bid, nds["tmpl"]["id"], 2, 40))
    assert (await _toggle(gm_client, bid, True)).status_code == 200
    gm_ws.mark()
    r = await _cast_mm(gm_client, nds["caster"], nds["idx"], bid)
    assert r.status_code == 200, r.text
    msg = await gm_ws.wait_for("npc_death_save", timeout=2.0)
    assert msg["data"]["combatant_id"] == bid
    assert msg["data"]["status"] == "dying"
    c = await _get_combatant(gm_client, bid)
    assert c["hp_current"] == 0, c
    assert c["death_saves"]["status"] == "dying", c
    assert c["death_saves"]["failures"] == 0, c


async def test_unflagged_npc_drops_inert(gm_client, nds):
    """Control: an NPC without the toggle still drops to 0 with no
    death-save state — unchanged pre-v2.1053.0 behavior."""
    bid = "tok_nds_inert"
    await _seed(gm_client, nds["caster"], _boss(bid, nds["tmpl"]["id"], 2, 40))
    r = await _cast_mm(gm_client, nds["caster"], nds["idx"], bid)
    assert r.status_code == 200, r.text
    c = await _get_combatant(gm_client, bid)
    assert c["hp_current"] == 0, c
    assert not c.get("death_saves"), c


async def test_damage_while_dying_ticks_failure(gm_client, gm_ws, nds):
    """A dying boss taking more damage gains a failure (RAW: damage at
    0 HP = a failed death save)."""
    bid = "tok_nds_tick"
    await _seed(gm_client, nds["caster"],
                _boss(bid, nds["tmpl"]["id"], 0, 40, rolls=True,
                      death_saves={"status": "dying", "successes": 0,
                                   "failures": 0}))
    gm_ws.mark()
    r = await _cast_mm(gm_client, nds["caster"], nds["idx"], bid)
    assert r.status_code == 200, r.text
    c = await _get_combatant(gm_client, bid)
    assert c["death_saves"]["status"] == "dying", c
    assert c["death_saves"]["failures"] == 1, c


async def _seed_dice(gm_client, seed):
    await gm_client.post("/api/test/dice/seed", json={"seed": seed})


async def _put_battle(gm_client, caster, boss, turn_index):
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": [_caster_combatant(caster), boss],
              "turn_index": turn_index, "round": 1, "active": True},
    )


async def test_turn_start_auto_rolls_death_save(gm_client, gm_ws, nds):
    """Phase 4b: when the turn advances to a dying boss, it auto-rolls a
    death save. The `npc_death_save` event carries `source: turn_start` +
    the raw d20, and the resulting counters are consistent with that roll
    (starting from 0/0)."""
    bid = "tok_nds_turn"
    boss = _boss(bid, nds["tmpl"]["id"], 0, 40, rolls=True,
                 death_saves={"status": "dying", "successes": 0,
                              "failures": 0})
    # Seed on the caster's turn (index 0), then advance to the boss (1).
    await _put_battle(gm_client, nds["caster"], boss, 0)
    await _seed_dice(gm_client, 5)
    try:
        gm_ws.mark()
        await _put_battle(gm_client, nds["caster"], boss, 1)
        msg = await gm_ws.wait_for("npc_death_save", timeout=2.0)
        d = msg["data"]
        assert d["combatant_id"] == bid
        assert d["source"] == "turn_start"
        raw = int(d["raw"])
        assert 1 <= raw <= 20, d
        c = await _get_combatant(gm_client, bid)
        ds = c["death_saves"]
        # Counters must match the rolled d20 (RAW: flat d20 vs 10).
        if raw == 20:
            assert ds["status"] == "alive" and c["hp_current"] == 1, (c, d)
        elif raw == 1:
            assert ds["failures"] == 2, (ds, d)
        elif raw >= 10:
            assert ds["successes"] == 1, (ds, d)
        else:
            assert ds["failures"] == 1, (ds, d)
    finally:
        await _seed_dice(gm_client, None)


async def test_turn_start_no_roll_for_alive_boss(gm_client, gm_ws, nds):
    """A flagged boss that is NOT dying (alive) does not auto-roll on its
    turn — pins the gate so healthy bosses don't spam death saves."""
    bid = "tok_nds_alive"
    boss = _boss(bid, nds["tmpl"]["id"], 40, 40, rolls=True,
                 death_saves={"status": "alive", "successes": 0,
                              "failures": 0})
    await _put_battle(gm_client, nds["caster"], boss, 0)
    gm_ws.mark()
    await _put_battle(gm_client, nds["caster"], boss, 1)
    import asyncio
    await asyncio.sleep(0.3)
    assert not gm_ws.buffered("npc_death_save"), "alive boss should not roll"
