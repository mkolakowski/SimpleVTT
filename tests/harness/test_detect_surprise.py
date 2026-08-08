"""v2.1057.0 — auto-detect surprise (RAW PHB p.189).

`POST /api/campaign/{cid}/detect_surprise {ambusher_combatant_ids}` (GM)
rolls each ambusher's Dexterity (Stealth) check and compares it against
every other combatant's passive Wisdom (Perception). A defender that
notices no ambusher (passive < every ambusher roll) is surprised — its
combatant `surprised` flag is set, feeding the Assassinate auto-crit.

Tests:
  - A stealthy ambusher vs a low-Perception defender → the defender is
    flagged surprised (and the flag persists on the combatant).
  - Consistency: ambushers are never surprised; surprised ∪ not_surprised
    covers all non-ambushers; threshold == min ambusher roll.
  - GM-only; 400 on no ambushers.
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID


def _pc(cid, char_id, name):
    return {"id": cid, "char_id": char_id, "name": name, "initiative": 20,
            "hp_current": 30, "hp_max": 30, "buffs": [],
            "economy": {"action": False, "bonus": False,
                        "reaction": False, "movement": 0}}


def _npc(cid, tmpl_id, name):
    return {"id": cid, "char_id": None, "token_template_id": tmpl_id,
            "name": name, "initiative": 1, "hp_current": 30, "hp_max": 30,
            "buffs": [], "economy": {"action": False, "bonus": False,
                                     "reaction": False, "movement": 0}}


async def _bandit_tmpl(gm_client):
    r = await gm_client.get(f"/api/campaign/{CAMPAIGN_ID}/templates")
    return next(t for t in r.json() if "bandit" in t["name"].lower())


async def _seed(gm_client, combatants):
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": combatants, "turn_index": 0, "round": 1,
              "active": True},
    )


async def _combatant(gm_client, cid):
    state = (await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/battle")).json().get("battle") or {}
    return next((c for c in (state.get("combatants") or [])
                 if c.get("id") == cid), None)


async def _seed_dice(gm_client, seed):
    await gm_client.post("/api/test/dice/seed", json={"seed": seed})


async def _detect(gm_client, ambusher_ids):
    return await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/detect_surprise",
        json={"ambusher_combatant_ids": ambusher_ids})


@pytest_asyncio.fixture
async def scene(gm_client, roster):
    """Pip (Rogue, high Stealth) ambushes a Bandit (passive Perception 10)."""
    pip = roster["Pip Quickfingers"]
    tmpl = await _bandit_tmpl(gm_client)
    amb, defn = f"tok_ds_amb_{pip['id']}", "tok_ds_guard"
    await _seed(gm_client, [_pc(amb, pip["id"], pip["name"]),
                            _npc(defn, tmpl["id"], "Bandit Guard")])
    try:
        yield {"amb": amb, "defn": defn}
    finally:
        await _seed_dice(gm_client, None)
        await gm_client.put(
            f"/api/campaign/{CAMPAIGN_ID}/battle",
            json={"combatants": [], "turn_index": 0, "round": 1,
                  "active": False},
        )


async def test_detect_flags_low_perception_defender(gm_client, scene):
    amb, defn = scene["amb"], scene["defn"]
    await _seed_dice(gm_client, 4)  # deterministic high-ish Stealth roll
    r = await _detect(gm_client, [amb])
    assert r.status_code == 200, r.text
    d = r.json()
    # The rogue out-stealths the bandit's passive Perception (10).
    assert d["threshold"] > 10, d  # sanity: the seeded roll beat pp 10
    assert defn in d["surprised"], d
    assert amb not in d["surprised"] and amb not in d["not_surprised"], d
    assert (await _combatant(gm_client, defn))["surprised"] is True


async def test_detect_consistency(gm_client, scene):
    amb, defn = scene["amb"], scene["defn"]
    await _seed_dice(gm_client, 4)
    r = await _detect(gm_client, [amb])
    assert r.status_code == 200, r.text
    d = r.json()
    # threshold is the minimum ambusher roll; every non-ambusher is
    # partitioned into exactly one of surprised / not_surprised.
    assert d["threshold"] == min(x["stealth"] for x in d["ambusher_rolls"]), d
    assert set(d["surprised"]) | set(d["not_surprised"]) == {defn}, d
    assert not (set(d["surprised"]) & set(d["not_surprised"])), d


async def test_detect_gm_only(alice_client, scene):
    r = await alice_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/detect_surprise",
        json={"ambusher_combatant_ids": [scene["amb"]]})
    assert r.status_code == 403, r.text


async def test_detect_no_ambushers(gm_client, scene):
    r = await _detect(gm_client, [])
    assert r.status_code == 400, r.text
