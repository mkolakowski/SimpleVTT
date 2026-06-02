"""v2.99.39 — Sorcerous Restoration (Sorcerer Lv 20 capstone).

RAW (PHB p.101): "Beginning at 20th level, you regain 4 expended
sorcery points whenever you finish a short rest."

Hook lives in `/character/{id}/rest` short-rest path: gated on
class==sorcerer + level>=20. Finds the `sorcery-points` resource,
adds min(4, max-current) SP, broadcasts `resource_update` +
`feature_used(source=sorcerous-restoration)`. Sorcery points use
`reset: "long"` so the resource-refill loop above doesn't touch
them on a short rest — Lv 20 is the only short-rest SP path.

Tests use the v2.99.39 `level` allowlist entry on `/sheet-fields`
to temporarily bump Zara to Lv 20 (or Lv 19) without rebuilding her
sheet, then PATCH back to Lv 5 at end of test so the next test sees
the clean fixture state.

Tests:
- happy: Lv 20 + drained SP + short rest → +4 SP + broadcast.
- level gate: Lv 19 → no refund.
- class gate: Krieger (Barbarian) at Lv 20 → no refund.
- cap: Lv 20 with full SP → 0 refund (no broadcast).
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID


@pytest_asyncio.fixture
async def zara_at_lv_20(gm_client, roster):
    """Bump Zara to Lv 20 for the test, restore at end.

    Uses the v2.99.39 class-scoped `level` patch — passes
    `class_slug` so the patch routes into the matching `classes[]`
    entry. Without `class_slug`, the next /rest's normalize would
    silently revert sheet["level"] from classes[0].level.
    """
    zara = roster["Zara Emberfire"]
    await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{zara['id']}/sheet-fields",
        json={"class_slug": "sorcerer", "level": 20},
    )
    yield zara
    # Restore Zara to Lv 5 so subsequent tests see her at the
    # canonical fixture level.
    await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{zara['id']}/sheet-fields",
        json={"class_slug": "sorcerer", "level": 5},
    )


async def test_sorcerous_restoration_refunds_4_sp_at_lv_20(
    gm_client, gm_ws, zara_at_lv_20,
):
    """Lv 20 Zara drained to 0 SP → short rest → +4 SP. Response
    carries `sorcerous_restoration_sp == 4`; broadcast fires.
    """
    zara = zara_at_lv_20
    # Drain SP via Empowered Spell × 5 (each costs 1 SP).
    for _ in range(5):
        await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/use_metamagic_empowered_spell",
            json={"character_id": zara["id"]},
        )
    gm_ws.mark()
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{zara['id']}/rest",
        json={"type": "short"},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["sorcerous_restoration_sp"] == 4, (
        f"expected +4 SP refund; got {data.get('sorcerous_restoration_sp')}"
    )

    # feature_used broadcast.
    import asyncio as _asy
    await _asy.sleep(0.2)
    fu_msgs = gm_ws.buffered("feature_used")
    sr = [
        m for m in fu_msgs
        if (m.get("data") or {}).get("source") == "sorcerous-restoration"
        and (m.get("data") or {}).get("character_id") == zara["id"]
    ]
    assert sr, (
        f"expected feature_used(source=sorcerous-restoration); buffered: "
        f"{[(m.get('type'), (m.get('data') or {}).get('source')) for m in gm_ws.buffered()]}"
    )

    # resource_update broadcast.
    ru_msgs = gm_ws.buffered("resource_update")
    sp = [
        m for m in ru_msgs
        if (m.get("data") or {}).get("character_id") == zara["id"]
        and (m.get("data") or {}).get("key") == "sorcery-points"
    ]
    assert sp, (
        f"expected resource_update for sorcery-points; buffered: "
        f"{[(m.get('type'), (m.get('data') or {}).get('key')) for m in gm_ws.buffered()]}"
    )
    last = sp[-1]["data"]
    assert last["current"] == 4, (
        f"expected SP current=4 post-rest; got {last['current']}"
    )


async def test_sorcerous_restoration_skips_at_lv_19(
    gm_client, gm_ws, roster,
):
    """Lv 19 Zara drained → short rest → no refund + no broadcast."""
    zara = roster["Zara Emberfire"]
    await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{zara['id']}/sheet-fields",
        json={"class_slug": "sorcerer", "level": 19},
    )
    try:
        for _ in range(5):
            await gm_client.post(
                f"/api/campaign/{CAMPAIGN_ID}/use_metamagic_empowered_spell",
                json={"character_id": zara["id"]},
            )
        gm_ws.mark()
        resp = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/character/{zara['id']}/rest",
            json={"type": "short"},
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["sorcerous_restoration_sp"] == 0, (
            f"Lv 19 should NOT trigger Sorcerous Restoration; "
            f"got {data.get('sorcerous_restoration_sp')}"
        )
        import asyncio as _asy
        await _asy.sleep(0.2)
        fu_msgs = gm_ws.buffered("feature_used")
        sr = [
            m for m in fu_msgs
            if (m.get("data") or {}).get("source") == "sorcerous-restoration"
        ]
        assert not sr, (
            f"Lv 19 should NOT broadcast Sorcerous Restoration; got {sr}"
        )
    finally:
        await gm_client.patch(
            f"/api/campaign/{CAMPAIGN_ID}/character/{zara['id']}/sheet-fields",
            json={"class_slug": "sorcerer", "level": 5},
        )


async def test_sorcerous_restoration_skips_for_non_sorcerer(
    gm_client, gm_ws, roster,
):
    """Krieger (Barbarian) bumped to Lv 20 → short rest → no refund."""
    krieger = roster["Krieger Stonefist"]
    await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{krieger['id']}/sheet-fields",
        json={"class_slug": "barbarian", "level": 20},
    )
    try:
        gm_ws.mark()
        resp = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/character/{krieger['id']}/rest",
            json={"type": "short"},
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["sorcerous_restoration_sp"] == 0, (
            f"Barbarian should NOT trigger Sorcerous Restoration; "
            f"got {data.get('sorcerous_restoration_sp')}"
        )
        import asyncio as _asy
        await _asy.sleep(0.2)
        fu_msgs = gm_ws.buffered("feature_used")
        sr = [
            m for m in fu_msgs
            if (m.get("data") or {}).get("source") == "sorcerous-restoration"
        ]
        assert not sr, (
            f"Non-sorcerer should NOT broadcast Sorcerous Restoration; got {sr}"
        )
    finally:
        # Krieger's canonical fixture level — adjust if the demo
        # seed changes. As of v2.99.39 Krieger is Lv 5.
        await gm_client.patch(
            f"/api/campaign/{CAMPAIGN_ID}/character/{krieger['id']}/sheet-fields",
            json={"class_slug": "barbarian", "level": 5},
        )


async def test_sorcerous_restoration_caps_at_max(
    gm_client, gm_ws, zara_at_lv_20,
):
    """Lv 20 Zara at FULL SP → short rest → 0 refund (no overflow)."""
    zara = zara_at_lv_20
    # Zara has 5 SP max at Lv 5. After clean_pcs long rest she's at 5/5.
    # Don't spend any SP — short rest immediately.
    gm_ws.mark()
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{zara['id']}/rest",
        json={"type": "short"},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["sorcerous_restoration_sp"] == 0, (
        f"Full-SP Lv 20 Sorcerer should refund 0 (no overflow); "
        f"got {data.get('sorcerous_restoration_sp')}"
    )
    import asyncio as _asy
    await _asy.sleep(0.2)
    fu_msgs = gm_ws.buffered("feature_used")
    sr = [
        m for m in fu_msgs
        if (m.get("data") or {}).get("source") == "sorcerous-restoration"
    ]
    assert not sr, (
        f"Full-SP path should NOT broadcast Sorcerous Restoration; got {sr}"
    )
