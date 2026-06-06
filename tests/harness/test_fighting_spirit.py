"""v2.99.370 — Samurai Fighter: Fighting Spirit (G Fighter sweep OPEN, Lv 3+, XGE).

Phase G Fighter martial archetype sweep — Samurai is the first new
archetype beyond Champion / Battle Master / Eldritch Knight.
RAW XGE p.31: as a bonus action, give yourself advantage on weapon
attack rolls until the end of the turn and gain temp HP (5, rising
to 10 at Lv 10, 15 at Lv 15). 3 uses per long rest.

v2.99.387 — Phase 1 of docs/plans/full-feature-automation.md: the
3-per-long-rest budget is now server-tracked via the feature-use
registry (`sheet.fighting_spirit_uses`): each use decrements, a
depleted budget returns 409 `out_of_uses`, and the /rest hook
refills it. The advantage + temp-HP application stay GM-tracked
pending the Phase 4 temp-HP primitive. Bonus chip.

Garrik Ironside (Fighter, PATCHed to Samurai Lv 9) is the demo
fixture (temp HP 5 below Lv 10).

Tests:
  - Lv 9 happy: advantage flag True, temp_hp 5, uses 3→2.
  - Exhausted budget (fighting_spirit_uses=0) → 409 out_of_uses.
  - Long-rest refill: exhaust → /rest long → works again.
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


def _fs_broadcasts(gm_ws, character_id):
    return [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "fighting-spirit"
        and (m.get("data") or {}).get("character_id") == character_id
    ]


@pytest_asyncio.fixture
async def garrik_samurai(gm_client, roster):
    """PATCH Garrik to Samurai + seed the 3-use budget; restore to
    Champion on teardown."""
    garrik = roster["Garrik Ironside"]
    await _patch_sheet(
        gm_client, garrik["id"],
        {"subclass": "Samurai", "fighting_spirit_uses": 3},
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


async def test_use_fs_happy_lv9(
    gm_client, gm_ws, garrik_samurai,
):
    """Lv 9 Samurai → advantage + 5 temp HP, uses 3→2 (server-tracked)."""
    garrik = garrik_samurai
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_fighting_spirit",
        json={"character_id": garrik["id"], "override": True},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["feature"] == "fighting-spirit"
    assert data["advantage_on_weapon_attacks"] is True
    assert data["temp_hp"] == 5
    assert data["uses_max"] == 3
    assert data["uses_remaining"] == 2
    assert data["fighter_level"] == 9
    await asyncio.sleep(0.3)
    feats = _fs_broadcasts(gm_ws, garrik["id"])
    assert feats
    assert feats[-1]["data"]["uses_remaining"] == 2


async def test_use_fs_out_of_uses(
    gm_client, roster,
):
    """Samurai with an exhausted budget (0 uses) → 409 out_of_uses."""
    garrik = roster["Garrik Ironside"]
    await _patch_sheet(
        gm_client, garrik["id"],
        {"subclass": "Samurai", "fighting_spirit_uses": 0},
        class_slug="fighter",
    )
    try:
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/use_fighting_spirit",
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


async def test_fs_long_rest_refill(
    gm_client, roster,
):
    """Exhausted Fighting Spirit refills to 3 on a long rest (the
    feature-use registry refill path)."""
    garrik = roster["Garrik Ironside"]
    await _patch_sheet(
        gm_client, garrik["id"],
        {"subclass": "Samurai", "fighting_spirit_uses": 0},
        class_slug="fighter",
    )
    try:
        url = f"/api/campaign/{CAMPAIGN_ID}/use_fighting_spirit"
        rest_url = (
            f"/api/campaign/{CAMPAIGN_ID}/character/{garrik['id']}/rest"
        )
        # Exhausted → 409.
        r0 = await gm_client.post(url, json={
            "character_id": garrik["id"], "override": True})
        assert r0.status_code == 409, r0.text

        # Long rest refills the budget to 3.
        lr = await gm_client.post(rest_url, json={"type": "long"})
        assert lr.status_code == 200, lr.text
        r1 = await gm_client.post(url, json={
            "character_id": garrik["id"], "override": True})
        assert r1.status_code == 200, r1.text
        assert r1.json()["uses_remaining"] == 2  # refilled to 3, spent 1
    finally:
        await _patch_sheet(
            gm_client, garrik["id"],
            {"subclass": "Champion"},
            class_slug="fighter",
        )


async def test_use_fs_wrong_subclass(
    gm_client, roster,
):
    """Default Garrik (Champion) → 409."""
    garrik = roster["Garrik Ironside"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_fighting_spirit",
        json={"character_id": garrik["id"], "override": True},
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "wrong_subclass_or_level"


async def test_use_fs_wrong_class(
    gm_client, roster,
):
    """Caelan (Paladin) → 409."""
    caelan = roster["Sir Caelan Lightbringer"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_fighting_spirit",
        json={"character_id": caelan["id"], "override": True},
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "wrong_subclass_or_level"
