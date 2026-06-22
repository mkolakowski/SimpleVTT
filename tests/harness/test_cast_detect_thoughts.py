"""Detect Thoughts — L2 divination, Bard/Sorcerer/Warlock/Wizard.
Phase 2 #64 of ``docs/plans/cast-and-broadcast-tail.md``.

v2.550.0 — RAW PHB p.231: "For the duration, you can read the thoughts
of certain creatures. ... you can read its surface thoughts ... you can
probe deeper ... it must make a Wisdom saving throw." Self, Concentration
up to 1 minute. A concentration flag-buff in the Zone of Truth DC-bake
mould: the buff carries `detect_thoughts: True` + a baked WIS `save_dc`
for the deeper probe. Thought-reading + the save are GM-narrated.

Tests:
  - Self-cast installs a concentration `detect-thoughts` buff with a
    baked WIS save_dc (10 rounds).
  - Concentration ride: casting Fly drops the buff.
  - Non-caster (Barbarian) → 409; missing character_id → 400.
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID


def _tok(char, tid=None, init=10):
    return {
        "id": tid or f"tok_dt_{char['id']}",
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
        for key in ("detect-thoughts", "fly"):
            await gm_client.post(
                f"/api/campaign/{CAMPAIGN_ID}/end_buff",
                json={"character_id": thal["id"], "key": key},
            )
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": [], "turn_index": 0, "round": 1, "active": False},
    )


async def test_cast_detect_thoughts_installs_dc_concentration_buff(gm_client, roster):
    """Self-cast → concentration `detect-thoughts` buff with a baked WIS
    save_dc; response flags concentration + WIS save."""
    thal = roster["Thalindra Moonwhisper"]
    await _set_battle(gm_client, [_tok(thal)])
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_detect_thoughts",
        json={"character_id": thal["id"]},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
    assert body["feature"] == "detect-thoughts"
    assert body["save_ability"] == "WIS"
    assert isinstance(body["save_dc"], int) and body["save_dc"] >= 8
    assert body["concentration"] is True
    assert body["duration_rounds"] == 10

    buffs = await _buffs(gm_client, thal["id"])
    dt = next((b for b in buffs if b.get("key") == "detect-thoughts"), None)
    assert dt is not None, f"buff missing: {buffs}"
    assert dt.get("concentration") is True
    eff = dt.get("effects") or {}
    assert eff.get("detect_thoughts") is True
    assert eff.get("save_ability") == "WIS"
    assert int(eff.get("save_dc") or 0) == body["save_dc"]


async def test_detect_thoughts_drops_on_new_concentration(gm_client, roster):
    """Concentration ride: casting Fly drops the Detect Thoughts buff."""
    thal = roster["Thalindra Moonwhisper"]
    await _set_battle(gm_client, [_tok(thal)])
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_detect_thoughts",
        json={"character_id": thal["id"]},
    )
    assert r.status_code == 200, r.text
    assert any(b.get("key") == "detect-thoughts"
               for b in await _buffs(gm_client, thal["id"]))

    f = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_fly",
        json={"character_id": thal["id"]},
    )
    assert f.status_code == 200, f.text
    after = await _buffs(gm_client, thal["id"])
    assert not any(x.get("key") == "detect-thoughts" for x in after), after
    assert any(x.get("key") == "fly" for x in after), after


async def test_cast_detect_thoughts_non_caster_rejected(gm_client, roster):
    """Krieger (Barbarian) → 409 cannot_cast."""
    krieger = roster["Krieger Stonefist"]
    await _set_battle(gm_client, [_tok(krieger)])
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_detect_thoughts",
        json={"character_id": krieger["id"]},
    )
    assert r.status_code == 409, r.text
    assert r.json()["error"] == "cannot_cast"
    assert "detect thoughts" in r.json()["expected"].lower()


async def test_cast_detect_thoughts_missing_character_id_400(gm_client):
    """Missing character_id → 400."""
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_detect_thoughts",
        json={},
    )
    assert r.status_code == 400, r.text
