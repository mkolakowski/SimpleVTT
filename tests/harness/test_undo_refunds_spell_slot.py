"""v2.92.0 — ``/undo_attack_damage`` refunds the spell slot.

Bug report: the ↶ Undo button on a spell-cast roll-log card reverted
HP damage (when auto_apply_damage was on) and buff installs (since
v2.65.0) but did NOT refund the spell slot consumed by the cast.
Side effect: spam-cast → spam-undo was a free-cast exploit; more
mundane case is just "I clicked the wrong spell, please give me my
slot back."

Fix (v2.92.0): /cast_spell now stamps a ``spell_slot_spend`` entry
into the per-cast undo log alongside the existing damage / heal /
buff_install entries. undo_attack_damage walks the entries in
reverse and, on hitting a ``spell_slot_spend``, decrements the
character's ``sheet["spell_slots"][cslug][lvl]["used"]`` by 1
(clamped at 0) and broadcasts ``spell_slot_update``.

Tests:
  - happy path: long-rest Thalindra, cast Magic Missile (L1 wizard),
    capture the ``used`` count from the response, undo the cast,
    verify the ``spell_slot_update`` broadcast carries ``used``
    decremented by 1 from the post-cast count.
  - no_op when the cast log has expired / cast_id unknown → 404.
  - sleep + undo round-trip via the dedicated /cast_sleep endpoint is
    NOT covered here; cast_sleep uses a separate code path that
    doesn't share the slot-spend logging yet (filed for a follow-up).
"""
from .conftest import CAMPAIGN_ID


async def _long_rest(gm_client, char_id: int) -> None:
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/rest",
        json={"type": "long"},
    )
    assert resp.status_code == 200, resp.text


async def test_undo_refunds_l1_wizard_slot(gm_client, gm_ws, roster):
    thalindra = roster["Thalindra Moonwhisper"]
    await _long_rest(gm_client, thalindra["id"])

    # Cast Magic Missile (L1 wizard spell — Thalindra has wizard slots
    # via the demo seed). spell_index 3 is the v2.4.x demo wizard
    # ordering — same constant test_cast_spell.py:test_cast_magic_missile
    # uses, so a future reorder breaks both tests at once.
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
    cast = resp.json()
    cast_id = cast["id"]
    post_cast_used = int(cast["slot"]["used"])
    post_cast_total = int(cast["slot"]["total"])
    # Sanity: cast actually consumed a slot. Without this guard a
    # silent ``used`` field equal to 0 would let the next assertion
    # pass meaninglessly.
    assert post_cast_used >= 1, (
        f"cast didn't decrement a slot (used={post_cast_used}). "
        f"Slot payload: {cast['slot']}"
    )

    # Re-mark the WS buffer here so the wait_for below scoops up only
    # the broadcast fired by the undo (the cast itself also broadcasts
    # ``spell_slot_update`` with the post-cast ``used`` count, which
    # would otherwise be the first hit after the mark).
    gm_ws.mark()

    # Undo. The cast_id from the response body matches the
    # data-attack-id the ↶ Undo button posts (same field is named
    # ``id`` on the response, ``attack_id`` on the request — legacy of
    # the v2.65.0 cross-attack/spell unification).
    undo = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/undo_attack_damage",
        json={"attack_id": cast_id},
    )
    assert undo.status_code == 200, undo.text
    undo_data = undo.json()
    assert undo_data["ok"] is True

    # Broadcast assertion — the new ``spell_slot_update`` fired by the
    # refund branch carries the same shape as the cast-time broadcast,
    # with ``used`` decremented back. wait_for is buffered-since-mark
    # so it scoops up the broadcast we just triggered.
    msg = await gm_ws.wait_for("spell_slot_update")
    data = msg["data"]
    assert data["character_id"] == thalindra["id"]
    assert data["class_slug"] == "wizard"
    assert data["level"] == 1
    assert data["total"] == post_cast_total
    assert data["used"] == post_cast_used - 1, (
        f"slot wasn't refunded: post-cast used={post_cast_used}, "
        f"post-undo used={data['used']}"
    )


async def test_undo_unknown_cast_id_returns_404(gm_client):
    """The 8-hour purge sweep evicts old cast_ids; an unknown id should
    surface a 404 rather than silently no-op (so the JS handler can
    show a 'nothing to undo' toast)."""
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/undo_attack_damage",
        json={"attack_id": "deadbeef0000"},
    )
    assert resp.status_code == 404, resp.text
