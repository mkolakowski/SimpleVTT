"""Find Steed — L2 conjuration, Paladin. Phase 1 demonstrator #2
(the Phase 1 closer) of ``docs/plans/cast-and-broadcast-tail.md``.

v2.441.0 — RAW PHB p.240: "You summon a spirit that assumes the
form of an unusually intelligent, strong, and loyal steed... the
steed takes on a form that you choose: a warhorse, a pony, a camel,
an elk, or a mastiff." Action, V/S, 30 ft, Instantaneous.

Phase 1 of the cast-and-broadcast tail closes with this ship — all 5
demonstrators wired. Reuses the existing v2.99.437 summon primitive
+ five new ``find-steed-*`` companion templates; concentration-bound
so a future drop-concentration cascade dismisses the steed
RAW-correctly.

Caster fixture: Dame Seraphine Vael (Vengeance Paladin, demo seed
v2.158.56).

Tests:
  - Happy path (warhorse): spawns a summon combatant tagged
    `is_summon` + `summoned_by` = Seraphine; companion_key is
    `find-steed-warhorse`; concentration_bound is True.
  - Mastiff variant uses the smaller stat block.
  - Krieger (Barbarian) → 409 cannot_cast.
  - Missing/unknown steed_type → 400.
"""
from .conftest import CAMPAIGN_ID


async def _seed_battle(gm_client, combatants):
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": combatants, "turn_index": 0,
              "round": 1, "active": False},
    )


def _pc_cb(c):
    return {
        "id": f"tok_fs_{c['id']}", "char_id": c["id"], "name": c["name"],
        "initiative": 10, "hp_current": 30, "hp_max": 30, "buffs": [],
        "economy": {"action": False, "bonus": False,
                    "reaction": False, "movement": 0},
    }


async def test_cast_find_steed_warhorse(gm_client, roster):
    """Seraphine summons a warhorse → real summon combatant +
    token; tagged as her summon; concentration-bound; HP/AC match
    the SRD warhorse stat block."""
    seraphine = roster["Dame Seraphine Vael"]
    await _seed_battle(gm_client, [_pc_cb(seraphine)])

    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_find_steed",
        json={"character_id": seraphine["id"], "steed_type": "warhorse",
              "x": 700.0, "y": 700.0},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    cb = body["combatant"]
    try:
        assert body["feature"] == "find-steed"
        assert body["steed_type"] == "warhorse"
        assert cb["is_summon"] is True
        assert cb["companion_key"] == "find-steed-warhorse"
        assert cb["summoned_by"] == seraphine["id"]
        assert cb["concentration_bound"] is True
        # SRD warhorse stat block (matches monsters/warhorse.json).
        assert cb["hp_max"] == 19
        assert cb["ac"] == 11
        assert cb["speed_walk"] == 60
        assert "Warhorse" in cb["name"]
        assert body["token_id"] is not None
    finally:
        await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/dismiss_companion",
            json={"combatant_id": cb["id"]},
        )


async def test_cast_find_steed_mastiff_variant(gm_client, roster):
    """The same caster, different steed type → the mastiff stat block
    (HP 5, AC 12, 40-ft speed) lands."""
    seraphine = roster["Dame Seraphine Vael"]
    await _seed_battle(gm_client, [_pc_cb(seraphine)])

    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_find_steed",
        json={"character_id": seraphine["id"], "steed_type": "mastiff",
              "x": 800.0, "y": 800.0},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    cb = body["combatant"]
    try:
        assert body["steed_type"] == "mastiff"
        assert cb["companion_key"] == "find-steed-mastiff"
        # SRD mastiff stat block (matches monsters/mastiff.json).
        assert cb["hp_max"] == 5
        assert cb["ac"] == 12
        assert cb["speed_walk"] == 40
    finally:
        await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/dismiss_companion",
            json={"combatant_id": cb["id"]},
        )


async def test_cast_find_steed_non_paladin_rejected(gm_client, roster):
    """Krieger Stonefist is a Barbarian — not a paladin. Returns 409
    cannot_cast."""
    krieger = roster["Krieger Stonefist"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_find_steed",
        json={"character_id": krieger["id"], "steed_type": "warhorse"},
    )
    assert r.status_code == 409, r.text
    body = r.json()
    assert body["error"] == "cannot_cast"
    assert "find steed" in body["expected"].lower()


async def test_cast_find_steed_invalid_steed_type_400(gm_client, roster):
    """Missing or unknown steed_type → 400."""
    seraphine = roster["Dame Seraphine Vael"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_find_steed",
        json={"character_id": seraphine["id"], "steed_type": "dragon"},
    )
    assert r.status_code == 400, r.text
    assert "steed_type" in r.text.lower()
