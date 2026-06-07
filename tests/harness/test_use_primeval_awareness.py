"""v2.99.221 — Primeval Awareness (Ranger Lv 3+).

Phase F.3 final of the v2.99.193 phased completion plan —
**Phase F.3 ✅ COMPLETE (5/5)**. RAW PHB p.92: "Beginning at
3rd level, you can use your action and expend one ranger spell
slot to focus your awareness on the region around you. For 1
minute per level of the spell slot you expend, you can sense
whether the following types of creatures are present within
1 mile of you (or within up to 6 miles if you are in your
favored terrain): aberrations, celestials, dragons,
elementals, fey, fiends, and undead."

v1 ships announce-only. /use_primeval_awareness validates
Ranger Lv 3+ + Ranger slot >= 1 + action slot gate. Atomically
decrements the slot + marks the action chip + broadcasts
feature_used naming the 7 creature types + duration. GM
resolves whether any are present.

Rowan Quickbow (Ranger Lv 7 default) is the demo fixture —
already at Lv 3+ + has Ranger slots seeded.

Tests:
  - Happy: spend an L1 slot → 200 + broadcast + slot
    decremented.
  - Higher slot: spend an L2 slot → duration_min = 2.
  - Gate: out of slots → 409 no_slot.
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


def _pa_broadcasts(gm_ws, character_id):
    return [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "primeval-awareness"
        and (m.get("data") or {}).get("character_id") == character_id
    ]


@pytest_asyncio.fixture
async def rowan_with_slots(gm_client, roster):
    """Long-rest Rowan so his Ranger slots are full. Teardown
    does another long rest to leave him in a known state.
    """
    rowan = roster["Rowan Quickbow"]
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{rowan['id']}/rest",
        json={"type": "long"},
    )
    yield rowan
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{rowan['id']}/rest",
        json={"type": "long"},
    )


async def test_use_primeval_awareness_l1_happy_path(
    gm_client, gm_ws, rowan_with_slots,
):
    """Rowan Lv 7 spends an L1 Ranger slot → 200, duration=1 min."""
    rowan = rowan_with_slots
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_primeval_awareness",
        json={
            "character_id": rowan["id"],
            "slot_level": 1,
            "override": True,
        },
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["slot_level"] == 1
    assert data["duration_min"] == 1
    assert "aberrations" in data["creature_types"]
    assert len(data["creature_types"]) == 7
    await asyncio.sleep(0.3)
    feats = _pa_broadcasts(gm_ws, rowan["id"])
    assert feats, (
        f"v2.99.221: expected feature_used(source=primeval-awareness); "
        f"buffered={gm_ws.buffered()}"
    )


async def test_use_primeval_awareness_l2_longer_duration(
    gm_client, rowan_with_slots,
):
    """L2 slot → duration_min = 2."""
    rowan = rowan_with_slots
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_primeval_awareness",
        json={
            "character_id": rowan["id"],
            "slot_level": 2,
            "override": True,
        },
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["slot_level"] == 2
    assert data["duration_min"] == 2


async def test_use_primeval_awareness_no_slot(
    gm_client, rowan_with_slots,
):
    """Drain L1 slots → next call returns 409 no_slot.

    Rowan at Lv 7 has 4 L1 slots, 3 L2 slots, 2 L3 slots. Spend
    all L1s, then try one more.
    """
    rowan = rowan_with_slots
    # Spend 4 L1 slots.
    for _ in range(4):
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/use_primeval_awareness",
            json={
                "character_id": rowan["id"],
                "slot_level": 1,
                "override": True,
            },
        )
        assert r.status_code == 200, r.text
    # 5th call: 409 no_slot.
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_primeval_awareness",
        json={
            "character_id": rowan["id"],
            "slot_level": 1,
            "override": True,
        },
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "no_slot"
    assert data.get("level") == 1


async def test_primeval_awareness_undo_refunds_slot(
    gm_client, gm_ws, rowan_with_slots,
):
    """v2.99.464 — the chat-card ↶ Undo now refunds the Ranger slot
    Primeval Awareness spent. Cast at L1 (used → 1) → the response carries
    a `cast_id`; /undo_attack_damage with it broadcasts a
    `spell_slot_update` with the ranger L1 slot's used back to 0."""
    rowan = rowan_with_slots
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_primeval_awareness",
        json={"character_id": rowan["id"], "slot_level": 1, "override": True},
    )
    assert r.status_code == 200, r.text
    cast_id = r.json().get("cast_id")
    assert cast_id, "cast response must carry a cast_id for undo"

    gm_ws.mark()
    u = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/undo_attack_damage",
        json={"attack_id": cast_id},
    )
    assert u.status_code == 200, u.text
    ssu = await gm_ws.wait_for("spell_slot_update", timeout=2.0)
    assert ssu["data"]["class_slug"] == "ranger"
    assert ssu["data"]["level"] == 1
    assert ssu["data"]["used"] == 0  # slot refunded (1 → 0)
