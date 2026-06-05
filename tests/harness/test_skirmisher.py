"""v2.99.309 — Scout Rogue: Skirmisher (E.3 batch, Lv 3+).

E.3 Rogue subclass ship #5. RAW XGE p.46: reaction to move
up to half walking speed when enemy ends turn within 5 ft;
movement doesn't provoke OAs.

v1 announce-only — actual half-speed-no-OA move is GM-tracked.
Costs reaction chip.

Pip (Thief Lv 7, halfling speed 25) PATCH'd to Scout.

Tests:
  - Lv 3+ happy → bonus_move_ft 12 (=25//2), no_oa True.
  - Default Pip (Thief) → 409.
  - Scout Lv 2 → 409.
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


def _sk_broadcasts(gm_ws, character_id):
    return [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "skirmisher"
        and (m.get("data") or {}).get("character_id") == character_id
    ]


@pytest_asyncio.fixture
async def pip_scout(gm_client, roster):
    """PATCH Pip to Scout subclass."""
    pip = roster["Pip Quickfingers"]
    await _patch_sheet(
        gm_client, pip["id"],
        {"subclass": "Scout"},
        class_slug="rogue",
    )
    try:
        yield pip
    finally:
        await _patch_sheet(
            gm_client, pip["id"],
            {"subclass": "Thief", "level": 7},
            class_slug="rogue",
        )


async def test_use_sk_happy_lv7(
    gm_client, gm_ws, pip_scout,
):
    """Lv 7 Scout (halfling speed 25) → bonus_move_ft 12, no_oa True."""
    pip = pip_scout
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_skirmisher",
        json={"character_id": pip["id"], "override": True},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["bonus_move_ft"] == 12
    assert data["base_speed"] == 25
    assert data["no_oa"] is True
    assert data["rogue_level"] == 7
    await asyncio.sleep(0.3)
    feats = _sk_broadcasts(gm_ws, pip["id"])
    assert feats


async def test_use_sk_wrong_subclass(
    gm_client, roster,
):
    """Default Pip (Thief) → 409."""
    pip = roster["Pip Quickfingers"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_skirmisher",
        json={"character_id": pip["id"], "override": True},
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "wrong_subclass_or_level"


async def test_use_sk_level_gate(
    gm_client, roster,
):
    """Scout Pip at Lv 2 → 409."""
    pip = roster["Pip Quickfingers"]
    await _patch_sheet(
        gm_client, pip["id"],
        {"subclass": "Scout", "level": 2},
        class_slug="rogue",
    )
    try:
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/use_skirmisher",
            json={"character_id": pip["id"], "override": True},
        )
        assert r.status_code == 409, r.text
        data = r.json()
        assert data.get("error") == "wrong_subclass_or_level"
    finally:
        await _patch_sheet(
            gm_client, pip["id"],
            {"subclass": "Thief", "level": 7},
            class_slug="rogue",
        )
