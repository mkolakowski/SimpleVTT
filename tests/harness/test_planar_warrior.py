"""v2.99.382 — Horizon Walker Ranger: Planar Warrior (G Ranger conclave CLOSE, Lv 3+, XGE).

Phase G Ranger conclave subclass batch ship #7 — Horizon Walker
opens and CLOSES the Ranger conclave batch.
RAW XGE p.42: as a bonus action, mark a creature within 30 ft; the
next weapon hit this turn deals all its damage as force, plus an
extra 1d8 force (2d8 at Lv 11).

v1 announce-only — the damage-type conversion + on-hit application
are GM-tracked. The extra force damage is rolled server-side. Bonus
chip.

Rowan Quickbow (Ranger, PATCHed to Horizon Walker Lv 5) is the demo
fixture (1d8 below Lv 11).

Tests:
  - Lv 5 happy: +1d8 force in [1,8], range 30, converts to force.
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


def _pw_broadcasts(gm_ws, character_id):
    return [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "planar-warrior"
        and (m.get("data") or {}).get("character_id") == character_id
    ]


@pytest_asyncio.fixture
async def rowan_horizon(gm_client, roster):
    """PATCH Rowan to Horizon Walker; restore to Hunter on teardown."""
    rowan = roster["Rowan Quickbow"]
    await _patch_sheet(
        gm_client, rowan["id"],
        {"subclass": "Horizon Walker"},
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


async def test_use_pw_happy_lv5(
    gm_client, gm_ws, rowan_horizon,
):
    """Lv 5 Horizon Walker → +1d8 force in [1,8], range 30."""
    rowan = rowan_horizon
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_planar_warrior",
        json={"character_id": rowan["id"], "override": True},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["feature"] == "planar-warrior"
    assert data["force_damage_dice"] == "1d8"
    assert 1 <= data["force_damage"] <= 8
    assert data["range_ft"] == 30
    assert data["converts_to_force"] is True
    assert data["ranger_level"] == 5
    await asyncio.sleep(0.3)
    feats = _pw_broadcasts(gm_ws, rowan["id"])
    assert feats
    assert feats[-1]["data"]["force_damage"] == data["force_damage"]


async def test_use_pw_wrong_subclass(
    gm_client, roster,
):
    """Default Rowan (Hunter) → 409."""
    rowan = roster["Rowan Quickbow"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_planar_warrior",
        json={"character_id": rowan["id"], "override": True},
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "wrong_subclass_or_level"


async def test_use_pw_wrong_class(
    gm_client, roster,
):
    """Caelan (Paladin) → 409."""
    caelan = roster["Sir Caelan Lightbringer"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_planar_warrior",
        json={"character_id": caelan["id"], "override": True},
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "wrong_subclass_or_level"
