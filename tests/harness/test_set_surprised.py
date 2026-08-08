"""v2.1056.0 — surprise-state model (RAW PHB p.189).

`POST /api/campaign/{cid}/set_surprised {combatant_ids, surprised}` (GM)
marks combatants surprised on the combatant dict in hub state. The flag
drives the Assassin rogue's auto-crit server-side (`_target_is_surprised`
in `/attack`) instead of the one-shot client `target_surprised`, and
auto-clears when the creature takes its first turn (turn-advance hook).

Tests:
  - Toggle marks + clears; GM-only; 400 no ids; unknown ids skipped.
  - An Assassin's hit against a server-flagged surprised target auto-crits
    (no client `target_surprised`).
  - The flag auto-clears when the target takes its first turn.
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID


def _pc(cid, char_id, name):
    return {"id": cid, "char_id": char_id, "name": name, "initiative": 20,
            "hp_current": 30, "hp_max": 30, "buffs": [],
            "economy": {"action": False, "bonus": False,
                        "reaction": False, "movement": 0}}


def _npc(cid, tmpl_id, name, ac=5):
    return {"id": cid, "char_id": None, "token_template_id": tmpl_id,
            "name": name, "initiative": 1, "ac": ac,
            "hp_current": 999, "hp_max": 999, "buffs": [],
            "economy": {"action": False, "bonus": False,
                        "reaction": False, "movement": 0}}


async def _bandit_tmpl(gm_client):
    r = await gm_client.get(f"/api/campaign/{CAMPAIGN_ID}/templates")
    return next(t for t in r.json() if "bandit" in t["name"].lower())


async def _seed(gm_client, combatants, turn_index=0):
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": combatants, "turn_index": turn_index,
              "round": 1, "active": True},
    )


async def _combatant(gm_client, cid):
    state = (await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/battle")).json().get("battle") or {}
    for c in (state.get("combatants") or []):
        if c.get("id") == cid:
            return c
    return None


async def _set_surprised(gm_client, ids, surprised=True):
    return await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/set_surprised",
        json={"combatant_ids": ids, "surprised": surprised},
    )


@pytest_asyncio.fixture
async def battle(gm_client, roster):
    pip = roster["Pip Quickfingers"]
    tmpl = await _bandit_tmpl(gm_client)
    pid, tid = f"tok_sp_pip_{pip['id']}", "tok_sp_target"
    await _seed(gm_client, [_pc(pid, pip["id"], pip["name"]),
                            _npc(tid, tmpl["id"], "Sleeping Guard")])
    try:
        yield {"pip": pip, "pid": pid, "tid": tid}
    finally:
        await gm_client.put(
            f"/api/campaign/{CAMPAIGN_ID}/battle",
            json={"combatants": [], "turn_index": 0, "round": 1,
                  "active": False},
        )


async def test_set_surprised_marks_and_clears(gm_client, battle):
    tid = battle["tid"]
    r = await _set_surprised(gm_client, [tid], True)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["updated"] == [tid] and d["surprised"] is True, d
    assert (await _combatant(gm_client, tid))["surprised"] is True
    r = await _set_surprised(gm_client, [tid], False)
    assert r.status_code == 200, r.text
    assert (await _combatant(gm_client, tid))["surprised"] is False


async def test_set_surprised_gm_only(alice_client, battle):
    r = await alice_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/set_surprised",
        json={"combatant_ids": [battle["tid"]], "surprised": True},
    )
    assert r.status_code == 403, r.text


async def test_set_surprised_no_ids(gm_client, battle):
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/set_surprised", json={"surprised": True})
    assert r.status_code == 400, r.text


async def test_set_surprised_unknown_skipped(gm_client, battle):
    r = await _set_surprised(gm_client, ["tok_ghost"], True)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["updated"] == [] and "tok_ghost" in d["skipped"], d


async def _seed_dice(gm_client, seed):
    await gm_client.post("/api/test/dice/seed", json={"seed": seed})


async def test_assassinate_auto_crit_from_server_flag(gm_client, gm_ws, battle):
    """An Assassin's hit against a server-flagged surprised target
    auto-crits — no client `target_surprised` in the attack body."""
    pip, tid = battle["pip"], battle["tid"]
    snap = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{pip['id']}/sheet-json")
    orig = ((snap.json() or {}).get("sheet") or {}).get("subclass") or ""
    await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{pip['id']}/sheet-fields",
        json={"subclass": "Assassin"})
    try:
        assert (await _set_surprised(gm_client, [tid], True)).status_code == 200
        await _seed_dice(gm_client, 3)  # deterministic hit vs AC 5
        gm_ws.mark()
        resp = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/attack",
            json={"character_id": pip["id"], "attack_index": 0,
                  "target_combatant_id": tid, "override": True},
        )
        assert resp.status_code == 200, resp.text
        msg = await gm_ws.wait_for("weapon_attack")
        d = msg["data"]
        assert d.get("is_crit") is True, (
            f"server surprise flag should auto-crit for an Assassin; got "
            f"is_crit={d.get('is_crit')!r} (hit={d.get('hit')!r})"
        )
    finally:
        await _seed_dice(gm_client, None)
        await gm_client.patch(
            f"/api/campaign/{CAMPAIGN_ID}/character/{pip['id']}/sheet-fields",
            json={"subclass": orig})


async def test_surprise_clears_on_first_turn(gm_client, battle):
    """The `surprised` flag auto-clears once the target takes its turn."""
    pip, pid, tid = battle["pip"], battle["pid"], battle["tid"]
    assert (await _set_surprised(gm_client, [tid], True)).status_code == 200
    assert (await _combatant(gm_client, tid))["surprised"] is True
    # Advance the turn to the target (index 1) — its turn starts, surprise ends.
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": [_pc(pid, pip["id"], pip["name"]),
                             {**(await _combatant(gm_client, tid))}],
              "turn_index": 1, "round": 1, "active": True},
    )
    assert (await _combatant(gm_client, tid))["surprised"] is False
