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


# ── v2.99.86 — L7/L8/L9 tier resources on Magnus's sheet ──


def _full_mystic_arcanum_resources():
    """v2.99.86 — the canonical L6/L7/L8/L9 + Eldritch Master resource
    list for Magnus's sheet. Used by the test fixture to PATCH the
    resources allowlist entry so the L7/L8/L9 tier tests don't depend
    on the running container being reseeded with v2.99.86's demo_seed
    edit.
    """
    return [
        {"key": "mystic-arcanum-l6", "name": "Mystic Arcanum (L6)",
         "current": 1, "max": 1, "reset": "long",
         "source": "warlock Lv 11 / Mystic Arcanum",
         "class_slug": "warlock",
         "desc": "1/long rest (Lv 11+)", "manual": False},
        {"key": "mystic-arcanum-l7", "name": "Mystic Arcanum (L7)",
         "current": 1, "max": 1, "reset": "long",
         "source": "warlock Lv 13 / Mystic Arcanum",
         "class_slug": "warlock",
         "desc": "1/long rest (Lv 13+)", "manual": False},
        {"key": "mystic-arcanum-l8", "name": "Mystic Arcanum (L8)",
         "current": 1, "max": 1, "reset": "long",
         "source": "warlock Lv 15 / Mystic Arcanum",
         "class_slug": "warlock",
         "desc": "1/long rest (Lv 15+)", "manual": False},
        {"key": "mystic-arcanum-l9", "name": "Mystic Arcanum (L9)",
         "current": 1, "max": 1, "reset": "long",
         "source": "warlock Lv 17 / Mystic Arcanum",
         "class_slug": "warlock",
         "desc": "1/long rest (Lv 17+)", "manual": False},
        {"key": "eldritch-master-uses", "name": "Eldritch Master",
         "current": 1, "max": 1, "reset": "long",
         "source": "warlock Lv 20 / Eldritch Master",
         "class_slug": "warlock",
         "desc": "1/long rest (Lv 20)", "manual": False},
    ]


@pytest_asyncio.fixture
async def magnus_at_lv(gm_client, roster):
    """Helper fixture factory — returns an async setter that flips
    Magnus's warlock level. Restores Lv 5 in teardown.

    Also PATCHes the full mystic-arcanum L6/L7/L8/L9 + eldritch-master
    resource list so the tests don't depend on whether the running
    container has been reseeded with v2.99.86's demo_seed edit.
    """
    magnus = roster["Magnus Hexbinder"]

    # Ensure all 4 tiers + eldritch master are present.
    await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{magnus['id']}/sheet-fields",
        json={"resources": _full_mystic_arcanum_resources()},
    )

    async def _set(level):
        await gm_client.patch(
            f"/api/campaign/{CAMPAIGN_ID}/character/{magnus['id']}/sheet-fields",
            json={"class_slug": "warlock", "level": level},
        )
        return magnus

    yield _set

    await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{magnus['id']}/sheet-fields",
        json={"class_slug": "warlock", "level": 5},
    )


async def test_mystic_arcanum_l7_decrements_at_lv_13(
    gm_client, gm_ws, magnus_at_lv,
):
    """v2.99.86 — bump Magnus to Lv 13; spending L7 arcanum →
    200 + mystic-arcanum-l7 resource decremented.
    """
    magnus = await magnus_at_lv(13)
    # Long-rest first so the resource counter is full regardless
    # of prior test runs.
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{magnus['id']}/rest",
        json={"type": "long"},
    )
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_mystic_arcanum",
        json={"character_id": magnus["id"], "slot_level": 7},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["slot_level"] == 7
    assert data["resource_key"] == "mystic-arcanum-l7"
    assert data["remaining"] == 0


async def test_mystic_arcanum_l8_decrements_at_lv_15(
    gm_client, gm_ws, magnus_at_lv,
):
    """v2.99.86 — Lv 15 unlocks L8 arcanum. Spend → 200 +
    mystic-arcanum-l8 decremented.
    """
    magnus = await magnus_at_lv(15)
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{magnus['id']}/rest",
        json={"type": "long"},
    )
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_mystic_arcanum",
        json={"character_id": magnus["id"], "slot_level": 8},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["slot_level"] == 8
    assert data["resource_key"] == "mystic-arcanum-l8"
    assert data["remaining"] == 0


async def test_mystic_arcanum_l9_decrements_at_lv_17(
    gm_client, gm_ws, magnus_at_lv,
):
    """v2.99.86 — Lv 17 unlocks L9 arcanum. Spend → 200 +
    mystic-arcanum-l9 decremented.
    """
    magnus = await magnus_at_lv(17)
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{magnus['id']}/rest",
        json={"type": "long"},
    )
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_mystic_arcanum",
        json={"character_id": magnus["id"], "slot_level": 9},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["slot_level"] == 9
    assert data["resource_key"] == "mystic-arcanum-l9"
    assert data["remaining"] == 0


async def test_mystic_arcanum_l8_level_too_low_at_lv_13(
    gm_client, magnus_at_lv,
):
    """v2.99.86 gate: Lv 13 Magnus can spend L6 + L7 but NOT L8.
    409 level_too_low with required=15.
    """
    magnus = await magnus_at_lv(13)
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_mystic_arcanum",
        json={"character_id": magnus["id"], "slot_level": 8},
    )
    assert resp.status_code == 409, resp.text
    err = resp.json()
    assert err["error"] == "level_too_low"
    assert err["required"] == 15
    assert err["got"] == 13
    assert err["slot_level"] == 8


async def test_mystic_arcanum_l9_level_too_low_at_lv_15(
    gm_client, magnus_at_lv,
):
    """v2.99.86 gate: Lv 15 Magnus can spend L6 + L7 + L8 but NOT L9.
    409 level_too_low with required=17.
    """
    magnus = await magnus_at_lv(15)
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_mystic_arcanum",
        json={"character_id": magnus["id"], "slot_level": 9},
    )
    assert resp.status_code == 409, resp.text
    err = resp.json()
    assert err["error"] == "level_too_low"
    assert err["required"] == 17
    assert err["got"] == 15
    assert err["slot_level"] == 9
