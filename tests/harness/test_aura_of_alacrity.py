"""v2.99.282 — Glory Paladin: Aura of Alacrity (H.2 depth).

H.2 depth ship — Glory's Lv 7 speed aura. RAW XGE p.37: your
walking speed +10 ft permanently. Allies starting their turn
within 5 ft (10 ft at Lv 18+) get +10 ft walking speed until
end of turn.

v1 announce-only. CLOSES the H.2 Lv 7 aura batch (5/5 oaths).

Note: radius is 5 ft (10 ft at Lv 18), distinct from the
10/30 ft pattern of the other H.2 oath auras.

Caelan Lv 7 → radius 5, speed_bonus 10.
Tests PATCH his subclass to "Oath of Glory".

Tests:
  - Lv 7 happy → radius 5, speed_bonus 10.
  - Lv 18 happy → radius 10 (RAW upgrade).
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


def _aoa_broadcasts(gm_ws, character_id):
    return [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "aura-of-alacrity"
        and (m.get("data") or {}).get("character_id") == character_id
    ]


@pytest_asyncio.fixture
async def caelan_glory_lv7(gm_client, roster):
    """PATCH Caelan to Glory. Default Lv 7 already qualifies."""
    caelan = roster["Sir Caelan Lightbringer"]
    await _patch_sheet(
        gm_client, caelan["id"],
        {"subclass": "Oath of Glory", "level": 7},
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


async def test_use_aoa_happy_lv7(
    gm_client, gm_ws, caelan_glory_lv7,
):
    """Lv 7 Glory → radius 5, speed_bonus 10."""
    caelan = caelan_glory_lv7
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_aura_of_alacrity",
        json={"character_id": caelan["id"]},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["radius_ft"] == 5
    assert data["speed_bonus_ft"] == 10
    assert data["paladin_level"] == 7
    # v2.99.449 — aura_installed only lands True with an active battle
    # (see the tick test). No battle here → field present.
    assert "aura_installed" in data
    await asyncio.sleep(0.3)
    feats = _aoa_broadcasts(gm_ws, caelan["id"])
    assert feats


async def _place_token(gm_client, char_id, x, y):
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/place-token",
        json={"x": float(x), "y": float(y)},
    )
    assert r.status_code == 200, r.text


async def test_aoa_installs_aura_and_buffs_ally_speed(
    gm_client, gm_ws, caelan_glory_lv7, roster,
):
    """v2.99.449 — Phase 5 follow-up: Aura of Alacrity installs a
    buff-payload aura. On the paladin's turn start, an ALLY in range gains
    the `alacrity-speed` buff (effects.speed_bonus_ft = 10). Validates the
    new aura buff-payload path end-to-end."""
    caelan = caelan_glory_lv7
    pip = roster["Pip Quickfingers"]
    caelan_tok, pip_tok = f"tok_aoa_caelan_{caelan['id']}", f"tok_aoa_pip_{pip['id']}"

    # Co-locate both PC tokens so the 5-ft range gate passes (dist 0).
    await _place_token(gm_client, caelan["id"], 700.0, 700.0)
    await _place_token(gm_client, pip["id"], 700.0, 700.0)

    def _pc(cid, c):
        return {"id": cid, "char_id": c["id"], "name": c["name"],
                "initiative": 10, "hp_current": 30, "hp_max": 30, "buffs": [],
                "economy": {"action": False, "bonus": False,
                            "reaction": False, "movement": 0}}

    # Seed on Pip's turn so activating doesn't tick for Caelan yet.
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": [
            {**_pc(caelan_tok, caelan), "initiative": 20},
            _pc(pip_tok, pip),
        ], "turn_index": 1, "round": 1, "active": True},
    )

    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_aura_of_alacrity",
        json={"character_id": caelan["id"]},
    )
    assert r.status_code == 200, r.text
    assert r.json()["aura_installed"] is True
    bu = await gm_ws.wait_for("buff_update")
    caelan_buffs = bu["data"]["buffs"]
    assert any(b.get("key") == "aura-of-alacrity" for b in caelan_buffs)

    # Advance to Caelan (index 0) carrying his aura buff → tick buffs Pip.
    gm_ws.mark()
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": [
            {**_pc(caelan_tok, caelan), "initiative": 20, "buffs": caelan_buffs},
            _pc(pip_tok, pip),
        ], "turn_index": 0, "round": 2, "active": True},
    )
    await asyncio.sleep(0.3)
    bus = gm_ws.buffered("battle_update")
    assert bus
    combs = {c.get("id"): c for c in (bus[-1]["data"].get("combatants") or [])}
    pip_cb = combs.get(pip_tok)
    assert pip_cb is not None
    speed_buff = next((b for b in (pip_cb.get("buffs") or [])
                       if b.get("key") == "alacrity-speed"), None)
    assert speed_buff is not None, pip_cb.get("buffs")
    assert (speed_buff.get("effects") or {}).get("speed_bonus_ft") == 10


async def test_use_aoa_lv18_radius_upgrade(
    gm_client, caelan_glory_lv7,
):
    """Lv 18 → radius 10 (RAW upgrade — note 5→10 ft, not 10→30)."""
    caelan = caelan_glory_lv7
    await _patch_sheet(
        gm_client, caelan["id"], {"level": 18},
        class_slug="paladin",
    )
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_aura_of_alacrity",
        json={"character_id": caelan["id"]},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["radius_ft"] == 10
    assert data["speed_bonus_ft"] == 10
    assert data["paladin_level"] == 18


async def test_use_aoa_wrong_subclass(
    gm_client, roster,
):
    """Default Caelan (Devotion) → 409."""
    caelan = roster["Sir Caelan Lightbringer"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_aura_of_alacrity",
        json={"character_id": caelan["id"]},
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "wrong_subclass_or_level"


async def test_use_aoa_level_gate(
    gm_client, roster,
):
    """Glory Caelan at Lv 6 → 409."""
    caelan = roster["Sir Caelan Lightbringer"]
    await _patch_sheet(
        gm_client, caelan["id"],
        {"subclass": "Oath of Glory", "level": 6},
        class_slug="paladin",
    )
    try:
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/use_aura_of_alacrity",
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
