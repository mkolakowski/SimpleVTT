"""/api/campaign/{cid}/use_dash — Dash propagation tests.

v2.100.3: /use_dash became authoritative for the Dash movement-cap
bonus. Besides the feature_used audit it now mutates the hub battle
combatant (action slot used + dash_bonus_ft) and broadcasts an
``economy_update`` carrying ``dash_bonus_ft`` so the bonus survives the
GM's wholesale ``battle_update`` replace on player clients. Pre-v2.100.3
the client ``_dashCombatant`` helper only mutated the dasher's LOCAL
battle dict + called pushBattle (a no-op for non-GM clients), so a
player's Dash bonus vanished on the next battle_update and the Mov chip
cap silently reverted to base speed.

Tests:
  - happy path: dash a seeded combatant → economy_update carries
    slot=action used=True + dash_bonus_ft == grant; feature_used fires;
    response echoes dash_bonus_ft.
  - additive: a second dash stacks the bonus (absolute value grows).
  - not-in-battle (error path): dashing a character absent from init
    still fires the feature_used audit but emits NO economy_update and
    returns dash_bonus_ft=None (no combatant to mutate).
"""
import asyncio

from .conftest import CAMPAIGN_ID


async def _seed_pip(gm_client, pip):
    pre_state = {
        "combatants": [
            {
                "char_id": pip["id"],
                "name": pip["name"],
                "init": 15,
                "speed_walk": 30,
                "economy": {
                    "action": False, "bonus": False,
                    "reaction": False, "movement": 0, "dash_bonus_ft": 0,
                },
            }
        ],
        "round": 1,
        "active_index": 0,
    }
    resp = await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle", json=pre_state,
    )
    assert resp.status_code == 200, resp.text


async def _clear_battle(gm_client):
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": [], "round": 0, "active_index": 0},
    )


async def test_use_dash_propagates_dash_bonus(gm_client, gm_ws, roster):
    """Dash a seeded combatant → economy_update reconciles the cap
    bonus surgically + the action chip flips used; feature_used audit
    still fires; response echoes the absolute dash_bonus_ft.
    """
    pip = roster["Pip Quickfingers"]
    await _seed_pip(gm_client, pip)
    gm_ws.mark()  # discard the battle_update from the seed PUT
    try:
        resp = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/use_dash",
            json={"character_id": pip["id"], "grant_ft": 30},
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["ok"] is True
        assert data["grant_ft"] == 30
        assert data["dash_bonus_ft"] == 30

        fu = await gm_ws.wait_for("feature_used")
        assert fu["data"]["source"] == "dash-action"

        eu = await gm_ws.wait_for("economy_update")
        assert eu["data"]["character_id"] == pip["id"]
        assert eu["data"]["slot"] == "action"
        assert eu["data"]["used"] is True
        assert eu["data"]["dash_bonus_ft"] == 30
    finally:
        await _clear_battle(gm_client)


async def test_use_dash_stacks_additively(gm_client, roster):
    """A second Dash on the same combatant stacks the cap bonus (the
    broadcast value is absolute: 30 → 60), so repeated Dash / Step of
    the Wind reads correctly rather than overwriting.
    """
    pip = roster["Pip Quickfingers"]
    await _seed_pip(gm_client, pip)
    try:
        first = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/use_dash",
            json={"character_id": pip["id"], "grant_ft": 30},
        )
        assert first.status_code == 200, first.text
        assert first.json()["dash_bonus_ft"] == 30

        second = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/use_dash",
            json={"character_id": pip["id"], "grant_ft": 30},
        )
        assert second.status_code == 200, second.text
        assert second.json()["dash_bonus_ft"] == 60
    finally:
        await _clear_battle(gm_client)


async def test_use_dash_not_in_battle_no_economy_update(gm_client, gm_ws, roster):
    """Error path: dashing a character who isn't in the init order
    still broadcasts the feature_used audit but mutates no hub state —
    no economy_update, and the response reports dash_bonus_ft=None.
    """
    pip = roster["Pip Quickfingers"]
    await _clear_battle(gm_client)  # ensure no combatants
    gm_ws.mark()
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_dash",
        json={"character_id": pip["id"], "grant_ft": 30},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["dash_bonus_ft"] is None

    fu = await gm_ws.wait_for("feature_used")
    assert fu["data"]["source"] == "dash-action"

    # Give any (erroneous) economy_update a moment to arrive, then
    # assert none did.
    await asyncio.sleep(0.3)
    assert gm_ws.buffered("economy_update") == [], (
        "no combatant in init → /use_dash must not broadcast economy_update"
    )
