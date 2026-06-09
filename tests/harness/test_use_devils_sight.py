"""v2.99.131 → v2.158.14 — /use_devils_sight endpoint tests.

Devil's Sight is a Warlock Lv 2+ Eldritch Invocation: 120 ft sight
in magical+nonmagical darkness (PHB p.110). v2.158.14 (Phase 8
Warlock diversification — first Warlock invocation flipped from
announce-only to tracked) wires the endpoint to install a
permanent `devils-sight-active` buff carrying the two vision
parameters (`devils_sight_range_ft: 120` +
`devils_sight_through_magical_darkness: True`).

Phase 2 (deferred): a `_pc_sees_in_darkness(sheet)` helper +
darkness-modifier resolver short-circuit the "attacker/target in
darkness" disadvantage adjudication at attack-roll time + skip
the install of a `blinded` condition from a darkness-trigger
source when the warlock is within 120 ft through magical
darkness.

Tests:
  - happy path (Magnus has the invocation) → 200 + WS feature_used
    broadcast with `source: devils-sight` + `range_ft: 120` +
    `buff_installed == True`
  - missing invocation (Krieger Barbarian → no invocation) → 409
    missing_invocation
  - missing character_id → 400
  - state contract: installed buff carries the two
    `devils_sight_*` effect keys with the right values
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID


def _pc(cid, c, *, hp_max=40):
    return {"id": cid, "char_id": c["id"], "name": c["name"],
            "initiative": 10, "hp_current": hp_max, "hp_max": hp_max,
            "buffs": [],
            "economy": {"action": False, "bonus": False,
                        "reaction": False, "movement": 0}}


async def _seed_magnus_in_battle(gm_client, magnus):
    """v2.158.14 — `_install_buff` requires an active battle.
    Seed a minimal one with Magnus."""
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={
            "combatants": [_pc(f"tok_ds_magnus_{magnus['id']}", magnus)],
            "turn_index": 0, "round": 1, "active": True,
        },
    )


async def test_use_devils_sight_happy_path(gm_client, gm_ws, roster):
    """Magnus has eldritch-invocation-devils-sight on his feats list.
    Endpoint returns 200 + broadcasts feature_used with the right
    source + range_ft + buff_installed True.
    """
    magnus = roster["Magnus Hexbinder"]
    await _seed_magnus_in_battle(gm_client, magnus)
    gm_ws.mark()
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_devils_sight",
        json={"character_id": magnus["id"]},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["ok"] is True
    assert data["range_ft"] == 120
    assert data["character_id"] == magnus["id"]
    assert data["buff_installed"] is True
    # WS broadcast.
    msg = await gm_ws.wait_for("feature_used")
    bd = msg["data"]
    assert bd.get("source") == "devils-sight"
    assert bd.get("character_id") == magnus["id"]
    assert bd.get("range_ft") == 120


async def test_use_devils_sight_without_invocation_409(gm_client, roster):
    """Krieger (Barbarian) has no Warlock invocations → 409
    missing_invocation.
    """
    krieger = roster["Krieger Stonefist"]
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_devils_sight",
        json={"character_id": krieger["id"]},
    )
    assert resp.status_code == 409, resp.text
    data = resp.json()
    assert data.get("error") == "missing_invocation"
    assert data.get("invocation") == "devils-sight"


async def test_use_devils_sight_missing_character_id_400(gm_client):
    """Missing character_id → 400."""
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_devils_sight",
        json={},
    )
    assert resp.status_code == 400, resp.text


async def test_ds_buff_payload_carries_vision_flags(
    gm_client, gm_ws, roster,
):
    """v2.158.14 — state contract (Phase 9): the installed
    `devils-sight-active` buff carries the two `devils_sight_*`
    effect keys with the right values (`range_ft: 120` +
    `through_magical_darkness: True`). Phase 2 (deferred) will
    have a `_pc_sees_in_darkness(sheet)` helper + darkness
    resolver read these off the caster's `_buffs_active`; this
    test pins the flag shape so that future read site has a
    stable contract."""
    magnus = roster["Magnus Hexbinder"]
    await _seed_magnus_in_battle(gm_client, magnus)
    gm_ws.mark()
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_devils_sight",
        json={"character_id": magnus["id"]},
    )
    assert resp.status_code == 200, resp.text
    bu = await gm_ws.wait_for("buff_update")
    magnus_buffs = bu["data"]["buffs"]
    ds_buff = next(
        (b for b in magnus_buffs if b.get("key") == "devils-sight-active"),
        None,
    )
    assert ds_buff is not None, (
        f"devils-sight-active buff missing; got keys="
        f"{[b.get('key') for b in magnus_buffs]}"
    )
    effects = ds_buff.get("effects") or {}
    assert effects.get("devils_sight_range_ft") == 120
    assert effects.get("devils_sight_through_magical_darkness") is True
    # Permanent passive — no concentration, very long duration.
    assert ds_buff.get("concentration") in (False, None)
    assert int(ds_buff.get("duration_rounds") or 0) >= 1000
