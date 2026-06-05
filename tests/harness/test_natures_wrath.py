"""v2.99.245 — Ancients Paladin: Nature's Wrath Channel Divinity (Phase H.2 Phase 1).

Phase H.2 first non-Devotion Paladin oath. RAW PHB p.86:
Ancients Paladin Lv 3+ CD — target within 10 ft makes Str or
Dex save (its choice) DC = 8 + prof + CHA mod or be Restrained
until end of next turn (repeat save each of its turns).

v1 ships:
  - /use_natures_wrath: validates Ancients Paladin Lv 3+ +
    channel-divinity resource current >= 1 + action chip.
    Decrements CD counter, marks chip, computes DC, broadcasts
    feature_used (source natures-wrath) with (target_name,
    save_ability, save_dc, uses_remaining).

Sir Caelan Lightbringer (Paladin Oath of Devotion Lv 8 default;
CHA 16 → +3 mod; prof +3) is the demo fixture. Tests PATCH his
subclass to "Oath of the Ancients" and seed him + a Bandit in
a battle. Expected DC: 8 + 3 + 3 = 14.

Tests:
  - Happy Str save → CD 1 → 0, DC 14, broadcast.
  - Dex save mode.
  - Bad save_ability (CON) → 400.
  - Out of CD uses → 409.
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


def _nw_broadcasts(gm_ws, character_id):
    return [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "natures-wrath"
        and (m.get("data") or {}).get("character_id") == character_id
    ]


def _cd_resource(current: int, maximum: int) -> dict:
    return {
        "key": "channel-divinity",
        "name": "Channel Divinity",
        "current": current, "max": maximum, "reset": "short",
        "source": "paladin Lv 3",
        "class_slug": "paladin",
        "subclass_slug": "ancients",
        "desc": "Channel a domain effect (Nature's Wrath, Turn the Faithless). One use per short rest.",
        "manual": False,
    }


@pytest_asyncio.fixture
async def caelan_ancients(gm_client, roster):
    """PATCH Caelan to Oath of the Ancients + reset CD to 1/1 +
    seed Caelan + a Bandit in a battle."""
    caelan = roster["Sir Caelan Lightbringer"]
    await _patch_sheet(
        gm_client, caelan["id"],
        {
            "subclass": "Oath of the Ancients",
            "resources": [_cd_resource(1, 1)],
        },
        class_slug="paladin",
    )
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": [
            {"id": f"tok_ca_{caelan['id']}",
             "char_id": caelan["id"], "name": caelan["name"],
             "initiative": 12, "hp_current": 60, "hp_max": 60,
             "buffs": [],
             "economy": {"action": False, "bonus": False,
                         "reaction": False, "movement": 0}},
            {"id": "tok_bandit_nw",
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


async def test_use_nw_str_happy(
    gm_client, gm_ws, caelan_ancients,
):
    """Ancients Caelan vs Bandit with STR save → DC 14, CD 1→0."""
    caelan = caelan_ancients
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_natures_wrath",
        json={
            "character_id": caelan["id"],
            "target_combatant_id": "tok_bandit_nw",
            "save_ability": "STR",
            "override": True,
        },
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["save_ability"] == "STR"
    assert data["save_dc"] == 14, data
    assert data["uses_remaining"] == 0
    await asyncio.sleep(0.3)
    feats = _nw_broadcasts(gm_ws, caelan["id"])
    assert feats


async def test_use_nw_dex_mode(
    gm_client, caelan_ancients,
):
    """Dex save mode → save_ability mirrored."""
    caelan = caelan_ancients
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_natures_wrath",
        json={
            "character_id": caelan["id"],
            "target_combatant_id": "tok_bandit_nw",
            "save_ability": "DEX",
            "override": True,
        },
    )
    assert r.status_code == 200, r.text
    assert r.json()["save_ability"] == "DEX"


async def test_use_nw_bad_save_ability(
    gm_client, caelan_ancients,
):
    """CON isn't in {STR, DEX} → 400."""
    caelan = caelan_ancients
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_natures_wrath",
        json={
            "character_id": caelan["id"],
            "target_combatant_id": "tok_bandit_nw",
            "save_ability": "CON",
            "override": True,
        },
    )
    assert r.status_code == 400, r.text


async def test_use_nw_out_of_cd(
    gm_client, caelan_ancients,
):
    """CD current=0 → 409 out_of_uses."""
    caelan = caelan_ancients
    await _patch_sheet(
        gm_client, caelan["id"],
        {"resources": [_cd_resource(0, 1)]},
    )
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_natures_wrath",
        json={
            "character_id": caelan["id"],
            "target_combatant_id": "tok_bandit_nw",
            "save_ability": "STR",
            "override": True,
        },
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "out_of_uses"


async def test_use_nw_wrong_subclass(
    gm_client, roster,
):
    """Default Caelan (Devotion) → 409 wrong_subclass_or_level."""
    caelan = roster["Sir Caelan Lightbringer"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_natures_wrath",
        json={
            "character_id": caelan["id"],
            "target_combatant_id": "tok_bandit_nw",
            "save_ability": "STR",
            "override": True,
        },
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "wrong_subclass_or_level"
