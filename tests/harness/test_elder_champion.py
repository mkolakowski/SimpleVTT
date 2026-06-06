"""v2.99.288 — Ancients Paladin: Elder Champion (H.2 deeper, Lv 20).

H.2 Lv 20 first ship. Opens the H.2 Lv 20 capstone batch.
RAW PHB p.87: action to transform for 1 min: 10 HP at turn
start; 1-action paladin spells castable as bonus action; 10
ft aura → enemies disadvantage on saves vs your paladin
spells + CDs. Once per long rest.

v1 announce-only — the heal, bonus-cast option, and aura are
GM-tracked. Costs an action chip. Auto-bootstraps an
`elder-champion` resource; refilled by long rest.

Caelan Lv 7 default → PATCH to Ancients Lv 20.

Tests:
  - Lv 20 happy → uses_remaining 0, turn_start_heal 10,
    aura_radius_ft 10, duration 1 min.
  - Wrong subclass → 409.
  - Level gate (Lv 19) → 409.
  - Out of uses → 409 (after first happy).
  - Long rest refills → second call after rest → 200.
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


def _ec_broadcasts(gm_ws, character_id):
    return [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "elder-champion"
        and (m.get("data") or {}).get("character_id") == character_id
    ]


@pytest_asyncio.fixture
async def caelan_ancients_lv20(gm_client, roster):
    """PATCH Caelan to Ancients Lv 20 + long-rest to refill."""
    caelan = roster["Sir Caelan Lightbringer"]
    await _patch_sheet(
        gm_client, caelan["id"],
        {"subclass": "Oath of the Ancients", "level": 20},
        class_slug="paladin",
    )
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{caelan['id']}/rest",
        json={"type": "long"},
    )
    try:
        yield caelan
    finally:
        await _patch_sheet(
            gm_client, caelan["id"],
            {"subclass": "Oath of Devotion", "level": 7},
            class_slug="paladin",
        )


async def test_use_ec_happy_lv20(
    gm_client, gm_ws, caelan_ancients_lv20,
):
    """Lv 20 Ancients → uses_remaining 0, heal 10, aura 10 ft."""
    caelan = caelan_ancients_lv20
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_elder_champion",
        json={"character_id": caelan["id"], "override": True},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["uses_remaining"] == 0
    assert data["max_uses"] == 1
    assert data["duration_minutes"] == 1
    assert data["turn_start_heal"] == 10
    assert data["aura_radius_ft"] == 10
    assert data["paladin_level"] == 20
    await asyncio.sleep(0.3)
    feats = _ec_broadcasts(gm_ws, caelan["id"])
    assert feats


async def test_use_ec_wrong_subclass(
    gm_client, roster,
):
    """Default Caelan (Devotion Lv 7) → 409."""
    caelan = roster["Sir Caelan Lightbringer"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_elder_champion",
        json={"character_id": caelan["id"], "override": True},
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "wrong_subclass_or_level"


async def test_use_ec_level_gate(
    gm_client, roster,
):
    """Ancients Caelan at Lv 19 → 409."""
    caelan = roster["Sir Caelan Lightbringer"]
    await _patch_sheet(
        gm_client, caelan["id"],
        {"subclass": "Oath of the Ancients", "level": 19},
        class_slug="paladin",
    )
    try:
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/use_elder_champion",
            json={"character_id": caelan["id"], "override": True},
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


async def test_use_ec_out_of_uses(
    gm_client, caelan_ancients_lv20,
):
    """Second call back-to-back → 409 no_uses_left."""
    caelan = caelan_ancients_lv20
    r1 = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_elder_champion",
        json={"character_id": caelan["id"], "override": True},
    )
    assert r1.status_code == 200, r1.text
    r2 = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_elder_champion",
        json={"character_id": caelan["id"], "override": True},
    )
    assert r2.status_code == 409, r2.text
    data = r2.json()
    assert data.get("error") == "no_uses_left"


async def test_use_ec_long_rest_refills(
    gm_client, caelan_ancients_lv20,
):
    """Use → long rest → use again → 200."""
    caelan = caelan_ancients_lv20
    r1 = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_elder_champion",
        json={"character_id": caelan["id"], "override": True},
    )
    assert r1.status_code == 200, r1.text
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{caelan['id']}/rest",
        json={"type": "long"},
    )
    r2 = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_elder_champion",
        json={"character_id": caelan["id"], "override": True},
    )
    assert r2.status_code == 200, r2.text
    data = r2.json()
    assert data["uses_remaining"] == 0
    assert data["max_uses"] == 1


async def test_ec_aura_self_heals_at_turn_start(
    gm_client, gm_ws, caelan_ancients_lv20,
):
    """v2.99.428 — Phase 5.4: Elder Champion installs a self-heal aura
    buff so the tick regains 10 HP at the start of the paladin's turn.

    Lower Caelan's sheet HP, activate Elder Champion, advance to his turn
    (carrying the buff), and assert the heal lands (hp.current rises 10).
    """
    caelan = caelan_ancients_lv20
    # Drop the paladin below max so the heal is observable (clamps to max).
    await _patch_sheet(
        gm_client, caelan["id"], {"hp": {"current": 20, "max": 60, "temp": 0}},
    )
    caelan_tok = f"tok_ec_{caelan['id']}"
    other = "tok_ec_other"

    def _battle(buffs, turn_index):
        return {"combatants": [
            {"id": caelan_tok, "char_id": caelan["id"], "name": caelan["name"],
             "initiative": 20, "hp_current": 20, "hp_max": 60, "buffs": buffs,
             "economy": {"action": False, "bonus": False,
                         "reaction": False, "movement": 0}},
            {"id": other, "char_id": None, "name": "NPC",
             "initiative": 10, "hp_current": 30, "hp_max": 30, "buffs": [],
             "economy": {"action": False, "bonus": False,
                         "reaction": False, "movement": 0}},
        ], "turn_index": turn_index, "round": 1, "active": True}

    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle", json=_battle([], 1))
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_elder_champion",
        json={"character_id": caelan["id"], "override": True},
    )
    assert r.status_code == 200, r.text
    assert r.json()["buff_installed"] is True

    bu = await gm_ws.wait_for("buff_update")
    buffs = bu["data"]["buffs"]
    assert any(b.get("key") == "elder-champion" for b in buffs)

    # Advance to Caelan's turn (index 0) carrying the buff → self-heal.
    gm_ws.mark()
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json=_battle(buffs, 0) | {"round": 2},
    )
    hp = await gm_ws.wait_for("character_hp_update")
    assert hp["data"]["character_id"] == caelan["id"]
    assert int(hp["data"]["hp"].get("current") or 0) == 30  # 20 + 10
