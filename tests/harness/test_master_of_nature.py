"""v2.99.302 — Nature Domain Cleric: Master of Nature (H.1 deeper, Lv 17).

H.1 Lv 17 Nature ship. RAW PHB p.62: bonus action to verbally
command beasts and plants charmed by your Charm Animals and
Plants CD what to do on their next turn.

v1 announce-only — actual charmed-creature command
interpretation is GM-tracked. Costs a bonus chip.

Tests:
  - Lv 17 happy → 200, broadcast.
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


def _mon_broadcasts(gm_ws, character_id):
    return [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "master-of-nature"
        and (m.get("data") or {}).get("character_id") == character_id
    ]


@pytest_asyncio.fixture
async def tavik_nature_lv17(gm_client, roster):
    """PATCH Tavik to Nature Domain Lv 17."""
    tavik = roster["Brother Tavik Stonebrow"]
    await _patch_sheet(
        gm_client, tavik["id"],
        {"subclass": "Nature Domain", "level": 17},
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


async def test_use_mon_happy_lv17(
    gm_client, gm_ws, tavik_nature_lv17,
):
    """Lv 17 Nature → 200, broadcast."""
    tavik = tavik_nature_lv17
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_master_of_nature",
        json={"character_id": tavik["id"], "override": True},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["cleric_level"] == 17
    await asyncio.sleep(0.3)
    feats = _mon_broadcasts(gm_ws, tavik["id"])
    assert feats


async def test_use_mon_wrong_subclass(
    gm_client, roster,
):
    """Default Tavik (Life Domain) → 409."""
    tavik = roster["Brother Tavik Stonebrow"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_master_of_nature",
        json={"character_id": tavik["id"], "override": True},
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "wrong_subclass_or_level"


async def test_use_mon_level_gate(
    gm_client, roster,
):
    """Nature Tavik at Lv 16 → 409."""
    tavik = roster["Brother Tavik Stonebrow"]
    await _patch_sheet(
        gm_client, tavik["id"],
        {"subclass": "Nature Domain", "level": 16},
        class_slug="cleric",
    )
    try:
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/use_master_of_nature",
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
