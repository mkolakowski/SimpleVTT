"""v2.99.379 — Monster Slayer Ranger: Slayer's Prey (G Ranger conclave #3, Lv 3+, XGE).

Phase G Ranger conclave subclass batch ship #3 — Monster Slayer
opens.
RAW XGE p.43: as a bonus action, designate a creature within 60 ft
as your prey; the first weapon hit each turn deals +1d6 to it until
you rest or mark a new target.

v1 announce-only — the target designation + once-per-turn on-hit
application are GM-tracked. The 1d6 is rolled server-side. Bonus
chip.

Rowan Quickbow (Ranger, PATCHed to Monster Slayer Lv 5) is the demo
fixture.

Tests:
  - Lv 5 happy: bonus damage 1d6 in [1,6], range 60.
  - Wrong subclass (default Hunter) → 409.
  - Wrong class (Caelan paladin) → 409.
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


def _sp_broadcasts(gm_ws, character_id):
    return [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "slayers-prey"
        and (m.get("data") or {}).get("character_id") == character_id
    ]


@pytest_asyncio.fixture
async def rowan_slayer(gm_client, roster):
    """PATCH Rowan to Monster Slayer; restore to Hunter on teardown."""
    rowan = roster["Rowan Quickbow"]
    await _patch_sheet(
        gm_client, rowan["id"],
        {"subclass": "Monster Slayer"},
        class_slug="ranger",
    )
    try:
        yield rowan
    finally:
        await _patch_sheet(
            gm_client, rowan["id"],
            {"subclass": "Hunter"},
            class_slug="ranger",
        )


async def test_use_sp_happy_lv5(
    gm_client, gm_ws, rowan_slayer,
):
    """Lv 5 Monster Slayer → +1d6 in [1,6], range 60."""
    rowan = rowan_slayer
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_slayers_prey",
        json={"character_id": rowan["id"], "override": True},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["feature"] == "slayers-prey"
    assert data["bonus_damage_die"] == "1d6"
    assert 1 <= data["bonus_damage"] <= 6
    assert data["range_ft"] == 60
    assert data["ranger_level"] == 5
    await asyncio.sleep(0.3)
    feats = _sp_broadcasts(gm_ws, rowan["id"])
    assert feats
    assert feats[-1]["data"]["bonus_damage"] == data["bonus_damage"]


async def test_use_sp_wrong_subclass(
    gm_client, roster,
):
    """Default Rowan (Hunter) → 409."""
    rowan = roster["Rowan Quickbow"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_slayers_prey",
        json={"character_id": rowan["id"], "override": True},
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "wrong_subclass_or_level"


async def test_use_sp_wrong_class(
    gm_client, roster,
):
    """Caelan (Paladin) → 409."""
    caelan = roster["Sir Caelan Lightbringer"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_slayers_prey",
        json={"character_id": caelan["id"], "override": True},
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "wrong_subclass_or_level"
