"""v2.99.314 — Land Druid: Natural Recovery (E.4 batch, Lv 2+).

E.4 Druid ship #2 (second Land Druid feature). RAW PHB p.68:
during a short rest, recover spell slots totaling ceil(druid
level / 2) levels (max slot level 5). Once per long rest.

v1 announce-only — actual spell-slot refund is GM-tracked.
Auto-bootstraps `natural-recovery` resource (max=1,
reset=long); refilled by long rest.

Mira Lv 5 → recoverable_level_pool = ceil(5 / 2) = 3.

Tests:
  - Lv 5 Land happy → pool 3, max slot 5.
  - Wrong subclass → 409.
  - Lv 1 gate → 409.
  - Back-to-back → 409 no_uses_left.
  - Long rest refills → 200.
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


def _nr_broadcasts(gm_ws, character_id):
    return [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "natural-recovery"
        and (m.get("data") or {}).get("character_id") == character_id
    ]


@pytest_asyncio.fixture
async def mira_land_lv5_fresh(gm_client, roster):
    """PATCH Mira to Land + long-rest to refill NR pool."""
    mira = roster["Mira Greenleaf"]
    await _patch_sheet(
        gm_client, mira["id"],
        {"subclass": "Circle of the Land"},
        class_slug="druid",
    )
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{mira['id']}/rest",
        json={"type": "long"},
    )
    try:
        yield mira
    finally:
        await _patch_sheet(
            gm_client, mira["id"],
            {"subclass": "Circle of the Moon", "level": 5},
            class_slug="druid",
        )


async def test_use_nr_happy_lv5(
    gm_client, gm_ws, mira_land_lv5_fresh,
):
    """Lv 5 Land → pool 3 (=ceil(5/2)), max slot 5."""
    mira = mira_land_lv5_fresh
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_natural_recovery",
        json={"character_id": mira["id"]},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["recoverable_level_pool"] == 3
    assert data["max_slot_level"] == 5
    assert data["uses_remaining"] == 0
    assert data["druid_level"] == 5
    await asyncio.sleep(0.3)
    feats = _nr_broadcasts(gm_ws, mira["id"])
    assert feats


async def test_use_nr_wrong_subclass(
    gm_client, roster,
):
    """Default Mira (Moon) → 409."""
    mira = roster["Mira Greenleaf"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_natural_recovery",
        json={"character_id": mira["id"]},
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "wrong_subclass_or_level"


async def test_use_nr_level_gate(
    gm_client, roster,
):
    """Land Mira at Lv 1 → 409."""
    mira = roster["Mira Greenleaf"]
    await _patch_sheet(
        gm_client, mira["id"],
        {"subclass": "Circle of the Land", "level": 1},
        class_slug="druid",
    )
    try:
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/use_natural_recovery",
            json={"character_id": mira["id"]},
        )
        assert r.status_code == 409, r.text
        data = r.json()
        assert data.get("error") == "wrong_subclass_or_level"
    finally:
        await _patch_sheet(
            gm_client, mira["id"],
            {"subclass": "Circle of the Moon", "level": 5},
            class_slug="druid",
        )


async def test_use_nr_out_of_uses(
    gm_client, mira_land_lv5_fresh,
):
    """Second back-to-back → 409 no_uses_left."""
    mira = mira_land_lv5_fresh
    r1 = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_natural_recovery",
        json={"character_id": mira["id"]},
    )
    assert r1.status_code == 200, r1.text
    r2 = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_natural_recovery",
        json={"character_id": mira["id"]},
    )
    assert r2.status_code == 409, r2.text
    data = r2.json()
    assert data.get("error") == "no_uses_left"


async def test_use_nr_long_rest_refills(
    gm_client, mira_land_lv5_fresh,
):
    """Use → long rest → use again → 200."""
    mira = mira_land_lv5_fresh
    r1 = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_natural_recovery",
        json={"character_id": mira["id"]},
    )
    assert r1.status_code == 200, r1.text
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{mira['id']}/rest",
        json={"type": "long"},
    )
    r2 = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_natural_recovery",
        json={"character_id": mira["id"]},
    )
    assert r2.status_code == 200, r2.text
    data = r2.json()
    assert data["uses_remaining"] == 0
