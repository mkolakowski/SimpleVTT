"""v2.99.333 — Transmutation Wizard: Minor Alchemy (G.1 batch, Lv 2+).

G.1 Wizard subclass batch ship #7. RAW PHB p.119: 10 min /
cubic foot transformation of one nonmagical object (wood,
stone, iron, copper, silver) into another. Reverts after 1
hour or on losing concentration.

v1 announce-only — transformation GM-tracked.

Tests:
  - Lv 7 happy default wood → stone.
  - Iron → copper passes through.
  - Invalid material (e.g. "gold") → clamps to default.
  - Wrong subclass → 409.
  - Transmutation Lv 1 → 409.
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


def _ma_broadcasts(gm_ws, character_id):
    return [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "minor-alchemy"
        and (m.get("data") or {}).get("character_id") == character_id
    ]


@pytest_asyncio.fixture
async def thalindra_transmutation(gm_client, roster):
    """PATCH Thalindra to School of Transmutation."""
    thal = roster["Thalindra Moonwhisper"]
    await _patch_sheet(
        gm_client, thal["id"],
        {"subclass": "School of Transmutation"},
        class_slug="wizard",
    )
    try:
        yield thal
    finally:
        await _patch_sheet(
            gm_client, thal["id"],
            {"subclass": "School of Evocation", "level": 7},
            class_slug="wizard",
        )


async def test_use_ma_happy_lv7_default(
    gm_client, gm_ws, thalindra_transmutation,
):
    """Lv 7 Transmutation default → wood → stone."""
    thal = thalindra_transmutation
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_minor_alchemy",
        json={"character_id": thal["id"]},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["source_material"] == "wood"
    assert data["target_material"] == "stone"
    assert data["time_per_cubic_foot_minutes"] == 10
    assert data["duration_minutes"] == 60
    assert data["concentration"] is True
    assert data["wizard_level"] == 7
    await asyncio.sleep(0.3)
    feats = _ma_broadcasts(gm_ws, thal["id"])
    assert feats


async def test_use_ma_iron_to_copper(
    gm_client, thalindra_transmutation,
):
    """iron → copper passes through."""
    thal = thalindra_transmutation
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_minor_alchemy",
        json={
            "character_id": thal["id"],
            "source_material": "iron",
            "target_material": "copper",
        },
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["source_material"] == "iron"
    assert data["target_material"] == "copper"


async def test_use_ma_invalid_material_clamps(
    gm_client, thalindra_transmutation,
):
    """source_material='gold' (invalid) → clamps to 'wood'."""
    thal = thalindra_transmutation
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_minor_alchemy",
        json={
            "character_id": thal["id"],
            "source_material": "gold",
            "target_material": "diamond",
        },
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["source_material"] == "wood"
    assert data["target_material"] == "stone"


async def test_use_ma_wrong_subclass(
    gm_client, roster,
):
    """Default Thalindra (Evocation) → 409."""
    thal = roster["Thalindra Moonwhisper"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_minor_alchemy",
        json={"character_id": thal["id"]},
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "wrong_subclass_or_level"


async def test_use_ma_level_gate(
    gm_client, roster,
):
    """Transmutation Thalindra at Lv 1 → 409."""
    thal = roster["Thalindra Moonwhisper"]
    await _patch_sheet(
        gm_client, thal["id"],
        {"subclass": "School of Transmutation", "level": 1},
        class_slug="wizard",
    )
    try:
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/use_minor_alchemy",
            json={"character_id": thal["id"]},
        )
        assert r.status_code == 409, r.text
        data = r.json()
        assert data.get("error") == "wrong_subclass_or_level"
    finally:
        await _patch_sheet(
            gm_client, thal["id"],
            {"subclass": "School of Evocation", "level": 7},
            class_slug="wizard",
        )
