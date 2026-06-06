"""v2.99.253 — Battle Master maneuver 3: Menacing Attack.

Phase E.1 Phase 3 (maneuver 3 of 16). RAW PHB p.74: on hit,
expend 1 superiority die; +die damage and target makes a WIS
save DC 8 + prof + max(STR, DEX) or be Frightened of attacker
until end of attacker's next turn.

Mirrors Trip / Disarming Attack but the save ability is WIS
and the on-fail effect is Frightened.

Garrik is the fixture. Tests PATCH his subclass to "Battle
Master" + seed superiority-dice.

Tests:
  - Happy d8 → extra 1..8, DC 16, save_ability WIS, dice 4→3.
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


def _ma_broadcasts(gm_ws, character_id):
    return [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "menacing-attack"
        and (m.get("data") or {}).get("character_id") == character_id
    ]


def _superiority_dice_block(current: int, maximum: int) -> dict:
    return {
        "key": "superiority-dice",
        "name": "Superiority Dice",
        "current": current, "max": maximum, "reset": "short",
        "source": "fighter Lv 3 / Combat Superiority",
        "class_slug": "fighter",
        "desc": "Battle Master maneuvers. Refreshes on short or long rest.",
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


async def test_use_ma_happy(
    gm_client, gm_ws, garrik_battle_master,
):
    """Lv 9 Garrik d8 → extra in 1..8, DC 16, WIS, dice 4→3."""
    garrik = garrik_battle_master
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_menacing_attack",
        json={"character_id": garrik["id"]},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["die_size"] == "d8"
    assert 1 <= data["extra_damage"] <= 8
    assert data["save_dc"] == 16
    assert data["save_ability"] == "WIS"
    assert data["dice_remaining"] == 3
    await asyncio.sleep(0.3)
    feats = _ma_broadcasts(gm_ws, garrik["id"])
    assert feats


async def test_use_ma_out_of_dice(
    gm_client, garrik_battle_master,
):
    """current=0 → 409."""
    garrik = garrik_battle_master
    await _patch_sheet(
        gm_client, garrik["id"],
        {"resources": [_superiority_dice_block(0, 4)]},
    )
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_menacing_attack",
        json={"character_id": garrik["id"]},
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "out_of_uses"


async def test_use_ma_wrong_subclass(
    gm_client, roster,
):
    """Default Garrik (Champion) → 409."""
    garrik = roster["Garrik Ironside"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_menacing_attack",
        json={"character_id": garrik["id"]},
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "wrong_subclass_or_level"


async def test_ma_resolves_npc_save_installs_frightened(
    gm_client, gm_ws, garrik_battle_master,
):
    """v2.99.406 — Phase 3.1: against an NPC target, Menacing Attack
    auto-resolves the WIS save server-side (_resolve_feature_save) and
    installs Frightened on a fail.

    NPC saves are random, so loop until a fail lands — Garrik's DC 16 vs
    a Bandit's +0 WIS fails ~75% of swings. Seed a deep die pool up front
    so each iteration is just one POST. Asserts both branches as they
    occur: on a pass nothing installs; on a fail the `frightened` buff
    lands on the dummy (verified via battle_update).
    """
    garrik = garrik_battle_master
    await _patch_sheet(
        gm_client, garrik["id"],
        {"resources": [_superiority_dice_block(40, 40)]},
    )
    tmpl_resp = await gm_client.get(f"/api/campaign/{CAMPAIGN_ID}/templates")
    templates = tmpl_resp.json()
    bandit = next(
        (t for t in templates if "bandit" in (t.get("name") or "").lower()),
        templates[0],
    )

    garrik_tok = f"tok_ma_garrik_{garrik['id']}"
    dummy_tok = "tok_ma_bandit"
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": [
            {"id": garrik_tok, "char_id": garrik["id"], "name": garrik["name"],
             "initiative": 12, "hp_current": 60, "hp_max": 60, "buffs": [],
             "economy": {"action": False, "bonus": False,
                         "reaction": False, "movement": 0}},
            {"id": dummy_tok, "char_id": None,
             "token_template_id": bandit["id"], "name": bandit["name"],
             "initiative": 8, "hp_current": 30, "hp_max": 30, "buffs": [],
             "economy": {"action": False, "bonus": False,
                         "reaction": False, "movement": 0}},
        ], "turn_index": 0, "round": 1, "active": True},
    )

    landed = False
    for _ in range(40):
        gm_ws.mark()
        resp = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/use_menacing_attack",
            json={"character_id": garrik["id"],
                  "target_combatant_id": dummy_tok},
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["save_resolved"] is True, data
        if data["save_passed"]:
            assert data["condition_installed"] is False
            continue
        # Failed save → Frightened installs.
        assert data["condition_installed"] is True
        bu = await gm_ws.wait_for("battle_update")
        dummy_cb = next(
            (c for c in (bu["data"].get("combatants") or [])
             if c.get("id") == dummy_tok), None)
        assert dummy_cb is not None
        frightened = next(
            (b for b in (dummy_cb.get("buffs") or [])
             if (b or {}).get("key") == "frightened"), None)
        assert frightened is not None, dummy_cb.get("buffs")
        assert frightened.get("source_char_id") == garrik["id"]
        assert frightened.get("name") == "Frightened (Menacing Attack)"
        landed = True
        break

    assert landed, "no failed WIS save in 40 tries; Frightened didn't install"
