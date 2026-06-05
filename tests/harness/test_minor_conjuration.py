"""v2.99.329 — Conjuration Wizard: Minor Conjuration (G.1 batch, Lv 2+).

G.1 Wizard subclass batch ship #3. RAW PHB p.116: action to
conjure a nonmagical inanimate object ≤3 ft any dim, ≤10 lb,
in hand or unoccupied space within 10 ft. Persists 1 hr or
until re-conjured/damaged.

v1 announce-only — actual object creation GM-tracked. Costs
action chip.

Tests:
  - Lv 2+ happy with "torch" → 60 min, dim 5 ft.
  - Default missing object_name → fallback string.
  - Wrong subclass → 409.
  - Conjuration Lv 1 → 409.
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


def _mc_broadcasts(gm_ws, character_id):
    return [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "minor-conjuration"
        and (m.get("data") or {}).get("character_id") == character_id
    ]


@pytest_asyncio.fixture
async def thalindra_conjuration(gm_client, roster):
    """PATCH Thalindra to School of Conjuration."""
    thal = roster["Thalindra Moonwhisper"]
    await _patch_sheet(
        gm_client, thal["id"],
        {"subclass": "School of Conjuration"},
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


async def test_use_mc_happy_lv7(
    gm_client, gm_ws, thalindra_conjuration,
):
    """Lv 7 Conjuration with 'torch' → 60 min."""
    thal = thalindra_conjuration
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_minor_conjuration",
        json={"character_id": thal["id"], "object_name": "torch", "override": True},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["object_name"] == "torch"
    assert data["duration_minutes"] == 60
    assert data["max_dim_ft"] == 3
    assert data["max_weight_lb"] == 10
    assert data["dim_light_radius_ft"] == 5
    assert data["wizard_level"] == 7
    await asyncio.sleep(0.3)
    feats = _mc_broadcasts(gm_ws, thal["id"])
    assert feats


async def test_use_mc_default_name(
    gm_client, thalindra_conjuration,
):
    """Missing object_name → fallback string."""
    thal = thalindra_conjuration
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_minor_conjuration",
        json={"character_id": thal["id"], "override": True},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert "unspecified" in data["object_name"]


async def test_use_mc_wrong_subclass(
    gm_client, roster,
):
    """Default Thalindra (Evocation) → 409."""
    thal = roster["Thalindra Moonwhisper"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_minor_conjuration",
        json={"character_id": thal["id"], "override": True},
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "wrong_subclass_or_level"


async def test_use_mc_level_gate(
    gm_client, roster,
):
    """Conjuration Thalindra at Lv 1 → 409."""
    thal = roster["Thalindra Moonwhisper"]
    await _patch_sheet(
        gm_client, thal["id"],
        {"subclass": "School of Conjuration", "level": 1},
        class_slug="wizard",
    )
    try:
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/use_minor_conjuration",
            json={"character_id": thal["id"], "override": True},
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
