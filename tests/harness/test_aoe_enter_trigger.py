"""Persistent-AoE enter-trigger — Phase 1 of
``docs/plans/aoe-enter-trigger.md``.

v2.567.0 — RAW: a persistent damaging AoE deals its save + damage *"when
a creature enters the area for the first time on a turn or starts its
turn there."* The start-of-turn half is `_tick_auras`; this is the
**enter-mid-move** half. After a `/token/{id}/move`,
`_trigger_persistent_aoe_on_move` fires the save+damage of any
RADIUS-shaped (`sphere` / `self_sphere`) persistent damaging concentration
AoE the moved creature just entered (origin outside → dest inside), once
per (creature, AoE) per turn. PC → a roll_request + save-for-half on
`/respond`; NPC → auto-roll + save-for-half inline.

Fixture spell: Brother Tavik Stonebrow (Life Cleric) casts Spirit
Guardians — `self_sphere`, 15-ft radius, 3d8 radiant, WIS save — anchored
to his token; victims move into the 15-ft emanation.

Grid: demo map is 70 px / cell, 5 ft / cell. 15 ft = 210 px.

Tests:
  - NPC moving in (25 ft → 5 ft) takes save-for-half damage.
  - No re-trigger the same turn (out-and-back-in damages once).
  - PC moving in gets a roll_request (Spirit Guardians WIS save).
  - The caster isn't hit by their own emanation.
  - A move that stays outside the radius fires nothing.
  - `override_barrier: true` skips the trigger (GM escape hatch).
"""
import pytest
import pytest_asyncio

from .conftest import CAMPAIGN_ID

# Spirit Guardians' index in Brother Tavik's *normalized/stored*
# ``sheet["spells"]`` (the list /cast_spell indexes — note this differs
# from the demo_seed source order). If the seed drifts, the
# ``pending_aoe_placement`` assert in ``_cast_and_place_sg`` fails loudly
# rather than silently testing the wrong spell.
SPIRIT_GUARDIANS_INDEX = 11
# Moonbeam in Mira Greenleaf's stored sheet (Druid). A PLACED 5-ft sphere
# — concentration via its "Up to 1 minute" duration (the SRD `concentration`
# flag is False, but the cast path treats "Up to …" as concentration), so it
# creates a fixed-center damaging marker. Exercises the non-self-anchored
# center path (vs SG's self_sphere) + a second real spell. The
# pending_aoe_placement assert guards against seed drift.
MOONBEAM_INDEX = 6
PX_PER_CELL = 70  # demo map: 5 ft / cell


async def _put_battle(gm_client, combatants):
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": combatants, "turn_index": 0,
              "round": 1, "active": True},
    )


async def _advance_turn(gm_client, combatants, turn_index):
    """PUT the battle with a new turn_index → fires the start-of-turn pass
    for combatants[turn_index] (update_battle runs it when the turn changes)."""
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": combatants, "turn_index": turn_index,
              "round": 1, "active": True},
    )


async def _clear_battle(gm_client):
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": [], "turn_index": 0, "round": 1, "active": False},
    )


async def _get_battle(gm_client):
    r = await gm_client.get(f"/api/campaign/{CAMPAIGN_ID}/battle")
    assert r.status_code == 200, r.text
    return (r.json() or {}).get("battle") or {}


def _combatant(battle, cid):
    for c in (battle.get("combatants") or []):
        if c.get("id") == cid:
            return c
    return None


async def _place(gm_client, char_id, x, y):
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/place-token",
        json={"x": float(x), "y": float(y)},
    )
    assert r.status_code == 200, r.text


async def _tokens_by_char(gm_client):
    r = await gm_client.get(f"/api/campaign/{CAMPAIGN_ID}/tokens")
    assert r.status_code == 200, r.text
    return {t["character_id"]: t for t in r.json()["tokens"]
            if t.get("character_id")}


async def _move(gm_client, token_id, x, y, override_barrier=False):
    body = {"x": float(x), "y": float(y),
            "over_speed_confirmed": True, "oa_confirmed": True}
    if override_barrier:
        body["override_barrier"] = True
    return await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/token/{token_id}/move",
        json=body,
    )


async def _bandit_tmpl(gm_client):
    r = await gm_client.get(f"/api/campaign/{CAMPAIGN_ID}/templates")
    return next(t for t in r.json() if "bandit" in t["name"].lower())


async def _cast_and_place_sg(gm_client, tavik, cx, cy):
    """Tavik casts Spirit Guardians + places the (self-anchored) emanation
    at his token. Leaves a persistent damaging AoE marker centred on him."""
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{tavik['id']}/rest",
        json={"type": "long"},
    )
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
        json={
            "character_id": tavik["id"],
            "spell_index": SPIRIT_GUARDIANS_INDEX,
            "slot_level": 3,
            "class_slug": "cleric",
            "override": True,
        },
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data.get("pending_aoe_placement") is True, (
        f"expected Spirit Guardians to be a pending AoE placement; the demo "
        f"seed may have drifted off index {SPIRIT_GUARDIANS_INDEX}: {data}"
    )
    cast_id = data["id"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/place_aoe",
        json={"cast_id": cast_id, "center": {"x": float(cx), "y": float(cy)},
              "override": True},
    )
    assert r.status_code == 200, r.text


async def _cast_and_place_moonbeam(gm_client, mira, cx, cy):
    """Mira casts Moonbeam + places the 5-ft sphere at (cx, cy) — a
    fixed-center (non-self-anchored) damaging concentration marker."""
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{mira['id']}/rest",
        json={"type": "long"},
    )
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
        json={"character_id": mira["id"], "spell_index": MOONBEAM_INDEX,
              "slot_level": 2, "class_slug": "druid", "override": True},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data.get("pending_aoe_placement") is True, (
        f"expected Moonbeam to be a pending AoE placement; the demo seed may "
        f"have drifted off index {MOONBEAM_INDEX}: {data}"
    )
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/place_aoe",
        json={"cast_id": data["id"], "center": {"x": float(cx), "y": float(cy)},
              "override": True},
    )
    assert r.status_code == 200, r.text


async def _end_conc(gm_client, char_id):
    """Drop the caster's concentration → clears the persistent AoE marker
    so it doesn't leak into other tests (markers are in-process state)."""
    await gm_client.delete(
        f"/api/campaign/{CAMPAIGN_ID}/concentration/{char_id}",
    )


@pytest_asyncio.fixture
async def npc_victim(gm_client, roster):
    """Tavik at (350,350) concentrating on Spirit Guardians; an NPC victim
    (bandit stats, token anchored to Krieger's placed token) starts at
    (700,350) = 25 ft, outside the 15-ft emanation. Yields
    (victim_token_id, victim_combatant_id, tavik)."""
    tavik = roster.get("Brother Tavik Stonebrow")
    standin = roster.get("Krieger Stonefist")
    if not (tavik and standin):
        pytest.skip("demo roster missing Tavik/Krieger")
    tmpl = await _bandit_tmpl(gm_client)
    await _place(gm_client, tavik["id"], 350.0, 350.0)
    await _place(gm_client, standin["id"], 700.0, 350.0)
    toks = await _tokens_by_char(gm_client)
    tavik_tok = toks[tavik["id"]]
    victim_tok_id = toks[standin["id"]]["id"]
    victim_cid = "npc_sg_victim"
    await _put_battle(gm_client, [
        {"id": f"tok_sg_{tavik['id']}", "char_id": tavik["id"],
         "name": tavik["name"], "initiative": 20,
         "hp_current": 40, "hp_max": 40, "buffs": [],
         "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0}},
        {"id": victim_cid, "char_id": None,
         "token_template_id": tmpl["id"], "source_token_id": victim_tok_id,
         "name": "Bandit Intruder", "initiative": 10,
         "hp_current": 50, "hp_max": 50, "buffs": [],
         "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0}},
    ])
    await _cast_and_place_sg(gm_client, tavik, tavik_tok["x"], tavik_tok["y"])
    try:
        yield victim_tok_id, victim_cid, tavik
    finally:
        await _end_conc(gm_client, tavik["id"])
        await _clear_battle(gm_client)


async def test_npc_entering_takes_damage(gm_client, npc_victim):
    """An NPC moving from 25 ft (outside) to 5 ft (inside) Spirit
    Guardians takes save-for-half radiant damage."""
    victim_tok_id, victim_cid, tavik = npc_victim
    before = _combatant(await _get_battle(gm_client), victim_cid)["hp_current"]
    r = await _move(gm_client, victim_tok_id, 420.0, 350.0)  # 5 ft from Tavik
    assert r.status_code == 200, r.text
    after = _combatant(await _get_battle(gm_client), victim_cid)["hp_current"]
    assert after < before, (
        f"entering Spirit Guardians should deal damage; "
        f"hp {before} → {after}"
    )


async def test_no_retrigger_same_turn(gm_client, npc_victim):
    """RAW 'first time on a turn': moving in, back out, and in again within
    the same turn deals the AoE damage exactly once."""
    victim_tok_id, victim_cid, tavik = npc_victim
    before = _combatant(await _get_battle(gm_client), victim_cid)["hp_current"]
    await _move(gm_client, victim_tok_id, 420.0, 350.0)  # in → triggers
    once = _combatant(await _get_battle(gm_client), victim_cid)["hp_current"]
    assert once < before
    await _move(gm_client, victim_tok_id, 700.0, 350.0)  # back out (no dmg)
    await _move(gm_client, victim_tok_id, 420.0, 350.0)  # in again, same turn
    twice = _combatant(await _get_battle(gm_client), victim_cid)["hp_current"]
    assert twice == once, (
        f"the enter-trigger must not re-fire the same turn; "
        f"hp after 1st entry {once}, after re-entry {twice}"
    )


async def test_no_entry_no_trigger(gm_client, npc_victim):
    """A move that stays outside the 15-ft radius fires nothing."""
    victim_tok_id, victim_cid, tavik = npc_victim
    before = _combatant(await _get_battle(gm_client), victim_cid)["hp_current"]
    r = await _move(gm_client, victim_tok_id, 640.0, 350.0)  # ~21 ft, still out
    assert r.status_code == 200, r.text
    after = _combatant(await _get_battle(gm_client), victim_cid)["hp_current"]
    assert after == before, f"no entry → no damage; hp {before} → {after}"


async def test_override_barrier_skips_trigger(gm_client, npc_victim):
    """override_barrier: true (the GM move-escape) skips the enter-trigger."""
    victim_tok_id, victim_cid, tavik = npc_victim
    before = _combatant(await _get_battle(gm_client), victim_cid)["hp_current"]
    r = await _move(gm_client, victim_tok_id, 420.0, 350.0, override_barrier=True)
    assert r.status_code == 200, r.text
    after = _combatant(await _get_battle(gm_client), victim_cid)["hp_current"]
    assert after == before, (
        f"override_barrier should skip the trigger; hp {before} → {after}"
    )


async def test_caster_immune_to_own_emanation(gm_client, roster):
    """The caster isn't damaged by their own Spirit Guardians when they
    move within it."""
    tavik = roster.get("Brother Tavik Stonebrow")
    if not tavik:
        pytest.skip("demo roster missing Tavik")
    await _place(gm_client, tavik["id"], 350.0, 350.0)
    cid = f"tok_sg_caster_{tavik['id']}"
    await _put_battle(gm_client, [
        {"id": cid, "char_id": tavik["id"], "name": tavik["name"],
         "initiative": 20, "hp_current": 40, "hp_max": 40, "buffs": [],
         "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0}},
    ])
    await _cast_and_place_sg(gm_client, tavik, 350.0, 350.0)
    try:
        tok = (await _tokens_by_char(gm_client))[tavik["id"]]
        before = _combatant(await _get_battle(gm_client), cid)["hp_current"]
        r = await _move(gm_client, tok["id"], 360.0, 350.0)  # nudge within zone
        assert r.status_code == 200, r.text
        after = _combatant(await _get_battle(gm_client), cid)["hp_current"]
        assert after == before, (
            f"the caster must not take their own AoE damage; "
            f"hp {before} → {after}"
        )
    finally:
        await _end_conc(gm_client, tavik["id"])
        await _clear_battle(gm_client)


async def test_start_of_turn_in_aoe_takes_damage(gm_client, roster):
    """RAW 'or starts its turn there': an NPC that begins its turn inside
    Spirit Guardians takes the save+damage on turn advance — even without
    moving."""
    tavik = roster.get("Brother Tavik Stonebrow")
    standin = roster.get("Krieger Stonefist")
    if not (tavik and standin):
        pytest.skip("demo roster missing Tavik/Krieger")
    tmpl = await _bandit_tmpl(gm_client)
    await _place(gm_client, tavik["id"], 350.0, 350.0)
    await _place(gm_client, standin["id"], 420.0, 350.0)  # 5 ft, INSIDE
    victim_tok_id = (await _tokens_by_char(gm_client))[standin["id"]]["id"]
    victim_cid = "npc_sg_sot"
    combatants = [
        {"id": f"tok_sgs_{tavik['id']}", "char_id": tavik["id"],
         "name": tavik["name"], "initiative": 20,
         "hp_current": 40, "hp_max": 40, "buffs": [],
         "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0}},
        {"id": victim_cid, "char_id": None,
         "token_template_id": tmpl["id"], "source_token_id": victim_tok_id,
         "name": "Bandit Lurker", "initiative": 10,
         "hp_current": 50, "hp_max": 50, "buffs": [],
         "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0}},
    ]
    await _put_battle(gm_client, combatants)  # turn 0 = Tavik active
    await _cast_and_place_sg(gm_client, tavik, 350.0, 350.0)
    try:
        before = _combatant(await _get_battle(gm_client), victim_cid)["hp_current"]
        await _advance_turn(gm_client, combatants, 1)  # → victim's turn starts
        after = _combatant(await _get_battle(gm_client), victim_cid)["hp_current"]
        assert after < before, (
            f"starting a turn inside Spirit Guardians should deal damage; "
            f"hp {before} → {after}"
        )
    finally:
        await _end_conc(gm_client, tavik["id"])
        await _clear_battle(gm_client)


async def test_moonbeam_placed_sphere_enter(gm_client, roster):
    """A PLACED damaging sphere (Moonbeam — concentration via its 'Up to 1
    minute' duration) covers a second real spell + the fixed-center path.
    An NPC moving into the 5-ft sphere takes save-for-half radiant damage."""
    mira = roster.get("Mira Greenleaf")
    standin = roster.get("Krieger Stonefist")
    if not (mira and standin):
        pytest.skip("demo roster missing Mira/Krieger")
    tmpl = await _bandit_tmpl(gm_client)
    await _place(gm_client, mira["id"], 100.0, 100.0)  # caster, away from the beam
    await _place(gm_client, standin["id"], 700.0, 350.0)  # 25 ft from the beam
    victim_tok_id = (await _tokens_by_char(gm_client))[standin["id"]]["id"]
    victim_cid = "npc_mb_victim"
    await _put_battle(gm_client, [
        {"id": f"tok_mb_{mira['id']}", "char_id": mira["id"],
         "name": mira["name"], "initiative": 20,
         "hp_current": 40, "hp_max": 40, "buffs": [],
         "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0}},
        {"id": victim_cid, "char_id": None,
         "token_template_id": tmpl["id"], "source_token_id": victim_tok_id,
         "name": "Bandit Strayer", "initiative": 10,
         "hp_current": 50, "hp_max": 50, "buffs": [],
         "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0}},
    ])
    await _cast_and_place_moonbeam(gm_client, mira, 350.0, 350.0)
    try:
        before = _combatant(await _get_battle(gm_client), victim_cid)["hp_current"]
        r = await _move(gm_client, victim_tok_id, 360.0, 350.0)  # ~1 ft, inside 5 ft
        assert r.status_code == 200, r.text
        after = _combatant(await _get_battle(gm_client), victim_cid)["hp_current"]
        assert after < before, (
            f"entering Moonbeam should deal damage; hp {before} → {after}"
        )
    finally:
        await _end_conc(gm_client, mira["id"])
        await _clear_battle(gm_client)


async def test_forced_move_into_aoe_triggers(gm_client, roster):
    """Phase 3: forced movement (push/pull) that carries a creature into a
    radius damaging AoE triggers it too — RAW, forced movement counts as
    entering. An NPC pushed into Spirit Guardians takes save-for-half
    damage via `/force_move` (not the voluntary `/token/{id}/move` path)."""
    tavik = roster.get("Brother Tavik Stonebrow")
    standin = roster.get("Krieger Stonefist")
    if not (tavik and standin):
        pytest.skip("demo roster missing Tavik/Krieger")
    tmpl = await _bandit_tmpl(gm_client)
    await _place(gm_client, tavik["id"], 350.0, 350.0)
    await _place(gm_client, standin["id"], 100.0, 350.0)  # ~18 ft LEFT, outside
    victim_tok_id = (await _tokens_by_char(gm_client))[standin["id"]]["id"]
    victim_cid = "npc_sg_pushed"
    await _put_battle(gm_client, [
        {"id": f"tok_sgf_{tavik['id']}", "char_id": tavik["id"],
         "name": tavik["name"], "initiative": 20,
         "hp_current": 40, "hp_max": 40, "buffs": [],
         "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0}},
        {"id": victim_cid, "char_id": None,
         "token_template_id": tmpl["id"], "source_token_id": victim_tok_id,
         "name": "Bandit Shoved", "initiative": 10,
         "hp_current": 50, "hp_max": 50, "buffs": [],
         "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0}},
    ])
    await _cast_and_place_sg(gm_client, tavik, 350.0, 350.0)
    try:
        before = _combatant(await _get_battle(gm_client), victim_cid)["hp_current"]
        # Push +x 10 ft (no source) → (100,350) → (240,350) = ~8 ft from
        # Tavik, inside the 15-ft emanation.
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/force_move",
            json={"target_combatant_id": victim_cid, "distance_ft": 10},
        )
        assert r.status_code == 200, r.text
        assert r.json()["moved"] is True, r.json()
        after = _combatant(await _get_battle(gm_client), victim_cid)["hp_current"]
        assert after < before, (
            f"being pushed into Spirit Guardians should deal damage; "
            f"hp {before} → {after}"
        )
    finally:
        await _end_conc(gm_client, tavik["id"])
        await _clear_battle(gm_client)


async def test_pc_entering_prompts_save(gm_client, gm_ws, roster):
    """A PC moving into Spirit Guardians gets a roll_request for their
    WIS save (the respond endpoint applies save-for-half)."""
    tavik = roster.get("Brother Tavik Stonebrow")
    victim = roster.get("Thalindra Moonwhisper")  # PC, owned by Bob
    if not (tavik and victim):
        pytest.skip("demo roster missing Tavik/Thalindra")
    await _place(gm_client, tavik["id"], 350.0, 350.0)
    await _place(gm_client, victim["id"], 700.0, 350.0)
    await _put_battle(gm_client, [
        {"id": f"tok_sgp_{tavik['id']}", "char_id": tavik["id"],
         "name": tavik["name"], "initiative": 20,
         "hp_current": 40, "hp_max": 40, "buffs": [],
         "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0}},
        {"id": f"tok_sgp_{victim['id']}", "char_id": victim["id"],
         "name": victim["name"], "initiative": 10,
         "hp_current": 24, "hp_max": 24, "buffs": [],
         "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0}},
    ])
    await _cast_and_place_sg(gm_client, tavik, 350.0, 350.0)
    try:
        victim_tok_id = (await _tokens_by_char(gm_client))[victim["id"]]["id"]
        gm_ws.mark()
        r = await _move(gm_client, victim_tok_id, 420.0, 350.0)  # 5 ft, inside
        assert r.status_code == 200, r.text
        rrs = gm_ws.buffered("roll_request")
        assert any(
            "spirit guardians" in (m["data"].get("label") or "").lower()
            for m in rrs
        ), (
            "expected a Spirit Guardians save roll_request when the PC "
            f"entered; got labels {[m['data'].get('label') for m in rrs]}"
        )
    finally:
        await _end_conc(gm_client, tavik["id"])
        await _clear_battle(gm_client)
