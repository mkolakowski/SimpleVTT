"""v2.99.284 — Vengeance Paladin: Soul of Vengeance (H.2 deeper).

H.2 Lv 15 Vengeance ship. RAW PHB p.88: when a creature under
Vow of Enmity makes an attack, you can use your reaction to
make a melee weapon attack against that creature if in range.

v1 announce-only — the actual reactive melee weapon attack is
a follow-up /attack call. Costs a reaction chip.

Caelan Lv 7 default → need PATCH to Vengeance Lv 15.

Tests:
  - Lv 15 happy → 200, reaction chip marked.
  - Wrong subclass → 409.
  - Level gate (Lv 14) → 409.
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


def _sov_broadcasts(gm_ws, character_id):
    return [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "soul-of-vengeance"
        and (m.get("data") or {}).get("character_id") == character_id
    ]


@pytest_asyncio.fixture
async def caelan_vengeance_lv15(gm_client, roster):
    """PATCH Caelan to Vengeance Lv 15."""
    caelan = roster["Sir Caelan Lightbringer"]
    await _patch_sheet(
        gm_client, caelan["id"],
        {"subclass": "Oath of Vengeance", "level": 15},
        class_slug="paladin",
    )
    try:
        yield caelan
    finally:
        await _patch_sheet(
            gm_client, caelan["id"],
            {"subclass": "Oath of Devotion", "level": 7},
            class_slug="paladin",
        )


async def test_use_sov_happy_lv15(
    gm_client, gm_ws, caelan_vengeance_lv15,
):
    """Lv 15 Vengeance → 200, broadcast."""
    caelan = caelan_vengeance_lv15
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_soul_of_vengeance",
        json={"character_id": caelan["id"], "override": True},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["paladin_level"] == 15
    await asyncio.sleep(0.3)
    feats = _sov_broadcasts(gm_ws, caelan["id"])
    assert feats


async def test_use_sov_wrong_subclass(
    gm_client, roster,
):
    """Default Caelan (Devotion Lv 7) → 409."""
    caelan = roster["Sir Caelan Lightbringer"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_soul_of_vengeance",
        json={"character_id": caelan["id"], "override": True},
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "wrong_subclass_or_level"


async def test_use_sov_level_gate(
    gm_client, roster,
):
    """Vengeance Caelan at Lv 14 → 409."""
    caelan = roster["Sir Caelan Lightbringer"]
    await _patch_sheet(
        gm_client, caelan["id"],
        {"subclass": "Oath of Vengeance", "level": 14},
        class_slug="paladin",
    )
    try:
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/use_soul_of_vengeance",
            json={"character_id": caelan["id"], "override": True},
        )
        assert r.status_code == 409, r.text
        data = r.json()
        assert data.get("error") == "wrong_subclass_or_level"
    finally:
        await _patch_sheet(
            gm_client, caelan["id"],
            {"subclass": "Oath of Devotion", "level": 7},
            class_slug="paladin",
        )
