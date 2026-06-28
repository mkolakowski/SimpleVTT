"""v2.729.0 — initiative-tracker "🎲 Prompt" roll requests.

A GM can prompt a player to roll initiative for a combatant that has none yet.
The prompt is a roll-request carrying `initiative_combatant_id`; when the
player (or GM) responds, the rolled total is written back as that combatant's
initiative and the tracker re-sorts (the prompt button then disappears).

Tests:
  - create echoes `initiative_combatant_id`;
  - responding writes the total back as the combatant's initiative (GET /battle);
  - a plain roll-request (no linkage) leaves initiative untouched (control).
"""
from .conftest import CAMPAIGN_ID


def _cb(cid, char, init=0):
    return {"id": cid, "char_id": char["id"], "name": char["name"],
            "initiative": init, "hp_current": 30, "hp_max": 30, "buffs": [],
            "economy": {"action": False, "bonus": False,
                        "reaction": False, "movement": 0}}


async def _seed(gm_client, combatants):
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": combatants, "turn_index": 0, "round": 1,
              "active": True})


async def _battle_combatant(gm_client, cid):
    b = (await gm_client.get(f"/api/campaign/{CAMPAIGN_ID}/battle")).json()
    state = b.get("battle") or {}
    return next((c for c in (state.get("combatants") or [])
                 if c.get("id") == cid), None)


async def test_initiative_prompt_writes_back_initiative(gm_client, roster):
    pip = roster["Pip Quickfingers"]
    cid = "tok_initprompt_pip"
    await _seed(gm_client, [_cb(cid, pip, init=0)])

    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/roll_request",
        json={"label": "Roll initiative — Pip", "stat_key": "initiative",
              "base_expression": "1d20", "initiative_combatant_id": cid})
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["initiative_combatant_id"] == cid  # echoed back
    req_id = data["id"]

    # GM responds on the character's behalf → records the roll.
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/roll_request/{req_id}/respond",
        json={"character_id": pip["id"]})
    assert resp.status_code == 200, resp.text
    total = resp.json()["total"]
    assert total >= 1

    # The combatant's initiative now equals the rolled total.
    c = await _battle_combatant(gm_client, cid)
    assert c is not None
    assert c["initiative"] == total, c


async def test_plain_roll_request_does_not_touch_initiative(gm_client, roster):
    """Control: a roll-request WITHOUT the initiative linkage doesn't change
    any combatant's initiative."""
    pip = roster["Pip Quickfingers"]
    cid = "tok_noinitlink_pip"
    await _seed(gm_client, [_cb(cid, pip, init=0)])

    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/roll_request",
        json={"label": "DEX check", "stat_key": "dex_check",
              "base_expression": "1d20"})
    assert r.status_code == 200, r.text
    assert r.json().get("initiative_combatant_id") is None
    req_id = r.json()["id"]
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/roll_request/{req_id}/respond",
        json={"character_id": pip["id"]})

    c = await _battle_combatant(gm_client, cid)
    assert c is not None
    assert c["initiative"] == 0, c  # unchanged
