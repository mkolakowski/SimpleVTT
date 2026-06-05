"""v2.99.322 — Whispers College Bard: Psychic Blades (F.1 batch, Lv 3+, XGE).

F.1 Bard subclass batch ship #4. RAW XGE p.17: on weapon hit,
expend 1 BI use to deal extra psychic damage.

Damage by bard level:
- Lv 3-4: 2d6
- Lv 5-9: 3d6
- Lv 10-14: 5d6
- Lv 15+: 8d6

Endpoint slug `/use_whispers_psychic_blades` to avoid collision
with Soulknife Rogue's `/use_psychic_blades` (v2.99.311).

v1 announce-only — BI decrement via existing flow.

Lyra Lv 6 → 3d6 psychic.

Tests:
  - Lv 6 happy → 3d6 psychic.
  - Lv 10 → 5d6.
  - Lv 15 → 8d6.
  - Wrong subclass → 409.
  - Whispers Lv 2 → 409.
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


def _wpb_broadcasts(gm_ws, character_id):
    return [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "whispers-psychic-blades"
        and (m.get("data") or {}).get("character_id") == character_id
    ]


@pytest_asyncio.fixture
async def lyra_whispers(gm_client, roster):
    """PATCH Lyra to College of Whispers."""
    lyra = roster["Lyra Sunstrider"]
    await _patch_sheet(
        gm_client, lyra["id"],
        {"subclass": "College of Whispers"},
        class_slug="bard",
    )
    try:
        yield lyra
    finally:
        await _patch_sheet(
            gm_client, lyra["id"],
            {"subclass": "College of Lore", "level": 6},
            class_slug="bard",
        )


async def test_use_wpb_happy_lv6(
    gm_client, gm_ws, lyra_whispers,
):
    """Lv 6 Whispers → 3d6 psychic."""
    lyra = lyra_whispers
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_whispers_psychic_blades",
        json={"character_id": lyra["id"]},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["damage_expression"] == "3d6"
    assert data["damage_type"] == "psychic"
    assert data["consumed_bardic_inspiration"] is True
    assert data["bard_level"] == 6
    await asyncio.sleep(0.3)
    feats = _wpb_broadcasts(gm_ws, lyra["id"])
    assert feats


async def test_use_wpb_lv10(
    gm_client, lyra_whispers,
):
    """Lv 10 → 5d6."""
    lyra = lyra_whispers
    await _patch_sheet(
        gm_client, lyra["id"], {"level": 10},
        class_slug="bard",
    )
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_whispers_psychic_blades",
        json={"character_id": lyra["id"]},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["damage_expression"] == "5d6"


async def test_use_wpb_lv15(
    gm_client, lyra_whispers,
):
    """Lv 15 → 8d6."""
    lyra = lyra_whispers
    await _patch_sheet(
        gm_client, lyra["id"], {"level": 15},
        class_slug="bard",
    )
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_whispers_psychic_blades",
        json={"character_id": lyra["id"]},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["damage_expression"] == "8d6"


async def test_use_wpb_wrong_subclass(
    gm_client, roster,
):
    """Default Lyra (Lore) → 409."""
    lyra = roster["Lyra Sunstrider"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_whispers_psychic_blades",
        json={"character_id": lyra["id"]},
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "wrong_subclass_or_level"


async def test_use_wpb_level_gate(
    gm_client, roster,
):
    """Whispers Lyra at Lv 2 → 409."""
    lyra = roster["Lyra Sunstrider"]
    await _patch_sheet(
        gm_client, lyra["id"],
        {"subclass": "College of Whispers", "level": 2},
        class_slug="bard",
    )
    try:
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/use_whispers_psychic_blades",
            json={"character_id": lyra["id"]},
        )
        assert r.status_code == 409, r.text
        data = r.json()
        assert data.get("error") == "wrong_subclass_or_level"
    finally:
        await _patch_sheet(
            gm_client, lyra["id"],
            {"subclass": "College of Lore", "level": 6},
            class_slug="bard",
        )
