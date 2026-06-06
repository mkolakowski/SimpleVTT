"""v2.99.363 — Way of the Long Death Monk: Touch of Death (G Monk batch CLOSE, Lv 3+, SCAG).

Phase G Monk Ways subclass batch ship #9 — Way of the Long Death
opens and CLOSES the Monk Ways batch.
RAW SCAG p.130: when you reduce a creature within 5 ft to 0 HP,
gain temporary HP = your WIS modifier + your monk level (minimum
of 1).

v1 announce-only — the kill trigger + temp-HP application are
GM-tracked. The temp-HP amount is computed server-side. No action
cost.

Kael Brightleaf (Monk, PATCHed to Way of the Long Death Lv 7) is
the demo fixture.

Tests:
  - Lv 7 happy: temp_hp = max(1, WIS mod + 7), broadcast fires.
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


def _td_broadcasts(gm_ws, character_id):
    return [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "touch-of-death"
        and (m.get("data") or {}).get("character_id") == character_id
    ]


@pytest_asyncio.fixture
async def kael_long_death(gm_client, roster):
    """PATCH Kael to Way of the Long Death; restore to Open Hand."""
    kael = roster["Kael Brightleaf"]
    await _patch_sheet(
        gm_client, kael["id"],
        {"subclass": "Way of the Long Death"},
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


async def test_use_tod_happy_lv7(
    gm_client, gm_ws, kael_long_death,
):
    """Lv 7 Long Death → temp_hp = max(1, WIS mod + 7)."""
    kael = kael_long_death
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_touch_of_death",
        json={"character_id": kael["id"]},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["feature"] == "touch-of-death"
    assert data["monk_level"] == 7
    assert data["temp_hp"] == max(1, data["wis_mod"] + data["monk_level"])
    assert data["temp_hp"] >= 1
    await asyncio.sleep(0.3)
    feats = _td_broadcasts(gm_ws, kael["id"])
    assert feats
    assert feats[-1]["data"]["temp_hp"] == data["temp_hp"]


async def test_use_tod_wrong_subclass(
    gm_client, roster,
):
    """Default Kael (Way of the Open Hand) → 409."""
    kael = roster["Kael Brightleaf"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_touch_of_death",
        json={"character_id": kael["id"]},
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "wrong_subclass_or_level"


async def test_use_tod_wrong_class(
    gm_client, roster,
):
    """Caelan (Paladin) → 409."""
    caelan = roster["Sir Caelan Lightbringer"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_touch_of_death",
        json={"character_id": caelan["id"]},
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "wrong_subclass_or_level"


async def test_tod_applies_temp_hp(
    gm_client, gm_ws, kael_long_death,
):
    """v2.99.418 — Phase 4.2: Touch of Death applies the temp HP to the
    monk's sheet via _grant_temp_hp.

    Long-rest first (temp → 0), then assert the grant via the
    character_hp_update broadcast (hp.temp + temp_delta).
    """
    kael = kael_long_death
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{kael['id']}/rest",
        json={"type": "long"},
    )
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_touch_of_death",
        json={"character_id": kael["id"]},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    temp = data["temp_hp"]
    assert temp >= 1
    assert data["temp_hp_applied"] is True

    bu = await gm_ws.wait_for("character_hp_update")
    assert bu["data"]["character_id"] == kael["id"]
    assert int(bu["data"]["hp"].get("temp") or 0) == temp
    assert int(bu["data"].get("temp_delta") or 0) == temp
