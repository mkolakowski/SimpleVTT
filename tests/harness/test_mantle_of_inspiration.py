"""v2.99.321 — Glamour College Bard: Mantle of Inspiration (F.1 batch, Lv 3+, XGE).

F.1 Bard subclass batch ship #3. RAW XGE p.16: bonus action +
1 BI use → up to CHA-mod (min 1) allies within 60 ft each gain
5+bard_level temp HP + immediate reaction-move at full speed
without provoking OAs.

v1 announce-only — actual temp HP / reaction-move application
GM-tracked. Costs bonus chip; BI decrement via existing flow.

Lyra Lv 6 CHA 17 mod 3 → 3 allies × 11 temp HP each.

Tests:
  - Lv 6 happy → max_targets 3, temp_hp 11, max_range 60 ft.
  - Wrong subclass → 409.
  - Glamour Lv 2 → 409.
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


def _mi_broadcasts(gm_ws, character_id):
    return [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "mantle-of-inspiration"
        and (m.get("data") or {}).get("character_id") == character_id
    ]


@pytest_asyncio.fixture
async def lyra_glamour(gm_client, roster):
    """PATCH Lyra to College of Glamour."""
    lyra = roster["Lyra Sunstrider"]
    await _patch_sheet(
        gm_client, lyra["id"],
        {"subclass": "College of Glamour"},
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


async def test_use_mi_happy_lv6(
    gm_client, gm_ws, lyra_glamour,
):
    """Lv 6 Glamour, CHA 17 mod 3 → 3 allies × 11 temp HP."""
    lyra = lyra_glamour
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_mantle_of_inspiration",
        json={"character_id": lyra["id"], "override": True},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["max_targets"] == 3
    assert data["temp_hp_per_target"] == 11
    assert data["max_range_ft"] == 60
    assert data["free_move_no_oa"] is True
    assert data["consumed_bardic_inspiration"] is True
    assert data["bard_level"] == 6
    await asyncio.sleep(0.3)
    feats = _mi_broadcasts(gm_ws, lyra["id"])
    assert feats


async def test_use_mi_wrong_subclass(
    gm_client, roster,
):
    """Default Lyra (Lore) → 409."""
    lyra = roster["Lyra Sunstrider"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_mantle_of_inspiration",
        json={"character_id": lyra["id"], "override": True},
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "wrong_subclass_or_level"


async def test_use_mi_level_gate(
    gm_client, roster,
):
    """Glamour Lyra at Lv 2 → 409."""
    lyra = roster["Lyra Sunstrider"]
    await _patch_sheet(
        gm_client, lyra["id"],
        {"subclass": "College of Glamour", "level": 2},
        class_slug="bard",
    )
    try:
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/use_mantle_of_inspiration",
            json={"character_id": lyra["id"], "override": True},
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
