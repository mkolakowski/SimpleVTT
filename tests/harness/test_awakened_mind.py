"""v2.99.352 — The Great Old One Warlock: Awakened Mind (G Warlock batch #4, Lv 1+, PHB).

Phase G Warlock patron subclass batch ship #4 — The Great Old One
opens.
RAW PHB p.110: telepathically speak (one-way) to any creature you
can see within 30 ft. No shared language needed (the creature must
understand at least one language). At-will, no action cost.

v1 announce-only — the target choice + one-way telepathy are
GM-narrated.

Magnus Hexbinder (Warlock, PATCHed to The Great Old One Lv 5) is
the demo fixture.

Tests:
  - Lv 5 happy: range_ft 30, broadcast fires.
  - Wrong subclass (default The Fiend) → 409.
  - Wrong class (Caelan paladin) → 409.
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


def _am_broadcasts(gm_ws, character_id):
    return [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "awakened-mind"
        and (m.get("data") or {}).get("character_id") == character_id
    ]


@pytest_asyncio.fixture
async def magnus_goo(gm_client, roster):
    """PATCH Magnus to The Great Old One; restore to The Fiend."""
    magnus = roster["Magnus Hexbinder"]
    await _patch_sheet(
        gm_client, magnus["id"],
        {"subclass": "The Great Old One"},
        class_slug="warlock",
    )
    try:
        yield magnus
    finally:
        await _patch_sheet(
            gm_client, magnus["id"],
            {"subclass": "The Fiend"},
            class_slug="warlock",
        )


async def test_use_am_happy_lv5(
    gm_client, gm_ws, magnus_goo,
):
    """Lv 5 Great Old One → range_ft 30, broadcast fires."""
    magnus = magnus_goo
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_awakened_mind",
        json={"character_id": magnus["id"]},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["feature"] == "awakened-mind"
    assert data["range_ft"] == 30
    assert data["warlock_level"] == 5
    await asyncio.sleep(0.3)
    feats = _am_broadcasts(gm_ws, magnus["id"])
    assert feats
    assert feats[-1]["data"]["range_ft"] == 30


async def test_use_am_wrong_subclass(
    gm_client, roster,
):
    """Default Magnus (The Fiend) → 409."""
    magnus = roster["Magnus Hexbinder"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_awakened_mind",
        json={"character_id": magnus["id"]},
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "wrong_subclass_or_level"


async def test_use_am_wrong_class(
    gm_client, roster,
):
    """Caelan (Paladin) → 409."""
    caelan = roster["Sir Caelan Lightbringer"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_awakened_mind",
        json={"character_id": caelan["id"]},
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "wrong_subclass_or_level"
