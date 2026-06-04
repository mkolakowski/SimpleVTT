"""v2.99.226 — Path of the Berserker features: Frenzy + Intimidating Presence.

Phase E.8 of the v2.99.193 phased completion plan. RAW PHB
p.49:
  - Frenzy (Lv 3): while raging, make a single melee weapon
    attack as a bonus action each turn. +1 exhaustion at
    rage-end (filed for v1 — GM-tracks).
  - Intimidating Presence (Lv 10): action; target makes Wis save
    DC 8 + prof + CHA mod or be frightened until end of next
    turn.

v1 ships:
  - /use_frenzy: validates Berserker Lv 3+ + currently raging +
    bonus chip; announces.
  - /use_intimidating_presence: validates Berserker Lv 10+ +
    action chip; computes DC; announces.

Krieger Stonefist (Barbarian Path of the Berserker Lv 7
default) is the demo fixture. The IP test PATCHes him Lv 7 →
10.

Tests:
  - Frenzy after rage → 200 + broadcast.
  - Frenzy without rage → 409 not_raging.
  - Frenzy wrong-class → 409 wrong_subclass_or_level.
  - Intimidating Presence at Lv 10 → 200 with DC.
  - Intimidating Presence level gate (Lv 7) → 409.
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


def _frenzy_broadcasts(gm_ws, character_id):
    return [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "frenzy"
        and (m.get("data") or {}).get("character_id") == character_id
    ]


def _ip_broadcasts(gm_ws, character_id):
    return [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "intimidating-presence"
        and (m.get("data") or {}).get("character_id") == character_id
    ]


@pytest_asyncio.fixture
async def krieger_in_battle(gm_client, roster):
    """Seed Krieger in an active battle so /use_rage's buff
    install can persist (Frenzy gates on rage-buff-active)."""
    krieger = roster["Krieger Stonefist"]
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": [
            {"id": f"tok_zerk_{krieger['id']}",
             "char_id": krieger["id"], "name": krieger["name"],
             "initiative": 15, "hp_current": 55, "hp_max": 55,
             "buffs": [],
             "economy": {"action": False, "bonus": False,
                         "reaction": False, "movement": 0}},
        ], "turn_index": 0, "round": 1, "active": True},
    )
    yield krieger


async def test_use_frenzy_after_rage(
    gm_client, gm_ws, krieger_in_battle,
):
    """Krieger /use_rage to install the rage buff, then /use_frenzy
    → 200 + broadcast."""
    krieger = krieger_in_battle
    rr = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_rage",
        json={"character_id": krieger["id"], "override": True},
    )
    assert rr.status_code == 200, rr.text
    await asyncio.sleep(0.2)
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_frenzy",
        json={"character_id": krieger["id"], "override": True},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["feature"] == "frenzy"
    await asyncio.sleep(0.3)
    feats = _frenzy_broadcasts(gm_ws, krieger["id"])
    assert feats


async def test_use_frenzy_without_rage(
    gm_client, krieger_in_battle,
):
    """No rage buff active → 409 not_raging."""
    krieger = krieger_in_battle
    # End any leftover rage buff via /end_buff (rage key) if
    # present. Cleanest: explicitly start without rage. The
    # krieger_in_battle fixture seeds an empty buffs list.
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_frenzy",
        json={"character_id": krieger["id"], "override": True},
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "not_raging"


async def test_use_frenzy_wrong_class(
    gm_client, roster,
):
    """Pip (Rogue) → 409 wrong_subclass_or_level."""
    pip = roster["Pip Quickfingers"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_frenzy",
        json={"character_id": pip["id"], "override": True},
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "wrong_subclass_or_level"


async def test_use_intimidating_presence_at_lv10(
    gm_client, gm_ws, roster,
):
    """Krieger PATCH'd to Lv 10 → /use_intimidating_presence →
    200 + DC + broadcast."""
    krieger = roster["Krieger Stonefist"]
    pre_level = 7
    await _patch_sheet(
        gm_client, krieger["id"], {"level": 10},
        class_slug="barbarian",
    )
    try:
        gm_ws.mark()
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/use_intimidating_presence",
            json={
                "character_id": krieger["id"],
                "target_name": "Bandit",
                "override": True,
            },
        )
        assert r.status_code == 200, r.text
        data = r.json()
        # Krieger sheet: CHA 8 → mod -1, sheet.proficiency_bonus
        # is +3 by demo seed (Lv 5-8 baseline; not auto-rederived
        # by the test PATCH on `level`).
        # DC = 8 + 3 + (-1) = 10.
        assert data["dc"] == 10, data
        assert data["target_name"] == "Bandit"
        await asyncio.sleep(0.3)
        feats = _ip_broadcasts(gm_ws, krieger["id"])
        assert feats
    finally:
        await _patch_sheet(
            gm_client, krieger["id"], {"level": pre_level},
            class_slug="barbarian",
        )


async def test_use_intimidating_presence_level_gate(
    gm_client, roster,
):
    """Control: Krieger at Lv 5 → 409 wrong_subclass_or_level."""
    krieger = roster["Krieger Stonefist"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_intimidating_presence",
        json={"character_id": krieger["id"], "override": True},
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "wrong_subclass_or_level"
