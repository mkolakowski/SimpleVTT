"""v2.99.141 — /use_ascendant_step endpoint tests.

Ascendant Step is a Warlock Lv 9+ Eldritch Invocation: cast
Levitate on yourself at will (PHB p.110). v1 ships the audit
broadcast + invocation gate only — vertical-position map
plumbing is filed (SimpleVTT has no 2D-with-altitude layer
today).

Mirror of the v2.99.138 Eldritch Sight / v2.99.131 Devil's Sight
pattern.

Tests:
  - happy path (Magnus has the invocation) → 200 + WS feature_used
    broadcast with `source: ascendant-step` + `altitude_ft: 20` +
    `duration_rounds: 100` (10 min concentration)
  - missing invocation (Krieger Barbarian) → 409 missing_invocation
  - missing character_id → 400
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID


async def test_use_ascendant_step_happy_path(gm_client, gm_ws, roster):
    """Magnus has eldritch-invocation-ascendant-step on his feats
    list. Endpoint returns 200 + emits the audit broadcast.
    """
    magnus = roster["Magnus Hexbinder"]
    gm_ws.mark()
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_ascendant_step",
        json={"character_id": magnus["id"]},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["ok"] is True
    assert data["altitude_ft"] == 20
    assert data["duration_rounds"] == 100
    assert data["character_id"] == magnus["id"]
    msg = await gm_ws.wait_for("feature_used")
    bd = msg["data"]
    assert bd.get("source") == "ascendant-step"
    assert bd.get("character_id") == magnus["id"]
    assert bd.get("altitude_ft") == 20


async def test_use_ascendant_step_without_invocation_409(gm_client, roster):
    """Krieger (Barbarian) → 409 missing_invocation."""
    krieger = roster["Krieger Stonefist"]
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_ascendant_step",
        json={"character_id": krieger["id"]},
    )
    assert resp.status_code == 409, resp.text
    data = resp.json()
    assert data.get("error") == "missing_invocation"
    assert data.get("invocation") == "ascendant-step"


async def test_use_ascendant_step_missing_character_id_400(gm_client):
    """Missing character_id → 400."""
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_ascendant_step",
        json={},
    )
    assert resp.status_code == 400, resp.text


def _pc(cid, c):
    return {"id": cid, "char_id": c["id"], "name": c["name"],
            "initiative": 10, "hp_current": 30, "hp_max": 30, "buffs": [],
            "economy": {"action": False, "bonus": False,
                        "reaction": False, "movement": 0}}


async def test_use_ascendant_step_installs_levitate_buff(
    gm_client, gm_ws, roster,
):
    """v2.147.0 — Phase 1: in an active battle, /use_ascendant_step
    installs an `ascendant-step-levitate` buff on Magnus carrying
    `effects.fly_speed_ft: 10` (vertical-only per RAW) +
    `concentration: True`. End-to-end: seed Magnus in a battle, call
    the endpoint, verify the response carries `buff_installed: True`
    and the `buff_update` broadcast shows the levitate buff with the
    right effects."""
    magnus = roster["Magnus Hexbinder"]
    mag_tok = f"tok_as_m_{magnus['id']}"
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": [_pc(mag_tok, magnus)],
              "turn_index": 0, "round": 1, "active": True},
    )
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_ascendant_step",
        json={"character_id": magnus["id"]},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data.get("buff_installed") is True
    assert data["fly_speed_ft"] == 10
    bu = await gm_ws.wait_for("buff_update")
    buffs = bu["data"]["buffs"]
    lev_buff = next(
        (b for b in buffs if b.get("key") == "ascendant-step-levitate"),
        None,
    )
    assert lev_buff is not None, (
        f"levitate buff missing from buff_update; got keys="
        f"{[b.get('key') for b in buffs]}"
    )
    effects = lev_buff.get("effects") or {}
    assert effects.get("fly_speed_ft") == 10
    assert lev_buff.get("concentration") is True
