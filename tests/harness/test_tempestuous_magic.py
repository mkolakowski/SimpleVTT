"""v2.99.339 — Storm Sorcery: Tempestuous Magic (G.2 batch open, Lv 1+, PHB).

G.2 Sorcerer subclass batch ship #1 — opens the Sorcerer batch.
RAW PHB p.137: bonus action on your turn to fly up to 10 ft
without provoking opportunity attacks, immediately after casting
a Lv 1+ sorcerer spell. Must be on the ground when casting.

**v2.697.0 (Phase 8):** installs a 1-round `tempestuous-magic-fly`
buff (`free_movement_remaining_ft: 10` + `oa_immune_during_move`)
riding the generalized free-move substrate (v2.696.0) — the next move
(≤ 10 ft) is cap-exempt + OA-free, then consumed. The recent-cast /
on-ground prerequisite + fly-vs-walk stay GM-narrated. Bonus chip.

Tests:
  - Lv 5 happy: fly_distance 10, oa_free True, buff_installed.
  - Generalized substrate: the buff exempts an over-cap move (no 409).
  - Wrong subclass (default Zara Draconic) → 409.
  - Wrong class (Caelan paladin) → 409.
"""
import asyncio
import pytest_asyncio

from .conftest import CAMPAIGN_ID


async def _place_token(gm_client, char_id, x, y):
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/place-token",
        json={"x": float(x), "y": float(y)},
    )
    assert r.status_code == 200, r.text


async def _get_token_for_char(gm_client, char_id):
    r = await gm_client.get(f"/api/campaign/{CAMPAIGN_ID}/tokens")
    assert r.status_code == 200, r.text
    for t in r.json()["tokens"]:
        if t.get("character_id") == char_id:
            return t
    return None


async def _patch_sheet(gm_client, char_id, fields, class_slug=None):
    body = dict(fields)
    if class_slug:
        body["class_slug"] = class_slug
    r = await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-fields",
        json=body,
    )
    assert r.status_code == 200, r.text


def _tm_broadcasts(gm_ws, character_id):
    return [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "tempestuous-magic"
        and (m.get("data") or {}).get("character_id") == character_id
    ]


@pytest_asyncio.fixture
async def zara_storm(gm_client, roster):
    """PATCH Zara to Storm Sorcery."""
    zara = roster["Zara Emberfire"]
    await _patch_sheet(
        gm_client, zara["id"],
        {"subclass": "Storm Sorcery"},
        class_slug="sorcerer",
    )
    try:
        yield zara
    finally:
        await _patch_sheet(
            gm_client, zara["id"],
            {"subclass": "Draconic Bloodline"},
            class_slug="sorcerer",
        )


async def test_use_tm_happy_lv5(
    gm_client, gm_ws, zara_storm,
):
    """Lv 5 Storm Sorcery → fly_distance 10, oa_free True."""
    zara = zara_storm
    # Seed Zara into an active battle so `_install_buff` lands.
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": [
            {"id": f"tok_tm_h_{zara['id']}", "char_id": zara["id"],
             "name": zara["name"], "initiative": 12,
             "hp_current": 30, "hp_max": 30, "buffs": [],
             "economy": {"action": False, "bonus": False,
                         "reaction": False, "movement": 0}},
        ], "turn_index": 0, "round": 1, "active": True},
    )
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_tempestuous_magic",
        json={"character_id": zara["id"], "override": True},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["feature"] == "tempestuous-magic"
    assert data["fly_distance"] == 10
    assert data["oa_free"] is True
    assert data["sorcerer_level"] == 5
    assert data["buff_installed"] is True
    await asyncio.sleep(0.3)
    feats = _tm_broadcasts(gm_ws, zara["id"])
    assert feats


async def test_tm_buff_rides_generalized_free_move_substrate(
    gm_client, zara_storm,
):
    """v2.697.0 — the `tempestuous-magic-fly` buff rides the generalized
    free-move read in /token/move. Zara at her 30-ft cap (movement=30): a
    +5-ft drag would 409 over_speed_cap, but the 10-ft Tempestuous budget
    exempts it → 200 + relentless_avenger_applied True (the generic flag).
    Control without the buff → 409."""
    zara = zara_storm
    _BUFF = {
        "key": "tempestuous-magic-fly", "name": "Tempestuous Magic (fly)",
        "icon": "🌪️", "duration_rounds": 1,
        "effects": {"free_movement_remaining_ft": 10,
                    "oa_immune_during_move": True},
    }

    def _cb(buffs):
        return {
            "id": f"tok_tm_{zara['id']}", "char_id": zara["id"],
            "name": zara["name"], "initiative": 10, "speed_walk": 30,
            "hp_current": 30, "hp_max": 30, "buffs": buffs,
            "economy": {"action": False, "bonus": False,
                        "reaction": False, "movement": 30},
        }

    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": [_cb([dict(_BUFF)])],
              "turn_index": 0, "round": 1, "active": True},
    )
    await _place_token(gm_client, zara["id"], 350.0, 350.0)
    tok = await _get_token_for_char(gm_client, zara["id"])
    assert tok, "Zara token must exist"
    await asyncio.sleep(0.15)
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/token/{tok['id']}/move",
        json={"x": 420.0, "y": 350.0},  # +1 cell = 5 ft
    )
    assert resp.status_code == 200, (
        f"tempestuous free move should be cap-exempt; got "
        f"{resp.status_code} {resp.text}"
    )
    assert resp.json().get("relentless_avenger_applied") is True, resp.text

    # Control: identical over-cap drag with NO buff → 409.
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": [_cb([])],
              "turn_index": 0, "round": 1, "active": True},
    )
    await _place_token(gm_client, zara["id"], 350.0, 350.0)
    tok = await _get_token_for_char(gm_client, zara["id"])
    await asyncio.sleep(0.15)
    resp2 = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/token/{tok['id']}/move",
        json={"x": 420.0, "y": 350.0},
    )
    assert resp2.status_code == 409, resp2.text
    assert resp2.json().get("error") == "over_speed_cap", resp2.text


async def test_use_tm_wrong_subclass(
    gm_client, roster,
):
    """Default Zara (Draconic Bloodline) → 409."""
    zara = roster["Zara Emberfire"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_tempestuous_magic",
        json={"character_id": zara["id"], "override": True},
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "wrong_subclass_or_level"


async def test_use_tm_wrong_class(
    gm_client, roster,
):
    """Caelan (Paladin) → 409."""
    caelan = roster["Sir Caelan Lightbringer"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_tempestuous_magic",
        json={"character_id": caelan["id"], "override": True},
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "wrong_subclass_or_level"
