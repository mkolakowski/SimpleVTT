"""Feather Fall — L1 reaction, Bard/Sorcerer/Wizard. Phase 2 #3
of ``docs/plans/cast-and-broadcast-tail.md``.

v2.444.0 — RAW PHB p.239: "Choose up to five falling creatures
within range. A falling creature's rate of descent slows to 60
feet per round until the spell ends. If the creature lands before
the spell ends, it takes no falling damage and can land on its
feet, and the spell ends for that creature." 1 reaction, 60 ft,
1 minute, non-concentration.

Flag buff — same shape as Speak with Animals' (v2.438.0)
`speaks_with_animals` flag and Spider Climb's (v2.439.0)
`climb_speed_equals_walk` flag. The engine doesn't model falling
damage, so the flag IS the mechanic; the GM narrates "no falling
damage" when the target lands.

Caster: Thalindra Moonwhisper (Wizard) is the canonical caster.

Tests:
  - Cast self-targets installs the buff with feather_fall: true.
  - Buff carries duration_rounds=10 + concentration=false.
  - Multi-target: caster + 4 companions ⇒ 5 buffs installed.
  - Over-cap (caster + 5 companions = 6) → 400.
  - Krieger Stonefist (Barbarian) → 409 cannot_cast.
"""
from .conftest import CAMPAIGN_ID


async def _set_battle(gm_client, caster):
    pc_cb = {
        "id": f"tok_ff_caster_{caster['id']}",
        "char_id": caster["id"],
        "name": caster["name"],
        "initiative": 15,
        "hp_current": 30, "hp_max": 30,
        "buffs": [],
        "economy": {"action": False, "bonus": False,
                    "reaction": False, "movement": 0},
    }
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": [pc_cb], "turn_index": 0,
              "round": 1, "active": True},
    )


async def _get_caster_buffs(gm_client, caster_id):
    r = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{caster_id}/buffs",
    )
    assert r.status_code == 200, r.text
    return r.json().get("buffs") or []


async def _find_ff_caster(roster):
    for name in (
        "Thalindra Moonwhisper",  # Wizard
        "Lyra Sunstrider",        # Bard
    ):
        if name in roster:
            return roster[name]
    return None


async def test_cast_feather_fall_installs_buff(gm_client, roster):
    """A Wizard self-targets Feather Fall; the installed buff carries
    effects.feather_fall = true."""
    caster = await _find_ff_caster(roster)
    if caster is None:
        import pytest
        pytest.skip("no Bard/Sorcerer/Wizard in the demo roster")
    await _set_battle(gm_client, caster)
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_feather_fall",
        json={"character_id": caster["id"]},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
    assert body["feature"] == "feather-fall"
    assert body["buffs_installed"] == 1
    assert body["targets"] == [caster["id"]]
    assert body["duration_rounds"] == 10

    buffs = await _get_caster_buffs(gm_client, caster["id"])
    ff_buff = next(
        (b for b in buffs if b.get("key") == "feather-fall"), None,
    )
    assert ff_buff is not None, f"feather-fall buff missing: {buffs}"
    effects = ff_buff.get("effects") or {}
    assert effects.get("feather_fall") is True


async def test_cast_feather_fall_buff_is_1_minute_non_concentration(
    gm_client, roster,
):
    """The installed buff carries duration_rounds=10 (1 minute) and
    concentration=false, matching RAW."""
    caster = await _find_ff_caster(roster)
    if caster is None:
        import pytest
        pytest.skip("no Bard/Sorcerer/Wizard in the demo roster")
    await _set_battle(gm_client, caster)
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_feather_fall",
        json={"character_id": caster["id"]},
    )
    assert r.status_code == 200, r.text
    buffs = await _get_caster_buffs(gm_client, caster["id"])
    ff_buff = next(
        (b for b in buffs if b.get("key") == "feather-fall"), None,
    )
    assert ff_buff is not None
    assert ff_buff.get("concentration") is False
    assert int(ff_buff.get("duration_rounds") or 0) == 10


async def test_cast_feather_fall_multi_target(gm_client, roster):
    """Caster + 4 companions ⇒ 5 buffs installed (the RAW cap).
    All targets must be in the active battle for _install_buff to
    find them as combatants — seed all 5 PCs."""
    caster = await _find_ff_caster(roster)
    if caster is None:
        import pytest
        pytest.skip("no Bard/Sorcerer/Wizard in the demo roster")

    # Pick 4 other PCs from the roster.
    other_pcs: list[dict] = []
    for name in (
        "Pip Quickfingers",
        "Brother Tavik Stonebrow",
        "Krieger Stonefist",
        "Magnus Hexbinder",
    ):
        if name in roster and roster[name]["id"] != caster["id"]:
            other_pcs.append(roster[name])
        if len(other_pcs) >= 4:
            break
    if len(other_pcs) < 4:
        import pytest
        pytest.skip("demo roster too small to test multi-target cap")
    other_ids = [pc["id"] for pc in other_pcs]

    # Seed all 5 PCs into the battle so _install_buff finds them.
    combatants = [{
        "id": f"tok_ff_{c['id']}",
        "char_id": c["id"], "name": c["name"],
        "initiative": 10 + i,
        "hp_current": 30, "hp_max": 30, "buffs": [],
        "economy": {"action": False, "bonus": False,
                    "reaction": False, "movement": 0},
    } for i, c in enumerate([caster] + other_pcs)]
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": combatants, "turn_index": 0,
              "round": 1, "active": True},
    )

    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_feather_fall",
        json={"character_id": caster["id"],
              "target_character_ids": other_ids},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["buffs_installed"] == 5, (
        f"expected 5 buffs (caster + 4); got {body['buffs_installed']} "
        f"with targets={body['targets']}"
    )
    assert caster["id"] in body["targets"]
    for tid in other_ids:
        assert tid in body["targets"], (
            f"target {tid} missing from response: {body['targets']}"
        )


async def test_cast_feather_fall_over_cap_400(gm_client, roster):
    """Caster + 5 companions = 6 unique targets → 400 (RAW cap is 5)."""
    caster = await _find_ff_caster(roster)
    if caster is None:
        import pytest
        pytest.skip("no Bard/Sorcerer/Wizard in the demo roster")
    other_ids: list[int] = []
    for name in (
        "Pip Quickfingers",
        "Brother Tavik Stonebrow",
        "Krieger Stonefist",
        "Magnus Hexbinder",
        "Mira Greenleaf",
    ):
        if name in roster and roster[name]["id"] != caster["id"]:
            other_ids.append(roster[name]["id"])
        if len(other_ids) >= 5:
            break
    if len(other_ids) < 5:
        import pytest
        pytest.skip("demo roster too small to test over-cap")
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_feather_fall",
        json={"character_id": caster["id"],
              "target_character_ids": other_ids},
    )
    assert r.status_code == 400, r.text


async def test_cast_feather_fall_non_caster_rejected(gm_client, roster):
    """Krieger (Barbarian) → 409 cannot_cast."""
    krieger = roster["Krieger Stonefist"]
    await _set_battle(gm_client, krieger)
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_feather_fall",
        json={"character_id": krieger["id"]},
    )
    assert r.status_code == 409, r.text
    body = r.json()
    assert body["error"] == "cannot_cast"
    assert "feather fall" in body["expected"].lower()
