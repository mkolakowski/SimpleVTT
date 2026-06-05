"""v2.99.267 — Eldritch Knight Fighter: War Magic (Phase E.2 Phase 2).

Phase E.2 Phase 2 per docs/plans/eldritch-knight.md. RAW PHB
p.74: Eldritch Knight Lv 7+ — after casting a cantrip with
your action, make one weapon attack as a bonus action.

v1 ships announce-only — the cantrip prereq is GM-tracked;
deeper /cast_spell-hook integration filed for follow-up.

Garrik Lv 9 is the demo fixture. Tests PATCH his subclass to
"Eldritch Knight"; he's already past Lv 7.

Tests:
  - Happy → bonus chip marked + broadcast.
  - Wrong subclass (default Champion) → 409.
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


def _wm_broadcasts(gm_ws, character_id):
    return [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "war-magic"
        and (m.get("data") or {}).get("character_id") == character_id
    ]


@pytest_asyncio.fixture
async def garrik_eldritch_knight(gm_client, roster):
    """PATCH Garrik to Eldritch Knight + put him in a battle so
    the bonus chip can be marked."""
    garrik = roster["Garrik Ironside"]
    await _patch_sheet(
        gm_client, garrik["id"],
        {"subclass": "Eldritch Knight"},
        class_slug="fighter",
    )
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": [
            {"id": f"tok_gk_{garrik['id']}",
             "char_id": garrik["id"], "name": garrik["name"],
             "initiative": 12, "hp_current": 85, "hp_max": 85,
             "buffs": [],
             "economy": {"action": False, "bonus": False,
                         "reaction": False, "movement": 0}},
        ], "turn_index": 0, "round": 1, "active": True},
    )
    try:
        yield garrik
    finally:
        await _patch_sheet(
            gm_client, garrik["id"],
            {"subclass": "Champion"},
            class_slug="fighter",
        )


async def test_use_wm_happy(
    gm_client, gm_ws, garrik_eldritch_knight,
):
    """Lv 9 Eldritch Knight Garrik → 200 + broadcast."""
    garrik = garrik_eldritch_knight
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_war_magic",
        json={"character_id": garrik["id"], "override": True},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["feature"] == "war-magic"
    await asyncio.sleep(0.3)
    feats = _wm_broadcasts(gm_ws, garrik["id"])
    assert feats


async def test_use_wm_wrong_subclass(
    gm_client, roster,
):
    """Default Garrik (Champion) → 409."""
    garrik = roster["Garrik Ironside"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_war_magic",
        json={"character_id": garrik["id"], "override": True},
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "wrong_subclass_or_level"


async def test_use_wm_level_gate(
    gm_client, roster,
):
    """Eldritch Knight at Lv 6 (not 7+) → 409."""
    garrik = roster["Garrik Ironside"]
    await _patch_sheet(
        gm_client, garrik["id"],
        {"subclass": "Eldritch Knight", "level": 6},
        class_slug="fighter",
    )
    try:
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/use_war_magic",
            json={"character_id": garrik["id"], "override": True},
        )
        assert r.status_code == 409, r.text
        data = r.json()
        assert data.get("error") == "wrong_subclass_or_level"
    finally:
        await _patch_sheet(
            gm_client, garrik["id"],
            {"subclass": "Champion", "level": 9},
            class_slug="fighter",
        )
