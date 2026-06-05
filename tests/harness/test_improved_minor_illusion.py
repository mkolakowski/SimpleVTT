"""v2.99.331 — Illusion Wizard: Improved Minor Illusion (G.1 batch, Lv 2+).

G.1 Wizard subclass batch ship #5. RAW PHB p.118: free Minor
Illusion cantrip (or alt wizard cantrip if already known).
Minor Illusion can create sound + image simultaneously.

v1 announce-only — dual-mode illusion applied at /cast_spell.
No chip — passive cantrip upgrade.

Tests:
  - Lv 2+ happy → dual_mode True.
  - Wrong subclass → 409.
  - Illusion Lv 1 → 409.
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


def _imi_broadcasts(gm_ws, character_id):
    return [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "improved-minor-illusion"
        and (m.get("data") or {}).get("character_id") == character_id
    ]


@pytest_asyncio.fixture
async def thalindra_illusion(gm_client, roster):
    """PATCH Thalindra to School of Illusion."""
    thal = roster["Thalindra Moonwhisper"]
    await _patch_sheet(
        gm_client, thal["id"],
        {"subclass": "School of Illusion"},
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


async def test_use_imi_happy_lv7(
    gm_client, gm_ws, thalindra_illusion,
):
    """Lv 7 Illusion → dual_mode True."""
    thal = thalindra_illusion
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_improved_minor_illusion",
        json={"character_id": thal["id"]},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["dual_mode"] is True
    assert "Minor Illusion" in data["free_cantrip"]
    assert data["wizard_level"] == 7
    await asyncio.sleep(0.3)
    feats = _imi_broadcasts(gm_ws, thal["id"])
    assert feats


async def test_use_imi_wrong_subclass(
    gm_client, roster,
):
    """Default Thalindra (Evocation) → 409."""
    thal = roster["Thalindra Moonwhisper"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_improved_minor_illusion",
        json={"character_id": thal["id"]},
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "wrong_subclass_or_level"


async def test_use_imi_level_gate(
    gm_client, roster,
):
    """Illusion Thalindra at Lv 1 → 409."""
    thal = roster["Thalindra Moonwhisper"]
    await _patch_sheet(
        gm_client, thal["id"],
        {"subclass": "School of Illusion", "level": 1},
        class_slug="wizard",
    )
    try:
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/use_improved_minor_illusion",
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
