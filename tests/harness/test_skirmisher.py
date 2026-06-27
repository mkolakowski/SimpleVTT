"""v2.99.309 — Scout Rogue: Skirmisher (E.3 batch, Lv 3+).

E.3 Rogue subclass ship #5. RAW XGE p.46: reaction to move
up to half walking speed when enemy ends turn within 5 ft;
movement doesn't provoke OAs.

**v2.696.0 (Phase 8):** installs a 1-round `skirmisher-bonus-move`
buff carrying `free_movement_remaining_ft` (= half speed) +
`oa_immune_during_move`, riding the **generalized free-move substrate**
in `/token/move` (the Relentless Avenger read site, made effect-keyed
this commit). The Rogue's next move is exempt from the over-speed cap
up to the budget AND provokes no OAs; the buff is consumed on that
move. Costs reaction chip.

Pip (Thief Lv 7, halfling speed 25) PATCH'd to Scout.

Tests:
  - Lv 3+ happy → bonus_move_ft 12 (=25//2), no_oa True, buff_installed.
  - Generalized substrate: the skirmisher buff exempts an over-cap move
    from the speed cap (proves the effect-keyed read honors a non-RA key).
  - Default Pip (Thief) → 409.
  - Scout Lv 2 → 409.
"""
import asyncio
import pytest_asyncio

from .conftest import CAMPAIGN_ID


_SK_BUFF = {
    "key": "skirmisher-bonus-move",
    "name": "Skirmisher (free move)",
    "icon": "🏃",
    "duration_rounds": 1,
    "effects": {
        "free_movement_remaining_ft": 12,
        "oa_immune_during_move": True,
    },
}


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


def _sk_broadcasts(gm_ws, character_id):
    return [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "skirmisher"
        and (m.get("data") or {}).get("character_id") == character_id
    ]


@pytest_asyncio.fixture
async def pip_scout(gm_client, roster):
    """PATCH Pip to Scout subclass."""
    pip = roster["Pip Quickfingers"]
    await _patch_sheet(
        gm_client, pip["id"],
        {"subclass": "Scout"},
        class_slug="rogue",
    )
    try:
        yield pip
    finally:
        await _patch_sheet(
            gm_client, pip["id"],
            {"subclass": "Thief", "level": 7},
            class_slug="rogue",
        )


async def test_use_sk_happy_lv7(
    gm_client, gm_ws, pip_scout,
):
    """Lv 7 Scout (halfling speed 25) → bonus_move_ft 12, no_oa True."""
    pip = pip_scout
    # Seed Pip into an active battle so `_install_buff` lands (returns True).
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": [
            {"id": f"tok_sk_h_{pip['id']}", "char_id": pip["id"],
             "name": pip["name"], "initiative": 12,
             "hp_current": 30, "hp_max": 30, "buffs": [],
             "economy": {"action": False, "bonus": False,
                         "reaction": False, "movement": 0}},
        ], "turn_index": 0, "round": 1, "active": True},
    )
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_skirmisher",
        json={"character_id": pip["id"], "override": True},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["bonus_move_ft"] == 12
    assert data["base_speed"] == 25
    assert data["no_oa"] is True
    assert data["rogue_level"] == 7
    assert data["buff_installed"] is True
    await asyncio.sleep(0.3)
    feats = _sk_broadcasts(gm_ws, pip["id"])
    assert feats


async def test_sk_buff_rides_generalized_free_move_substrate(
    gm_client, pip_scout,
):
    """v2.696.0 — the `skirmisher-bonus-move` buff rides the generalized
    free-move read site in /token/move (proving it's effect-keyed, not
    hardcoded to Relentless Avenger). Pip at his 25 ft cap
    (economy.movement = 25): a +5 ft drag would 409 over_speed_cap, but the
    12 ft Skirmisher budget exempts it → 200 + relentless_avenger_applied
    True (the generic free-move flag). Control without the buff → 409."""
    pip = pip_scout

    def _cb(buffs):
        # speed_walk set explicitly so the over-speed cap is unambiguous
        # (25 ft); movement preloaded AT the cap so a +5 ft drag is over.
        return {
            "id": f"tok_sk_{pip['id']}", "char_id": pip["id"],
            "name": pip["name"], "initiative": 10, "speed_walk": 25,
            "hp_current": 30, "hp_max": 30, "buffs": buffs,
            "economy": {"action": False, "bonus": False,
                        "reaction": False, "movement": 25},
        }

    # With the skirmisher buff: at-cap + 5 ft drag is exempted.
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": [_cb([dict(_SK_BUFF)])],
              "turn_index": 0, "round": 1, "active": True},
    )
    await _place_token(gm_client, pip["id"], 350.0, 350.0)
    tok = await _get_token_for_char(gm_client, pip["id"])
    assert tok, "Pip token must exist"
    await asyncio.sleep(0.15)
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/token/{tok['id']}/move",
        json={"x": 420.0, "y": 350.0},  # +1 cell = 5 ft
    )
    assert resp.status_code == 200, (
        f"skirmisher free move should be exempt from the cap; got "
        f"{resp.status_code} {resp.text}"
    )
    assert resp.json().get("relentless_avenger_applied") is True, resp.text

    # Control: identical over-cap drag with NO buff → 409 over_speed_cap.
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": [_cb([])],
              "turn_index": 0, "round": 1, "active": True},
    )
    await _place_token(gm_client, pip["id"], 350.0, 350.0)
    tok = await _get_token_for_char(gm_client, pip["id"])
    await asyncio.sleep(0.15)
    resp2 = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/token/{tok['id']}/move",
        json={"x": 420.0, "y": 350.0},
    )
    assert resp2.status_code == 409, resp2.text
    assert resp2.json().get("error") == "over_speed_cap", resp2.text


async def test_use_sk_wrong_subclass(
    gm_client, roster,
):
    """Default Pip (Thief) → 409."""
    pip = roster["Pip Quickfingers"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_skirmisher",
        json={"character_id": pip["id"], "override": True},
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "wrong_subclass_or_level"


async def test_use_sk_level_gate(
    gm_client, roster,
):
    """Scout Pip at Lv 2 → 409."""
    pip = roster["Pip Quickfingers"]
    await _patch_sheet(
        gm_client, pip["id"],
        {"subclass": "Scout", "level": 2},
        class_slug="rogue",
    )
    try:
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/use_skirmisher",
            json={"character_id": pip["id"], "override": True},
        )
        assert r.status_code == 409, r.text
        data = r.json()
        assert data.get("error") == "wrong_subclass_or_level"
    finally:
        await _patch_sheet(
            gm_client, pip["id"],
            {"subclass": "Thief", "level": 7},
            class_slug="rogue",
        )
