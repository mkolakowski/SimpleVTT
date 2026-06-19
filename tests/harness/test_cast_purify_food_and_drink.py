"""Purify Food and Drink — L1 transmutation ritual,
Cleric/Druid/Paladin. Phase 2 #17 of
``docs/plans/cast-and-broadcast-tail.md``.

v2.460.0 — RAW PHB p.270: "All nonmagical food and drink within
a 5-foot-radius sphere centered on a point of your choice within
range is purified and rendered free of poison and disease." 1
action (ritual), V/S, 10 ft, Instantaneous.

**Second non-buff cast in the Phase 2 arc** (after Identify
v2.459.0). The endpoint broadcasts a `feature_used` card naming
the caster + the spell; the GM narrates which rations/wineskins
were purified.

Tests:
  - Cleric (Tavik) self-casts → response carries
    feature == "purify-food-and-drink"; no buff installed.
  - Druid (Mira) self-casts → response 200; asserts the gate
    covers Druids too.
  - Paladin (Caelan) self-casts → response 200; asserts the gate
    covers Paladins too.
  - Krieger (Barbarian) → 409 cannot_cast.
"""
from .conftest import CAMPAIGN_ID


async def _set_battle(gm_client, caster):
    pc_cb = {
        "id": f"tok_pfd_caster_{caster['id']}",
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


async def _get_buffs(gm_client, char_id):
    r = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/buffs",
    )
    assert r.status_code == 200, r.text
    return r.json().get("buffs") or []


async def test_cast_pfd_cleric_no_buff_installed(gm_client, roster):
    """Tavik (Cleric) self-casts; response carries the feature
    slug, and NO purify-food-and-drink buff is installed (RAW
    instantaneous)."""
    cleric = roster["Brother Tavik Stonebrow"]
    await _set_battle(gm_client, cleric)
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_purify_food_and_drink",
        json={"character_id": cleric["id"]},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
    assert body["feature"] == "purify-food-and-drink"

    buffs = await _get_buffs(gm_client, cleric["id"])
    assert not any(
        b.get("key") == "purify-food-and-drink" for b in buffs
    ), (
        "no purify-food-and-drink buff expected (instantaneous spell); "
        f"got {buffs}"
    )


async def test_cast_pfd_druid_succeeds(gm_client, roster):
    """Mira (Druid) succeeds — asserts the gate covers Druids."""
    if "Mira Greenleaf" not in roster:
        import pytest
        pytest.skip("no Druid in the demo roster")
    druid = roster["Mira Greenleaf"]
    await _set_battle(gm_client, druid)
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_purify_food_and_drink",
        json={"character_id": druid["id"]},
    )
    assert r.status_code == 200, r.text
    assert r.json()["ok"] is True


async def test_cast_pfd_paladin_succeeds(gm_client, roster):
    """Caelan (Paladin) succeeds — asserts the gate covers
    Paladins."""
    if "Sir Caelan Lightbringer" not in roster:
        import pytest
        pytest.skip("no Paladin in the demo roster")
    paladin = roster["Sir Caelan Lightbringer"]
    await _set_battle(gm_client, paladin)
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_purify_food_and_drink",
        json={"character_id": paladin["id"]},
    )
    assert r.status_code == 200, r.text
    assert r.json()["ok"] is True


async def test_cast_pfd_non_caster_rejected(gm_client, roster):
    """Krieger (Barbarian) → 409 cannot_cast — Purify Food and
    Drink is Cleric/Druid/Paladin only per RAW."""
    krieger = roster["Krieger Stonefist"]
    await _set_battle(gm_client, krieger)
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_purify_food_and_drink",
        json={"character_id": krieger["id"]},
    )
    assert r.status_code == 409, r.text
    body = r.json()
    assert body["error"] == "cannot_cast"
    assert "purify food and drink" in body["expected"].lower()
