"""v2.99.45 — Mystic Arcanum (Warlock Lv 11+).

RAW (PHB p.108): "At 11th level, your patron bestows upon you a
magical secret called an arcanum. Choose one 6th-level spell from
the warlock spell list as this arcanum. You can cast your arcanum
spell once without expending a spell slot. You must finish a long
rest before you can do so again. At higher levels: one 7th-level
spell at 13th, one 8th at 15th, one 9th at 17th."

v1 ship covers the L6 tier only. Endpoint takes
`{character_id, slot_level: 6|7|8|9}`, validates Warlock + class
level >= gate (Lv 11/13/15/17 for L6/L7/L8/L9) + the matching
`mystic-arcanum-l{N}` resource has uses remaining. Atomically
decrements + broadcasts.

Tests use the v2.99.39 capstone-test pattern (class-scoped level
PATCH) to bump Magnus to Lv 11.
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID


@pytest_asyncio.fixture
async def magnus_at_lv_11(gm_client, roster):
    """Bump Magnus to Lv 11 for the test, restore at end."""
    magnus = roster["Magnus Hexbinder"]
    await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{magnus['id']}/sheet-fields",
        json={"class_slug": "warlock", "level": 11},
    )
    yield magnus
    await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{magnus['id']}/sheet-fields",
        json={"class_slug": "warlock", "level": 5},
    )


async def test_mystic_arcanum_l6_decrements_at_lv_11(
    gm_client, gm_ws, magnus_at_lv_11,
):
    """Lv 11 Magnus spends his L6 arcanum → 200 + resource decremented
    + feature_used + resource_update broadcasts.
    """
    magnus = magnus_at_lv_11
    gm_ws.mark()
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_mystic_arcanum",
        json={"character_id": magnus["id"], "slot_level": 6},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["slot_level"] == 6
    assert data["resource_key"] == "mystic-arcanum-l6"
    assert data["remaining"] == 0
    assert data["max"] == 1

    import asyncio as _asy
    await _asy.sleep(0.2)
    fu_msgs = gm_ws.buffered("feature_used")
    ma = [
        m for m in fu_msgs
        if (m.get("data") or {}).get("source") == "mystic-arcanum"
        and (m.get("data") or {}).get("character_id") == magnus["id"]
    ]
    assert ma, (
        f"expected feature_used(source=mystic-arcanum); "
        f"buffered: {[(m.get('type'), (m.get('data') or {}).get('source')) for m in gm_ws.buffered()]}"
    )

    ru_msgs = gm_ws.buffered("resource_update")
    rk = [
        m for m in ru_msgs
        if (m.get("data") or {}).get("character_id") == magnus["id"]
        and (m.get("data") or {}).get("key") == "mystic-arcanum-l6"
    ]
    assert rk, (
        f"expected resource_update for mystic-arcanum-l6; got: "
        f"{[(m.get('data') or {}).get('key') for m in ru_msgs]}"
    )
    last = rk[-1]["data"]
    assert last["current"] == 0


async def test_mystic_arcanum_no_uses_left(
    gm_client, magnus_at_lv_11,
):
    """Spend twice → second call returns 409 no_uses_left."""
    magnus = magnus_at_lv_11
    r1 = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_mystic_arcanum",
        json={"character_id": magnus["id"], "slot_level": 6},
    )
    assert r1.status_code == 200, r1.text
    r2 = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_mystic_arcanum",
        json={"character_id": magnus["id"], "slot_level": 6},
    )
    assert r2.status_code == 409, r2.text
    body = r2.json()
    assert body["error"] == "no_uses_left"


async def test_mystic_arcanum_level_too_low(gm_client, roster):
    """Lv 5 Magnus (canonical fixture level) → 409 level_too_low for L6."""
    magnus = roster["Magnus Hexbinder"]
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_mystic_arcanum",
        json={"character_id": magnus["id"], "slot_level": 6},
    )
    assert resp.status_code == 409, resp.text
    body = resp.json()
    assert body["error"] == "level_too_low"
    assert body["required"] == 11
    assert body["got"] == 5


async def test_mystic_arcanum_wrong_class(gm_client, roster):
    """Tavik (Cleric) → 409 wrong_class."""
    tavik = roster["Brother Tavik Stonebrow"]
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_mystic_arcanum",
        json={"character_id": tavik["id"], "slot_level": 6},
    )
    assert resp.status_code == 409, resp.text
    body = resp.json()
    assert body["error"] == "wrong_class"


async def test_mystic_arcanum_invalid_slot_level(gm_client, magnus_at_lv_11):
    """slot_level outside {6,7,8,9} → 400."""
    magnus = magnus_at_lv_11
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_mystic_arcanum",
        json={"character_id": magnus["id"], "slot_level": 3},
    )
    assert resp.status_code == 400, resp.text


async def test_mystic_arcanum_l7_level_too_low_at_lv_11(
    gm_client, magnus_at_lv_11,
):
    """Lv 11 Magnus tries L7 arcanum → 409 (L7 requires Lv 13)."""
    magnus = magnus_at_lv_11
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_mystic_arcanum",
        json={"character_id": magnus["id"], "slot_level": 7},
    )
    # L7 resource isn't even on Magnus's sheet yet (v1 ships L6 only),
    # but the level gate fires first → 409 level_too_low.
    assert resp.status_code == 409, resp.text
    body = resp.json()
    assert body["error"] == "level_too_low"
    assert body["required"] == 13


async def test_mystic_arcanum_long_rest_refills(
    gm_client, magnus_at_lv_11,
):
    """Spend the L6 arcanum, long rest → resource refills back to 1."""
    magnus = magnus_at_lv_11
    r1 = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_mystic_arcanum",
        json={"character_id": magnus["id"], "slot_level": 6},
    )
    assert r1.status_code == 200
    # Long rest.
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{magnus['id']}/rest",
        json={"type": "long"},
    )
    # Second spend should now succeed.
    r2 = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_mystic_arcanum",
        json={"character_id": magnus["id"], "slot_level": 6},
    )
    assert r2.status_code == 200, r2.text
    assert r2.json()["remaining"] == 0
