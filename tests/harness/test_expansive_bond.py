"""v2.99.303 — Peace Domain Cleric: Expansive Bond (H.1 deeper, Lv 17).

H.1 Lv 17 Peace ship. CLOSES the H.1 Lv 17 batch (11/11
RAW PHB+TCE domains shipped). RAW TCE p.39: Emboldening Bond
now works within 60 ft between bonded creatures (was 30);
the d4 bonus becomes a d6.

v1 announce-only — the new 60 ft range + d6 substitution is
GM-tracked on the existing Emboldening Bond aura.

Tests:
  - Lv 17 happy → bond_radius_ft 60, bonus_die d6.
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


def _eb_broadcasts(gm_ws, character_id):
    return [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "expansive-bond"
        and (m.get("data") or {}).get("character_id") == character_id
    ]


@pytest_asyncio.fixture
async def tavik_peace_lv17(gm_client, roster):
    """PATCH Tavik to Peace Domain Lv 17."""
    tavik = roster["Brother Tavik Stonebrow"]
    await _patch_sheet(
        gm_client, tavik["id"],
        {"subclass": "Peace Domain", "level": 17},
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


async def test_use_eb_happy_lv17(
    gm_client, gm_ws, tavik_peace_lv17,
):
    """Lv 17 Peace → bond 60 ft, d6 bonus."""
    tavik = tavik_peace_lv17
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_expansive_bond",
        json={"character_id": tavik["id"]},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["bond_radius_ft"] == 60
    assert data["bonus_die"] == "d6"
    assert data["previous_bonus_die"] == "d4"
    assert data["cleric_level"] == 17
    await asyncio.sleep(0.3)
    feats = _eb_broadcasts(gm_ws, tavik["id"])
    assert feats


async def test_use_eb_wrong_subclass(
    gm_client, roster,
):
    """Default Tavik (Life Domain) → 409."""
    tavik = roster["Brother Tavik Stonebrow"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_expansive_bond",
        json={"character_id": tavik["id"]},
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "wrong_subclass_or_level"


async def test_use_eb_level_gate(
    gm_client, roster,
):
    """Peace Tavik at Lv 16 → 409."""
    tavik = roster["Brother Tavik Stonebrow"]
    await _patch_sheet(
        gm_client, tavik["id"],
        {"subclass": "Peace Domain", "level": 16},
        class_slug="cleric",
    )
    try:
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/use_expansive_bond",
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
