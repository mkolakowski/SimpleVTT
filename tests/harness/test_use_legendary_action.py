"""v2.159.34 — /api/campaign/{cid}/use_legendary_action — Phase 1b of
`docs/plans/legendary-actions.md`. Budget gate + spend endpoint for
legendary actions.

RAW DMG p.11:
- A legendary creature has 3 legendary-action points per round (default).
- Points refresh at the START of the legendary creature's own turn.
- Points are spent at the END of ANOTHER creature's turn — never on the
  legendary creature's own turn.
- Each action has a cost (1, 2, or 3 points); Phase 1a backfilled the
  cost integer on every "(Costs N Actions)" SRD action.

Coverage:
  - happy path: cost-1 spend drops pool 3 → 2 + broadcasts both
    `legendary_action_pool_update(reason=spent)` and
    `feature_used(source=legendary-action)`.
  - cost-2 spend drops pool 3 → 1 (multi-cost path).
  - 409 `cannot_use_on_own_turn` when the legendary creature is the
    active combatant.
  - 409 `insufficient_legendary_action_points` when pool < cost.
  - turn-start refresh: spend pool down to 1, advance through to the
    dragon's turn, pool resets to 3 + `legendary_action_pool_update`
    broadcast with `reason=turn_start_refresh`.
  - 400 missing combatant_id.
  - 403 non-GM caller.
"""
from .conftest import CAMPAIGN_ID


def _mkc(cid, char_id=None, hp_cur=30, hp_max=30, name="X", initiative=10):
    return {
        "id": cid,
        "char_id": char_id,
        "name": name,
        "initiative": initiative,
        "hp_current": hp_cur,
        "hp_max": hp_max,
        "buffs": [],
        "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0},
    }


async def _seed_battle(gm_client, combatants, turn_index=0):
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={
            "combatants": combatants,
            "turn_index": turn_index,
            "round": 1,
            "active": True,
        },
    )


async def test_use_legendary_action_cost_1_spends_one_point(gm_client, gm_ws, roster):
    """Tail Attack (cost 1): pool 3 → 2 + broadcasts."""
    pip = roster["Pip Quickfingers"]
    pip_cid = f"tok_{pip['id']}"
    dragon_cid = "npc_dragon_test_cost1"
    # Seed with Pip active (turn_index=1) so the dragon CAN spend.
    await _seed_battle(gm_client, [
        _mkc(dragon_cid, hp_cur=546, hp_max=546, name="Ancient Red Dragon", initiative=20),
        _mkc(pip_cid, pip["id"], hp_cur=30, hp_max=30, name=pip["name"], initiative=15),
    ], turn_index=1)

    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_legendary_action",
        json={
            "combatant_id": dragon_cid,
            "action_id": "tail-attack",
            "action_name": "Tail Attack",
            "cost": 1,
            "target_combatant_id": pip_cid,
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["ok"] is True
    assert data["combatant_id"] == dragon_cid
    assert data["action_name"] == "Tail Attack"
    assert data["cost"] == 1
    assert data["pool_max"] == 3
    assert data["pool_current"] == 2  # 3 → 2

    pool_msg = await gm_ws.wait_for("legendary_action_pool_update")
    assert pool_msg["data"]["combatant_id"] == dragon_cid
    assert pool_msg["data"]["current"] == 2
    assert pool_msg["data"]["max"] == 3
    assert pool_msg["data"]["reason"] == "spent"
    assert pool_msg["data"]["cost"] == 1

    feat_msg = await gm_ws.wait_for("feature_used")
    assert feat_msg["data"]["source"] == "legendary-action"
    assert feat_msg["data"]["action_name"] == "Tail Attack"
    assert feat_msg["data"]["combatant_name"] == "Ancient Red Dragon"


async def test_use_legendary_action_cost_2_spends_two_points(gm_client, gm_ws, roster):
    """Wing Attack (cost 2): pool 3 → 1."""
    pip = roster["Pip Quickfingers"]
    pip_cid = f"tok_{pip['id']}"
    dragon_cid = "npc_dragon_test_cost2"
    await _seed_battle(gm_client, [
        _mkc(dragon_cid, hp_cur=546, hp_max=546, name="Ancient Red Dragon", initiative=20),
        _mkc(pip_cid, pip["id"], hp_cur=30, hp_max=30, name=pip["name"], initiative=15),
    ], turn_index=1)

    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_legendary_action",
        json={
            "combatant_id": dragon_cid,
            "action_id": "wing-attack-costs-2-actions",
            "action_name": "Wing Attack (Costs 2 Actions)",
            "cost": 2,
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["cost"] == 2
    assert data["pool_current"] == 1  # 3 → 1


async def test_use_legendary_action_blocked_on_own_turn(gm_client, roster):
    """Dragon is the active combatant → 409 cannot_use_on_own_turn."""
    pip = roster["Pip Quickfingers"]
    pip_cid = f"tok_{pip['id']}"
    dragon_cid = "npc_dragon_test_own_turn"
    # turn_index=0 = dragon's own turn.
    await _seed_battle(gm_client, [
        _mkc(dragon_cid, hp_cur=546, hp_max=546, name="Ancient Red Dragon", initiative=20),
        _mkc(pip_cid, pip["id"], hp_cur=30, hp_max=30, name=pip["name"], initiative=15),
    ], turn_index=0)

    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_legendary_action",
        json={
            "combatant_id": dragon_cid,
            "action_id": "tail-attack",
            "action_name": "Tail Attack",
            "cost": 1,
        },
    )
    assert resp.status_code == 409
    assert resp.json()["error"] == "cannot_use_on_own_turn"


async def test_use_legendary_action_blocked_when_pool_empty(gm_client, roster):
    """Spend pool down to 0, then attempt cost 1 → 409 insufficient."""
    pip = roster["Pip Quickfingers"]
    pip_cid = f"tok_{pip['id']}"
    dragon_cid = "npc_dragon_test_empty"
    await _seed_battle(gm_client, [
        _mkc(dragon_cid, hp_cur=546, hp_max=546, name="Ancient Red Dragon", initiative=20),
        _mkc(pip_cid, pip["id"], hp_cur=30, hp_max=30, name=pip["name"], initiative=15),
    ], turn_index=1)

    # Spend the full 3-point pool: 3 × cost 1.
    for _ in range(3):
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/use_legendary_action",
            json={
                "combatant_id": dragon_cid,
                "action_id": "tail-attack",
                "action_name": "Tail Attack",
                "cost": 1,
            },
        )
        assert r.status_code == 200, r.text

    # Pool now 0; next attempt 409s.
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_legendary_action",
        json={
            "combatant_id": dragon_cid,
            "action_id": "tail-attack",
            "action_name": "Tail Attack",
            "cost": 1,
        },
    )
    assert resp.status_code == 409
    body = resp.json()
    assert body["error"] == "insufficient_legendary_action_points"
    assert body["current"] == 0
    assert body["cost"] == 1


async def test_turn_start_refreshes_legendary_action_pool(gm_client, gm_ws, roster):
    """Spend dragon pool to 1, then advance turn back to the dragon
    (turn_index 1 → 0) → pool should refresh to 3 + the
    legendary_action_pool_update broadcast carries reason=turn_start_refresh."""
    pip = roster["Pip Quickfingers"]
    pip_cid = f"tok_{pip['id']}"
    dragon_cid = "npc_dragon_test_refresh"
    await _seed_battle(gm_client, [
        _mkc(dragon_cid, hp_cur=546, hp_max=546, name="Ancient Red Dragon", initiative=20),
        _mkc(pip_cid, pip["id"], hp_cur=30, hp_max=30, name=pip["name"], initiative=15),
    ], turn_index=1)  # Pip's turn — dragon CAN spend.

    # Spend twice: 3 → 2 → 1.
    for _ in range(2):
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/use_legendary_action",
            json={
                "combatant_id": dragon_cid,
                "action_id": "tail-attack",
                "action_name": "Tail Attack",
                "cost": 1,
            },
        )
        assert r.status_code == 200

    # Advance turn — dragon (idx 0) becomes active again. Fetch current
    # battle state to preserve the spent pool through the PUT. mark()
    # first so the only legendary_action_pool_update visible to
    # wait_for is the refresh (not the two prior "spent" broadcasts).
    bs = (await gm_client.get(f"/api/campaign/{CAMPAIGN_ID}/battle")).json()["battle"]
    bs["turn_index"] = 0
    gm_ws.mark()
    await gm_client.put(f"/api/campaign/{CAMPAIGN_ID}/battle", json=bs)

    refresh_msg = await gm_ws.wait_for("legendary_action_pool_update")
    assert refresh_msg["data"]["reason"] == "turn_start_refresh"
    assert refresh_msg["data"]["combatant_id"] == dragon_cid
    assert refresh_msg["data"]["current"] == 3
    assert refresh_msg["data"]["max"] == 3


async def test_use_legendary_action_missing_combatant_id_400(gm_client):
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_legendary_action",
        json={"action_name": "Tail Attack", "cost": 1},
    )
    assert resp.status_code == 400


async def test_use_legendary_action_player_caller_403(alice_client, roster):
    """Non-GM players cannot fire NPC legendary actions."""
    pip = roster["Pip Quickfingers"]
    pip_cid = f"tok_{pip['id']}"
    dragon_cid = "npc_dragon_test_player"
    resp = await alice_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_legendary_action",
        json={
            "combatant_id": dragon_cid,
            "action_id": "tail-attack",
            "action_name": "Tail Attack",
            "cost": 1,
        },
    )
    assert resp.status_code == 403
