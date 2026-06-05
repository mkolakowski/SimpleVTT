"""v2.99.275 — Redemption Paladin: Emissary of Peace CD (H.2 depth).

H.2 depth — Redemption sibling CD to Rebuke the Violent. RAW
XGE p.39: bonus action; self +5 Persuasion for 10 minutes.

Tests:
  - Happy → CD 1 → 0 + persuasion_bonus 5 + broadcast.
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


def _eop_broadcasts(gm_ws, character_id):
    return [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "emissary-of-peace"
        and (m.get("data") or {}).get("character_id") == character_id
    ]


def _cd_resource(current: int, maximum: int) -> dict:
    return {
        "key": "channel-divinity",
        "name": "Channel Divinity",
        "current": current, "max": maximum, "reset": "short",
        "source": "paladin Lv 3",
        "class_slug": "paladin",
        "subclass_slug": "redemption",
        "desc": "Channel Divinity.",
        "manual": False,
    }


@pytest_asyncio.fixture
async def caelan_redemption(gm_client, roster):
    """PATCH Caelan to Redemption + seed battle + reset CD."""
    caelan = roster["Sir Caelan Lightbringer"]
    await _patch_sheet(
        gm_client, caelan["id"],
        {
            "subclass": "Oath of Redemption",
            "resources": [_cd_resource(1, 1)],
        },
        class_slug="paladin",
    )
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": [
            {"id": f"tok_eo_{caelan['id']}",
             "char_id": caelan["id"], "name": caelan["name"],
             "initiative": 12, "hp_current": 60, "hp_max": 60,
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


async def test_use_eop_happy(
    gm_client, gm_ws, caelan_redemption,
):
    """Redemption Caelan → CD 1 → 0, persuasion_bonus 5."""
    caelan = caelan_redemption
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_emissary_of_peace",
        json={"character_id": caelan["id"], "override": True},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["persuasion_bonus"] == 5
    assert data["duration_minutes"] == 10
    assert data["uses_remaining"] == 0
    await asyncio.sleep(0.3)
    feats = _eop_broadcasts(gm_ws, caelan["id"])
    assert feats


async def test_use_eop_out_of_cd(
    gm_client, caelan_redemption,
):
    """CD 0 → 409."""
    caelan = caelan_redemption
    await _patch_sheet(
        gm_client, caelan["id"],
        {"resources": [_cd_resource(0, 1)]},
    )
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_emissary_of_peace",
        json={"character_id": caelan["id"], "override": True},
    )
    assert r.status_code == 409, r.text


async def test_use_eop_wrong_subclass(
    gm_client, roster,
):
    """Default Caelan (Devotion) → 409."""
    caelan = roster["Sir Caelan Lightbringer"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_emissary_of_peace",
        json={"character_id": caelan["id"], "override": True},
    )
    assert r.status_code == 409, r.text
