"""v2.662.0 — Eldritch Knight Arcane Charge teleport (Phase 4 of
docs/plans/eldritch-knight.md).

Phase 1 (v2.158.11) installed the `arcane-charge-active` buff; Phase 2
(v2.158.39) surfaced the 30-ft budget on `/use_action_surge`. This is the
ACTUAL movement: `POST /use_arcane_charge_teleport` moves the EK's token to a
chosen destination, bypassing the walk-speed cap that `/token/{id}/move`
enforces, while gating on the buff's 30-ft budget (RAW PHB p.74). The
"unoccupied space you can see" clause stays GM-narrated.

Garrik (Lv 9 Fighter) is the demo fixture; the fixture PATCHes him to
Eldritch Knight Lv 15, seeds a battle (so `_install_buff` lands), installs the
arcane-charge buff, and is restore-safe (snapshots subclass + level). The demo
active map is a 70 px / 5 ft grid (PX_PER_CELL below).

Tests:
  - in-range teleport → 200 + token_move(teleport=True) + the token moves.
  - too-far teleport → 409 too_far (with max_ft / attempted_ft).
  - no Arcane Charge buff (a Rogue) → 409 no_arcane_charge.
  - missing dest coords → 400.
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID

PX_PER_CELL = 70  # demo active map: 70 px/cell, 5 ft/cell → 30 ft = 420 px


async def _patch(gm_client, char_id, fields):
    r = await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-fields",
        json={**fields, "class_slug": "fighter"},
    )
    assert r.status_code == 200, r.text


async def _garrik_token(gm_client, char_id):
    r = await gm_client.get(f"/api/campaign/{CAMPAIGN_ID}/tokens")
    for t in r.json().get("tokens") or []:
        if t.get("character_id") == char_id:
            return t
    return None


async def _place_and_read(gm_client, char_id, x, y):
    """Place the PC's token at (x, y) and return its actual stored coords
    (place-token may grid-snap; read back so the test math is exact)."""
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/place-token",
        json={"x": float(x), "y": float(y)},
    )
    tok = await _garrik_token(gm_client, char_id)
    assert tok is not None, "token not placed"
    return float(tok["x"]), float(tok["y"])


@pytest_asyncio.fixture
async def garrik_arcane_charge(gm_client, roster):
    """PATCH Garrik to Eldritch Knight Lv 15, seed a battle, install the
    arcane-charge buff. Restore-safe (subclass + level)."""
    garrik = roster["Garrik Ironside"]
    sj = (await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{garrik['id']}/sheet-json"
    )).json().get("sheet") or {}
    orig_sub = sj.get("subclass") or "Champion"
    orig_lv = sj.get("level") or 9
    await _patch(gm_client, garrik["id"],
                 {"subclass": "Eldritch Knight", "level": 15})
    # Seed a solo battle so _install_buff (which needs the PC in init) lands.
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": [{
            "id": f"tok_ac_{garrik['id']}", "char_id": garrik["id"],
            "name": garrik["name"], "initiative": 12,
            "hp_current": 80, "hp_max": 80, "buffs": [],
            "economy": {"action": False, "bonus": False,
                        "reaction": False, "movement": 0},
        }], "turn_index": 0, "round": 1, "active": True},
    )
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_arcane_charge",
        json={"character_id": garrik["id"]},
    )
    assert r.status_code == 200, r.text
    assert r.json()["buff_installed"] is True
    try:
        yield garrik
    finally:
        await _patch(gm_client, garrik["id"],
                     {"subclass": orig_sub, "level": orig_lv})


async def test_arcane_charge_teleport_in_range(
    gm_client, gm_ws, garrik_arcane_charge,
):
    """Happy path: a ≤30-ft teleport moves the token + broadcasts
    token_move(teleport=True)."""
    garrik = garrik_arcane_charge
    sx, sy = await _place_and_read(gm_client, garrik["id"], 140.0, 140.0)
    # 4 cells right = 20 ft (≤ 30 ft budget).
    dest_x, dest_y = sx + 4 * PX_PER_CELL, sy
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_arcane_charge_teleport",
        json={"character_id": garrik["id"],
              "dest_x": dest_x, "dest_y": dest_y},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["ok"] is True
    assert data["max_ft"] == 30
    assert data["distance_ft"] == 20.0
    assert data["to_x"] == dest_x and data["to_y"] == dest_y

    tm = await gm_ws.wait_for("token_move")
    assert tm["data"].get("teleport") is True
    assert tm["data"]["character_id"] == garrik["id"]
    assert tm["data"]["x"] == dest_x and tm["data"]["y"] == dest_y

    # The token actually moved on the map.
    tok = await _garrik_token(gm_client, garrik["id"])
    assert float(tok["x"]) == dest_x and float(tok["y"]) == dest_y


async def test_arcane_charge_teleport_too_far_409(
    gm_client, garrik_arcane_charge,
):
    """A teleport past the 30-ft budget → 409 too_far."""
    garrik = garrik_arcane_charge
    sx, sy = await _place_and_read(gm_client, garrik["id"], 140.0, 140.0)
    # 8 cells = 40 ft > 30 ft.
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_arcane_charge_teleport",
        json={"character_id": garrik["id"],
              "dest_x": sx + 8 * PX_PER_CELL, "dest_y": sy},
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data["error"] == "too_far"
    assert data["max_ft"] == 30
    assert data["attempted_ft"] == 40.0

    # override bypasses the range gate.
    r2 = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_arcane_charge_teleport",
        json={"character_id": garrik["id"],
              "dest_x": sx + 8 * PX_PER_CELL, "dest_y": sy,
              "override": True},
    )
    assert r2.status_code == 200, r2.text
    assert r2.json()["distance_ft"] == 40.0


async def test_arcane_charge_teleport_no_buff_409(gm_client, roster):
    """A PC without the arcane-charge buff (a Rogue) → 409 no_arcane_charge."""
    pip = roster["Pip Quickfingers"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_arcane_charge_teleport",
        json={"character_id": pip["id"], "dest_x": 100.0, "dest_y": 100.0},
    )
    assert r.status_code == 409, r.text
    assert r.json()["error"] == "no_arcane_charge"


async def test_arcane_charge_teleport_missing_dest_400(
    gm_client, garrik_arcane_charge,
):
    """Missing dest coords → 400."""
    garrik = garrik_arcane_charge
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_arcane_charge_teleport",
        json={"character_id": garrik["id"]},
    )
    assert r.status_code == 400, r.text
