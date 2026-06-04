"""v2.99.210 — Perfect Self (Monk Lv 20).

Phase F.2 final of the v2.99.193 phased completion plan. RAW
PHB p.79: "At 20th level, when you roll for initiative and have
no ki points remaining, you regain 4 ki points."

Direct mirror of v2.99.44 Superior Inspiration. Hook lives in
/battle PUT's inactive → active transition (the canonical "rolled
initiative" moment). Walks PC Monks Lv 20+; if their ki-points
resource is at 0, refunds 4 ki + broadcasts feature_used +
resource_update.

Kael Brightleaf is the demo fixture; tests PATCH him Lv 7 → 20
+ seed ki-points 0/15.

Tests:
  - Happy: Kael Lv 20, ki=0 → /battle PUT (inactive → active) →
    ki refunded to 4 + feature_used(source=perfect-self) fires.
  - Skips at ki > 0: Kael Lv 20, ki=2 → no refund / broadcast.
  - Skips below Lv 20.
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


async def _seed_battle_inactive_then_active(gm_client, kael):
    """Seed an inactive battle, then PUT to active to trigger the
    inactive → active transition the hook listens for.
    """
    kael_tok = f"tok_ps_{kael['id']}"
    # Inactive first.
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": [
            {"id": kael_tok, "char_id": kael["id"],
             "name": kael["name"], "initiative": 10,
             "hp_current": 47, "hp_max": 47,
             "buffs": [],
             "economy": {"action": False, "bonus": False,
                         "reaction": False, "movement": 0}},
        ], "turn_index": 0, "round": 1, "active": False},
    )
    # Now activate.
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": [
            {"id": kael_tok, "char_id": kael["id"],
             "name": kael["name"], "initiative": 10,
             "hp_current": 47, "hp_max": 47,
             "buffs": [],
             "economy": {"action": False, "bonus": False,
                         "reaction": False, "movement": 0}},
        ], "turn_index": 0, "round": 1, "active": True},
    )


def _ps_broadcasts(gm_ws, character_id):
    return [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "perfect-self"
        and (m.get("data") or {}).get("character_id") == character_id
    ]


@pytest_asyncio.fixture
async def kael_lv20_zero_ki(gm_client, roster):
    """PATCH Kael to Lv 20 + ki=0/15. Restore Lv 7 in teardown."""
    kael = roster["Kael Brightleaf"]
    await _patch_sheet(
        gm_client, kael["id"], {"level": 20},
        class_slug="monk",
    )
    await _patch_sheet(
        gm_client, kael["id"],
        {"resources": [
            {"key": "ki-points", "label": "Ki Points",
             "current": 0, "max": 15, "reset": "short"},
        ]},
    )
    yield kael
    await _patch_sheet(
        gm_client, kael["id"], {"level": 7},
        class_slug="monk",
    )
    await _patch_sheet(
        gm_client, kael["id"],
        {"resources": [
            {"key": "ki-points", "label": "Ki Points",
             "current": 7, "max": 7, "reset": "short"},
        ]},
    )


async def test_perfect_self_refunds_4_ki_on_init(
    gm_client, gm_ws, kael_lv20_zero_ki,
):
    """Kael Lv 20, ki=0 → battle PUT inactive→active → ki refunded
    to 4 + feature_used(source=perfect-self) broadcast fires.
    """
    kael = kael_lv20_zero_ki
    gm_ws.mark()
    await _seed_battle_inactive_then_active(gm_client, kael)
    await asyncio.sleep(0.3)
    feats = _ps_broadcasts(gm_ws, kael["id"])
    assert feats, (
        f"v2.99.210: expected feature_used(source=perfect-self) "
        f"on init; buffered={gm_ws.buffered()}"
    )
    feat_data = feats[-1].get("data") or {}
    assert feat_data.get("granted") == 4
    assert feat_data.get("remaining") == 4


async def test_perfect_self_skips_when_ki_above_zero(
    gm_client, gm_ws, roster,
):
    """Control: Kael Lv 20 + ki=2 (non-zero) → no refund."""
    kael = roster["Kael Brightleaf"]
    pre_level = 7
    await _patch_sheet(
        gm_client, kael["id"], {"level": 20},
        class_slug="monk",
    )
    await _patch_sheet(
        gm_client, kael["id"],
        {"resources": [
            {"key": "ki-points", "label": "Ki Points",
             "current": 2, "max": 15, "reset": "short"},
        ]},
    )
    try:
        gm_ws.mark()
        await _seed_battle_inactive_then_active(gm_client, kael)
        await asyncio.sleep(0.3)
        feats = _ps_broadcasts(gm_ws, kael["id"])
        assert not feats, (
            f"v2.99.210: Perfect Self shouldn't fire when ki > 0; "
            f"got {feats}"
        )
    finally:
        await _patch_sheet(
            gm_client, kael["id"], {"level": pre_level},
            class_slug="monk",
        )
        await _patch_sheet(
            gm_client, kael["id"],
            {"resources": [
                {"key": "ki-points", "label": "Ki Points",
                 "current": 7, "max": 7, "reset": "short"},
            ]},
        )


async def test_perfect_self_skips_below_lv20(
    gm_client, gm_ws, roster,
):
    """Control: Kael at Lv 7 default → no refund even when ki=0."""
    kael = roster["Kael Brightleaf"]
    await _patch_sheet(
        gm_client, kael["id"],
        {"resources": [
            {"key": "ki-points", "label": "Ki Points",
             "current": 0, "max": 7, "reset": "short"},
        ]},
    )
    try:
        gm_ws.mark()
        await _seed_battle_inactive_then_active(gm_client, kael)
        await asyncio.sleep(0.3)
        feats = _ps_broadcasts(gm_ws, kael["id"])
        assert not feats, (
            f"v2.99.210: Perfect Self shouldn't fire at Lv 7; "
            f"got {feats}"
        )
    finally:
        await _patch_sheet(
            gm_client, kael["id"],
            {"resources": [
                {"key": "ki-points", "label": "Ki Points",
                 "current": 7, "max": 7, "reset": "short"},
            ]},
        )
