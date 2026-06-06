"""v2.99.360 — Way of the Drunken Master Monk: Drunken Technique (G Monk batch #6, Lv 3+, XGE).

Phase G Monk Ways subclass batch ship #6 — Way of the Drunken
Master opens.
RAW XGE p.33: whenever you use Flurry of Blows, you gain the
benefit of the Disengage action and your walking speed increases
by 10 ft until the end of the current turn.

v1 announce-only — the Disengage benefit + speed boost are
GM-tracked. No additional action cost (an automatic rider on
Flurry of Blows).

Kael Brightleaf (Monk, PATCHed to Way of the Drunken Master Lv 7)
is the demo fixture.

Tests:
  - Lv 7 happy: disengage True, speed_bonus_ft 10, broadcast fires.
  - Wrong subclass (default Way of the Open Hand) → 409.
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


def _dt_broadcasts(gm_ws, character_id):
    return [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "drunken-technique"
        and (m.get("data") or {}).get("character_id") == character_id
    ]


@pytest_asyncio.fixture
async def kael_drunken(gm_client, roster):
    """PATCH Kael to Way of the Drunken Master; restore to Open Hand."""
    kael = roster["Kael Brightleaf"]
    await _patch_sheet(
        gm_client, kael["id"],
        {"subclass": "Way of the Drunken Master"},
        class_slug="monk",
    )
    try:
        yield kael
    finally:
        await _patch_sheet(
            gm_client, kael["id"],
            {"subclass": "Way of the Open Hand"},
            class_slug="monk",
        )


async def test_use_dt_happy_lv7(
    gm_client, gm_ws, kael_drunken,
):
    """Lv 7 Drunken Master → disengage True, +10 ft speed."""
    kael = kael_drunken
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_drunken_technique",
        json={"character_id": kael["id"]},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["feature"] == "drunken-technique"
    assert data["disengage"] is True
    assert data["speed_bonus_ft"] == 10
    assert data["monk_level"] == 7
    await asyncio.sleep(0.3)
    feats = _dt_broadcasts(gm_ws, kael["id"])
    assert feats
    assert feats[-1]["data"]["speed_bonus_ft"] == 10


async def test_use_dt_wrong_subclass(
    gm_client, roster,
):
    """Default Kael (Way of the Open Hand) → 409."""
    kael = roster["Kael Brightleaf"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_drunken_technique",
        json={"character_id": kael["id"]},
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "wrong_subclass_or_level"


async def test_use_dt_wrong_class(
    gm_client, roster,
):
    """Caelan (Paladin) → 409."""
    caelan = roster["Sir Caelan Lightbringer"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_drunken_technique",
        json={"character_id": caelan["id"]},
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "wrong_subclass_or_level"
