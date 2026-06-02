"""v2.99.46 — Eldritch Master (Warlock Lv 20 capstone).

RAW (PHB p.107): "At 20th level, you can draw on your inner reserve
of mystical power while entreating your patron to regain expended
spell slots. You can spend 1 minute entreating your patron for aid
to regain all your expended spell slots from your Pact Magic
feature. Once you regain spell slots with this feature, you must
finish a long rest before you can do so again."

Endpoint `/use_eldritch_master` (Lv 20 gate) walks every spell_slots
row carrying `reset: "short"` (the Pact Magic marker), sets used=0,
broadcasts `spell_slot_update` per refreshed row + decrements the
`eldritch-master-uses` daily counter + broadcasts `resource_update`
+ `feature_used(source=eldritch-master)`.

Tests use the v2.99.39 capstone-test pattern (class-scoped level
PATCH bump Magnus Lv 5 → Lv 20) and the v2.99.46 spell_slots PATCH
allowlist add to drain Magnus's Pact slots without going through
/cast_spell.
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID


@pytest_asyncio.fixture
async def magnus_at_lv_20(gm_client, roster):
    """Bump Magnus to Lv 20 for the test, restore at end."""
    magnus = roster["Magnus Hexbinder"]
    await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{magnus['id']}/sheet-fields",
        json={"class_slug": "warlock", "level": 20},
    )
    yield magnus
    await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{magnus['id']}/sheet-fields",
        json={"class_slug": "warlock", "level": 5},
    )


async def _drain_pact_slots(gm_client, char_id, used=2, total=2, level=3):
    """Mark all of Magnus's Pact Magic L3 slots as spent. v2.99.46
    spell_slots PATCH allowlist add lets this land via /sheet-fields.
    """
    return await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-fields",
        json={
            "spell_slots": {
                "warlock": {
                    str(level): {
                        "total": total, "used": used, "reset": "short",
                    },
                },
            },
        },
    )


async def test_eldritch_master_refills_pact_slots_at_lv_20(
    gm_client, gm_ws, magnus_at_lv_20,
):
    """Lv 20 Magnus with drained Pact slots → /use_eldritch_master
    refills all Pact slots + decrements daily counter + broadcasts.
    """
    magnus = magnus_at_lv_20
    # Drain both L3 Pact slots.
    r = await _drain_pact_slots(gm_client, magnus["id"], used=2)
    assert r.status_code == 200, r.text

    gm_ws.mark()
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_eldritch_master",
        json={"character_id": magnus["id"]},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["remaining"] == 0
    assert data["max"] == 1
    assert data["refilled_slots"] >= 1  # at least the warlock L3 row

    import asyncio as _asy
    await _asy.sleep(0.2)

    # feature_used broadcast.
    fu_msgs = gm_ws.buffered("feature_used")
    em = [
        m for m in fu_msgs
        if (m.get("data") or {}).get("source") == "eldritch-master"
        and (m.get("data") or {}).get("character_id") == magnus["id"]
    ]
    assert em, (
        f"expected feature_used(source=eldritch-master); buffered: "
        f"{[(m.get('type'), (m.get('data') or {}).get('source')) for m in gm_ws.buffered()]}"
    )

    # spell_slot_update fires for warlock L3 with used=0.
    ss_msgs = gm_ws.buffered("spell_slot_update")
    pact = [
        m for m in ss_msgs
        if (m.get("data") or {}).get("character_id") == magnus["id"]
        and (m.get("data") or {}).get("class_slug") == "warlock"
        and (m.get("data") or {}).get("level") == 3
    ]
    assert pact, (
        f"expected spell_slot_update for warlock L3 after Eldritch "
        f"Master; got: {[(m.get('data') or {}) for m in ss_msgs]}"
    )
    last_ss = pact[-1]["data"]
    assert last_ss["used"] == 0
    assert last_ss["total"] == 2

    # resource_update for the daily counter.
    ru_msgs = gm_ws.buffered("resource_update")
    em_ru = [
        m for m in ru_msgs
        if (m.get("data") or {}).get("character_id") == magnus["id"]
        and (m.get("data") or {}).get("key") == "eldritch-master-uses"
    ]
    assert em_ru, (
        f"expected resource_update for eldritch-master-uses; got: "
        f"{[(m.get('data') or {}).get('key') for m in ru_msgs]}"
    )
    last_ru = em_ru[-1]["data"]
    assert last_ru["current"] == 0


async def test_eldritch_master_no_uses_left(
    gm_client, magnus_at_lv_20,
):
    """Second invocation same long rest → 409 no_uses_left."""
    magnus = magnus_at_lv_20
    r1 = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_eldritch_master",
        json={"character_id": magnus["id"]},
    )
    assert r1.status_code == 200, r1.text
    r2 = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_eldritch_master",
        json={"character_id": magnus["id"]},
    )
    assert r2.status_code == 409, r2.text
    body = r2.json()
    assert body["error"] == "no_uses_left"


async def test_eldritch_master_level_too_low(gm_client, roster):
    """Lv 5 Magnus → 409 level_too_low (required 20)."""
    magnus = roster["Magnus Hexbinder"]
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_eldritch_master",
        json={"character_id": magnus["id"]},
    )
    assert resp.status_code == 409, resp.text
    body = resp.json()
    assert body["error"] == "level_too_low"
    assert body["required"] == 20


async def test_eldritch_master_wrong_class(gm_client, roster):
    """Tavik (Cleric) → 409 wrong_class."""
    tavik = roster["Brother Tavik Stonebrow"]
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_eldritch_master",
        json={"character_id": tavik["id"]},
    )
    assert resp.status_code == 409, resp.text
    body = resp.json()
    assert body["error"] == "wrong_class"


async def test_eldritch_master_long_rest_refills(
    gm_client, magnus_at_lv_20,
):
    """Spend the daily charge, long rest → second invocation succeeds."""
    magnus = magnus_at_lv_20
    r1 = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_eldritch_master",
        json={"character_id": magnus["id"]},
    )
    assert r1.status_code == 200
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{magnus['id']}/rest",
        json={"type": "long"},
    )
    r2 = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_eldritch_master",
        json={"character_id": magnus["id"]},
    )
    assert r2.status_code == 200, r2.text
    assert r2.json()["remaining"] == 0
