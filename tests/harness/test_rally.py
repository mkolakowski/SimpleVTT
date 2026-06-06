"""v2.99.260 — Battle Master maneuver 10: Rally.

Phase E.1 Phase 3 (maneuver 10 of 16). RAW PHB p.74: bonus
action; ally who can see or hear you gets temp HP = die roll
+ CHA mod. Garrik CHA 10 → mod 0; temp HP equals die roll.

Tests:
  - Happy d8 → temp_hp = die_roll, cha_mod 0, dice 4→3.
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


def _ra_broadcasts(gm_ws, character_id):
    return [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "rally"
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


async def test_use_ra_happy(
    gm_client, gm_ws, garrik_battle_master,
):
    """Lv 9 Garrik d8 → temp_hp = die_roll (CHA 10 → mod 0)."""
    garrik = garrik_battle_master
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_rally",
        json={
            "character_id": garrik["id"],
            "ally_name": "Pip",
            "override": True,
        },
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["cha_mod"] == 0
    assert 1 <= data["die_roll"] <= 8
    assert data["temp_hp"] == data["die_roll"]
    assert data["ally_name"] == "Pip"
    assert data["dice_remaining"] == 3
    await asyncio.sleep(0.3)
    feats = _ra_broadcasts(gm_ws, garrik["id"])
    assert feats


async def test_use_ra_out_of_dice(
    gm_client, garrik_battle_master,
):
    """current=0 → 409."""
    garrik = garrik_battle_master
    await _patch_sheet(
        gm_client, garrik["id"],
        {"resources": [_superiority_dice_block(0, 4)]},
    )
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_rally",
        json={"character_id": garrik["id"], "override": True},
    )
    assert r.status_code == 409, r.text


async def test_use_ra_wrong_subclass(
    gm_client, roster,
):
    """Default Garrik (Champion) → 409."""
    garrik = roster["Garrik Ironside"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_rally",
        json={"character_id": garrik["id"], "override": True},
    )
    assert r.status_code == 409, r.text


def _mkc(cid, char_id=None, name="X", hp=50):
    return {
        "id": cid, "char_id": char_id, "name": name,
        "initiative": 10, "hp_current": hp, "hp_max": hp, "buffs": [],
        "economy": {"action": False, "bonus": False,
                    "reaction": False, "movement": 0},
    }


async def test_ra_grants_temp_hp_and_absorbs_damage(
    gm_client, gm_ws, garrik_battle_master,
):
    """v2.99.416 — Phase 4.1: Rally targeting an ally applies temp HP via
    _grant_temp_hp, and a subsequent hit spends that temp pool BEFORE
    real HP.

    Deterministic invariant (any rolled temp T + any hit damage D):
    after the hit the ally's temp = max(0, T - D) and hp_current =
    hp_max - max(0, D - T) — i.e. temp drains first.
    """
    garrik = garrik_battle_master
    garrik_tok = f"tok_ra_g_{garrik['id']}"
    ally_tok = "tok_ra_ally"
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": [
            _mkc(garrik_tok, garrik["id"], name=garrik["name"], hp=60),
            _mkc(ally_tok, None, name="Ally Dummy", hp=50),
        ], "turn_index": 0, "round": 1, "active": True},
    )

    # Rally the ally → grant temp HP.
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_rally",
        json={"character_id": garrik["id"],
              "target_combatant_id": ally_tok, "override": True},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    temp = data["temp_hp"]
    assert temp >= 1  # CHA 10 → mod 0, 1d8 → 1-8
    assert data["temp_hp_applied"] is True
    bu = await gm_ws.wait_for("battle_update")
    ally = next((c for c in (bu["data"].get("combatants") or [])
                 if c.get("id") == ally_tok), None)
    assert ally is not None
    assert int(ally.get("temp_hp") or 0) == temp

    # Attack the ally until a swing lands; the hit drains temp first.
    hit = None
    for _ in range(25):
        gm_ws.mark()
        a = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/attack",
            json={"character_id": garrik["id"], "attack_index": 0,
                  "target_combatant_id": ally_tok, "override": True},
        )
        assert a.status_code == 200, a.text
        ad = a.json()
        if ad["hit"] and int(ad.get("damage_applied") or 0) > 0:
            hit = ad
            break
    assert hit is not None, "no damaging hit in 25 swings"

    dmg = int(hit["damage_applied"])
    bu2 = await gm_ws.wait_for("battle_update")
    ally2 = next((c for c in (bu2["data"].get("combatants") or [])
                  if c.get("id") == ally_tok), None)
    assert ally2 is not None
    # Temp drains before real HP.
    assert int(ally2.get("temp_hp") or 0) == max(0, temp - dmg)
    assert int(ally2.get("hp_current") or 0) == 50 - max(0, dmg - temp)
