"""v2.99.305 — Order Domain Cleric: Order's Wrath (H.1 deeper, Lv 17).

H.1 Lv 17 Order ship. CLOSES the H.1 Lv 17 batch (13/13
PHB+TCE+SCAG domains). RAW TCE p.40: when you deal Divine
Strike damage, curse target until start of your next turn.
Next ally hit triggers 2d8 psychic and ends curse. Once per
turn.

v1 announce-only — curse install + ally-hit trigger is
GM-tracked. No chip — passive trigger on Divine Strike.

Tests:
  - Lv 17 happy → 2d8 psychic expression, next-turn expiry.
  - Optional target_combatant_id passed through.
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


def _ow_broadcasts(gm_ws, character_id):
    return [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "orders-wrath"
        and (m.get("data") or {}).get("character_id") == character_id
    ]


@pytest_asyncio.fixture
async def tavik_order_lv17(gm_client, roster):
    """PATCH Tavik to Order Domain Lv 17."""
    tavik = roster["Brother Tavik Stonebrow"]
    await _patch_sheet(
        gm_client, tavik["id"],
        {"subclass": "Order Domain", "level": 17},
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


async def test_use_ow_happy_lv17(
    gm_client, gm_ws, tavik_order_lv17,
):
    """Lv 17 Order → 2d8 psychic, next-turn expiry."""
    tavik = tavik_order_lv17
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_orders_wrath",
        json={"character_id": tavik["id"]},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["psychic_damage_expression"] == "2d8"
    assert data["expires_on"] == "next_turn_start"
    assert data["cleric_level"] == 17
    await asyncio.sleep(0.3)
    feats = _ow_broadcasts(gm_ws, tavik["id"])
    assert feats


async def test_use_ow_with_target(
    gm_client, tavik_order_lv17,
):
    """Optional target_combatant_id passed through."""
    tavik = tavik_order_lv17
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_orders_wrath",
        json={"character_id": tavik["id"], "target_combatant_id": "tok_test"},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["target_combatant_id"] == "tok_test"


async def test_use_ow_wrong_subclass(
    gm_client, roster,
):
    """Default Tavik (Life Domain) → 409."""
    tavik = roster["Brother Tavik Stonebrow"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_orders_wrath",
        json={"character_id": tavik["id"]},
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "wrong_subclass_or_level"


async def test_use_ow_level_gate(
    gm_client, roster,
):
    """Order Tavik at Lv 16 → 409."""
    tavik = roster["Brother Tavik Stonebrow"]
    await _patch_sheet(
        gm_client, tavik["id"],
        {"subclass": "Order Domain", "level": 16},
        class_slug="cleric",
    )
    try:
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/use_orders_wrath",
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
