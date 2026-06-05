"""v2.99.293 — Light Domain Cleric: Corona of Light (H.1 deeper, Lv 17).

H.1 Lv 17 first ship — opens the H.1 Lv 17 batch. RAW PHB
p.61: action to activate 60 ft bright sunlight + 30 ft dim
beyond (90 ft total dim radius) for 1 min (or until dismissed
with another action). Enemies in the bright light have
disadvantage on saves vs your fire and radiant spells.

v1 announce-only — light + disadvantage aura are GM-tracked.
Costs action chip. No per-rest gate (RAW at will).

Tavik PATCH'd to Light Domain Lv 17.

Tests:
  - Lv 17 happy → bright 60 ft, dim 90 ft, 1 min, disadvantage
    vs fire+radiant.
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


def _col_broadcasts(gm_ws, character_id):
    return [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "corona-of-light"
        and (m.get("data") or {}).get("character_id") == character_id
    ]


@pytest_asyncio.fixture
async def tavik_light_lv17(gm_client, roster):
    """PATCH Tavik to Light Domain Lv 17."""
    tavik = roster["Brother Tavik Stonebrow"]
    await _patch_sheet(
        gm_client, tavik["id"],
        {"subclass": "Light Domain", "level": 17},
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


async def test_use_col_happy_lv17(
    gm_client, gm_ws, tavik_light_lv17,
):
    """Lv 17 Light → bright 60, dim 90, 1 min, disadv fire+radiant."""
    tavik = tavik_light_lv17
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_corona_of_light",
        json={"character_id": tavik["id"], "override": True},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["bright_light_radius_ft"] == 60
    assert data["dim_light_radius_ft"] == 90
    assert data["duration_minutes"] == 1
    assert "fire" in data["save_disadvantage_types"]
    assert "radiant" in data["save_disadvantage_types"]
    assert data["cleric_level"] == 17
    await asyncio.sleep(0.3)
    feats = _col_broadcasts(gm_ws, tavik["id"])
    assert feats


async def test_use_col_wrong_subclass(
    gm_client, roster,
):
    """Default Tavik (Life Domain Lv 6) → 409."""
    tavik = roster["Brother Tavik Stonebrow"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_corona_of_light",
        json={"character_id": tavik["id"], "override": True},
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "wrong_subclass_or_level"


async def test_use_col_level_gate(
    gm_client, roster,
):
    """Light Tavik at Lv 16 → 409."""
    tavik = roster["Brother Tavik Stonebrow"]
    await _patch_sheet(
        gm_client, tavik["id"],
        {"subclass": "Light Domain", "level": 16},
        class_slug="cleric",
    )
    try:
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/use_corona_of_light",
            json={"character_id": tavik["id"], "override": True},
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
