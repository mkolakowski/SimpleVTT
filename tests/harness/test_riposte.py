"""v2.99.262 — Battle Master maneuver 12: Riposte.

Phase E.1 Phase 3 (maneuver 12 of 16). RAW PHB p.74: reaction
when missed by melee; make a melee weapon attack vs the
attacker. If hit, die added to damage.

Tests:
  - Happy d8 → extra_damage_on_hit 1..8, dice 4→3.
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


def _ri_broadcasts(gm_ws, character_id):
    return [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "riposte"
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


async def test_use_ri_happy(
    gm_client, gm_ws, garrik_battle_master,
):
    """Lv 9 Garrik d8 → extra_damage_on_hit 1..8."""
    garrik = garrik_battle_master
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_riposte",
        json={"character_id": garrik["id"], "override": True},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert 1 <= data["extra_damage_on_hit"] <= 8
    assert data["dice_remaining"] == 3
    await asyncio.sleep(0.3)
    feats = _ri_broadcasts(gm_ws, garrik["id"])
    assert feats


async def test_use_ri_out_of_dice(
    gm_client, garrik_battle_master,
):
    """current=0 → 409."""
    garrik = garrik_battle_master
    await _patch_sheet(
        gm_client, garrik["id"],
        {"resources": [_superiority_dice_block(0, 4)]},
    )
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_riposte",
        json={"character_id": garrik["id"], "override": True},
    )
    assert r.status_code == 409, r.text


async def test_use_ri_wrong_subclass(
    gm_client, roster,
):
    """Default Garrik (Champion) → 409."""
    garrik = roster["Garrik Ironside"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_riposte",
        json={"character_id": garrik["id"], "override": True},
    )
    assert r.status_code == 409, r.text


def _mkc(cid, char_id, name="C", hp=40):
    return {
        "id": cid, "char_id": char_id, "name": name,
        "initiative": 10, "hp_current": hp, "hp_max": hp, "buffs": [],
        "economy": {"action": False, "bonus": False,
                    "reaction": False, "movement": 0},
    }


async def test_riposte_resolves_counter_attack(
    gm_client, garrik_battle_master,
):
    """v2.99.455 — Phase 7: with a target_combatant_id, Riposte resolves
    the counter-attack (Greatsword) server-side + adds the superiority die
    to damage on a hit. Garrik's Greatsword is +8 vs AC 10 → near-certain
    hit; loop a couple times for the rare miss."""
    garrik = garrik_battle_master
    g_cid = f"tok_ri_g_{garrik['id']}"
    dummy_cid = "tok_ri_dummy"
    hit_data = None
    for _ in range(8):
        await _patch_sheet(
            gm_client, garrik["id"],
            {"resources": [_superiority_dice_block(4, 4)]},
        )
        await gm_client.put(
            f"/api/campaign/{CAMPAIGN_ID}/battle",
            json={"combatants": [
                _mkc(g_cid, garrik["id"], name=garrik["name"]),
                _mkc(dummy_cid, None, name="Dummy"),
            ], "turn_index": 0, "round": 1, "active": True},
        )
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/use_riposte",
            json={"character_id": garrik["id"], "attack_index": 0,
                  "target_combatant_id": dummy_cid, "override": True},
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["attacked"] is True
        assert data["target_ac"] > 0
        if data["hit"]:
            assert data["damage_type"] == "slashing"
            # weapon (2d6+4) + superiority die → strictly more than the die.
            assert data["damage_rolled"] > data["extra_damage_on_hit"]
            assert data["damage_applied"] > 0
            hit_data = data
            break
    assert hit_data is not None, "no riposte hit in 8 tries"


async def test_riposte_target_not_in_battle_404(
    gm_client, garrik_battle_master,
):
    """A target_combatant_id not in battle → 404."""
    garrik = garrik_battle_master
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_riposte",
        json={"character_id": garrik["id"], "attack_index": 0,
              "target_combatant_id": "nope_not_in_battle", "override": True},
    )
    assert r.status_code == 404, r.text
