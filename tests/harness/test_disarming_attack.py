"""v2.99.252 — Battle Master maneuver 2: Disarming Attack.

Phase E.1 Phase 3 (maneuver 2 of 16) of the v2.99.193 phased
completion plan. RAW PHB p.74: Battle Master Lv 3+ — on a hit,
expend 1 superiority die; +die damage and target makes a STR
save DC 8 + prof + max(STR, DEX) mod or drop one held object.

Mirrors Trip Attack (v2.99.233): same dice pool, same DC
formula, same fixed-save-ability shape. Only the on-fail
effect differs (drop object vs Prone).

Garrik is the demo fixture. Tests PATCH his subclass to
"Battle Master" + seed superiority-dice resource.

**v2.692.0 (Phase 8):** with a `target_combatant_id` (trust-the-
caller), the superiority die lands as bonus damage via
`_apply_damage_to_combatant` + the STR save is rolled via
`_resolve_feature_save` (`condition_buff=None` — the drop-object has
no engine condition, GM-narrated). Response gains `damage_applied` +
`feature_save`.

Tests:
  - Happy d8 → extra 1..8, DC 16, dice 4→3, broadcast.
  - Apply: templated NPC → bonus damage applied + STR save resolved.
  - Announce-only: no target → damage_applied/feature_save None.
  - Out of dice → 409.
  - Wrong subclass → 409.
  - Level gate → 409.
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


def _da_broadcasts(gm_ws, character_id):
    return [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "disarming-attack"
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


async def test_use_da_happy(
    gm_client, gm_ws, garrik_battle_master,
):
    """Lv 9 Garrik d8 → extra in 1..8, DC 16, dice 4→3."""
    garrik = garrik_battle_master
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_disarming_attack",
        json={"character_id": garrik["id"]},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["die_size"] == "d8"
    assert 1 <= data["extra_damage"] <= 8
    assert data["save_dc"] == 16
    assert data["dice_remaining"] == 3
    await asyncio.sleep(0.3)
    feats = _da_broadcasts(gm_ws, garrik["id"])
    assert feats


async def test_da_applies_damage_and_resolves_save(
    gm_client, garrik_battle_master,
):
    """v2.692.0 — Phase 8: with a target, the superiority die lands as bonus
    damage + the STR save resolves server-side (no condition — drop-object is
    GM-narrated). Templated bandit (untyped → no resistance) → damage_applied
    == extra_damage; feature_save resolved, no condition installed."""
    garrik = garrik_battle_master
    templates = (await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/templates")).json()
    bandit = next(
        (t for t in templates if "bandit" in (t.get("name") or "").lower()),
        templates[0],
    )
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": [
            {"id": f"tok_da_{garrik['id']}", "char_id": garrik["id"],
             "name": garrik["name"], "initiative": 14,
             "hp_current": 60, "hp_max": 60, "buffs": [],
             "economy": {"action": False, "bonus": False,
                         "reaction": False, "movement": 0}},
            {"id": "tok_da_bandit", "char_id": None,
             "token_template_id": bandit["id"], "name": bandit["name"],
             "initiative": 8, "hp_current": 50, "hp_max": 50, "buffs": [],
             "economy": {"action": False, "bonus": False,
                         "reaction": False, "movement": 0}},
        ], "turn_index": 0, "round": 1, "active": True},
    )
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_disarming_attack",
        json={"character_id": garrik["id"],
              "target_combatant_id": "tok_da_bandit"},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["damage_applied"] == data["extra_damage"], data
    fs = data["feature_save"]
    assert fs is not None and fs["resolved"] is True, data
    assert isinstance(fs["passed"], bool), fs
    # No engine condition for "drop object" → never installs one.
    assert fs["condition_installed"] is False, fs


async def test_da_no_target_announce_only(
    gm_client, garrik_battle_master,
):
    """v2.692.0 — no target → backward-compatible announce-only."""
    garrik = garrik_battle_master
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_disarming_attack",
        json={"character_id": garrik["id"]},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["damage_applied"] is None
    assert data["feature_save"] is None


async def test_use_da_out_of_dice(
    gm_client, garrik_battle_master,
):
    """current=0 → 409."""
    garrik = garrik_battle_master
    await _patch_sheet(
        gm_client, garrik["id"],
        {"resources": [_superiority_dice_block(0, 4)]},
    )
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_disarming_attack",
        json={"character_id": garrik["id"]},
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "out_of_uses"


async def test_use_da_wrong_subclass(
    gm_client, roster,
):
    """Default Garrik (Champion) → 409."""
    garrik = roster["Garrik Ironside"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_disarming_attack",
        json={"character_id": garrik["id"]},
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "wrong_subclass_or_level"


async def test_use_da_level_gate(
    gm_client, roster,
):
    """Battle Master at Lv 2 (not 3+) → 409."""
    garrik = roster["Garrik Ironside"]
    await _patch_sheet(
        gm_client, garrik["id"],
        {
            "subclass": "Battle Master",
            "level": 2,
            "resources": [_superiority_dice_block(4, 4)],
        },
        class_slug="fighter",
    )
    try:
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/use_disarming_attack",
            json={"character_id": garrik["id"]},
        )
        assert r.status_code == 409, r.text
        data = r.json()
        assert data.get("error") == "wrong_subclass_or_level"
    finally:
        await _patch_sheet(
            gm_client, garrik["id"],
            {"subclass": "Champion", "level": 9, "resources": []},
            class_slug="fighter",
        )
