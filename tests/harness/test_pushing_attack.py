"""v2.99.254 — Battle Master maneuver 4: Pushing Attack.

Phase E.1 Phase 3 (maneuver 4 of 16). RAW PHB p.74: on hit
vs Large-or-smaller, expend 1 superiority die; +die damage and
target Str save DC 8 + prof + max(STR, DEX) or be pushed up
to 15 ft away from attacker.

Mirrors Trip / Disarming / Menacing. Size-gate (Large or
smaller) is GM-tracked in v1.

Tests:
  - Happy d8 → extra 1..8, DC 16, save STR, push 15.
  - Out of dice → 409.
  - Wrong subclass → 409.
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


def _pa_broadcasts(gm_ws, character_id):
    return [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "pushing-attack"
        and (m.get("data") or {}).get("character_id") == character_id
    ]


def _superiority_dice_block(current: int, maximum: int) -> dict:
    return {
        "key": "superiority-dice",
        "name": "Superiority Dice",
        "current": current, "max": maximum, "reset": "short",
        "source": "fighter Lv 3 / Combat Superiority",
        "class_slug": "fighter",
        "desc": "Battle Master maneuvers.",
        "manual": False,
    }


@pytest_asyncio.fixture
async def garrik_battle_master(gm_client, roster):
    """PATCH Garrik to Battle Master + seed superiority-dice."""
    garrik = roster["Garrik Ironside"]
    await _patch_sheet(
        gm_client, garrik["id"],
        {
            "subclass": "Battle Master",
            "superiority_die_size": "d8",
            "resources": [_superiority_dice_block(4, 4)],
        },
        class_slug="fighter",
    )
    try:
        yield garrik
    finally:
        await _patch_sheet(
            gm_client, garrik["id"],
            {"subclass": "Champion", "resources": []},
            class_slug="fighter",
        )


async def test_use_pa_happy(
    gm_client, gm_ws, garrik_battle_master,
):
    """Lv 9 Garrik d8 → extra 1..8, DC 16, STR, push 15."""
    garrik = garrik_battle_master
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_pushing_attack",
        json={"character_id": garrik["id"]},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["die_size"] == "d8"
    assert 1 <= data["extra_damage"] <= 8
    assert data["save_dc"] == 16
    assert data["save_ability"] == "STR"
    assert data["push_max_ft"] == 15
    assert data["dice_remaining"] == 3
    await asyncio.sleep(0.3)
    feats = _pa_broadcasts(gm_ws, garrik["id"])
    assert feats


async def test_use_pa_out_of_dice(
    gm_client, garrik_battle_master,
):
    """current=0 → 409."""
    garrik = garrik_battle_master
    await _patch_sheet(
        gm_client, garrik["id"],
        {"resources": [_superiority_dice_block(0, 4)]},
    )
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_pushing_attack",
        json={"character_id": garrik["id"]},
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "out_of_uses"


async def test_use_pa_wrong_subclass(
    gm_client, roster,
):
    """Default Garrik (Champion) → 409."""
    garrik = roster["Garrik Ironside"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_pushing_attack",
        json={"character_id": garrik["id"]},
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "wrong_subclass_or_level"


def _cb(cid, char_id, name):
    return {
        "id": cid, "char_id": char_id, "name": name,
        "initiative": 10, "hp_current": 40, "hp_max": 40, "buffs": [],
        "economy": {"action": False, "bonus": False,
                    "reaction": False, "movement": 0},
    }


async def _place_token(gm_client, char_id, x, y):
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/place-token",
        json={"x": float(x), "y": float(y)},
    )
    assert r.status_code == 200, r.text


async def _token_y(gm_client, char_id):
    resp = await gm_client.get(f"/api/campaign/{CAMPAIGN_ID}/tokens")
    for t in resp.json()["tokens"]:
        if t.get("character_id") == char_id:
            return float(t["y"])
    return None


async def test_pa_push_moves_target_on_failed_save(
    gm_client, roster, garrik_battle_master,
):
    """v2.99.433 — Phase 6.2: on a failed STR save, Pushing Attack pushes
    the target's token 15 ft away from the Battle Master via _force_move.

    Garrik (above Pip) pushes Pip downward. The save is rolled, so loop
    until Pip fails — then push_applied is True and Pip's token moved
    +210 px (3 cells / 15 ft). Deep die pool so the loop is just POSTs.
    """
    garrik = garrik_battle_master
    pip = roster["Pip Quickfingers"]
    await _patch_sheet(
        gm_client, garrik["id"],
        {"resources": [_superiority_dice_block(40, 40)]},
    )
    pip_cb, garrik_cb = "tok_pa_pip", "tok_pa_garrik"
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": [
            _cb(garrik_cb, garrik["id"], garrik["name"]),
            _cb(pip_cb, pip["id"], pip["name"]),
        ], "turn_index": 0, "round": 1, "active": False},
    )
    # Garrik directly above Pip (same x) → push is straight down (+y).
    await _place_token(gm_client, garrik["id"], 700.0, 560.0)
    await _place_token(gm_client, pip["id"], 700.0, 700.0)

    pushed = False
    for _ in range(30):
        before_y = await _token_y(gm_client, pip["id"])
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/use_pushing_attack",
            json={"character_id": garrik["id"], "target_combatant_id": pip_cb},
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["save_resolved"] is True
        if data["save_passed"] is False:
            assert data["push_applied"] is True
            after_y = await _token_y(gm_client, pip["id"])
            assert after_y == before_y + 210.0  # 15 ft on the 70-px grid
            pushed = True
            break
        # On a pass nothing moved.
        assert data["push_applied"] is False
        assert await _token_y(gm_client, pip["id"]) == before_y
    assert pushed, "no failed STR save in 30 swings"
