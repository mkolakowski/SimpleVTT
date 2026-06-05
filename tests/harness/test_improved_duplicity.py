"""v2.99.298 — Trickery Domain Cleric: Improved Duplicity (H.1 deeper, Lv 17).

H.1 Lv 17 Trickery ship. RAW PHB p.62: Invoke Duplicity now
creates up to 4 duplicates (was 1). Bonus action: move any
number of them up to 30 ft each, max 120 ft from caster.

v1 announce-only — duplicate-count + per-bonus-action move
logic is GM-tracked. No chip — passive upgrade to the
existing Lv 2 CD.

Tests:
  - Lv 17 happy → max_duplicates 4, bonus_move 30 ft, max
    range 120 ft.
  - Wrong subclass → 409.
  - Level gate (Lv 16) → 409.
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


def _id_broadcasts(gm_ws, character_id):
    return [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "improved-duplicity"
        and (m.get("data") or {}).get("character_id") == character_id
    ]


@pytest_asyncio.fixture
async def tavik_trickery_lv17(gm_client, roster):
    """PATCH Tavik to Trickery Domain Lv 17."""
    tavik = roster["Brother Tavik Stonebrow"]
    await _patch_sheet(
        gm_client, tavik["id"],
        {"subclass": "Trickery Domain", "level": 17},
        class_slug="cleric",
    )
    try:
        yield tavik
    finally:
        await _patch_sheet(
            gm_client, tavik["id"],
            {"subclass": "Life Domain", "level": 6},
            class_slug="cleric",
        )


async def test_use_id_happy_lv17(
    gm_client, gm_ws, tavik_trickery_lv17,
):
    """Lv 17 Trickery → 4 duplicates, 30 ft move, 120 ft range."""
    tavik = tavik_trickery_lv17
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_improved_duplicity",
        json={"character_id": tavik["id"]},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["max_duplicates"] == 4
    assert data["bonus_move_per_duplicate_ft"] == 30
    assert data["max_range_ft"] == 120
    assert data["cleric_level"] == 17
    await asyncio.sleep(0.3)
    feats = _id_broadcasts(gm_ws, tavik["id"])
    assert feats


async def test_use_id_wrong_subclass(
    gm_client, roster,
):
    """Default Tavik (Life Domain) → 409."""
    tavik = roster["Brother Tavik Stonebrow"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_improved_duplicity",
        json={"character_id": tavik["id"]},
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "wrong_subclass_or_level"


async def test_use_id_level_gate(
    gm_client, roster,
):
    """Trickery Tavik at Lv 16 → 409."""
    tavik = roster["Brother Tavik Stonebrow"]
    await _patch_sheet(
        gm_client, tavik["id"],
        {"subclass": "Trickery Domain", "level": 16},
        class_slug="cleric",
    )
    try:
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/use_improved_duplicity",
            json={"character_id": tavik["id"]},
        )
        assert r.status_code == 409, r.text
        data = r.json()
        assert data.get("error") == "wrong_subclass_or_level"
    finally:
        await _patch_sheet(
            gm_client, tavik["id"],
            {"subclass": "Life Domain", "level": 6},
            class_slug="cleric",
        )
