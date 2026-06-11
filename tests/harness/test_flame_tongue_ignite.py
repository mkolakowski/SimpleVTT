"""v2.158.92 — magic-items-automation Phase 5b: Flame Tongue
ignite/extinguish toggle via /use_item_action. RAW DMG p.170: bonus
action to speak the command word, flames last until you use a bonus
action to speak the command word again (or drop/sheathe the sword).

Phase 5a fired the +2d6 fire rider whenever Garrik was equipped +
attuned. Phase 5b adds the per-item ``_lit`` boolean state as a third
gate: the rider only fires while ``_lit: True``. The state persists on
the inventory item itself (not a combatant buff), so it survives rests
+ session boundaries — matching RAW's "lasts until extinguished" wording.

Demo fixture: Garrik's seed ships ``_lit: True`` on the Flame Tongue so
the out-of-the-box demo + the Phase 5a tests continue to fire the rider
without a manual ignite step.

Tests:
  - extinguish path: POST extinguish → 200 + ``lit: false`` + the next
    attack carries no rider.
  - re-ignite + restore: POST ignite from extinguished state → 200 +
    ``lit: true`` + attack restores the rider. Used to verify the
    toggle is bidirectional and Garrik's state is left as he started.
  - already-lit path: POST ignite when already lit → 409
    ``no_state_change``.
  - already-extinguished path: extinguish twice → 409
    ``no_state_change`` on the second call. Re-ignites in teardown.
  - unknown action_key for flame-tongue → 404 (catalog miss). Reuses
    the existing /use_item_action dispatch guard.
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID


GARRIK_FLAME_TONGUE_ATTACK_IDX = 3
GARRIK_FLAME_TONGUE_INV_IDX = 7


def _uplifts(data, source):
    return [u for u in (data.get("auto_uplifts") or [])
            if u.get("source") == source]


async def _ignite(gm_client, char_id):
    return await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/use_item_action",
        json={
            "inventory_index": GARRIK_FLAME_TONGUE_INV_IDX,
            "action_key": "ignite",
        },
    )


async def _extinguish(gm_client, char_id):
    return await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/use_item_action",
        json={
            "inventory_index": GARRIK_FLAME_TONGUE_INV_IDX,
            "action_key": "extinguish",
        },
    )


async def _attack(gm_client, char_id, idx=GARRIK_FLAME_TONGUE_ATTACK_IDX):
    return await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/attack",
        json={"character_id": char_id, "attack_index": idx, "override": True},
    )


@pytest_asyncio.fixture
async def garrik(roster):
    return roster["Garrik Ironside"]


async def test_extinguish_then_attack_has_no_rider(gm_client, garrik):
    """v2.158.92: POST extinguish on a lit Flame Tongue → 200 with
    ``lit: false``. The next /attack with the Flame Tongue must omit
    the rider. Re-ignites the staff in teardown."""
    try:
        resp = await _extinguish(gm_client, garrik["id"])
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["ok"] is True
        assert body["lit"] is False
        assert body["action_key"] == "extinguish"

        atk = await _attack(gm_client, garrik["id"])
        assert atk.status_code == 200, atk.text
        ups = _uplifts(atk.json(), "item-flame-tongue")
        assert ups == [], (
            f"Extinguished Flame Tongue must not fire the rider; got {ups!r}"
        )
    finally:
        await _ignite(gm_client, garrik["id"])


async def test_reignite_restores_rider(gm_client, garrik):
    """v2.158.92: extinguish, attack (no rider), re-ignite, attack
    (rider restored). Verifies the toggle is bidirectional."""
    try:
        await _extinguish(gm_client, garrik["id"])
        cold_atk = await _attack(gm_client, garrik["id"])
        assert _uplifts(cold_atk.json(), "item-flame-tongue") == []

        ig = await _ignite(gm_client, garrik["id"])
        assert ig.status_code == 200, ig.text
        assert ig.json()["lit"] is True

        hot_atk = await _attack(gm_client, garrik["id"])
        ups = _uplifts(hot_atk.json(), "item-flame-tongue")
        assert len(ups) == 1
        assert ups[0]["damage_type"] == "fire"
    finally:
        # Already lit if the test ran cleanly; ignite() may 409 if so.
        # Force the state to lit via extinguish→ignite for robustness.
        await _extinguish(gm_client, garrik["id"])
        await _ignite(gm_client, garrik["id"])


async def test_ignite_when_already_lit_returns_409(gm_client, garrik):
    """v2.158.92: ignite a lit Flame Tongue → 409 ``no_state_change``.
    The seed ships lit so this is the default starting state."""
    resp = await _ignite(gm_client, garrik["id"])
    assert resp.status_code == 409, resp.text
    body = resp.json()
    assert body["error"] == "no_state_change"
    assert body["current"] is True
    assert "Flame Tongue" in body["label"]


async def test_extinguish_twice_409_on_second(gm_client, garrik):
    """v2.158.92: extinguish → 200; extinguish again → 409 no-state-
    change with current=False. Re-ignites in teardown."""
    try:
        first = await _extinguish(gm_client, garrik["id"])
        assert first.status_code == 200, first.text
        second = await _extinguish(gm_client, garrik["id"])
        assert second.status_code == 409, second.text
        body = second.json()
        assert body["error"] == "no_state_change"
        assert body["current"] is False
    finally:
        await _ignite(gm_client, garrik["id"])


async def test_unknown_action_key_404(gm_client, garrik):
    """v2.158.92: action_key not in the flame-tongue actions sub-map
    → 404 via the existing /use_item_action dispatch guard
    (v2.158.88 Phase 4d). Regression catch for the multi-action
    sub-dispatch."""
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{garrik['id']}/use_item_action",
        json={
            "inventory_index": GARRIK_FLAME_TONGUE_INV_IDX,
            "action_key": "cast-fireball",
        },
    )
    assert resp.status_code == 404, resp.text
