"""v2.99.280 — Vengeance Paladin: Relentless Avenger (H.2 depth).

H.2 depth ship — Vengeance's Lv 7 OA-rider feature. RAW PHB
p.88: when you hit a creature with an opportunity attack, you
can move up to half your speed immediately after the attack
and as part of the same reaction; this movement doesn't
provoke opportunity attacks.

v1 announce-only. The actual half-speed-without-provoke move
application is GM-tracked.

Caelan Lv 7 (speed 30 ft) → bonus_move_ft 15.
Tests PATCH his subclass to "Oath of Vengeance".

Tests:
  - Lv 7 happy → bonus_move_ft 15, base_speed 30.
  - Wrong subclass → 409.
  - Level gate (Lv 6) → 409.
"""
import asyncio
import pytest_asyncio

from .conftest import CAMPAIGN_ID


async def _patch_sheet(gm_client, char_id, fields, class_slug=None):
    body = dict(fields)
    if class_slug:
        body["class_slug"] = class_slug
    r = await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-fields",
        json=body,
    )
    assert r.status_code == 200, r.text


def _ra_broadcasts(gm_ws, character_id):
    return [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "relentless-avenger"
        and (m.get("data") or {}).get("character_id") == character_id
    ]


@pytest_asyncio.fixture
async def caelan_vengeance_lv7(gm_client, roster):
    """PATCH Caelan to Vengeance. Default Lv 7 already qualifies."""
    caelan = roster["Sir Caelan Lightbringer"]
    await _patch_sheet(
        gm_client, caelan["id"],
        {"subclass": "Oath of Vengeance"},
        class_slug="paladin",
    )
    try:
        yield caelan
    finally:
        await _patch_sheet(
            gm_client, caelan["id"],
            {"subclass": "Oath of Devotion", "level": 7},
            class_slug="paladin",
        )


async def test_use_ra_happy_lv7(
    gm_client, gm_ws, caelan_vengeance_lv7,
):
    """Lv 7 Vengeance, speed 30 → bonus_move_ft 15."""
    caelan = caelan_vengeance_lv7
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_relentless_avenger",
        json={"character_id": caelan["id"]},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["bonus_move_ft"] == 15
    assert data["base_speed"] == 30
    assert data["paladin_level"] == 7
    await asyncio.sleep(0.3)
    feats = _ra_broadcasts(gm_ws, caelan["id"])
    assert feats


async def test_use_ra_wrong_subclass(
    gm_client, roster,
):
    """Default Caelan (Devotion) → 409."""
    caelan = roster["Sir Caelan Lightbringer"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_relentless_avenger",
        json={"character_id": caelan["id"]},
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "wrong_subclass_or_level"


async def test_use_ra_level_gate(
    gm_client, roster,
):
    """Vengeance Caelan at Lv 6 → 409."""
    caelan = roster["Sir Caelan Lightbringer"]
    await _patch_sheet(
        gm_client, caelan["id"],
        {"subclass": "Oath of Vengeance", "level": 6},
        class_slug="paladin",
    )
    try:
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/use_relentless_avenger",
            json={"character_id": caelan["id"]},
        )
        assert r.status_code == 409, r.text
        data = r.json()
        assert data.get("error") == "wrong_subclass_or_level"
    finally:
        await _patch_sheet(
            gm_client, caelan["id"],
            {"subclass": "Oath of Devotion", "level": 7},
            class_slug="paladin",
        )


def _pc(cid, c):
    return {"id": cid, "char_id": c["id"], "name": c["name"],
            "initiative": 10, "hp_current": 60, "hp_max": 60, "buffs": [],
            "economy": {"action": False, "bonus": False,
                        "reaction": False, "movement": 0}}


async def test_ra_installs_free_move_buff_on_caelan(
    gm_client, gm_ws, caelan_vengeance_lv7,
):
    """v2.149.0 — Phase 1 mechanical wiring: when Caelan
    (Vengeance Lv 7+) calls /use_relentless_avenger in an active
    battle, install a 1-round `relentless-avenger-bonus-move` buff
    on Caelan carrying both `effects.free_movement_remaining_ft: 15`
    (half of 30 ft base walking speed) AND
    `effects.oa_immune_during_move: True`. Verify the `buff_update`
    broadcast shows the buff with the right effects."""
    caelan = caelan_vengeance_lv7
    cael_tok = f"tok_ra_c_{caelan['id']}"
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": [_pc(cael_tok, caelan)],
              "turn_index": 0, "round": 1, "active": True},
    )
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_relentless_avenger",
        json={"character_id": caelan["id"]},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["bonus_move_ft"] == 15      # 30 / 2
    assert data.get("buff_installed") is True
    bu = await gm_ws.wait_for("buff_update")
    buffs = bu["data"]["buffs"]
    ra_buff = next(
        (b for b in buffs if b.get("key") == "relentless-avenger-bonus-move"),
        None,
    )
    assert ra_buff is not None, (
        f"RA buff missing from buff_update; got keys="
        f"{[b.get('key') for b in buffs]}"
    )
    effects = ra_buff.get("effects") or {}
    assert int(effects.get("free_movement_remaining_ft") or 0) == 15
    assert effects.get("oa_immune_during_move") is True
