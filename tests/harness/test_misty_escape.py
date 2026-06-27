"""v2.699.0 — The Archfey Warlock: Misty Escape (Phase 8, Lv 6+, PHB p.109).

New endpoint. RAW: "When you take damage, you can use your reaction to turn
invisible and teleport up to 60 feet to an unoccupied space you can see. You
remain invisible until the start of your next turn or until you attack or
cast a spell." Once per short rest.

Mechanized onto two existing substrates:
  - installs a `misty-escape-invisible` buff (`effects.invisible: True`) that
    the attack-resolution invisibility edge reads; and
  - a 1-round `misty-escape-disengage` buff (`effects.disengage: True`) so the
    60-ft teleport drag provokes no OAs (the v2.698.0 disengage read).
The teleport destination is the player dragging the token; the "ends if you
attack/cast" cancel stays GM-narrated (buff also expires after ~2 rounds).

Magnus Hexbinder (Warlock) PATCH'd to The Archfey Lv 6.

Tests:
  - Happy (battle seeded) → teleport_ft 60, both buffs installed, uses 1→0.
  - Out of uses → 409 no_uses_left.
  - Wrong subclass (default The Fiend) → 409.
  - Level gate (Archfey Lv 5) → 409.
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


def _me_broadcasts(gm_ws, character_id):
    return [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "misty-escape"
        and (m.get("data") or {}).get("character_id") == character_id
    ]


async def _seed_solo_battle(gm_client, magnus):
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": [
            {"id": f"tok_me_{magnus['id']}", "char_id": magnus["id"],
             "name": magnus["name"], "initiative": 12,
             "hp_current": 30, "hp_max": 30, "buffs": [],
             "economy": {"action": False, "bonus": False,
                         "reaction": False, "movement": 0}},
        ], "turn_index": 0, "round": 1, "active": True},
    )


@pytest_asyncio.fixture
async def magnus_archfey(gm_client, roster):
    """PATCH Magnus to The Archfey Lv 6; restore to The Fiend Lv 5."""
    magnus = roster["Magnus Hexbinder"]
    await _patch_sheet(
        gm_client, magnus["id"],
        {"subclass": "The Archfey", "level": 6},
        class_slug="warlock",
    )
    try:
        yield magnus
    finally:
        await _patch_sheet(
            gm_client, magnus["id"],
            {"subclass": "The Fiend", "level": 5},
            class_slug="warlock",
        )


async def test_use_me_happy(gm_client, gm_ws, magnus_archfey):
    """Lv 6 Archfey (battle seeded) → teleport_ft 60, both buffs, uses 1→0."""
    magnus = magnus_archfey
    await _seed_solo_battle(gm_client, magnus)
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_misty_escape",
        json={"character_id": magnus["id"], "override": True},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["feature"] == "misty-escape"
    assert data["teleport_ft"] == 60
    assert data["invisible_installed"] is True
    assert data["disengage_installed"] is True
    assert data["uses_remaining"] == 0
    assert data["warlock_level"] == 6
    await asyncio.sleep(0.3)
    assert _me_broadcasts(gm_ws, magnus["id"])


async def test_use_me_out_of_uses(gm_client, magnus_archfey):
    """Second back-to-back use (no rest) → 409 no_uses_left."""
    magnus = magnus_archfey
    await _seed_solo_battle(gm_client, magnus)
    r1 = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_misty_escape",
        json={"character_id": magnus["id"], "override": True},
    )
    assert r1.status_code == 200, r1.text
    r2 = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_misty_escape",
        json={"character_id": magnus["id"], "override": True},
    )
    assert r2.status_code == 409, r2.text
    assert r2.json().get("error") == "no_uses_left"


async def test_use_me_wrong_subclass(gm_client, roster):
    """Default Magnus (The Fiend) → 409."""
    magnus = roster["Magnus Hexbinder"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_misty_escape",
        json={"character_id": magnus["id"], "override": True},
    )
    assert r.status_code == 409, r.text
    assert r.json().get("error") == "wrong_subclass_or_level"


async def test_use_me_level_gate(gm_client, roster):
    """Archfey Magnus at Lv 5 (< 6) → 409."""
    magnus = roster["Magnus Hexbinder"]
    await _patch_sheet(
        gm_client, magnus["id"],
        {"subclass": "The Archfey", "level": 5},
        class_slug="warlock",
    )
    try:
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/use_misty_escape",
            json={"character_id": magnus["id"], "override": True},
        )
        assert r.status_code == 409, r.text
        assert r.json().get("error") == "wrong_subclass_or_level"
    finally:
        await _patch_sheet(
            gm_client, magnus["id"],
            {"subclass": "The Fiend", "level": 5},
            class_slug="warlock",
        )
