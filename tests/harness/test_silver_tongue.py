"""v2.99.324 — Eloquence College Bard: Silver Tongue (F.1 batch, Lv 3+, TCE).

F.1 Bard subclass batch ship #6. RAW TCE p.28: Cha (Persuasion)
and Cha (Deception) checks treat a d20 roll of 9 or lower as
a 10.

v1 announce-only — the d20 minimum-10 substitution is
GM-tracked. No chip — passive permanent.

Tests:
  - Lv 3+ happy → minimum_d20_value 10, applies_to includes
    persuasion + deception.
  - Wrong subclass → 409.
  - Eloquence Lv 2 → 409.
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


def _st_broadcasts(gm_ws, character_id):
    return [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "silver-tongue"
        and (m.get("data") or {}).get("character_id") == character_id
    ]


@pytest_asyncio.fixture
async def lyra_eloquence(gm_client, roster):
    """PATCH Lyra to College of Eloquence."""
    lyra = roster["Lyra Sunstrider"]
    await _patch_sheet(
        gm_client, lyra["id"],
        {"subclass": "College of Eloquence"},
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


async def test_use_st_happy_lv6(
    gm_client, gm_ws, lyra_eloquence,
):
    """Lv 6 Eloquence → minimum_d20_value 10."""
    lyra = lyra_eloquence
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_silver_tongue",
        json={"character_id": lyra["id"]},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["minimum_d20_value"] == 10
    assert "persuasion" in data["applies_to"]
    assert "deception" in data["applies_to"]
    assert data["ability"] == "CHA"
    assert data["bard_level"] == 6
    await asyncio.sleep(0.3)
    feats = _st_broadcasts(gm_ws, lyra["id"])
    assert feats


async def test_use_st_wrong_subclass(
    gm_client, roster,
):
    """Default Lyra (Lore) → 409."""
    lyra = roster["Lyra Sunstrider"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_silver_tongue",
        json={"character_id": lyra["id"]},
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "wrong_subclass_or_level"


async def test_use_st_level_gate(
    gm_client, roster,
):
    """Eloquence Lyra at Lv 2 → 409."""
    lyra = roster["Lyra Sunstrider"]
    await _patch_sheet(
        gm_client, lyra["id"],
        {"subclass": "College of Eloquence", "level": 2},
        class_slug="bard",
    )
    try:
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/use_silver_tongue",
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
