"""v2.99.44 — Superior Inspiration (Bard Lv 20 capstone).

RAW (PHB p.54): "At 20th level, when you roll initiative and have no
uses of Bardic Inspiration left, you regain one use."

Hook lives in /battle PUT: when the battle transitions inactive →
active (the canonical "initiative was just rolled" moment), walks
combatants for PC Bards Lv 20+ whose bardic-inspiration resource is
at 0; refunds 1 use + broadcasts resource_update + feature_used.

Tests use the v2.99.39 capstone-test pattern (class-scoped level
PATCH) to temporarily bump Lyra to Lv 20.

Tests:
- happy: Lyra at Lv 20 with BI=0 + battle becomes active → BI=1 + broadcast.
- gate: Lv 19 → no refund.
- gate: BI > 0 → no refund (RAW "no uses left").
- gate: non-Bard at Lv 20 → no refund.
- gate: battle already active → no refund (only fires on transition).
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID


@pytest_asyncio.fixture
async def lyra_at_lv_20(gm_client, roster):
    """Bump Lyra to Lv 20 for the test, restore at end."""
    lyra = roster["Lyra Sunstrider"]
    await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{lyra['id']}/sheet-fields",
        json={"class_slug": "bard", "level": 20},
    )
    yield lyra
    await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{lyra['id']}/sheet-fields",
        json={"class_slug": "bard", "level": 6},
    )


def _tok(char):
    return {
        "id": f"tok_si_{char['id']}",
        "char_id": char["id"],
        "name": char["name"],
        "initiative": 10,
        "hp_current": 30,
        "hp_max": 30,
        "buffs": [],
        "economy": {"action": False, "bonus": False,
                    "reaction": False, "movement": 0},
    }


async def _drain_bardic_inspiration(gm_client, lyra_id, target_id):
    """Spend all 3 BI uses via /use_bardic_inspiration so the
    resource is at 0 going into the test.
    """
    for _ in range(3):
        await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/use_bardic_inspiration",
            json={
                "character_id": lyra_id,
                "target_character_id": target_id,
            },
        )


async def _set_battle_inactive(gm_client, combatants):
    """Reset battle to inactive=False so the next PUT-with-active=True
    cleanly triggers the transition hook.
    """
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": combatants, "turn_index": 0,
              "round": 1, "active": False},
    )


async def test_superior_inspiration_refunds_1_use_at_lv_20(
    gm_client, gm_ws, lyra_at_lv_20, roster,
):
    """Lv 20 Lyra with drained BI + battle goes from inactive → active
    → BI refunded to 1 + feature_used broadcast fires.
    """
    lyra = lyra_at_lv_20
    pip = roster["Pip Quickfingers"]
    # Drain Lyra's BI uses to 0.
    await _drain_bardic_inspiration(gm_client, lyra["id"], pip["id"])

    # Reset battle to inactive.
    combatants = [_tok(lyra), _tok(pip)]
    await _set_battle_inactive(gm_client, combatants)

    gm_ws.mark()
    # Battle becomes active (= initiative rolled).
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": combatants, "turn_index": 0,
              "round": 1, "active": True},
    )

    import asyncio as _asy
    await _asy.sleep(0.2)

    # Superior Inspiration broadcast fires.
    fu_msgs = gm_ws.buffered("feature_used")
    si = [
        m for m in fu_msgs
        if (m.get("data") or {}).get("source") == "superior-inspiration"
        and (m.get("data") or {}).get("character_id") == lyra["id"]
    ]
    assert si, (
        f"expected feature_used(source=superior-inspiration); buffered: "
        f"{[(m.get('type'), (m.get('data') or {}).get('source')) for m in gm_ws.buffered()]}"
    )

    # resource_update lands BI=1.
    ru_msgs = gm_ws.buffered("resource_update")
    bi = [
        m for m in ru_msgs
        if (m.get("data") or {}).get("character_id") == lyra["id"]
        and (m.get("data") or {}).get("key") == "bardic-inspiration"
    ]
    assert bi, (
        f"expected resource_update for bardic-inspiration; got: "
        f"{[(m.get('data') or {}).get('key') for m in ru_msgs]}"
    )
    last = bi[-1]["data"]
    assert last["current"] == 1, (
        f"expected BI current=1 post-trigger; got {last['current']}"
    )


async def test_superior_inspiration_skips_at_lv_19(
    gm_client, gm_ws, roster,
):
    """Lv 19 Lyra with drained BI + battle activates → NO refund."""
    lyra = roster["Lyra Sunstrider"]
    pip = roster["Pip Quickfingers"]
    await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{lyra['id']}/sheet-fields",
        json={"class_slug": "bard", "level": 19},
    )
    try:
        await _drain_bardic_inspiration(gm_client, lyra["id"], pip["id"])
        combatants = [_tok(lyra), _tok(pip)]
        await _set_battle_inactive(gm_client, combatants)
        gm_ws.mark()
        await gm_client.put(
            f"/api/campaign/{CAMPAIGN_ID}/battle",
            json={"combatants": combatants, "turn_index": 0,
                  "round": 1, "active": True},
        )
        import asyncio as _asy
        await _asy.sleep(0.2)
        fu_msgs = gm_ws.buffered("feature_used")
        si = [
            m for m in fu_msgs
            if (m.get("data") or {}).get("source") == "superior-inspiration"
        ]
        assert not si, (
            f"Lv 19 should NOT trigger Superior Inspiration; got {si}"
        )
    finally:
        await gm_client.patch(
            f"/api/campaign/{CAMPAIGN_ID}/character/{lyra['id']}/sheet-fields",
            json={"class_slug": "bard", "level": 6},
        )


async def test_superior_inspiration_skips_when_bi_above_zero(
    gm_client, gm_ws, lyra_at_lv_20, roster,
):
    """Lv 20 Lyra with BI=3 (full) + battle activates → NO refund
    (RAW: "no uses left" required).
    """
    lyra = lyra_at_lv_20
    pip = roster["Pip Quickfingers"]
    # Do NOT drain BI — clean_pcs already long-rested to BI=3.
    combatants = [_tok(lyra), _tok(pip)]
    await _set_battle_inactive(gm_client, combatants)
    gm_ws.mark()
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": combatants, "turn_index": 0,
              "round": 1, "active": True},
    )
    import asyncio as _asy
    await _asy.sleep(0.2)
    fu_msgs = gm_ws.buffered("feature_used")
    si = [
        m for m in fu_msgs
        if (m.get("data") or {}).get("source") == "superior-inspiration"
    ]
    assert not si, (
        f"BI > 0 should NOT trigger Superior Inspiration; got {si}"
    )


async def test_superior_inspiration_skips_for_non_bard(
    gm_client, gm_ws, roster,
):
    """Krieger (Barbarian) bumped to Lv 20 → no refund (no BI resource)."""
    krieger = roster["Krieger Stonefist"]
    await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{krieger['id']}/sheet-fields",
        json={"class_slug": "barbarian", "level": 20},
    )
    try:
        combatants = [_tok(krieger)]
        await _set_battle_inactive(gm_client, combatants)
        gm_ws.mark()
        await gm_client.put(
            f"/api/campaign/{CAMPAIGN_ID}/battle",
            json={"combatants": combatants, "turn_index": 0,
                  "round": 1, "active": True},
        )
        import asyncio as _asy
        await _asy.sleep(0.2)
        fu_msgs = gm_ws.buffered("feature_used")
        si = [
            m for m in fu_msgs
            if (m.get("data") or {}).get("source") == "superior-inspiration"
        ]
        assert not si, (
            f"Barbarian should NOT trigger Superior Inspiration; got {si}"
        )
    finally:
        await gm_client.patch(
            f"/api/campaign/{CAMPAIGN_ID}/character/{krieger['id']}/sheet-fields",
            json={"class_slug": "barbarian", "level": 5},
        )


async def test_superior_inspiration_only_fires_on_transition(
    gm_client, gm_ws, lyra_at_lv_20, roster,
):
    """Battle already active + drained BI + a re-PUT (e.g. GM tweaks
    turn_index) → NO refund. Hook only fires when active goes from
    False → True; subsequent re-PUTs that keep active=True don't
    re-trigger.
    """
    lyra = lyra_at_lv_20
    pip = roster["Pip Quickfingers"]
    # First put with active=True so the battle is "in progress."
    combatants = [_tok(lyra), _tok(pip)]
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": combatants, "turn_index": 0,
              "round": 1, "active": True},
    )
    # NOW drain BI (during combat).
    await _drain_bardic_inspiration(gm_client, lyra["id"], pip["id"])

    gm_ws.mark()
    # GM bumps turn_index. Battle was already active — hook should
    # NOT trigger Superior Inspiration.
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": combatants, "turn_index": 1,
              "round": 1, "active": True},
    )
    import asyncio as _asy
    await _asy.sleep(0.2)
    fu_msgs = gm_ws.buffered("feature_used")
    si = [
        m for m in fu_msgs
        if (m.get("data") or {}).get("source") == "superior-inspiration"
    ]
    assert not si, (
        f"Re-PUT mid-combat should NOT trigger Superior Inspiration; "
        f"got {si}"
    )
