"""v2.99.99 — /token/move server-side over-speed gate tests.

Pre-v2.99.99 /token/move accepted any distance — the speed cap was
a client-side advisory only (Mov chip color, Dash modal). v2.99.99
adds a 409 gate so a scripted client can't bypass the Dash modal.

Gate applies ONLY when:
  - a battle is active in the hub
  - the mover is the active combatant
  - distance + economy.movement > effective_cap + 0.01
  - body does NOT pass `over_speed_confirmed: true`

Tests cover:
  - within cap → 200 (control)
  - over cap without flag → 409 over_speed_cap
  - over cap WITH `over_speed_confirmed: true` → 200
  - off-turn dragger (not active combatant) → no gate, 200
  - Lance of Lethargy buff reduces the effective cap → 409 at lower
    threshold than the unreduced base would allow
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID


async def _tokens_by_char(client) -> dict[int, dict]:
    resp = await client.get(f"/api/campaign/{CAMPAIGN_ID}/tokens")
    assert resp.status_code == 200, resp.text
    data = resp.json()
    by_char = {}
    for t in data["tokens"]:
        if t.get("character_id"):
            by_char[t["character_id"]] = t
    return by_char


def _mkc(cid, char_id=None, name="X", source_token_id=None,
         speed_walk=30, movement=0, buffs=None):
    return {
        "id": cid,
        "char_id": char_id,
        "name": name,
        "source_token_id": source_token_id,
        "initiative": 10,
        "hp_current": 50, "hp_max": 50,
        "speed_walk": speed_walk,
        "buffs": buffs or [],
        "economy": {
            "action": False, "bonus": False, "reaction": False,
            "movement": movement, "dash_bonus_ft": 0,
        },
    }


async def _seed_battle(gm_client, combatants, turn_index=0):
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": combatants, "turn_index": turn_index,
              "round": 1, "active": True},
    )


async def _move(gm_client, token_id, x, y, over_speed_confirmed=False):
    body = {"x": x, "y": y}
    if over_speed_confirmed:
        body["over_speed_confirmed"] = True
    return await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/token/{token_id}/move",
        json=body,
    )


@pytest_asyncio.fixture
async def pip_active(gm_client, roster):
    """Set up Garrik as the active combatant with a known starting
    position. Restore stale state on teardown.
    """
    pip = roster["Pip Quickfingers"]
    tokens = await _tokens_by_char(gm_client)
    assert pip["id"] in tokens, "no Pip token"
    tok = tokens[pip["id"]]
    # Park Garrik at a known position (350, 350).
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/token/{tok['id']}/move",
        json={"x": 350.0, "y": 350.0, "over_speed_confirmed": True,
              "oa_confirmed": True},
    )
    yield pip, tok
    # Teardown clears the battle so other tests see a fresh slate.
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": [], "turn_index": 0,
              "round": 1, "active": False},
    )


async def test_move_within_cap_returns_200(gm_client, pip_active):
    """Control: a 25 ft move (5 cells) within Garrik's 30 ft cap
    returns 200, no 409.
    """
    pip, tok = pip_active
    pip_combat_tok = f"tok_speed_cap_{pip['id']}"
    await _seed_battle(gm_client, [
        _mkc(pip_combat_tok, pip["id"], name=pip["name"],
             source_token_id=tok["id"], speed_walk=30, movement=0),
    ])
    # Grid is 70 px / cell, 5 ft / cell. 350 + (5 × 70) = 700 → 25 ft.
    resp = await _move(gm_client, tok["id"], 700.0, 350.0)
    assert resp.status_code == 200, resp.text


async def test_move_over_cap_without_flag_returns_409(
    gm_client, pip_active,
):
    """A 35 ft move with no `over_speed_confirmed` flag exceeds
    Garrik's 30 ft cap → 409 over_speed_cap.
    """
    pip, tok = pip_active
    pip_combat_tok = f"tok_speed_cap_{pip['id']}"
    await _seed_battle(gm_client, [
        _mkc(pip_combat_tok, pip["id"], name=pip["name"],
             source_token_id=tok["id"], speed_walk=30, movement=0),
    ])
    # 350 + (7 × 70) = 840 → 35 ft (over 30 ft cap).
    resp = await _move(gm_client, tok["id"], 840.0, 350.0)
    assert resp.status_code == 409, resp.text
    data = resp.json()
    assert data.get("error") == "over_speed_cap", data
    assert data.get("cap_ft") == 30, data
    assert data.get("distance_ft") == 35.0, data


async def test_move_over_cap_with_flag_returns_200(
    gm_client, pip_active,
):
    """Passing `over_speed_confirmed: true` bypasses the gate."""
    pip, tok = pip_active
    pip_combat_tok = f"tok_speed_cap_{pip['id']}"
    await _seed_battle(gm_client, [
        _mkc(pip_combat_tok, pip["id"], name=pip["name"],
             source_token_id=tok["id"], speed_walk=30, movement=0),
    ])
    resp = await _move(gm_client, tok["id"], 840.0, 350.0,
                       over_speed_confirmed=True)
    assert resp.status_code == 200, resp.text


async def test_off_turn_drag_is_not_gated(gm_client, pip_active, roster):
    """When the dragger isn't the active combatant (here Garrik
    moves but the battle's active combatant is Tavik), the over-
    speed gate doesn't apply. GM-side bypass.
    """
    pip, tok = pip_active
    tavik = roster["Brother Tavik Stonebrow"]
    tokens = await _tokens_by_char(gm_client)
    tavik_tok_entry = tokens.get(tavik["id"])
    if not tavik_tok_entry:
        # Tavik has no token in the demo map — skip this test setup
        # via a synthesized in-init Tavik but no real token. The gate
        # only applies when the dragged token IS the active
        # combatant's, so we make Tavik active and drag Garrik.
        pass
    pip_combat_tok = f"tok_speed_cap_off_{pip['id']}"
    tavik_combat_tok = f"tok_speed_cap_off_tav_{tavik['id']}"
    await _seed_battle(gm_client, [
        _mkc(tavik_combat_tok, tavik["id"], name=tavik["name"]),
        _mkc(pip_combat_tok, pip["id"], name=pip["name"],
             source_token_id=tok["id"], speed_walk=30, movement=0),
    ], turn_index=0)  # Tavik active, Garrik off-turn.
    # 35 ft move on Garrik (off-turn for him) → no 409.
    resp = await _move(gm_client, tok["id"], 840.0, 350.0)
    assert resp.status_code == 200, resp.text


async def test_lance_of_lethargy_reduces_effective_cap(
    gm_client, pip_active,
):
    """A combatant with a `lance-of-lethargy` buff carrying
    `effects.speed_reduction_ft: 10` has effective_cap = 20 ft.
    A 25 ft move that would PASS without the buff (≤ 30) now 409s
    against the reduced 20 ft cap.
    """
    pip, tok = pip_active
    pip_combat_tok = f"tok_speed_cap_lol_{pip['id']}"
    await _seed_battle(gm_client, [
        _mkc(pip_combat_tok, pip["id"], name=pip["name"],
             source_token_id=tok["id"], speed_walk=30, movement=0,
             buffs=[{
                 "key": "lance-of-lethargy",
                 "name": "Lance of Lethargy",
                 "effects": {"speed_reduction_ft": 10},
                 "duration_rounds": 1,
             }]),
    ])
    # 25 ft move on a 20 ft effective cap → 409.
    resp = await _move(gm_client, tok["id"], 700.0, 350.0)
    assert resp.status_code == 409, resp.text
    data = resp.json()
    assert data.get("error") == "over_speed_cap", data
    assert data.get("cap_ft") == 20, data
    assert data.get("speed_reduction_ft") == 10, data
