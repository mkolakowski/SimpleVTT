"""v2.99.377 — Gloom Stalker Ranger: Dread Ambusher (G Ranger conclave OPEN, Lv 3+, XGE).

Phase G Ranger conclave subclass batch OPEN — Gloom Stalker is the
first new conclave beyond the already-wired Hunter (Colossus Slayer).
RAW XGE p.42: +WIS modifier to initiative; at the start of your
first turn, +10 ft speed and (on a first-turn Attack action) one
extra weapon attack that deals +1d8 on a hit.

v1 announce-only — the initiative bonus, speed boost, and extra
attack are GM-tracked. The WIS init bonus + 1d8 ambush damage are
computed server-side. No separate action cost.

Rowan Quickbow (Ranger, PATCHed to Gloom Stalker Lv 5) is the demo
fixture.

Tests:
  - Lv 5 happy: init bonus = WIS mod, ambush 1d8 in [1,8], speed 10.
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


def _da_broadcasts(gm_ws, character_id):
    return [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "dread-ambusher"
        and (m.get("data") or {}).get("character_id") == character_id
    ]


@pytest_asyncio.fixture
async def rowan_gloom(gm_client, roster):
    """PATCH Rowan to Gloom Stalker; restore to Hunter on teardown."""
    rowan = roster["Rowan Quickbow"]
    await _patch_sheet(
        gm_client, rowan["id"],
        {"subclass": "Gloom Stalker"},
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


async def test_use_da_happy_lv5(
    gm_client, gm_ws, rowan_gloom,
):
    """Lv 5 Gloom Stalker → WIS init bonus, 1d8 ambush, +10 speed."""
    rowan = rowan_gloom
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_dread_ambusher",
        json={"character_id": rowan["id"]},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["feature"] == "dread-ambusher"
    assert data["ambush_damage_die"] == "1d8"
    assert 1 <= data["ambush_damage"] <= 8
    assert data["speed_bonus_ft"] == 10
    assert isinstance(data["initiative_bonus"], int)
    assert data["ranger_level"] == 5
    await asyncio.sleep(0.3)
    feats = _da_broadcasts(gm_ws, rowan["id"])
    assert feats
    assert feats[-1]["data"]["ambush_damage"] == data["ambush_damage"]


async def test_use_da_wrong_subclass(
    gm_client, roster,
):
    """Default Rowan (Hunter) → 409."""
    rowan = roster["Rowan Quickbow"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_dread_ambusher",
        json={"character_id": rowan["id"]},
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "wrong_subclass_or_level"


async def test_use_da_wrong_class(
    gm_client, roster,
):
    """Caelan (Paladin) → 409."""
    caelan = roster["Sir Caelan Lightbringer"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_dread_ambusher",
        json={"character_id": caelan["id"]},
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "wrong_subclass_or_level"
