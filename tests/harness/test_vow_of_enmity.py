"""v2.99.246 — Vengeance Paladin: Vow of Enmity CD (Phase H.2 second oath).

Phase H.2 second non-Devotion Paladin oath. RAW PHB p.87:
Vengeance Paladin Lv 3+ bonus action CD — utter a vow against
a target within 10 ft you can see. Advantage on attacks vs
target for 1 min or until target drops to 0 HP.

v1 ships:
  - /use_vow_of_enmity: validates Vengeance Paladin Lv 3+ +
    channel-divinity resource current >= 1 + bonus chip + target
    in battle. Decrements CD, installs vow-of-enmity-active
    buff on caster (attack_advantage_vs_target_combatant_id),
    marks chip, broadcasts.

Sir Caelan Lightbringer is the demo fixture. Tests PATCH his
subclass to "Oath of Vengeance" + seed CD + Bandit target in
battle.

Tests:
  - Happy → CD 1 → 0, buff installed, broadcast.
  - Target not in battle → 404.
  - Out of CD → 409.
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


def _voe_broadcasts(gm_ws, character_id):
    return [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "vow-of-enmity"
        and (m.get("data") or {}).get("character_id") == character_id
    ]


def _cd_resource(current: int, maximum: int) -> dict:
    return {
        "key": "channel-divinity",
        "name": "Channel Divinity",
        "current": current, "max": maximum, "reset": "short",
        "source": "paladin Lv 3",
        "class_slug": "paladin",
        "subclass_slug": "vengeance",
        "desc": "Channel a domain effect (Abjure Enemy, Vow of Enmity). One use per short rest.",
        "manual": False,
    }


@pytest_asyncio.fixture
async def caelan_vengeance_with_bandit(gm_client, roster):
    """PATCH Caelan to Vengeance + reset CD + seed battle."""
    caelan = roster["Sir Caelan Lightbringer"]
    await _patch_sheet(
        gm_client, caelan["id"],
        {
            "subclass": "Oath of Vengeance",
            "resources": [_cd_resource(1, 1)],
        },
        class_slug="paladin",
    )
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": [
            {"id": f"tok_cv_{caelan['id']}",
             "char_id": caelan["id"], "name": caelan["name"],
             "initiative": 12, "hp_current": 60, "hp_max": 60,
             "buffs": [],
             "economy": {"action": False, "bonus": False,
                         "reaction": False, "movement": 0}},
            {"id": "tok_bandit_voe",
             "char_id": None,
             "name": "Bandit Alpha", "initiative": 8,
             "hp_current": 50, "hp_max": 50,
             "buffs": [],
             "economy": {"action": False, "bonus": False,
                         "reaction": False, "movement": 0}},
        ], "turn_index": 0, "round": 1, "active": True},
    )
    try:
        yield caelan
    finally:
        await _patch_sheet(
            gm_client, caelan["id"],
            {"subclass": "Oath of Devotion", "resources": []},
            class_slug="paladin",
        )


async def test_use_voe_happy(
    gm_client, gm_ws, caelan_vengeance_with_bandit,
):
    """Vengeance Caelan vs Bandit → CD 1 → 0, buff installed."""
    caelan = caelan_vengeance_with_bandit
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_vow_of_enmity",
        json={
            "character_id": caelan["id"],
            "target_combatant_id": "tok_bandit_voe",
            "override": True,
        },
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["uses_remaining"] == 0
    assert data["buff_installed"] is True
    assert data["target_name"] == "Bandit Alpha"
    await asyncio.sleep(0.3)
    feats = _voe_broadcasts(gm_ws, caelan["id"])
    assert feats


async def test_use_voe_target_not_in_battle(
    gm_client, caelan_vengeance_with_bandit,
):
    """Unknown target → 404."""
    caelan = caelan_vengeance_with_bandit
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_vow_of_enmity",
        json={
            "character_id": caelan["id"],
            "target_combatant_id": "tok_ghost",
            "override": True,
        },
    )
    assert r.status_code == 404, r.text


async def test_use_voe_out_of_cd(
    gm_client, caelan_vengeance_with_bandit,
):
    """CD current=0 → 409 out_of_uses."""
    caelan = caelan_vengeance_with_bandit
    await _patch_sheet(
        gm_client, caelan["id"],
        {"resources": [_cd_resource(0, 1)]},
    )
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_vow_of_enmity",
        json={
            "character_id": caelan["id"],
            "target_combatant_id": "tok_bandit_voe",
            "override": True,
        },
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "out_of_uses"


async def test_use_voe_wrong_subclass(
    gm_client, roster,
):
    """Default Caelan (Devotion) → 409 wrong_subclass_or_level."""
    caelan = roster["Sir Caelan Lightbringer"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_vow_of_enmity",
        json={
            "character_id": caelan["id"],
            "target_combatant_id": "tok_bandit_voe",
            "override": True,
        },
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "wrong_subclass_or_level"
