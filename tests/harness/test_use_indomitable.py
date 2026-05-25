"""v2.56.0 — Fighter Indomitable (Lv 9+).

Endpoint + buff-consumption test. RAW: "When you make a saving throw
and fail, you can spend one use of Indomitable to reroll the new roll."
We ship advantage-on-the-next-save as a v1 simplification (the post-
roll reroll-with-consequence-undo flow is filed in TODO.md). Flow:
  - `/use_indomitable` decrements the Indomitable counter + installs
    a single-use `indomitable-armed` self-buff.
  - The next save-roll construction hook reads the buff, swaps
    `1d20 → 2d20kh1` in `base_expression`, and consumes the buff
    via `_remove_buff` so the arm is per-save (not per-turn).
  - Broadcasts `feature_used(source="indomitable")` both on arm
    (from the endpoint) and on consume (from the save-roll hook).

Tests:
  - endpoint happy path: /use_indomitable returns 200, decrements
    counter, installs buff, broadcasts feature_used.
  - endpoint validation: wrong class (Pip Rogue) → 409 wrong_class;
    out of uses → 409 out_of_uses.
  - end-to-end consume: arm Indomitable, then cast Suggestion at
    Garrik → his save roll_request `base_expression="2d20kh1"`,
    buff is REMOVED from his combatant after the cast, and a
    consume-side `feature_used(source=indomitable)` fires.
  - second save after arm consumed: re-cast Suggestion → save
    `base_expression="1d20"` (no kh1, buff already consumed).
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID


# Lyra's Suggestion spell index (see test_use_countercharm.py).
SUGGESTION_INDEX = 9


@pytest_asyncio.fixture
async def garrik_full(gm_client, roster):
    garrik = roster["Garrik Ironside"]
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{garrik['id']}/rest",
        json={"type": "long"},
    )
    return garrik


@pytest_asyncio.fixture
async def lyra_rested(gm_client, roster):
    lyra = roster["Lyra Sunstrider"]
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{lyra['id']}/rest",
        json={"type": "long"},
    )
    return lyra


def _make_combatant(name, char_id, init=10, hp=40):
    return {
        "id": f"tok_ind_{char_id}",
        "char_id": char_id,
        "name": name,
        "initiative": init,
        "hp_current": hp, "hp_max": hp,
        "buffs": [],
        "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0},
    }


async def _seed_battle(gm_client, combatants):
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": combatants, "turn_index": 0, "round": 1, "active": True},
    )


async def _get_buffs(gm_client, char_id: int) -> list:
    r = await gm_client.get(f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/buffs")
    return r.json().get("buffs", [])


def _indomitable_broadcasts(gm_ws, char_id: int) -> list:
    return [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "indomitable"
        and (m.get("data") or {}).get("character_id") == char_id
    ]


async def _wait_for_roll_request(gm_ws):
    return await gm_ws.wait_for("roll_request", timeout=3.0)


async def test_use_indomitable_arms_buff(gm_client, gm_ws, garrik_full):
    """POST /use_indomitable → 200, decrements Indomitable counter from
    1 → 0, installs `indomitable-armed` buff on Garrik's combatant,
    broadcasts feature_used(source=indomitable)."""
    garrik = garrik_full
    await _seed_battle(gm_client, [
        _make_combatant(garrik["name"], garrik["id"], init=10, hp=85),
    ])
    gm_ws.mark()
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_indomitable",
        json={"character_id": garrik["id"]},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["ok"] is True
    assert data["remaining"] == 0
    assert data["max"] == 1
    assert data["buff_installed"] is True

    # Buff lands on Garrik's combatant.
    buffs = await _get_buffs(gm_client, garrik["id"])
    assert any((b or {}).get("key") == "indomitable-armed" for b in buffs), (
        f"expected indomitable-armed buff on Garrik; got "
        f"{[(b or {}).get('key') for b in buffs]}"
    )
    # Arm-side broadcast (from the endpoint, not the consume hook).
    arm_msgs = _indomitable_broadcasts(gm_ws, garrik["id"])
    assert arm_msgs, "expected feature_used(source=indomitable) arm broadcast"


async def test_use_indomitable_wrong_class(gm_client, roster):
    """Pip (Rogue) → 409 wrong_class."""
    pip = roster["Pip Quickfingers"]
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_indomitable",
        json={"character_id": pip["id"]},
    )
    assert resp.status_code == 409, resp.text
    data = resp.json()
    assert data["error"] == "wrong_class"
    assert data["expected"] == "fighter"


async def test_use_indomitable_out_of_uses(gm_client, gm_ws, garrik_full):
    """Spend Garrik's only Indomitable use, then try again → 409
    out_of_uses with label=Indomitable."""
    garrik = garrik_full
    await _seed_battle(gm_client, [
        _make_combatant(garrik["name"], garrik["id"], init=10, hp=85),
    ])
    # Burn the only use.
    first = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_indomitable",
        json={"character_id": garrik["id"]},
    )
    assert first.status_code == 200, first.text

    # Second call should 409.
    second = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_indomitable",
        json={"character_id": garrik["id"]},
    )
    assert second.status_code == 409, second.text
    data = second.json()
    assert data["error"] == "out_of_uses"
    assert data["label"] == "Indomitable"


async def test_indomitable_consumes_on_save(
    gm_client, gm_ws, roster, garrik_full, lyra_rested,
):
    """End-to-end: Garrik arms Indomitable, then Lyra casts Suggestion
    at him. The save's `base_expression` swaps to `2d20kh1`, the
    indomitable-armed buff is removed, and a consume-side
    feature_used(source=indomitable) broadcast fires.
    """
    garrik = garrik_full
    lyra = lyra_rested
    await _seed_battle(gm_client, [
        _make_combatant(lyra["name"], lyra["id"], init=12),
        _make_combatant(garrik["name"], garrik["id"], init=10, hp=85),
    ])
    # Arm Indomitable.
    arm = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_indomitable",
        json={"character_id": garrik["id"]},
    )
    assert arm.status_code == 200, arm.text

    gm_ws.mark()
    # Lyra casts Suggestion at Garrik → Wis save roll_request.
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
        json={
            "character_id": lyra["id"],
            "spell_index": SUGGESTION_INDEX,
            "slot_level": 2,
            "class_slug": "bard",
            "target_combatant_id": f"tok_ind_{garrik['id']}",
            "target_character_id": garrik["id"],
            "target_name": garrik["name"],
            "override": True,
        },
    )
    assert resp.status_code == 200, resp.text

    rr = await _wait_for_roll_request(gm_ws)
    assert rr["data"]["base_expression"] == "2d20kh1", (
        f"Indomitable should swap d20 → 2d20kh1; got "
        f"{rr['data']['base_expression']!r}"
    )

    # Buff was consumed — Garrik no longer carries indomitable-armed.
    buffs = await _get_buffs(gm_client, garrik["id"])
    assert not any((b or {}).get("key") == "indomitable-armed" for b in buffs), (
        f"Indomitable should consume the buff on first save use; "
        f"got remaining buffs: {[(b or {}).get('key') for b in buffs]}"
    )

    # Consume-side broadcast fired (the arm broadcast was before mark()).
    consume_msgs = _indomitable_broadcasts(gm_ws, garrik["id"])
    assert consume_msgs, "expected consume-side feature_used(source=indomitable)"


async def test_indomitable_one_save_only(
    gm_client, gm_ws, roster, garrik_full, lyra_rested,
):
    """After consuming Indomitable on one save, a SECOND save in the
    same round gets no advantage — base_expression="1d20" again.
    """
    garrik = garrik_full
    lyra = lyra_rested
    await _seed_battle(gm_client, [
        _make_combatant(lyra["name"], lyra["id"], init=12),
        _make_combatant(garrik["name"], garrik["id"], init=10, hp=85),
    ])
    # Arm.
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_indomitable",
        json={"character_id": garrik["id"]},
    )
    # First save — consumes the buff.
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
        json={
            "character_id": lyra["id"],
            "spell_index": SUGGESTION_INDEX,
            "slot_level": 2,
            "class_slug": "bard",
            "target_combatant_id": f"tok_ind_{garrik['id']}",
            "target_character_id": garrik["id"],
            "target_name": garrik["name"],
            "override": True,
        },
    )

    gm_ws.mark()
    # Second save — buff already consumed, no advantage.
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
        json={
            "character_id": lyra["id"],
            "spell_index": SUGGESTION_INDEX,
            "slot_level": 2,
            "class_slug": "bard",
            "target_combatant_id": f"tok_ind_{garrik['id']}",
            "target_character_id": garrik["id"],
            "target_name": garrik["name"],
            "override": True,
        },
    )
    assert resp.status_code == 200, resp.text
    rr = await _wait_for_roll_request(gm_ws)
    assert rr["data"]["base_expression"] == "1d20", (
        f"second save should be 1d20 (no kh1 — Indomitable consumed); "
        f"got {rr['data']['base_expression']!r}"
    )
