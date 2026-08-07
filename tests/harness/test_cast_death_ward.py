"""Death Ward — L4 abjuration, Cleric/Paladin.
Phase 2 #29 of ``docs/plans/cast-and-broadcast-tail.md``.

v2.496.0 — RAW PHB p.230: "The first time the target would drop to 0
hit points as a result of taking damage, the target instead drops to
1 hit point, and the spell ends." 1 action, V/S, Touch, 8 hours,
non-concentration.

First tail spell that needed NEW mechanical code: the drop-to-1 floor
lives in `_apply_hp_change` alongside the Half-Orc Relentless Endurance
branch (the identical mechanic). The endpoint installs the
`effects.death_ward` marker buff + mirrors it to the target's sheet so
the sync HP-change function reads it; firing consumes the buff and the
central damage path drops the hub copy + broadcasts.

Tests (buff-install contract + the end-to-end floor):
  - Cleric casts on an ally → buff installs with effects.death_ward.
  - Buff is 8-hour, non-concentration.
  - GATE: warded target dropped toward 0 by an attack lands at 1 HP
    (not 0/dying), the death-ward buff is gone, and a
    feature_used(source=death-ward, "held at 1 HP") broadcast fires.
  - Non-caster (Barbarian) → 409.
  - Missing character_id → 400.
"""
from .conftest import CAMPAIGN_ID
from .helpers import AttemptLog


async def _seed_dice(gm_client, seed: int):
    # TEST_MODE-only; best-effort so this test also runs against a dev
    # container with TEST_MODE off (dice stay random but the attack loop
    # still converges on a qualifying hit). Deterministic in CI where
    # TEST_MODE=true.
    await gm_client.post("/api/test/dice/seed", json={"seed": seed})


async def _set_hp(gm_client, char_id: int, hp_current: int):
    await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-fields",
        json={"hp": {"current": hp_current}},
    )


async def _long_rest(gm_client, char_id: int):
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/rest",
        json={"type": "long"},
    )


async def _get_buffs(gm_client, char_id):
    r = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/buffs",
    )
    assert r.status_code == 200, r.text
    return r.json().get("buffs") or []


def _tok(char, hp_current=30, hp_max=60, tag="dw"):
    return {
        "id": f"tok_{tag}_{char['id']}",
        "char_id": char["id"],
        "name": char["name"],
        "initiative": 10,
        "hp_current": hp_current, "hp_max": hp_max,
        "buffs": [],
        "economy": {"action": False, "bonus": False,
                    "reaction": False, "movement": 0},
    }


async def _set_battle(gm_client, combatants):
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": combatants, "turn_index": 0,
              "round": 1, "active": True},
    )


async def test_cast_death_ward_installs_marker_buff(gm_client, roster):
    """A Cleric wards an ally; the installed buff carries
    effects.death_ward == True."""
    tavik = roster["Brother Tavik Stonebrow"]
    garrik = roster["Garrik Ironside"]
    await _set_battle(gm_client, [_tok(tavik), _tok(garrik)])
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_death_ward",
        json={"character_id": tavik["id"],
              "target_character_id": garrik["id"]},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
    assert body["feature"] == "death-ward"
    assert body["buff_installed"] is True
    assert body["duration_rounds"] == 4800
    assert body["target_character_id"] == garrik["id"]

    buffs = await _get_buffs(gm_client, garrik["id"])
    dw = next((b for b in buffs if b.get("key") == "death-ward"), None)
    assert dw is not None, f"death-ward buff missing: {buffs}"
    assert (dw.get("effects") or {}).get("death_ward") is True


async def test_cast_death_ward_is_8_hours_non_concentration(gm_client, roster):
    """The installed buff carries duration_rounds=4800 (8 hours) and
    concentration=false."""
    tavik = roster["Brother Tavik Stonebrow"]
    await _set_battle(gm_client, [_tok(tavik)])
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_death_ward",
        json={"character_id": tavik["id"]},
    )
    assert r.status_code == 200, r.text
    buffs = await _get_buffs(gm_client, tavik["id"])
    dw = next((b for b in buffs if b.get("key") == "death-ward"), None)
    assert dw is not None
    assert dw.get("concentration") is False
    assert int(dw.get("duration_rounds") or 0) == 4800


async def test_death_ward_floors_lethal_hit_at_1_hp(gm_client, gm_ws, roster):
    """GATE: with Death Ward on Garrik, a hit that would drop him to 0
    instead leaves him at 1 HP, the buff is consumed, and a
    feature_used(source=death-ward, 'held at 1 HP') broadcast fires."""
    pip = roster["Pip Quickfingers"]
    tavik = roster["Brother Tavik Stonebrow"]
    garrik = roster["Garrik Ironside"]
    await _long_rest(gm_client, pip["id"])
    await _long_rest(gm_client, garrik["id"])
    garrik_tok = f"tok_dw_{garrik['id']}"
    await _set_battle(gm_client, [
        _tok(pip, hp_current=40, hp_max=40),
        _tok(garrik, hp_current=3, hp_max=60),
    ])
    # Ward Garrik (mirrors the buff to his sheet so the HP floor reads it).
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_death_ward",
        json={"character_id": tavik["id"],
              "target_character_id": garrik["id"]},
    )
    assert r.status_code == 200, r.text
    # Put Garrik at 3 HP so any hit ≥3 would drop him to 0.
    await _set_hp(gm_client, garrik["id"], 3)

    gm_ws.mark()
    hit_landed = False
    _log = AttemptLog()
    for seed in range(1, 200):
        await _seed_dice(gm_client, seed)
        a = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/attack",
            json={
                "character_id": pip["id"],
                "attack_index": 0,
                "target_combatant_id": garrik_tok,
                "override": True,
            },
        )
        _log.record(a)
        if a.status_code != 200:
            continue
        data = a.json()
        if data.get("hit") and int(data.get("damage_applied") or 0) >= 3:
            hit_landed = True
            break
    assert hit_landed, f"no hit dealing >=3 damage landed in 200 seeds — {_log.summary()}"

    import asyncio as _asy
    await _asy.sleep(0.3)

    # HP update shows 1, not 0.
    hp_msgs = [
        m for m in gm_ws.buffered("character_hp_update")
        if (m.get("data") or {}).get("character_id") == garrik["id"]
    ]
    assert hp_msgs, "expected a character_hp_update for Garrik"
    assert (hp_msgs[-1].get("data") or {}).get("hp", {}).get("current") == 1, (
        f"expected HP=1 after Death Ward floor; got {hp_msgs[-1].get('data')}"
    )

    # The fire broadcast (distinct from the cast broadcast by its
    # "held at 1 HP" feature_name) fired.
    fire = [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "death-ward"
        and "held" in str((m.get("data") or {}).get("feature_name", ""))
    ]
    assert fire, (
        "expected a feature_used(source=death-ward, held at 1 HP) broadcast"
    )

    # Buff consumed.
    keys = {b.get("key") for b in await _get_buffs(gm_client, garrik["id"])}
    assert "death-ward" not in keys, f"death-ward should be consumed: {keys}"


async def test_cast_death_ward_non_caster_rejected(gm_client, roster):
    """Krieger (Barbarian) → 409 cannot_cast."""
    krieger = roster["Krieger Stonefist"]
    await _set_battle(gm_client, [_tok(krieger)])
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_death_ward",
        json={"character_id": krieger["id"]},
    )
    assert r.status_code == 409, r.text
    assert r.json()["error"] == "cannot_cast"
    assert "death ward" in r.json()["expected"].lower()


async def test_cast_death_ward_missing_character_id_400(gm_client):
    """Missing character_id → 400."""
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_death_ward",
        json={},
    )
    assert r.status_code == 400, r.text
