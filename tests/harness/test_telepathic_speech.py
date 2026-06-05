"""v2.99.341 — Aberrant Mind: Telepathic Speech (G.2 batch ship #3, Lv 1+, TCE).

G.2 Sorcerer subclass batch ship #3 — Aberrant Mind opens.
RAW TCE p.68: as a bonus action, form a telepathic connection to
a creature you can see within 30 ft. The link lasts a number of
minutes equal to your sorcerer level.

v1 announce-only — target choice + range + duration GM-tracked.
Bonus chip.

Tests:
  - Lv 5 happy: range_ft 30, duration_minutes 5 (= sorcerer level).
  - Wrong subclass (default Zara Draconic) → 409.
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


def _ts_broadcasts(gm_ws, character_id):
    return [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "telepathic-speech"
        and (m.get("data") or {}).get("character_id") == character_id
    ]


@pytest_asyncio.fixture
async def zara_aberrant(gm_client, roster):
    """PATCH Zara to Aberrant Mind."""
    zara = roster["Zara Emberfire"]
    await _patch_sheet(
        gm_client, zara["id"],
        {"subclass": "Aberrant Mind"},
        class_slug="sorcerer",
    )
    try:
        yield zara
    finally:
        await _patch_sheet(
            gm_client, zara["id"],
            {"subclass": "Draconic Bloodline"},
            class_slug="sorcerer",
        )


async def test_use_ts_happy_lv5(
    gm_client, gm_ws, zara_aberrant,
):
    """Lv 5 Aberrant Mind → range 30 ft, duration 5 min."""
    zara = zara_aberrant
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_telepathic_speech",
        json={"character_id": zara["id"], "override": True},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["feature"] == "telepathic-speech"
    assert data["range_ft"] == 30
    assert data["duration_minutes"] == 5
    assert data["sorcerer_level"] == 5
    await asyncio.sleep(0.3)
    feats = _ts_broadcasts(gm_ws, zara["id"])
    assert feats
    assert feats[-1]["data"]["duration_minutes"] == 5


async def test_use_ts_wrong_subclass(
    gm_client, roster,
):
    """Default Zara (Draconic Bloodline) → 409."""
    zara = roster["Zara Emberfire"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_telepathic_speech",
        json={"character_id": zara["id"], "override": True},
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "wrong_subclass_or_level"


async def test_use_ts_wrong_class(
    gm_client, roster,
):
    """Caelan (Paladin) → 409."""
    caelan = roster["Sir Caelan Lightbringer"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_telepathic_speech",
        json={"character_id": caelan["id"], "override": True},
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "wrong_subclass_or_level"
