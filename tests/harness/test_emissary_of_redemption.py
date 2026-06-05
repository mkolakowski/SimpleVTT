"""v2.99.292 — Redemption Paladin: Emissary of Redemption (H.2 deeper, Lv 20).

H.2 Lv 20 Redemption ship. CLOSES the H.2 Lv 20 batch (5/5
oaths). RAW XGE p.39: passive permanent capstone. Resistance
to all damage from creatures + half-damage radiant counter on
hit. Both negated against a creature you attack/spell/damage
until next long rest.

v1 announce-only — full effect application is GM-tracked
(the "until you attack them" caveat needs per-target
state). No chip cost — passive permanent.

Tests:
  - Lv 20 happy → resistance_all_creature_damage True,
    radiant_back_fraction 0.5.
  - Wrong subclass → 409.
  - Level gate (Lv 19) → 409.
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


def _er_broadcasts(gm_ws, character_id):
    return [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "emissary-of-redemption"
        and (m.get("data") or {}).get("character_id") == character_id
    ]


@pytest_asyncio.fixture
async def caelan_redemption_lv20(gm_client, roster):
    """PATCH Caelan to Redemption Lv 20."""
    caelan = roster["Sir Caelan Lightbringer"]
    await _patch_sheet(
        gm_client, caelan["id"],
        {"subclass": "Oath of Redemption", "level": 20},
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


async def test_use_er_happy_lv20(
    gm_client, gm_ws, caelan_redemption_lv20,
):
    """Lv 20 Redemption → resistance + half radiant back."""
    caelan = caelan_redemption_lv20
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_emissary_of_redemption",
        json={"character_id": caelan["id"]},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["resistance_all_creature_damage"] is True
    assert data["radiant_back_fraction"] == 0.5
    assert data["paladin_level"] == 20
    await asyncio.sleep(0.3)
    feats = _er_broadcasts(gm_ws, caelan["id"])
    assert feats


async def test_use_er_wrong_subclass(
    gm_client, roster,
):
    """Default Caelan (Devotion Lv 7) → 409."""
    caelan = roster["Sir Caelan Lightbringer"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_emissary_of_redemption",
        json={"character_id": caelan["id"]},
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "wrong_subclass_or_level"


async def test_use_er_level_gate(
    gm_client, roster,
):
    """Redemption Caelan at Lv 19 → 409."""
    caelan = roster["Sir Caelan Lightbringer"]
    await _patch_sheet(
        gm_client, caelan["id"],
        {"subclass": "Oath of Redemption", "level": 19},
        class_slug="paladin",
    )
    try:
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/use_emissary_of_redemption",
            json={"character_id": caelan["id"]},
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
