"""v2.99.295 — Life Domain Cleric: Supreme Healing (H.1 deeper, Lv 17).

H.1 Lv 17 Life ship. RAW PHB p.61: when you would roll dice
to restore HP with a spell, take the maximum on each die
instead.

v1 announce-only — the max-dice substitution for heal-spell
dice is GM-tracked (a follow-up could wire this into the
heal-spell pipeline). No chip cost — passive permanent.

Tavik is Life Domain in the demo (just bumped to Lv 17).

Tests:
  - Lv 17 happy → max_dice_substitution True.
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


def _sh_broadcasts(gm_ws, character_id):
    return [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "supreme-healing"
        and (m.get("data") or {}).get("character_id") == character_id
    ]


@pytest_asyncio.fixture
async def tavik_life_lv17(gm_client, roster):
    """PATCH Tavik to Life Domain Lv 17 (subclass is already
    Life by default — just bump level)."""
    tavik = roster["Brother Tavik Stonebrow"]
    await _patch_sheet(
        gm_client, tavik["id"],
        {"subclass": "Life Domain", "level": 17},
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


async def test_use_sh_happy_lv17(
    gm_client, gm_ws, tavik_life_lv17,
):
    """Lv 17 Life → max_dice_substitution True."""
    tavik = tavik_life_lv17
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_supreme_healing",
        json={"character_id": tavik["id"]},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["max_dice_substitution"] is True
    assert data["cleric_level"] == 17
    await asyncio.sleep(0.3)
    feats = _sh_broadcasts(gm_ws, tavik["id"])
    assert feats


async def test_use_sh_wrong_subclass(
    gm_client, roster,
):
    """Light Domain Tavik (PATCH) at Lv 17 → 409."""
    tavik = roster["Brother Tavik Stonebrow"]
    await _patch_sheet(
        gm_client, tavik["id"],
        {"subclass": "Light Domain", "level": 17},
        class_slug="cleric",
    )
    try:
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/use_supreme_healing",
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


async def test_use_sh_level_gate(
    gm_client, roster,
):
    """Life Tavik at Lv 16 → 409."""
    tavik = roster["Brother Tavik Stonebrow"]
    await _patch_sheet(
        gm_client, tavik["id"],
        {"subclass": "Life Domain", "level": 16},
        class_slug="cleric",
    )
    try:
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/use_supreme_healing",
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
