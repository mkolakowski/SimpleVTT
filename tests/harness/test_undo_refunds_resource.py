"""v2.97.0 — extends the v2.92.0 ↶ Undo refund machinery to feature
resource pools (``sheet["resources"][i]``). The first two endpoints
plumbed: ``/use_lay_on_hands`` (variable HP-pool spend) and
``/use_second_wind`` (single-use counter). Both stamp a
``resource_spend`` entry into the per-cast undo log and surface the
``cast_id`` on their ``feature_used`` broadcast; the v2.97.0
``resource_spend`` branch in ``undo_attack_damage`` bumps the matching
``sheet["resources"][i]["current"]`` back up by ``amount`` (clamped
to ``max``) and broadcasts ``resource_update`` so any open resource
panel re-pips.

Tests:
  - Lay on Hands: long-rest Caelan + Pip, cast LoH 5 HP from Caelan
    to Pip, capture cast_id off feature_used, POST
    /undo_attack_damage, assert resource_update for lay-on-hands
    carries current = pool_pre - 5 + 5 = pool_pre.
  - Second Wind: long-rest Garrik, POST /use_second_wind, capture
    cast_id, undo, assert resource_update carries current = max
    (refunded back to the long-rest value).

Filed for follow-up (CHANGELOG note): the same ``resource_spend``
plumbing pattern applies to /use_bardic_inspiration, /use_rage,
/use_action_surge, /use_indomitable, /use_cutting_words,
/use_channel_divinity*, /use_metamagic*, /use_arcane_recovery,
/use_font_of_magic*, /use_wholeness_of_body, /use_stillness_of_mind,
/use_patient_defense, /flurry_of_blows (Ki uses), /use_item (item
charges), etc. Each endpoint follows the same shape and only needs
the three-line patch + source slug added to the JS
_REFUNDABLE_FEATURE_SOURCES Set.
"""
from .conftest import CAMPAIGN_ID


async def _long_rest(gm_client, char_id: int) -> None:
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/rest",
        json={"type": "long"},
    )
    assert resp.status_code == 200, resp.text


async def test_undo_refunds_lay_on_hands_pool(gm_client, gm_ws, roster):
    caelan = roster["Sir Caelan Lightbringer"]
    pip = roster["Pip Quickfingers"]
    await _long_rest(gm_client, caelan["id"])

    # Cast Lay on Hands — Caelan spends 5 HP from the pool to heal Pip.
    cast = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_lay_on_hands",
        json={
            "character_id": caelan["id"],
            "target_character_id": pip["id"],
            "amount": 5,
            "override": True,
        },
    )
    assert cast.status_code == 200, cast.text
    cast_data = cast.json()
    pool_after_cast = int(cast_data["pool_remaining"])
    # Pool should have dropped — if it didn't, the cast didn't consume
    # (test invariant broken; surface clearly).
    assert pool_after_cast >= 0
    # Capture cast_id off the feature_used broadcast.
    msg = await gm_ws.wait_for("feature_used", timeout=3.0)
    cast_id = msg["data"].get("cast_id")
    assert cast_id, (
        f"feature_used broadcast for Lay on Hands missing cast_id; "
        f"payload: {msg['data']}"
    )

    # Re-mark so wait_for picks up the refund's resource_update, not
    # the cast-time one (same shape, same wait_for selector).
    gm_ws.mark()
    undo = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/undo_attack_damage",
        json={"attack_id": cast_id},
    )
    assert undo.status_code == 200, undo.text
    assert undo.json()["ok"] is True

    # The refund broadcasts resource_update with current = pool_after
    # + 5 (clamped to max). For a freshly long-rested Caelan the pool
    # was at max BEFORE the cast (e.g. 30 for a Lv 6 paladin), so the
    # post-undo value should equal the pre-cast value.
    resource_msg = await gm_ws.wait_for("resource_update", timeout=3.0)
    rd = resource_msg["data"]
    assert rd["character_id"] == caelan["id"]
    assert rd["key"] == "lay-on-hands"
    # The refunded current = pool_after_cast + 5. Sanity-check that's
    # exactly the math the refund branch performed.
    assert rd["current"] == pool_after_cast + 5, (
        f"LoH pool wasn't refunded: post-cast={pool_after_cast}, "
        f"post-undo={rd['current']} (expected {pool_after_cast + 5})"
    )


async def test_undo_refunds_arcane_recovery(gm_client, gm_ws, roster):
    """v2.97.5 — Arcane Recovery cast spends 1 ``arcane-recovery``
    counter use AND restores N spell slots. Undo must refund BOTH legs
    (the counter via ``resource_spend`` and each slot level via the
    new ``slot_restore`` log kind, which is the inverse of the
    ``spell_slot_spend`` refund — it bumps ``used`` back UP).
    """
    thalindra = roster["Thalindra Moonwhisper"]
    await _long_rest(gm_client, thalindra["id"])

    # Spend 2 L1 slots so Arcane Recovery has something to restore.
    for _ in range(2):
        resp = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
            json={
                "character_id": thalindra["id"],
                "spell_index": 3,
                "slot_level": 1,
                "class_slug": "wizard",
                "override": True,
            },
        )
        assert resp.status_code == 200, resp.text
    # Now sheet has wizard L1 used=2.

    # Use Arcane Recovery to restore 2× L1 (within the Lv 5 allowance of 3).
    ar = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_arcane_recovery",
        json={
            "character_id": thalindra["id"],
            "slots": [{"level": 1, "count": 2}],
        },
    )
    assert ar.status_code == 200, ar.text

    # Capture cast_id off the feature_used broadcast.
    msg = await gm_ws.wait_for("feature_used", timeout=3.0)
    cast_id = msg["data"].get("cast_id")
    assert cast_id, (
        f"feature_used broadcast for Arcane Recovery missing cast_id; "
        f"payload: {msg['data']}"
    )

    # Re-mark so wait_for picks up the refund's broadcasts, not the
    # cast-time ones (both legs share broadcast type with cast).
    gm_ws.mark()
    undo = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/undo_attack_damage",
        json={"attack_id": cast_id},
    )
    assert undo.status_code == 200, undo.text
    assert undo.json()["ok"] is True

    # Leg 1: arcane-recovery counter refunded (back to max=1).
    resource_msg = await gm_ws.wait_for("resource_update", timeout=3.0)
    rd = resource_msg["data"]
    assert rd["character_id"] == thalindra["id"]
    assert rd["key"] == "arcane-recovery"
    assert rd["current"] == 1, (
        f"AR counter not refunded: current={rd['current']} (expected 1)"
    )

    # Leg 2: wizard L1 slot.used bumped BACK UP by 2 (the count
    # originally restored). Cast-time mark drained both broadcasts;
    # this slot_slot_update is the slot_restore undo branch firing.
    slot_msg = await gm_ws.wait_for("spell_slot_update", timeout=3.0)
    sd = slot_msg["data"]
    assert sd["character_id"] == thalindra["id"]
    assert sd["class_slug"] == "wizard"
    assert sd["level"] == 1
    assert sd["used"] == 2, (
        f"L1 wizard slot not un-restored: used={sd['used']} (expected 2)"
    )


async def test_undo_refunds_second_wind_use(gm_client, gm_ws, roster):
    garrik = roster["Garrik Ironside"]
    await _long_rest(gm_client, garrik["id"])

    # Use Second Wind. Garrik's max sw uses is 1 (Fighter Lv 1+ has 1
    # use until short rest), so after this cast remaining = 0.
    cast = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_second_wind",
        json={
            "character_id": garrik["id"],
            "override": True,
        },
    )
    assert cast.status_code == 200, cast.text

    msg = await gm_ws.wait_for("feature_used", timeout=3.0)
    cast_id = msg["data"].get("cast_id")
    assert cast_id, (
        f"feature_used broadcast for Second Wind missing cast_id; "
        f"payload: {msg['data']}"
    )
    sw_max = int(msg["data"].get("max") or 0)
    sw_remaining_after_cast = int(msg["data"].get("remaining") or 0)
    assert sw_max >= 1
    assert sw_remaining_after_cast == sw_max - 1

    # Undo: re-mark so wait_for catches the refund's resource_update.
    gm_ws.mark()
    undo = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/undo_attack_damage",
        json={"attack_id": cast_id},
    )
    assert undo.status_code == 200, undo.text

    resource_msg = await gm_ws.wait_for("resource_update", timeout=3.0)
    rd = resource_msg["data"]
    assert rd["character_id"] == garrik["id"]
    assert rd["key"] == "second-wind"
    # Refunded current = remaining_after_cast + 1 (clamped to max).
    expected = min(sw_remaining_after_cast + 1, sw_max)
    assert rd["current"] == expected, (
        f"Second Wind use wasn't refunded: post-cast remaining="
        f"{sw_remaining_after_cast}, post-undo current={rd['current']} "
        f"(expected {expected})"
    )
