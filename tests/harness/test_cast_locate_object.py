"""Locate Object — L2 divination, Bard/Cleric/Druid/Ranger/Wizard.
Phase 2 #58 of ``docs/plans/cast-and-broadcast-tail.md``.

v2.544.0 — RAW PHB p.256: "Describe or name an object that is familiar
to you. You sense the direction to the object's location, as long as
that object is within 1,000 feet of you." Self, Concentration up to 10
minutes. The direction-sensing is GM-narrated (no spatial search); the
mechanical half is the **concentration ride** — the buff is
concentration-bound, so casting another concentration spell drops it
(you can't locate two things at once).

Tests:
  - Self-cast installs a concentration `locate-object` buff carrying
    locate_target + locate_range_ft 1000 (10 rounds → 100).
  - A named `object_name` surfaces as locate_target.
  - Concentration ride: casting Barkskin (another concentration spell)
    drops the locate buff.
  - Non-caster (Barbarian) → 409; missing character_id → 400.
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID


def _tok(char, tid=None, init=10):
    return {
        "id": tid or f"tok_lo_{char['id']}",
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
        for key in ("locate-object", "barkskin"):
            await gm_client.post(
                f"/api/campaign/{CAMPAIGN_ID}/end_buff",
                json={"character_id": mira["id"], "key": key},
            )
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": [], "turn_index": 0, "round": 1, "active": False},
    )


async def test_cast_locate_object_installs_concentration_buff(gm_client, roster):
    """Self-cast → concentration `locate-object` buff with default
    target + 1000 ft range; response flags concentration."""
    mira = roster["Mira Greenleaf"]
    await _set_battle(gm_client, [_tok(mira)])
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_locate_object",
        json={"character_id": mira["id"]},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
    assert body["feature"] == "locate-object"
    assert body["locate_range_ft"] == 1000
    assert body["concentration"] is True
    assert body["duration_rounds"] == 100
    assert body["locate_target"] == "an object"

    buffs = await _buffs(gm_client, mira["id"])
    lo = next((b for b in buffs if b.get("key") == "locate-object"), None)
    assert lo is not None, f"buff missing: {buffs}"
    assert lo.get("concentration") is True
    eff = lo.get("effects") or {}
    assert eff.get("locate_active") is True
    assert int(eff.get("locate_range_ft") or 0) == 1000
    assert eff.get("locate_target") == "an object"


async def test_cast_locate_object_named_target(gm_client, roster):
    """A named object surfaces as locate_target."""
    mira = roster["Mira Greenleaf"]
    await _set_battle(gm_client, [_tok(mira)])
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_locate_object",
        json={"character_id": mira["id"], "object_name": "the lost crown"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["locate_target"] == "the lost crown"
    buffs = await _buffs(gm_client, mira["id"])
    lo = next((b for b in buffs if b.get("key") == "locate-object"), None)
    assert (lo.get("effects") or {}).get("locate_target") == "the lost crown"


async def test_locate_object_drops_on_new_concentration(gm_client, roster):
    """Concentration ride: casting Barkskin (another concentration
    spell) drops the Locate Object buff — you can't locate while
    concentrating on something else."""
    mira = roster["Mira Greenleaf"]
    await _set_battle(gm_client, [_tok(mira)])
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_locate_object",
        json={"character_id": mira["id"]},
    )
    assert r.status_code == 200, r.text
    assert any(b.get("key") == "locate-object"
               for b in await _buffs(gm_client, mira["id"]))

    # A second concentration spell drops the first (RAW one-at-a-time).
    b = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_barkskin",
        json={"character_id": mira["id"]},
    )
    assert b.status_code == 200, b.text
    after = await _buffs(gm_client, mira["id"])
    assert not any(x.get("key") == "locate-object" for x in after), after
    assert any(x.get("key") == "barkskin" for x in after), after


async def test_cast_locate_object_non_caster_rejected(gm_client, roster):
    """Krieger (Barbarian) → 409 cannot_cast."""
    krieger = roster["Krieger Stonefist"]
    await _set_battle(gm_client, [_tok(krieger)])
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_locate_object",
        json={"character_id": krieger["id"]},
    )
    assert r.status_code == 409, r.text
    assert r.json()["error"] == "cannot_cast"
    assert "locate object" in r.json()["expected"].lower()


async def test_cast_locate_object_missing_character_id_400(gm_client):
    """Missing character_id → 400."""
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_locate_object",
        json={},
    )
    assert r.status_code == 400, r.text
