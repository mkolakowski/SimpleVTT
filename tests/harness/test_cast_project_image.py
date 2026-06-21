"""Project Image — L7 illusion, Bard/Wizard.
Phase 2 #61 of ``docs/plans/cast-and-broadcast-tail.md``.

v2.547.0 — RAW PHB p.270: "You create an illusory copy of yourself that
lasts for the duration. ... The illusion looks and sounds like you but
is intangible. ... you can see through its eyes and hear through its
ears as if you were in its space." 500 miles, Concentration up to 24
hours. Unlike Mislead (#60) it grants no invisibility — the remote
intangible copy is GM-narrated, so the mechanical half is the
concentration flag-buff marking the active projection.

Tests:
  - Self-cast installs a concentration `project-image` buff carrying
    project_image_active + a location label (14400 rounds).
  - A named `location` surfaces on the buff + response.
  - Concentration ride: casting Fly drops the projection.
  - Non-caster (Barbarian) → 409; missing character_id → 400.
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID


def _tok(char, tid=None, init=10):
    return {
        "id": tid or f"tok_pi_{char['id']}",
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
    thal = roster.get("Thalindra Moonwhisper")
    if thal:
        for key in ("project-image", "fly"):
            await gm_client.post(
                f"/api/campaign/{CAMPAIGN_ID}/end_buff",
                json={"character_id": thal["id"], "key": key},
            )
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": [], "turn_index": 0, "round": 1, "active": False},
    )


async def test_cast_project_image_installs_concentration_buff(gm_client, roster):
    """Self-cast → concentration `project-image` buff with default
    location + 24h duration; response flags concentration."""
    thal = roster["Thalindra Moonwhisper"]
    await _set_battle(gm_client, [_tok(thal)])
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_project_image",
        json={"character_id": thal["id"]},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
    assert body["feature"] == "project-image"
    assert body["concentration"] is True
    assert body["duration_rounds"] == 14400
    assert body["location"] == "a remembered location"

    buffs = await _buffs(gm_client, thal["id"])
    pi = next((b for b in buffs if b.get("key") == "project-image"), None)
    assert pi is not None, f"buff missing: {buffs}"
    assert pi.get("concentration") is True
    eff = pi.get("effects") or {}
    assert eff.get("project_image_active") is True
    assert eff.get("project_image_location") == "a remembered location"


async def test_cast_project_image_named_location(gm_client, roster):
    """A named location surfaces on response + buff."""
    thal = roster["Thalindra Moonwhisper"]
    await _set_battle(gm_client, [_tok(thal)])
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_project_image",
        json={"character_id": thal["id"], "location": "the throne room"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["location"] == "the throne room"
    buffs = await _buffs(gm_client, thal["id"])
    pi = next((b for b in buffs if b.get("key") == "project-image"), None)
    assert (pi.get("effects") or {}).get("project_image_location") == "the throne room"


async def test_project_image_drops_on_new_concentration(gm_client, roster):
    """Concentration ride: casting Fly drops the projection."""
    thal = roster["Thalindra Moonwhisper"]
    await _set_battle(gm_client, [_tok(thal)])
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_project_image",
        json={"character_id": thal["id"]},
    )
    assert r.status_code == 200, r.text
    assert any(b.get("key") == "project-image"
               for b in await _buffs(gm_client, thal["id"]))

    f = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_fly",
        json={"character_id": thal["id"]},
    )
    assert f.status_code == 200, f.text
    after = await _buffs(gm_client, thal["id"])
    assert not any(x.get("key") == "project-image" for x in after), after
    assert any(x.get("key") == "fly" for x in after), after


async def test_cast_project_image_non_caster_rejected(gm_client, roster):
    """Krieger (Barbarian) → 409 cannot_cast."""
    krieger = roster["Krieger Stonefist"]
    await _set_battle(gm_client, [_tok(krieger)])
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_project_image",
        json={"character_id": krieger["id"]},
    )
    assert r.status_code == 409, r.text
    assert r.json()["error"] == "cannot_cast"
    assert "project image" in r.json()["expected"].lower()


async def test_cast_project_image_missing_character_id_400(gm_client):
    """Missing character_id → 400."""
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_project_image",
        json={},
    )
    assert r.status_code == 400, r.text
