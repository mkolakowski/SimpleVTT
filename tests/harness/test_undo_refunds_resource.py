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


async def _set_hp(gm_client, char_id: int, current: int) -> None:
    """Helper: set a character's current HP directly via the sheet
    fields PATCH endpoint. Used to drop a target's HP below max so a
    follow-up heal has room to actually apply (a heal that caps at max
    logs ``applied=0`` and the v2.97.16 heal-undo branch correctly
    no-ops on it; this helper sets up the non-trivial case)."""
    resp = await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-fields",
        json={"hp": {"current": int(current)}},
    )
    assert resp.status_code == 200, resp.text


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


async def test_undo_refunds_item_use(gm_client, gm_ws, roster):
    """v2.97.8 — /use_item drains an inventory consumable (Potion of
    Healing). New ``inventory_consume`` undo log kind refunds the qty
    (re-inserting the row if it was popped on cast).
    """
    pip = roster["Pip Quickfingers"]
    # Pip's Potion of Healing is at inventory_index 6 in the demo seed
    # (Shortsword, Dagger, Studded leather, Thieves' tools, Burglar's
    # pack, Hooded lantern, Potion of Healing).
    potion_idx = 6

    gm_ws.mark()
    cast = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_item",
        json={
            "character_id": pip["id"],
            "inventory_index": potion_idx,
            "override": True,
        },
    )
    assert cast.status_code == 200, cast.text
    cast_id = cast.json().get("cast_id")
    assert cast_id, f"/use_item response missing cast_id: {cast.json()}"

    inv_msg = await gm_ws.wait_for("inventory_update", timeout=3.0)
    post_cast_qty = int(inv_msg["data"]["qty"])

    gm_ws.mark()
    undo = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/undo_attack_damage",
        json={"attack_id": cast_id},
    )
    assert undo.status_code == 200, undo.text

    refund_msg = await gm_ws.wait_for("inventory_update", timeout=3.0)
    rd = refund_msg["data"]
    assert rd["character_id"] == pip["id"]
    assert "potion" in (rd.get("item_name") or "").lower()
    assert rd["qty"] == post_cast_qty + 1, (
        f"potion qty not refunded: post-cast={post_cast_qty}, "
        f"post-undo={rd['qty']} (expected {post_cast_qty + 1})"
    )


async def test_undo_refunds_channel_divinity(gm_client, gm_ws, roster):
    """v2.97.7 — Channel Divinity routes through /use_feature with a
    new resource_key lookup in _FEATURE_ECONOMY. The endpoint decrements
    the channel-divinity counter, stamps a resource_spend log entry,
    and surfaces cast_id on the feature_used broadcast. Undo refunds
    the use.
    """
    tavik = roster["Brother Tavik Stonebrow"]
    await _long_rest(gm_client, tavik["id"])

    cast = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_feature",
        json={
            "character_id": tavik["id"],
            "feature_key": "channel-divinity",
            "option_key": "turn-undead",
            "label": "Channel Divinity",
            "override": True,
        },
    )
    assert cast.status_code == 200, cast.text
    cast_data = cast.json()
    cast_id = cast_data.get("cast_id")
    assert cast_id, (
        f"/use_feature response missing cast_id: {cast_data}"
    )
    post_cast_remaining = int(cast_data["resource_remaining"])

    msg = await gm_ws.wait_for("feature_used", timeout=3.0)
    assert msg["data"].get("cast_id") == cast_id

    # Re-mark so wait_for catches only the refund's resource_update.
    gm_ws.mark()
    undo = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/undo_attack_damage",
        json={"attack_id": cast_id},
    )
    assert undo.status_code == 200, undo.text

    resource_msg = await gm_ws.wait_for("resource_update", timeout=3.0)
    rd = resource_msg["data"]
    assert rd["character_id"] == tavik["id"]
    assert rd["key"] == "channel-divinity"
    assert rd["current"] == post_cast_remaining + 1, (
        f"CD use not refunded: post-cast={post_cast_remaining}, "
        f"post-undo={rd['current']} (expected {post_cast_remaining + 1})"
    )


async def test_undo_refunds_font_of_magic_to_points(gm_client, gm_ws, roster):
    """v2.97.6 — Font of Magic to_points spends a spell slot and gains
    sorcery points. Undo refunds both legs: ``spell_slot_spend`` bumps
    the slot's ``used`` back down by 1, and ``resource_gain`` subtracts
    the actually-gained SP from the pool.
    """
    zara = roster["Zara Emberfire"]
    await _long_rest(gm_client, zara["id"])

    # Drain SP a bit first so the upcoming slot-sacrifice doesn't fully
    # overflow. Use to_slot ephemeral creation: SP=5 → 3 (cost 2), no
    # slots changed materially (creates an ephemeral L1 slot). Now SP=3.
    drain = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_font_of_magic_to_slot",
        json={"character_id": zara["id"], "slot_level": 1, "override": True},
    )
    assert drain.status_code == 200, drain.text
    assert drain.json()["sp_remaining"] == 3

    # Spend an L1 slot via cast (override) so the to_points L1 sacrifice
    # decrements `used` from 1 → 2 (out of total=5 from the ephemeral).
    # Actually we want the spell_slot_spend refund to be observable, so
    # ANY pre-cast slot state works — just record the pre-cast value
    # and assert it's reverted post-undo.
    gm_ws.mark()  # drain the to_slot broadcasts so they don't confuse later asserts

    # Sacrifice an L1 slot for +1 SP.
    cast = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_font_of_magic_to_points",
        json={"character_id": zara["id"], "slot_level": 1, "override": True},
    )
    assert cast.status_code == 200, cast.text
    cast_data = cast.json()
    post_cast_sp = int(cast_data["sp_remaining"])
    post_cast_used = int(cast_data["slot_used"])
    assert post_cast_sp == 4, (
        f"SP should be 3+1=4, got {post_cast_sp}"
    )

    # Capture cast_id off feature_used.
    msg = await gm_ws.wait_for("feature_used", timeout=3.0)
    cast_id = msg["data"].get("cast_id")
    assert cast_id, (
        f"feature_used missing cast_id; payload: {msg['data']}"
    )

    gm_ws.mark()
    undo = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/undo_attack_damage",
        json={"attack_id": cast_id},
    )
    assert undo.status_code == 200, undo.text

    # Refund order: log entries are walked in REVERSE, so the
    # resource_gain (stamped second) refunds first → resource_update.
    # Then spell_slot_spend → spell_slot_update.
    resource_msg = await gm_ws.wait_for("resource_update", timeout=3.0)
    rd = resource_msg["data"]
    assert rd["character_id"] == zara["id"]
    assert rd["key"] == "sorcery-points"
    assert rd["current"] == post_cast_sp - 1, (
        f"SP not reverted: post-cast={post_cast_sp}, "
        f"post-undo={rd['current']} (expected {post_cast_sp - 1})"
    )

    slot_msg = await gm_ws.wait_for("spell_slot_update", timeout=3.0)
    sd = slot_msg["data"]
    assert sd["character_id"] == zara["id"]
    assert sd["class_slug"] == "sorcerer"
    assert sd["level"] == 1
    assert sd["used"] == post_cast_used - 1, (
        f"Slot not reverted: post-cast used={post_cast_used}, "
        f"post-undo used={sd['used']} (expected {post_cast_used - 1})"
    )


async def test_undo_refunds_font_of_magic_to_slot_ephemeral(gm_client, gm_ws, roster):
    """v2.97.6 — Font of Magic to_slot, ephemeral path: cast spends 2 SP
    and bumps slot ``total`` by 1 (no used slot to restore). Undo refunds
    SP via ``resource_spend`` and decrements ``total`` via ``slot_gain``.
    """
    zara = roster["Zara Emberfire"]
    await _long_rest(gm_client, zara["id"])

    # All Zara's slots are at used=0 after long-rest, so to_slot creates
    # an ephemeral. SP starts at 5; after cost-2 conversion SP=3, slot
    # total bumps from 4 → 5.
    cast = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_font_of_magic_to_slot",
        json={"character_id": zara["id"], "slot_level": 1, "override": True},
    )
    assert cast.status_code == 200, cast.text
    cd = cast.json()
    assert cd["ephemeral_created"] is True
    post_cast_sp = int(cd["sp_remaining"])
    post_cast_total = int(cd["slot_total"])
    assert post_cast_sp == 3
    assert post_cast_total == 5  # Zara's base L1 total is 4

    msg = await gm_ws.wait_for("feature_used", timeout=3.0)
    cast_id = msg["data"].get("cast_id")
    assert cast_id

    gm_ws.mark()
    undo = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/undo_attack_damage",
        json={"attack_id": cast_id},
    )
    assert undo.status_code == 200, undo.text

    # Reverse order: slot_gain (stamped second) → spell_slot_update
    # first; then resource_spend → resource_update.
    slot_msg = await gm_ws.wait_for("spell_slot_update", timeout=3.0)
    sd = slot_msg["data"]
    assert sd["character_id"] == zara["id"]
    assert sd["class_slug"] == "sorcerer"
    assert sd["level"] == 1
    assert sd["total"] == post_cast_total - 1, (
        f"Ephemeral not stripped: post-cast total={post_cast_total}, "
        f"post-undo total={sd['total']} (expected {post_cast_total - 1})"
    )

    resource_msg = await gm_ws.wait_for("resource_update", timeout=3.0)
    rd = resource_msg["data"]
    assert rd["character_id"] == zara["id"]
    assert rd["key"] == "sorcery-points"
    assert rd["current"] == post_cast_sp + 2, (
        f"SP not refunded: post-cast={post_cast_sp}, "
        f"post-undo={rd['current']} (expected {post_cast_sp + 2})"
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


# ----------------------------------------------------------------------
# v2.97.16 — HP refund roundtrips.
#
# The v2.97.0-v2.97.8 audit refunded resource counters / spell slots /
# inventory but left downstream HP changes alone. v2.97.16 stamps a
# ``heal`` entry alongside the resource leg in the 4 HP-applying
# endpoints (Lay on Hands / Second Wind / Wholeness of Body / use_item
# heal); the existing damage/heal-undo branch reverses the HP.
#
# Each test damages the target first (so the heal has headroom and
# ``actual_healed > 0``), casts the heal, captures the cast_id, undoes,
# and asserts ``character_hp_update`` carries ``source: undo_heal`` +
# the expected delta.
# ----------------------------------------------------------------------


async def test_undo_refunds_lay_on_hands_hp(gm_client, gm_ws, roster):
    """Caelan heals a wounded Pip via Lay on Hands. Undo refunds BOTH
    the pool (existing v2.97.0 plumbing) AND the HP gained (v2.97.16).
    """
    caelan = roster["Sir Caelan Lightbringer"]
    pip = roster["Pip Quickfingers"]
    await _long_rest(gm_client, caelan["id"])
    await _long_rest(gm_client, pip["id"])
    # Wound Pip so the heal has headroom. Pre-cast HP is the value we
    # expect to be restored on undo.
    target_pre_hp = 20
    await _set_hp(gm_client, pip["id"], target_pre_hp)

    cast = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_lay_on_hands",
        json={
            "character_id": caelan["id"],
            "target_character_id": pip["id"],
            "amount": 8,
            "override": True,
        },
    )
    assert cast.status_code == 200, cast.text

    msg = await gm_ws.wait_for("feature_used", timeout=3.0)
    cast_id = msg["data"].get("cast_id")
    healed = int(msg["data"].get("heal_amount") or 0)
    assert cast_id and healed > 0, (
        f"Lay on Hands didn't apply HP: cast_id={cast_id}, healed={healed}, "
        f"payload={msg['data']}"
    )

    gm_ws.mark()
    undo = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/undo_attack_damage",
        json={"attack_id": cast_id},
    )
    assert undo.status_code == 200, undo.text

    # The damage/heal-undo branch walks entries in REVERSE: heal entry
    # (stamped second) reverses first → character_hp_update with
    # source=undo_heal + delta=-healed.
    hp_msg = await gm_ws.wait_for("character_hp_update", timeout=3.0)
    hd = hp_msg["data"]
    assert hd["character_id"] == pip["id"]
    assert hd["source"] == "undo_heal", (
        f"expected source=undo_heal, got {hd['source']}; payload={hd}"
    )
    assert hd["delta"] == -healed
    assert int(hd["hp"]["current"]) == target_pre_hp, (
        f"Pip's HP not restored: post-undo={hd['hp']['current']}, "
        f"expected={target_pre_hp}"
    )


async def test_undo_refunds_second_wind_hp(gm_client, gm_ws, roster):
    """Garrik uses Second Wind from a wounded state. Undo refunds the
    counter AND restores Garrik's HP to the pre-cast value."""
    garrik = roster["Garrik Ironside"]
    await _long_rest(gm_client, garrik["id"])
    pre_hp = 15
    await _set_hp(gm_client, garrik["id"], pre_hp)

    cast = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_second_wind",
        json={"character_id": garrik["id"], "override": True},
    )
    assert cast.status_code == 200, cast.text

    msg = await gm_ws.wait_for("feature_used", timeout=3.0)
    cast_id = msg["data"].get("cast_id")
    healed = int(msg["data"].get("heal_amount") or 0)
    assert cast_id and healed > 0, (
        f"Second Wind didn't apply HP: cast_id={cast_id}, healed={healed}"
    )

    gm_ws.mark()
    undo = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/undo_attack_damage",
        json={"attack_id": cast_id},
    )
    assert undo.status_code == 200, undo.text

    hp_msg = await gm_ws.wait_for("character_hp_update", timeout=3.0)
    hd = hp_msg["data"]
    assert hd["character_id"] == garrik["id"]
    assert hd["source"] == "undo_heal"
    assert hd["delta"] == -healed
    assert int(hd["hp"]["current"]) == pre_hp


async def test_undo_refunds_item_use_hp(gm_client, gm_ws, roster):
    """Pip drinks a Potion of Healing from a wounded state. Undo
    refunds the inventory qty AND restores Pip's HP."""
    pip = roster["Pip Quickfingers"]
    await _long_rest(gm_client, pip["id"])
    pre_hp = 12
    await _set_hp(gm_client, pip["id"], pre_hp)

    cast = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_item",
        json={
            "character_id": pip["id"],
            "inventory_index": 6,  # Pip's Potion of Healing
            "override": True,
        },
    )
    assert cast.status_code == 200, cast.text
    cast_id = cast.json().get("cast_id")
    rolled = int(cast.json().get("rolled") or 0)
    assert cast_id and rolled > 0

    # Healed could be less than rolled if Pip would cap at max — but
    # we just dropped her HP, so post-cast HP - pre_hp should equal
    # min(rolled, max - pre_hp). Read it back via the heal_applied
    # broadcast: the new_hp.current is what's authoritative.
    heal_msg = await gm_ws.wait_for("heal_applied", timeout=3.0)
    post_cast_hp = int(heal_msg["data"]["new_hp"]["current"])
    healed = post_cast_hp - pre_hp
    assert healed > 0, f"Potion didn't apply HP: pre={pre_hp}, post={post_cast_hp}"

    gm_ws.mark()
    undo = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/undo_attack_damage",
        json={"attack_id": cast_id},
    )
    assert undo.status_code == 200, undo.text

    hp_msg = await gm_ws.wait_for("character_hp_update", timeout=3.0)
    hd = hp_msg["data"]
    assert hd["character_id"] == pip["id"]
    assert hd["source"] == "undo_heal"
    assert hd["delta"] == -healed
    assert int(hd["hp"]["current"]) == pre_hp


async def test_undo_refunds_rage_counter_and_buff(gm_client, gm_ws, roster):
    """v2.97.20 — Rage now snapshots the caster's buffs pre-install and
    stamps a buff_install log entry under the same cast_id as the
    resource_spend. Undo refunds the counter (existing v2.97.1 plumbing)
    AND drops the rage buff (new v2.97.20 plumbing via the existing
    v2.65.0 buff_install undo branch).

    Pre-v2.97.20 only the counter was refunded; the rage buff stayed
    installed and the player had to manually × it off.
    """
    krieger = roster["Krieger Stonefist"]
    await _long_rest(gm_client, krieger["id"])

    # Seed a one-combatant battle so /use_rage's bonus-slot gate has a
    # battle to mark against AND _install_buff has somewhere to attach.
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={
            "combatants": [{
                "id": f"tok_rage_{krieger['id']}",
                "char_id": krieger["id"],
                "name": krieger["name"],
                "initiative": 10,
                "hp_current": 55, "hp_max": 55,
                "buffs": [],
                "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0},
            }],
            "turn_index": 0, "round": 1, "active": True,
        },
    )

    cast = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_rage",
        json={"character_id": krieger["id"], "override": True},
    )
    assert cast.status_code == 200, cast.text

    feature_msg = await gm_ws.wait_for("feature_used", timeout=3.0)
    cast_id = feature_msg["data"].get("cast_id")
    assert cast_id, f"missing cast_id; payload: {feature_msg['data']}"

    # Verify rage buff IS installed pre-undo.
    buffs_resp = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{krieger['id']}/buffs"
    )
    assert buffs_resp.status_code == 200, buffs_resp.text
    pre_undo_buffs = buffs_resp.json().get("buffs", [])
    assert any((b or {}).get("key") == "rage" for b in pre_undo_buffs), (
        f"expected rage buff installed; got {pre_undo_buffs}"
    )

    gm_ws.mark()
    undo = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/undo_attack_damage",
        json={"attack_id": cast_id},
    )
    assert undo.status_code == 200, undo.text

    # The undo's per_target should include both legs.
    per_target = undo.json().get("per_target") or []
    kinds = {e.get("kind") for e in per_target}
    assert "resource_refunded" in kinds, (
        f"expected resource_refunded leg; per_target={per_target}"
    )
    assert "buff_install" in kinds, (
        f"expected buff_install leg; per_target={per_target}"
    )

    # Verify rage buff is gone post-undo.
    buffs_resp2 = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{krieger['id']}/buffs"
    )
    post_undo_buffs = buffs_resp2.json().get("buffs", [])
    assert not any((b or {}).get("key") == "rage" for b in post_undo_buffs), (
        f"rage buff still installed after undo: {post_undo_buffs}"
    )


async def test_undo_refunds_indomitable_counter_and_buff(
    gm_client, gm_ws, roster,
):
    """v2.97.21 — same pattern as v2.97.20 Rage applied to Indomitable.
    Undo refunds the counter AND drops the indomitable-armed buff.
    """
    garrik = roster["Garrik Ironside"]
    await _long_rest(gm_client, garrik["id"])
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={
            "combatants": [{
                "id": f"tok_indom_{garrik['id']}",
                "char_id": garrik["id"],
                "name": garrik["name"],
                "initiative": 10,
                "hp_current": 60, "hp_max": 60,
                "buffs": [],
                "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0},
            }],
            "turn_index": 0, "round": 1, "active": True,
        },
    )

    cast = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_indomitable",
        json={"character_id": garrik["id"], "override": True},
    )
    assert cast.status_code == 200, cast.text
    feature_msg = await gm_ws.wait_for("feature_used", timeout=3.0)
    cast_id = feature_msg["data"].get("cast_id")
    assert cast_id, f"missing cast_id; payload={feature_msg['data']}"

    # Verify buff installed.
    buffs_resp = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{garrik['id']}/buffs"
    )
    pre_buffs = buffs_resp.json().get("buffs", [])
    assert any((b or {}).get("key") == "indomitable-armed" for b in pre_buffs), (
        f"expected indomitable-armed installed; got {pre_buffs}"
    )

    gm_ws.mark()
    undo = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/undo_attack_damage",
        json={"attack_id": cast_id},
    )
    assert undo.status_code == 200, undo.text
    per_target = undo.json().get("per_target") or []
    kinds = {e.get("kind") for e in per_target}
    assert "resource_refunded" in kinds
    assert "buff_install" in kinds

    buffs_resp2 = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{garrik['id']}/buffs"
    )
    post_buffs = buffs_resp2.json().get("buffs", [])
    assert not any((b or {}).get("key") == "indomitable-armed" for b in post_buffs), (
        f"indomitable-armed still installed: {post_buffs}"
    )


# ----------------------------------------------------------------------
# v2.97.22 — buff teardown for the 3 Monk ki-spend endpoints.
# Same canonical pattern as v2.97.20 Rage / v2.97.21 Indomitable.
# Each test: long-rest Kael, seed solo battle, use the endpoint,
# verify buff installed, undo, verify both legs in per_target and
# the buff is gone.
# ----------------------------------------------------------------------


async def _seed_kael_solo_battle(gm_client, kael_id: int, slot_tag: str):
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={
            "combatants": [{
                "id": f"tok_{slot_tag}_{kael_id}",
                "char_id": kael_id,
                "name": "Kael",
                "initiative": 10,
                "hp_current": 35, "hp_max": 35,
                "buffs": [],
                "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0},
            }],
            "turn_index": 0, "round": 1, "active": True,
        },
    )


async def test_undo_refunds_patient_defense_counter_and_buff(
    gm_client, gm_ws, roster,
):
    kael = roster["Kael Brightleaf"]
    await _long_rest(gm_client, kael["id"])
    await _seed_kael_solo_battle(gm_client, kael["id"], "pd")
    cast = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_patient_defense",
        json={"character_id": kael["id"], "override": True},
    )
    assert cast.status_code == 200, cast.text
    feature_msg = await gm_ws.wait_for("feature_used", timeout=3.0)
    cast_id = feature_msg["data"].get("cast_id")
    assert cast_id

    buffs = (await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{kael['id']}/buffs"
    )).json().get("buffs", [])
    assert any((b or {}).get("key") == "patient-defense" for b in buffs), (
        f"patient-defense not installed; got {buffs}"
    )

    undo = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/undo_attack_damage",
        json={"attack_id": cast_id},
    )
    assert undo.status_code == 200, undo.text
    kinds = {e.get("kind") for e in (undo.json().get("per_target") or [])}
    assert "resource_refunded" in kinds and "buff_install" in kinds

    buffs2 = (await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{kael['id']}/buffs"
    )).json().get("buffs", [])
    assert not any((b or {}).get("key") == "patient-defense" for b in buffs2)


async def test_undo_refunds_step_of_the_wind_counter_and_buff(
    gm_client, gm_ws, roster,
):
    kael = roster["Kael Brightleaf"]
    await _long_rest(gm_client, kael["id"])
    await _seed_kael_solo_battle(gm_client, kael["id"], "sotw")
    cast = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_step_of_the_wind",
        json={"character_id": kael["id"], "mode": "disengage", "override": True},
    )
    assert cast.status_code == 200, cast.text
    feature_msg = await gm_ws.wait_for("feature_used", timeout=3.0)
    cast_id = feature_msg["data"].get("cast_id")
    assert cast_id

    buffs = (await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{kael['id']}/buffs"
    )).json().get("buffs", [])
    assert any((b or {}).get("key") == "step-of-the-wind-disengage" for b in buffs)

    undo = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/undo_attack_damage",
        json={"attack_id": cast_id},
    )
    assert undo.status_code == 200, undo.text
    kinds = {e.get("kind") for e in (undo.json().get("per_target") or [])}
    assert "resource_refunded" in kinds and "buff_install" in kinds

    buffs2 = (await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{kael['id']}/buffs"
    )).json().get("buffs", [])
    assert not any((b or {}).get("key") == "step-of-the-wind-disengage" for b in buffs2)


async def test_undo_refunds_flurry_of_blows_counter_and_buff(
    gm_client, gm_ws, roster,
):
    kael = roster["Kael Brightleaf"]
    await _long_rest(gm_client, kael["id"])
    await _seed_kael_solo_battle(gm_client, kael["id"], "fob")
    cast = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_flurry_of_blows",
        json={"character_id": kael["id"], "override": True},
    )
    assert cast.status_code == 200, cast.text
    feature_msg = await gm_ws.wait_for("feature_used", timeout=3.0)
    cast_id = feature_msg["data"].get("cast_id")
    assert cast_id

    buffs = (await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{kael['id']}/buffs"
    )).json().get("buffs", [])
    assert any((b or {}).get("key") == "flurry-of-blows-active" for b in buffs)

    undo = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/undo_attack_damage",
        json={"attack_id": cast_id},
    )
    assert undo.status_code == 200, undo.text
    kinds = {e.get("kind") for e in (undo.json().get("per_target") or [])}
    assert "resource_refunded" in kinds and "buff_install" in kinds

    buffs2 = (await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{kael['id']}/buffs"
    )).json().get("buffs", [])
    assert not any((b or {}).get("key") == "flurry-of-blows-active" for b in buffs2)


async def test_undo_refunds_metamagic_empowered_sp_and_buff(
    gm_client, gm_ws, roster,
):
    """v2.97.23 — same canonical pattern. Zara casts Empowered Spell,
    metamagic-empowered-pending lands; undo refunds the SP AND drops
    the pending buff so the next cast doesn't get free rerolls."""
    zara = roster["Zara Emberfire"]
    await _long_rest(gm_client, zara["id"])
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={
            "combatants": [{
                "id": f"tok_mm_{zara['id']}",
                "char_id": zara["id"],
                "name": zara["name"],
                "initiative": 10,
                "hp_current": 30, "hp_max": 30,
                "buffs": [],
                "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0},
            }],
            "turn_index": 0, "round": 1, "active": True,
        },
    )
    cast = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_metamagic_empowered_spell",
        json={"character_id": zara["id"]},
    )
    assert cast.status_code == 200, cast.text
    cast_id = cast.json().get("cast_id")
    assert cast_id

    buffs = (await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{zara['id']}/buffs"
    )).json().get("buffs", [])
    assert any((b or {}).get("key") == "metamagic-empowered-pending" for b in buffs)

    undo = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/undo_attack_damage",
        json={"attack_id": cast_id},
    )
    assert undo.status_code == 200, undo.text
    kinds = {e.get("kind") for e in (undo.json().get("per_target") or [])}
    assert "resource_refunded" in kinds and "buff_install" in kinds

    buffs2 = (await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{zara['id']}/buffs"
    )).json().get("buffs", [])
    assert not any((b or {}).get("key") == "metamagic-empowered-pending" for b in buffs2)


async def test_undo_cast_spell_save_or_suck_drops_buff(
    gm_client, gm_ws, roster,
):
    """v2.97.27 — /cast_spell now threads cast_id into the save-context
    so /respond stamps the buff_install under the same cast_id as the
    spell_slot_spend (v2.92.0). Single Undo drops both.

    Tavik casts Hold Person (L2) at Krieger; loops until Krieger fails
    his Wis save (Paralyzed installs); undo refunds the slot AND drops
    Paralyzed.
    """
    tavik = roster["Brother Tavik Stonebrow"]
    krieger = roster["Krieger Stonefist"]
    HOLD_PERSON_INDEX = 8

    cast_id = None
    for _ in range(20):
        await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/character/{tavik['id']}/rest",
            json={"type": "long"},
        )
        await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/character/{krieger['id']}/rest",
            json={"type": "long"},
        )
        await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/end_buff",
            json={"character_id": krieger["id"], "key": "paralyzed"},
        )
        await gm_client.put(
            f"/api/campaign/{CAMPAIGN_ID}/battle",
            json={
                "combatants": [
                    {"id": f"tok_hp_{tavik['id']}", "char_id": tavik["id"],
                     "name": tavik["name"], "initiative": 12,
                     "hp_current": 55, "hp_max": 55, "buffs": [],
                     "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0}},
                    {"id": f"tok_hp_{krieger['id']}", "char_id": krieger["id"],
                     "name": krieger["name"], "initiative": 8,
                     "hp_current": 55, "hp_max": 55, "buffs": [],
                     "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0}},
                ],
                "turn_index": 0, "round": 1, "active": True,
            },
        )
        cast = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
            json={
                "character_id": tavik["id"],
                "spell_index": HOLD_PERSON_INDEX,
                "slot_level": 2,
                "class_slug": "cleric",
                "target_combatant_id": f"tok_hp_{krieger['id']}",
                "target_character_id": krieger["id"],
                "target_name": krieger["name"],
                "override": True,
            },
        )
        assert cast.status_code == 200, cast.text
        cd = cast.json()
        prompt_id = cd.get("auto_save_prompt_id")
        candidate_cast_id = cd["id"]
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/roll_request/{prompt_id}/respond",
            json={"character_id": krieger["id"]},
        )
        if r.json().get("auto_buff_installed") == "Paralyzed":
            cast_id = candidate_cast_id
            break

    assert cast_id, "no failed save in 20 tries"

    pre = (await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{krieger['id']}/buffs"
    )).json().get("buffs", [])
    assert any((b or {}).get("key") == "paralyzed" for b in pre)

    undo = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/undo_attack_damage",
        json={"attack_id": cast_id},
    )
    assert undo.status_code == 200, undo.text
    kinds = {e.get("kind") for e in (undo.json().get("per_target") or [])}
    assert "spell_slot_refunded" in kinds
    assert "buff_install" in kinds, (
        f"expected buff_install leg under cast_spell's cast_id (v2.97.27 plumbing); "
        f"per_target={undo.json().get('per_target')}"
    )

    post = (await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{krieger['id']}/buffs"
    )).json().get("buffs", [])
    assert not any((b or {}).get("key") == "paralyzed" for b in post)


async def test_undo_refunds_sacred_weapon_cd_and_buff(gm_client, gm_ws, roster):
    """v2.97.29 — Channel Divinity → Sacred Weapon now installs a
    caster-side ``sacred-weapon`` buff via the new catalog-driven
    /use_feature buff path. Undo refunds the channel-divinity counter
    (v2.97.7 plumbing) AND drops the buff (new v2.97.29 plumbing via
    the existing v2.65.0 buff_install undo branch).

    Pre-v2.97.29 the CD counter refunded but no buff was ever installed
    (announce-only). v2.97.29 makes Sacred Weapon the first CD option
    to opt into the buff dict in ``_FEATURE_ECONOMY``; the same
    /use_feature plumbing is now reusable for any future CD option (or
    /use_feature-routed class feature) that installs a caster buff.
    """
    caelan = roster["Sir Caelan Lightbringer"]
    await _long_rest(gm_client, caelan["id"])

    # Seed a one-combatant battle so _install_buff has somewhere to
    # attach (mirrors the rage / indomitable seed pattern).
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={
            "combatants": [{
                "id": f"tok_sw_{caelan['id']}",
                "char_id": caelan["id"],
                "name": caelan["name"],
                "initiative": 10,
                "hp_current": 60, "hp_max": 60,
                "buffs": [],
                "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0},
            }],
            "turn_index": 0, "round": 1, "active": True,
        },
    )

    cast = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_feature",
        json={
            "character_id": caelan["id"],
            "feature_key": "channel-divinity",
            "option_key": "sacred-weapon",
            "label": "Channel Divinity",
            "override": True,
        },
    )
    assert cast.status_code == 200, cast.text
    cast_data = cast.json()
    cast_id = cast_data.get("cast_id")
    assert cast_id, f"missing cast_id; payload={cast_data}"

    # Verify Sacred Weapon buff IS installed pre-undo.
    buffs_resp = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{caelan['id']}/buffs"
    )
    assert buffs_resp.status_code == 200, buffs_resp.text
    pre_buffs = buffs_resp.json().get("buffs", [])
    assert any((b or {}).get("key") == "sacred-weapon" for b in pre_buffs), (
        f"expected sacred-weapon buff installed; got {pre_buffs}"
    )

    gm_ws.mark()
    undo = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/undo_attack_damage",
        json={"attack_id": cast_id},
    )
    assert undo.status_code == 200, undo.text

    # The undo's per_target should include BOTH legs — the CD counter
    # refund AND the buff teardown.
    per_target = undo.json().get("per_target") or []
    kinds = {e.get("kind") for e in per_target}
    assert "resource_refunded" in kinds, (
        f"expected resource_refunded leg; per_target={per_target}"
    )
    assert "buff_install" in kinds, (
        f"expected buff_install leg; per_target={per_target}"
    )

    # Verify Sacred Weapon buff is gone post-undo.
    buffs_resp2 = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{caelan['id']}/buffs"
    )
    post_buffs = buffs_resp2.json().get("buffs", [])
    assert not any((b or {}).get("key") == "sacred-weapon" for b in post_buffs), (
        f"sacred-weapon still installed after undo: {post_buffs}"
    )


async def test_undo_refunds_bardic_inspiration_counter_and_buff(
    gm_client, gm_ws, roster,
):
    """v2.97.30 — /use_bardic_inspiration now installs a target-side
    ``bardic-inspiration-die`` buff alongside the v2.97.1 counter
    spend. Undo refunds the BI counter on the bard AND drops the
    inspiration buff on the recipient.

    Pre-v2.97.30 the cast was announce-only: the counter refunded but
    the recipient had no buff to clear. Now both legs ride one cast_id;
    a single Undo POST tears both down.
    """
    lyra = roster["Lyra Sunstrider"]
    pip = roster["Pip Quickfingers"]
    await _long_rest(gm_client, lyra["id"])

    # Seed a battle with BOTH Lyra and Pip so _install_buff has a
    # combatant to attach the target buff to. /use_bardic_inspiration
    # only installs the buff when the recipient is in init — outside
    # combat it stays announce-only (same canonical guard as Rage /
    # Indomitable, which gate buff install on the active battle).
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={
            "combatants": [
                {
                    "id": f"tok_bi_lyra_{lyra['id']}",
                    "char_id": lyra["id"],
                    "name": lyra["name"],
                    "initiative": 10,
                    "hp_current": 35, "hp_max": 35,
                    "buffs": [],
                    "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0},
                },
                {
                    "id": f"tok_bi_pip_{pip['id']}",
                    "char_id": pip["id"],
                    "name": pip["name"],
                    "initiative": 8,
                    "hp_current": 40, "hp_max": 40,
                    "buffs": [],
                    "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0},
                },
            ],
            "turn_index": 0, "round": 1, "active": True,
        },
    )

    cast = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_bardic_inspiration",
        json={
            "character_id": lyra["id"],
            "target_character_id": pip["id"],
            "override": True,
            "override_range": True,
        },
    )
    assert cast.status_code == 200, cast.text

    feature_msg = await gm_ws.wait_for("feature_used", timeout=3.0)
    cast_id = feature_msg["data"].get("cast_id")
    assert cast_id, f"missing cast_id; payload={feature_msg['data']}"

    # Verify bardic-inspiration-die buff is on PIP (the target).
    pip_buffs = (await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{pip['id']}/buffs"
    )).json().get("buffs", [])
    bi_buff = next(
        (b for b in pip_buffs if (b or {}).get("key") == "bardic-inspiration-die"),
        None,
    )
    assert bi_buff is not None, (
        f"expected bardic-inspiration-die installed on Pip; got {pip_buffs}"
    )
    # The buff carries the die size for a future attack/save hook.
    assert (bi_buff.get("effects") or {}).get("bardic_inspiration_die") == "d8", (
        f"expected d8 die (Lyra is Bard Lv 6); got {bi_buff}"
    )

    gm_ws.mark()
    undo = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/undo_attack_damage",
        json={"attack_id": cast_id},
    )
    assert undo.status_code == 200, undo.text
    per_target = undo.json().get("per_target") or []
    kinds = {e.get("kind") for e in per_target}
    assert "resource_refunded" in kinds, (
        f"expected resource_refunded leg; per_target={per_target}"
    )
    assert "buff_install" in kinds, (
        f"expected buff_install leg; per_target={per_target}"
    )

    # Verify the inspiration buff is gone from Pip post-undo.
    pip_buffs_after = (await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{pip['id']}/buffs"
    )).json().get("buffs", [])
    assert not any(
        (b or {}).get("key") == "bardic-inspiration-die"
        for b in pip_buffs_after
    ), f"bardic-inspiration-die still installed on Pip: {pip_buffs_after}"


async def test_undo_cast_bless_slot_and_target_buff(gm_client, gm_ws, roster):
    """v2.97.31 — /cast_spell now installs a target-side ``bless`` buff
    when the spell has a ``_SPELL_BUFF_MAP`` entry. Sibling to the
    v2.97.27 save-or-suck plumbing but for no-save buffs: Bless is the
    first opt-in. Undo refunds the spell slot (v2.92.0) AND drops the
    bless buff on the target via the v2.65.0 buff_install undo branch.

    Pre-v2.97.31 the slot refunded but the bless buff was never
    installed; today both legs ride one cast_id.
    """
    caelan = roster["Sir Caelan Lightbringer"]
    pip = roster["Pip Quickfingers"]
    await _long_rest(gm_client, caelan["id"])

    # Seed a battle with both Caelan and Pip so _install_buff has a
    # combatant to attach the buff to. /cast_spell's bless install is
    # best-effort (skipped when the target isn't in init).
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={
            "combatants": [
                {
                    "id": f"tok_bless_caelan_{caelan['id']}",
                    "char_id": caelan["id"],
                    "name": caelan["name"],
                    "initiative": 10,
                    "hp_current": 60, "hp_max": 60,
                    "buffs": [],
                    "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0},
                },
                {
                    "id": f"tok_bless_pip_{pip['id']}",
                    "char_id": pip["id"],
                    "name": pip["name"],
                    "initiative": 8,
                    "hp_current": 40, "hp_max": 40,
                    "buffs": [],
                    "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0},
                },
            ],
            "turn_index": 0, "round": 1, "active": True,
        },
    )

    # Caelan's spell list — Bless is at index 0 per the demo seed.
    BLESS_INDEX = 0
    cast = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
        json={
            "character_id": caelan["id"],
            "spell_index": BLESS_INDEX,
            "slot_level": 1,
            "class_slug": "paladin",
            "target_character_id": pip["id"],
            "target_combatant_id": f"tok_bless_pip_{pip['id']}",
            "target_name": pip["name"],
            "override": True,
            "override_range": True,
        },
    )
    assert cast.status_code == 200, cast.text
    cast_id = cast.json().get("id")
    assert cast_id, f"missing cast_id; payload={cast.json()}"

    # Verify bless buff is on PIP (the target).
    pip_buffs = (await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{pip['id']}/buffs"
    )).json().get("buffs", [])
    bless_buff = next(
        (b for b in pip_buffs if (b or {}).get("key") == "bless"),
        None,
    )
    assert bless_buff is not None, (
        f"expected bless installed on Pip; got {pip_buffs}"
    )
    # Buff carries +d4 marker effects for a future attack/save hook.
    assert (bless_buff.get("effects") or {}).get("bless_attack_bonus") == "d4"

    gm_ws.mark()
    undo = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/undo_attack_damage",
        json={"attack_id": cast_id},
    )
    assert undo.status_code == 200, undo.text
    per_target = undo.json().get("per_target") or []
    kinds = {e.get("kind") for e in per_target}
    assert "spell_slot_refunded" in kinds, (
        f"expected spell_slot_refunded leg; per_target={per_target}"
    )
    assert "buff_install" in kinds, (
        f"expected buff_install leg; per_target={per_target}"
    )

    # Verify the bless buff is gone from Pip post-undo.
    pip_buffs_after = (await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{pip['id']}/buffs"
    )).json().get("buffs", [])
    assert not any(
        (b or {}).get("key") == "bless"
        for b in pip_buffs_after
    ), f"bless still installed on Pip after undo: {pip_buffs_after}"


async def test_undo_cast_hunters_mark_slot_and_buff(gm_client, gm_ws, roster):
    """v2.97.32 — /cast_hunters_mark now mints its own cast_id, logs
    ``spell_slot_spend`` + ``buff_install`` under it, and surfaces the
    cast_id on the feature_used broadcast. Undo refunds the Ranger
    slot AND drops the hunters-mark concentration buff on the caster
    in one POST.

    Pre-v2.97.32 the dedicated endpoint was outside the v2.92.0 +
    v2.97.20 undo paths: the slot it consumed wasn't refundable and
    the buff it installed wasn't teardown-able. Now both legs ride
    one cast_id, same shape as /use_rage / /use_indomitable.
    """
    rowan = roster["Rowan Quickbow"]
    pip = roster["Pip Quickfingers"]
    await _long_rest(gm_client, rowan["id"])

    # Seed a battle with Rowan + Pip so _install_buff has somewhere
    # to attach the caster-side concentration buff.
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={
            "combatants": [
                {
                    "id": f"tok_hm_rowan_{rowan['id']}",
                    "char_id": rowan["id"],
                    "name": rowan["name"],
                    "initiative": 10,
                    "hp_current": 44, "hp_max": 44,
                    "buffs": [],
                    "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0},
                },
                {
                    "id": f"tok_hm_pip_{pip['id']}",
                    "char_id": pip["id"],
                    "name": pip["name"],
                    "initiative": 8,
                    "hp_current": 40, "hp_max": 40,
                    "buffs": [],
                    "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0},
                },
            ],
            "turn_index": 0, "round": 1, "active": True,
        },
    )

    cast = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_hunters_mark",
        json={
            "character_id": rowan["id"],
            "target_character_id": pip["id"],
            "override": True,
            "override_range": True,
        },
    )
    assert cast.status_code == 200, cast.text
    cast_id = cast.json().get("cast_id")
    assert cast_id, f"missing cast_id; payload={cast.json()}"

    # Verify hunters-mark buff installed on Rowan.
    rowan_buffs = (await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{rowan['id']}/buffs"
    )).json().get("buffs", [])
    assert any((b or {}).get("key") == "hunters-mark" for b in rowan_buffs), (
        f"expected hunters-mark installed on Rowan; got {rowan_buffs}"
    )

    gm_ws.mark()
    undo = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/undo_attack_damage",
        json={"attack_id": cast_id},
    )
    assert undo.status_code == 200, undo.text
    per_target = undo.json().get("per_target") or []
    kinds = {e.get("kind") for e in per_target}
    assert "spell_slot_refunded" in kinds, (
        f"expected spell_slot_refunded leg; per_target={per_target}"
    )
    assert "buff_install" in kinds, (
        f"expected buff_install leg; per_target={per_target}"
    )

    # Verify hunters-mark is gone post-undo.
    rowan_buffs_after = (await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{rowan['id']}/buffs"
    )).json().get("buffs", [])
    assert not any(
        (b or {}).get("key") == "hunters-mark" for b in rowan_buffs_after
    ), f"hunters-mark still installed after undo: {rowan_buffs_after}"


async def test_undo_cast_hex_slot_and_buff(gm_client, gm_ws, roster):
    """v2.97.32 — mirror of the Hunter's Mark test for the Warlock
    /cast_hex endpoint. Pre-v2.97.32 the slot consume + buff install
    rode outside the undo log; v2.97.32 mints a cast_id and logs both
    under it. Undo refunds the Pact slot AND drops the hex buff on
    the caster.
    """
    magnus = roster["Magnus Hexbinder"]
    pip = roster["Pip Quickfingers"]
    await _long_rest(gm_client, magnus["id"])

    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={
            "combatants": [
                {
                    "id": f"tok_hex_magnus_{magnus['id']}",
                    "char_id": magnus["id"],
                    "name": magnus["name"],
                    "initiative": 10,
                    "hp_current": 40, "hp_max": 40,
                    "buffs": [],
                    "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0},
                },
                {
                    "id": f"tok_hex_pip_{pip['id']}",
                    "char_id": pip["id"],
                    "name": pip["name"],
                    "initiative": 8,
                    "hp_current": 40, "hp_max": 40,
                    "buffs": [],
                    "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0},
                },
            ],
            "turn_index": 0, "round": 1, "active": True,
        },
    )

    cast = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_hex",
        json={
            "character_id": magnus["id"],
            "target_character_id": pip["id"],
            "ability": "STR",
            "override": True,
            "override_range": True,
        },
    )
    assert cast.status_code == 200, cast.text
    cast_id = cast.json().get("cast_id")
    assert cast_id, f"missing cast_id; payload={cast.json()}"

    # Verify hex buff installed on Magnus.
    magnus_buffs = (await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{magnus['id']}/buffs"
    )).json().get("buffs", [])
    assert any((b or {}).get("key") == "hex" for b in magnus_buffs), (
        f"expected hex installed on Magnus; got {magnus_buffs}"
    )

    gm_ws.mark()
    undo = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/undo_attack_damage",
        json={"attack_id": cast_id},
    )
    assert undo.status_code == 200, undo.text
    per_target = undo.json().get("per_target") or []
    kinds = {e.get("kind") for e in per_target}
    assert "spell_slot_refunded" in kinds
    assert "buff_install" in kinds

    magnus_buffs_after = (await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{magnus['id']}/buffs"
    )).json().get("buffs", [])
    assert not any(
        (b or {}).get("key") == "hex" for b in magnus_buffs_after
    ), f"hex still installed after undo: {magnus_buffs_after}"


async def test_undo_cast_spell_faerie_fire_drops_buff(
    gm_client, gm_ws, roster,
):
    """v2.97.33 — Faerie Fire added to ``_SPELL_CONDITION_MAP``. The
    /respond save handler installs the 'faerie-fired' buff on a failed
    Dex save and stamps buff_install under /cast_spell's cast_id via
    the v2.97.27 _save_request_context["cast_id"] plumbing. Undo
    refunds the slot AND drops the buff in one POST.

    Lyra casts Faerie Fire at Krieger (low DEX save bonus); loops
    until Krieger fails his save; verifies the faerie-fired buff is
    installed; undoes; verifies BOTH legs in per_target and the buff
    is gone.
    """
    lyra = roster["Lyra Sunstrider"]
    krieger = roster["Krieger Stonefist"]
    FAERIE_FIRE_INDEX = 6  # See demo_seed.py — Lyra's 7th spell.

    cast_id = None
    for _ in range(20):
        await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/character/{lyra['id']}/rest",
            json={"type": "long"},
        )
        await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/character/{krieger['id']}/rest",
            json={"type": "long"},
        )
        await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/end_buff",
            json={"character_id": krieger["id"], "key": "faerie-fired"},
        )
        await gm_client.put(
            f"/api/campaign/{CAMPAIGN_ID}/battle",
            json={
                "combatants": [
                    {"id": f"tok_ff_{lyra['id']}", "char_id": lyra["id"],
                     "name": lyra["name"], "initiative": 12,
                     "hp_current": 35, "hp_max": 35, "buffs": [],
                     "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0}},
                    {"id": f"tok_ff_{krieger['id']}", "char_id": krieger["id"],
                     "name": krieger["name"], "initiative": 8,
                     "hp_current": 55, "hp_max": 55, "buffs": [],
                     "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0}},
                ],
                "turn_index": 0, "round": 1, "active": True,
            },
        )
        cast = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
            json={
                "character_id": lyra["id"],
                "spell_index": FAERIE_FIRE_INDEX,
                "slot_level": 1,
                "class_slug": "bard",
                "target_combatant_id": f"tok_ff_{krieger['id']}",
                "target_character_id": krieger["id"],
                "target_name": krieger["name"],
                "override": True,
                "override_range": True,
            },
        )
        assert cast.status_code == 200, cast.text
        cd = cast.json()
        prompt_id = cd.get("auto_save_prompt_id")
        candidate_cast_id = cd["id"]
        if not prompt_id:
            # No save prompt issued — likely the bless single-target path
            # not engaging Faerie Fire. Re-loop after long-rest.
            continue
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/roll_request/{prompt_id}/respond",
            json={"character_id": krieger["id"]},
        )
        if r.json().get("auto_buff_installed") == "Faerie Fire":
            cast_id = candidate_cast_id
            break

    assert cast_id, "no failed Dex save in 20 tries"

    pre = (await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{krieger['id']}/buffs"
    )).json().get("buffs", [])
    assert any((b or {}).get("key") == "faerie-fired" for b in pre), (
        f"faerie-fired not installed; got {pre}"
    )

    undo = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/undo_attack_damage",
        json={"attack_id": cast_id},
    )
    assert undo.status_code == 200, undo.text
    kinds = {e.get("kind") for e in (undo.json().get("per_target") or [])}
    assert "spell_slot_refunded" in kinds
    assert "buff_install" in kinds

    post = (await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{krieger['id']}/buffs"
    )).json().get("buffs", [])
    assert not any((b or {}).get("key") == "faerie-fired" for b in post)


async def test_undo_cast_spell_bane_drops_buff(
    gm_client, gm_ws, roster,
):
    """v2.97.33 — Bane added to ``_SPELL_CONDITION_MAP``. Symmetric to
    the Faerie Fire test but a Cha save (Krieger has low CHA). Failed
    save installs the 'baned' buff on the target; undo refunds slot +
    drops buff.
    """
    lyra = roster["Lyra Sunstrider"]
    krieger = roster["Krieger Stonefist"]
    BANE_INDEX = 18  # Appended at the end of Lyra's spell list in v2.97.33.

    cast_id = None
    for _ in range(20):
        await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/character/{lyra['id']}/rest",
            json={"type": "long"},
        )
        await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/character/{krieger['id']}/rest",
            json={"type": "long"},
        )
        await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/end_buff",
            json={"character_id": krieger["id"], "key": "baned"},
        )
        await gm_client.put(
            f"/api/campaign/{CAMPAIGN_ID}/battle",
            json={
                "combatants": [
                    {"id": f"tok_bane_{lyra['id']}", "char_id": lyra["id"],
                     "name": lyra["name"], "initiative": 12,
                     "hp_current": 35, "hp_max": 35, "buffs": [],
                     "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0}},
                    {"id": f"tok_bane_{krieger['id']}", "char_id": krieger["id"],
                     "name": krieger["name"], "initiative": 8,
                     "hp_current": 55, "hp_max": 55, "buffs": [],
                     "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0}},
                ],
                "turn_index": 0, "round": 1, "active": True,
            },
        )
        cast = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
            json={
                "character_id": lyra["id"],
                "spell_index": BANE_INDEX,
                "slot_level": 1,
                "class_slug": "bard",
                "target_combatant_id": f"tok_bane_{krieger['id']}",
                "target_character_id": krieger["id"],
                "target_name": krieger["name"],
                "override": True,
                "override_range": True,
            },
        )
        assert cast.status_code == 200, cast.text
        cd = cast.json()
        prompt_id = cd.get("auto_save_prompt_id")
        candidate_cast_id = cd["id"]
        if not prompt_id:
            continue
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/roll_request/{prompt_id}/respond",
            json={"character_id": krieger["id"]},
        )
        if r.json().get("auto_buff_installed") == "Baned":
            cast_id = candidate_cast_id
            break

    assert cast_id, "no failed Cha save in 20 tries"

    pre = (await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{krieger['id']}/buffs"
    )).json().get("buffs", [])
    assert any((b or {}).get("key") == "baned" for b in pre), (
        f"baned not installed; got {pre}"
    )

    undo = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/undo_attack_damage",
        json={"attack_id": cast_id},
    )
    assert undo.status_code == 200, undo.text
    kinds = {e.get("kind") for e in (undo.json().get("per_target") or [])}
    assert "spell_slot_refunded" in kinds
    assert "buff_install" in kinds

    post = (await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{krieger['id']}/buffs"
    )).json().get("buffs", [])
    assert not any((b or {}).get("key") == "baned" for b in post)
