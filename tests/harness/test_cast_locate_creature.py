"""Locate Creature — L4 divination, Bard/Cleric/Druid/Ranger/Wizard.
Phase 2 #59 of ``docs/plans/cast-and-broadcast-tail.md``.

v2.545.0 — RAW PHB p.256: "Describe or name a creature that is familiar
to you. You sense the direction to the creature's location, as long as
that creature is within 1,000 feet of you." Self, Concentration up to 1
hour. The L4, 1-hour sibling of Locate Object (#58) on the shared
`_do_cast_locate` helper — bearing GM-narrated, concentration ride
mechanical.

Tests:
  - Self-cast installs a concentration `locate-creature` buff carrying
    locate_target + locate_range_ft 1000 (1 hour → 600 rounds).
  - A named `creature_name` surfaces as locate_target.
  - Concentration ride: casting Barkskin drops the locate buff.
  - Non-caster (Barbarian) → 409; missing character_id → 400.
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID


def _tok(char, tid=None, init=10):
    return {
        "id": tid or f"tok_lc_{char['id']}",
        "char_id": char["id"],
        "name": char["name"],
        "initiative": init,
        "hp_current": 40, "hp_max": 40,
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


async def _buffs(gm_client, char_id):
    r = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/buffs",
    )
    assert r.status_code == 200, r.text
    return r.json().get("buffs") or []


@pytest_asyncio.fixture(autouse=True)
async def _cleanup(gm_client, roster):
    yield
    mira = roster.get("Mira Greenleaf")
    if mira:
        for key in ("locate-creature", "barkskin"):
            await gm_client.post(
                f"/api/campaign/{CAMPAIGN_ID}/end_buff",
                json={"character_id": mira["id"], "key": key},
            )
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": [], "turn_index": 0, "round": 1, "active": False},
    )


async def test_cast_locate_creature_installs_concentration_buff(gm_client, roster):
    """Self-cast → concentration `locate-creature` buff with default
    target + 1000 ft range, 600 rounds; response flags concentration."""
    mira = roster["Mira Greenleaf"]
    await _set_battle(gm_client, [_tok(mira)])
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_locate_creature",
        json={"character_id": mira["id"]},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
    assert body["feature"] == "locate-creature"
    assert body["locate_range_ft"] == 1000
    assert body["concentration"] is True
    assert body["duration_rounds"] == 600
    assert body["locate_target"] == "a creature"

    buffs = await _buffs(gm_client, mira["id"])
    lc = next((b for b in buffs if b.get("key") == "locate-creature"), None)
    assert lc is not None, f"buff missing: {buffs}"
    assert lc.get("concentration") is True
    eff = lc.get("effects") or {}
    assert eff.get("locate_active") is True
    assert int(eff.get("locate_range_ft") or 0) == 1000
    assert eff.get("locate_kind") == "creature"


async def test_cast_locate_creature_named_target(gm_client, roster):
    """A named creature surfaces as locate_target."""
    mira = roster["Mira Greenleaf"]
    await _set_battle(gm_client, [_tok(mira)])
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_locate_creature",
        json={"character_id": mira["id"], "creature_name": "the fled goblin"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["locate_target"] == "the fled goblin"
    buffs = await _buffs(gm_client, mira["id"])
    lc = next((b for b in buffs if b.get("key") == "locate-creature"), None)
    assert (lc.get("effects") or {}).get("locate_target") == "the fled goblin"


async def test_locate_creature_drops_on_new_concentration(gm_client, roster):
    """Concentration ride: casting Barkskin drops the Locate Creature
    buff — you can't locate while concentrating on something else."""
    mira = roster["Mira Greenleaf"]
    await _set_battle(gm_client, [_tok(mira)])
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_locate_creature",
        json={"character_id": mira["id"]},
    )
    assert r.status_code == 200, r.text
    assert any(b.get("key") == "locate-creature"
               for b in await _buffs(gm_client, mira["id"]))

    b = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_barkskin",
        json={"character_id": mira["id"]},
    )
    assert b.status_code == 200, b.text
    after = await _buffs(gm_client, mira["id"])
    assert not any(x.get("key") == "locate-creature" for x in after), after
    assert any(x.get("key") == "barkskin" for x in after), after


async def test_cast_locate_creature_non_caster_rejected(gm_client, roster):
    """Krieger (Barbarian) → 409 cannot_cast."""
    krieger = roster["Krieger Stonefist"]
    await _set_battle(gm_client, [_tok(krieger)])
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_locate_creature",
        json={"character_id": krieger["id"]},
    )
    assert r.status_code == 409, r.text
    assert r.json()["error"] == "cannot_cast"
    assert "locate creature" in r.json()["expected"].lower()


async def test_cast_locate_creature_missing_character_id_400(gm_client):
    """Missing character_id → 400."""
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_locate_creature",
        json={},
    )
    assert r.status_code == 400, r.text
