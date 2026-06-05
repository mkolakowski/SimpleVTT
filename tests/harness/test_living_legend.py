"""v2.99.291 — Glory Paladin: Living Legend (H.2 deeper, Lv 20).

H.2 Lv 20 Glory ship. RAW XGE p.38: bonus action to become an
avatar of legend for 1 minute. Advantage on CHA checks. 1/turn
(up to 4 total) turn missed weapon attack into hit. Once,
reroll a failed save as reaction. Once per long rest.

v1 announce-only — the AC bonus, miss→hit conversion, save
reroll are GM-tracked. Costs bonus chip. Auto-bootstraps a
`living-legend` resource if missing.

Tests:
  - Lv 20 happy → miss_to_hit_uses 4, save_reroll_uses 1,
    duration 1 min.
  - Wrong subclass → 409.
  - Level gate (Lv 19) → 409.
  - Long rest refills → 200 after rest.
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


def _ll_broadcasts(gm_ws, character_id):
    return [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "living-legend"
        and (m.get("data") or {}).get("character_id") == character_id
    ]


@pytest_asyncio.fixture
async def caelan_glory_lv20(gm_client, roster):
    """PATCH Caelan to Glory Lv 20 + long-rest."""
    caelan = roster["Sir Caelan Lightbringer"]
    await _patch_sheet(
        gm_client, caelan["id"],
        {"subclass": "Oath of Glory", "level": 20},
        class_slug="paladin",
    )
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{caelan['id']}/rest",
        json={"type": "long"},
    )
    try:
        yield caelan
    finally:
        await _patch_sheet(
            gm_client, caelan["id"],
            {"subclass": "Oath of Devotion", "level": 7},
            class_slug="paladin",
        )


async def test_use_ll_happy_lv20(
    gm_client, gm_ws, caelan_glory_lv20,
):
    """Lv 20 Glory → 4 miss→hit, 1 save reroll, 1 min."""
    caelan = caelan_glory_lv20
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_living_legend",
        json={"character_id": caelan["id"], "override": True},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["miss_to_hit_uses"] == 4
    assert data["save_reroll_uses"] == 1
    assert data["duration_minutes"] == 1
    assert data["uses_remaining"] == 0
    assert data["paladin_level"] == 20
    await asyncio.sleep(0.3)
    feats = _ll_broadcasts(gm_ws, caelan["id"])
    assert feats


async def test_use_ll_wrong_subclass(
    gm_client, roster,
):
    """Default Caelan (Devotion Lv 7) → 409."""
    caelan = roster["Sir Caelan Lightbringer"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_living_legend",
        json={"character_id": caelan["id"], "override": True},
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "wrong_subclass_or_level"


async def test_use_ll_level_gate(
    gm_client, roster,
):
    """Glory Caelan at Lv 19 → 409."""
    caelan = roster["Sir Caelan Lightbringer"]
    await _patch_sheet(
        gm_client, caelan["id"],
        {"subclass": "Oath of Glory", "level": 19},
        class_slug="paladin",
    )
    try:
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/use_living_legend",
            json={"character_id": caelan["id"], "override": True},
        )
        assert r.status_code == 409, r.text
        data = r.json()
        assert data.get("error") == "wrong_subclass_or_level"
    finally:
        await _patch_sheet(
            gm_client, caelan["id"],
            {"subclass": "Oath of Devotion", "level": 7},
            class_slug="paladin",
        )


async def test_use_ll_long_rest_refills(
    gm_client, caelan_glory_lv20,
):
    """Use → long rest → use again → 200."""
    caelan = caelan_glory_lv20
    r1 = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_living_legend",
        json={"character_id": caelan["id"], "override": True},
    )
    assert r1.status_code == 200, r1.text
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{caelan['id']}/rest",
        json={"type": "long"},
    )
    r2 = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_living_legend",
        json={"character_id": caelan["id"], "override": True},
    )
    assert r2.status_code == 200, r2.text
    data = r2.json()
    assert data["uses_remaining"] == 0
