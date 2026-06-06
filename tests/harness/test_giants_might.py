"""v2.99.372 — Rune Knight Fighter: Giant's Might (G Fighter sweep #3, Lv 3+, TCE).

Phase G Fighter martial archetype sweep ship #3 — Rune Knight
opens.
RAW TCE p.45: as a bonus action, become Large for 1 min, gain
advantage on STR checks/saves, and once per turn a weapon/unarmed
hit deals +1d6 damage (grows to 1d8 at Lv 10, 1d10 at Lv 18).
Usable PB times per long rest.

v2.99.389 — Phase 1 of docs/plans/full-feature-automation.md: the
PB-per-long-rest budget is now server-tracked via the feature-use
registry (`sheet.giants_might_uses`, computed max = proficiency
bonus): each use decrements, a depleted budget returns 409
`out_of_uses`, and the /rest hook refills it. The Large size, STR
advantage, and once-per-turn bonus damage stay GM-tracked pending
the Phase 2/4 primitives. Bonus chip.

Garrik Ironside (Fighter, PATCHed to Rune Knight Lv 9) is the demo
fixture (bonus die 1d6 below Lv 10; PB 4 → 4 uses).

Tests:
  - Lv 9 happy: size Large, +1d6, STR advantage, uses 4→3 (PB).
  - Exhausted budget (giants_might_uses=0) → 409 out_of_uses.
  - Long-rest refill: exhaust → /rest long → refills to PB (4).
  - Wrong subclass (default Champion) → 409.
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


def _gm_broadcasts(gm_ws, character_id):
    return [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "giants-might"
        and (m.get("data") or {}).get("character_id") == character_id
    ]


@pytest_asyncio.fixture
async def garrik_rune(gm_client, roster):
    """PATCH Garrik to Rune Knight + seed the PB (4) use budget; restore
    to Champion on teardown."""
    garrik = roster["Garrik Ironside"]
    await _patch_sheet(
        gm_client, garrik["id"],
        {"subclass": "Rune Knight", "giants_might_uses": 4},
        class_slug="fighter",
    )
    try:
        yield garrik
    finally:
        await _patch_sheet(
            gm_client, garrik["id"],
            {"subclass": "Champion"},
            class_slug="fighter",
        )


async def test_use_gm_happy_lv9(
    gm_client, gm_ws, garrik_rune,
):
    """Lv 9 Rune Knight → Large, +1d6, STR advantage, uses 4→3 (PB)."""
    garrik = garrik_rune
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_giants_might",
        json={"character_id": garrik["id"], "override": True},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["feature"] == "giants-might"
    assert data["size"] == "Large"
    assert data["str_advantage"] is True
    assert data["bonus_damage_die"] == "1d6"
    assert data["duration_minutes"] == 1
    assert data["uses_max"] == 4  # proficiency bonus at Lv 9
    assert data["uses_remaining"] == 3
    assert data["fighter_level"] == 9
    await asyncio.sleep(0.3)
    feats = _gm_broadcasts(gm_ws, garrik["id"])
    assert feats
    assert feats[-1]["data"]["uses_remaining"] == 3


async def test_use_gm_out_of_uses(
    gm_client, roster,
):
    """Rune Knight with an exhausted budget (0 uses) → 409 out_of_uses."""
    garrik = roster["Garrik Ironside"]
    await _patch_sheet(
        gm_client, garrik["id"],
        {"subclass": "Rune Knight", "giants_might_uses": 0},
        class_slug="fighter",
    )
    try:
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/use_giants_might",
            json={"character_id": garrik["id"], "override": True},
        )
        assert r.status_code == 409, r.text
        data = r.json()
        assert data.get("error") == "out_of_uses"
        assert data.get("uses_remaining") == 0
    finally:
        await _patch_sheet(
            gm_client, garrik["id"],
            {"subclass": "Champion"},
            class_slug="fighter",
        )


async def test_gm_long_rest_refill(
    gm_client, roster,
):
    """Exhausted Giant's Might refills to PB (4) on a long rest — via the
    feature-use registry (computed max_fn)."""
    garrik = roster["Garrik Ironside"]
    await _patch_sheet(
        gm_client, garrik["id"],
        {"subclass": "Rune Knight", "giants_might_uses": 0},
        class_slug="fighter",
    )
    try:
        url = f"/api/campaign/{CAMPAIGN_ID}/use_giants_might"
        rest_url = (
            f"/api/campaign/{CAMPAIGN_ID}/character/{garrik['id']}/rest"
        )
        r0 = await gm_client.post(url, json={
            "character_id": garrik["id"], "override": True})
        assert r0.status_code == 409, r0.text

        lr = await gm_client.post(rest_url, json={"type": "long"})
        assert lr.status_code == 200, lr.text
        r1 = await gm_client.post(url, json={
            "character_id": garrik["id"], "override": True})
        assert r1.status_code == 200, r1.text
        data = r1.json()
        assert data["uses_max"] == 4
        assert data["uses_remaining"] == 3  # refilled to 4, spent 1
    finally:
        await _patch_sheet(
            gm_client, garrik["id"],
            {"subclass": "Champion"},
            class_slug="fighter",
        )


async def test_use_gm_wrong_subclass(
    gm_client, roster,
):
    """Default Garrik (Champion) → 409."""
    garrik = roster["Garrik Ironside"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_giants_might",
        json={"character_id": garrik["id"], "override": True},
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "wrong_subclass_or_level"


async def test_use_gm_wrong_class(
    gm_client, roster,
):
    """Caelan (Paladin) → 409."""
    caelan = roster["Sir Caelan Lightbringer"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_giants_might",
        json={"character_id": caelan["id"], "override": True},
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "wrong_subclass_or_level"
