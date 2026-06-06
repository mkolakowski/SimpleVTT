"""v2.99.432 — Phase 6.2: server-side forced movement (`/force_move`).

docs/plans/movement-and-summons.md P6.2 — `_force_move` mutates a target
combatant's Token `x/y` along the line from a source combatant (pushed
away, or pulled toward) and broadcasts `token_move` with `forced: True`.
Bypasses the speed cap + OA (forced move is involuntary).

The test positions two PC tokens on the demo's gridded map, pushes one
15 ft directly away from the other, and asserts the moved token's new
position (3 cells = 210 px on the 70-px grid) + the reported distance.
"""
import pytest

from .conftest import CAMPAIGN_ID


async def _tokens_by_char(client):
    resp = await client.get(f"/api/campaign/{CAMPAIGN_ID}/tokens")
    assert resp.status_code == 200, resp.text
    return {t["character_id"]: t for t in resp.json()["tokens"]
            if t.get("character_id")}


def _cb(cid, char_id, name):
    return {
        "id": cid, "char_id": char_id, "name": name,
        "initiative": 10, "hp_current": 30, "hp_max": 30, "buffs": [],
        "economy": {"action": False, "bonus": False,
                    "reaction": False, "movement": 0},
    }


async def _move_token(gm_client, token_id, x, y):
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/token/{token_id}/move",
        json={"x": x, "y": y},
    )
    assert r.status_code == 200, r.text


async def test_force_move_pushes_target_away(gm_client, gm_ws, roster):
    """Push Pip 15 ft directly away from Tavik → Pip's token moves +210
    px on the axis from Tavik to Pip (3 cells / 15 ft)."""
    pip = roster["Pip Quickfingers"]
    tavik = roster["Brother Tavik Stonebrow"]
    tokens = await _tokens_by_char(gm_client)
    pip_tok, tavik_tok = tokens[pip["id"]], tokens[tavik["id"]]
    pip_cb, tavik_cb = "tok_fm_pip", "tok_fm_tavik"

    # Inactive battle so the move-endpoint speed cap doesn't gate the
    # setup positioning; force_move bypasses the cap regardless.
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": [
            _cb(pip_cb, pip["id"], pip["name"]),
            _cb(tavik_cb, tavik["id"], tavik["name"]),
        ], "turn_index": 0, "round": 1, "active": False},
    )
    # Tavik above Pip (same x) → push direction is straight down (+y).
    await _move_token(gm_client, tavik_tok["id"], 700.0, 560.0)
    await _move_token(gm_client, pip_tok["id"], 700.0, 700.0)

    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/force_move",
        json={"target_combatant_id": pip_cb,
              "source_combatant_id": tavik_cb, "distance_ft": 15},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["moved"] is True
    assert data["distance_ft"] == 15.0
    assert data["to_x"] == pytest.approx(700.0)
    assert data["to_y"] == pytest.approx(910.0)  # 700 + 15ft (210 px)

    # The token row actually moved.
    tokens2 = await _tokens_by_char(gm_client)
    assert tokens2[pip["id"]]["y"] == pytest.approx(910.0)

    # A forced token_move was broadcast.
    tm = await gm_ws.wait_for("token_move")
    assert tm["data"]["forced"] is True
    assert tm["data"]["id"] == pip_tok["id"]


async def test_force_move_missing_target_400(gm_client):
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/force_move", json={"distance_ft": 15})
    assert r.status_code == 400, r.text


async def test_force_move_zero_distance_400(gm_client):
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/force_move",
        json={"target_combatant_id": "x", "distance_ft": 0})
    assert r.status_code == 400, r.text


async def test_force_move_unknown_target_404(gm_client):
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/force_move",
        json={"target_combatant_id": "nope_not_in_battle", "distance_ft": 15})
    assert r.status_code == 404, r.text
