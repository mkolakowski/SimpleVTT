"""v2.99.381 — Fey Wanderer Ranger: Dreadful Strike (G Ranger conclave #5, Lv 3+, TCE).

Phase G Ranger conclave subclass batch ship #5 — Fey Wanderer
opens.
RAW TCE p.60: when you hit a creature with a weapon attack, deal
+1d4 psychic (once per turn). The die grows to 1d6 at Lv 11.

v1 announce-only — the on-hit application + once-per-turn limit are
GM-tracked. The psychic damage is rolled server-side. No separate
action cost.

Rowan Quickbow (Ranger, PATCHed to Fey Wanderer Lv 5) is the demo
fixture (1d4 below Lv 11).

Tests:
  - Lv 5 happy: +1d4 psychic in [1,4].
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


def _ds_broadcasts(gm_ws, character_id):
    return [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "dreadful-strike"
        and (m.get("data") or {}).get("character_id") == character_id
    ]


@pytest_asyncio.fixture
async def rowan_fey(gm_client, roster):
    """PATCH Rowan to Fey Wanderer; restore to Hunter on teardown."""
    rowan = roster["Rowan Quickbow"]
    await _patch_sheet(
        gm_client, rowan["id"],
        {"subclass": "Fey Wanderer"},
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


async def test_use_ds_happy_lv5(
    gm_client, gm_ws, rowan_fey,
):
    """Lv 5 Fey Wanderer → +1d4 psychic in [1,4]."""
    rowan = rowan_fey
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_dreadful_strike",
        json={"character_id": rowan["id"]},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["feature"] == "dreadful-strike"
    assert data["damage_die"] == "1d4"
    assert 1 <= data["psychic_damage"] <= 4
    assert data["ranger_level"] == 5
    await asyncio.sleep(0.3)
    feats = _ds_broadcasts(gm_ws, rowan["id"])
    assert feats
    assert feats[-1]["data"]["psychic_damage"] == data["psychic_damage"]


async def test_use_ds_wrong_subclass(
    gm_client, roster,
):
    """Default Rowan (Hunter) → 409."""
    rowan = roster["Rowan Quickbow"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_dreadful_strike",
        json={"character_id": rowan["id"]},
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "wrong_subclass_or_level"


async def test_use_ds_wrong_class(
    gm_client, roster,
):
    """Caelan (Paladin) → 409."""
    caelan = roster["Sir Caelan Lightbringer"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_dreadful_strike",
        json={"character_id": caelan["id"]},
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "wrong_subclass_or_level"
