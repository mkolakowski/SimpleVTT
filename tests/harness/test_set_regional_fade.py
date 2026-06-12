"""v2.181.0 — /api/campaign/{cid}/set_regional_fade — the regional-effect
fade tracker (see `docs/plans/legendary-actions.md`).

RAW MM p.11: when a lair-dwelling creature dies, its regional effects don't
vanish — they "fade over the course of 1d10 days." This GM-driven endpoint
models that countdown on the battle state (distinct from the initiative-20
lair actions and the always-on passive regional effects).

Coverage:
  - start: rolls 1d10, seeds `regional_fade` {days_total, days_remaining,
    faded=False, lair_slug}, broadcasts `regional_fade_changed`, persists.
  - advance: ticks days_remaining down by 1; at 0 sets faded=True.
  - clear: removes the tracker (regional_fade=None).
  - 409 no_active_fade when advancing with no fade in progress.
  - 400 unknown action.
  - 403 non-GM caller.
"""
from .conftest import CAMPAIGN_ID


async def _seed_battle(gm_client, *, regional_fade=None):
    body = {
        "combatants": [
            {
                "id": "npc_fade_filler",
                "char_id": None,
                "name": "Filler",
                "initiative": 10,
                "hp_current": 10, "hp_max": 10,
                "buffs": [],
                "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0},
            },
        ],
        "turn_index": 0,
        "round": 1,
        "active": True,
        "in_lair": True,
        "lair_slug": "adult-red-dragon",
        # Sent explicitly so the carry-forward guard doesn't leak a prior
        # test's tracker into this one.
        "regional_fade": regional_fade,
    }
    await gm_client.put(f"/api/campaign/{CAMPAIGN_ID}/battle", json=body)


async def test_start_rolls_1d10_and_broadcasts(gm_client, gm_ws):
    await _seed_battle(gm_client)
    gm_ws.mark()
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/set_regional_fade",
        json={"action": "start", "lair_slug": "adult-red-dragon"},
    )
    assert resp.status_code == 200, resp.text
    fade = resp.json()["regional_fade"]
    assert 1 <= fade["days_total"] <= 10
    assert fade["days_remaining"] == fade["days_total"]
    assert fade["faded"] is False
    assert fade["lair_slug"] == "adult-red-dragon"

    msg = await gm_ws.wait_for("regional_fade_changed")
    assert msg["data"]["regional_fade"]["days_total"] == fade["days_total"]

    # Persisted onto the battle-state dict.
    bs = (await gm_client.get(f"/api/campaign/{CAMPAIGN_ID}/battle")).json()["battle"]
    assert bs["regional_fade"]["days_remaining"] == fade["days_total"]


async def test_start_defaults_lair_slug_from_battle(gm_client):
    await _seed_battle(gm_client)
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/set_regional_fade",
        json={"action": "start"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["regional_fade"]["lair_slug"] == "adult-red-dragon"


async def test_advance_ticks_days_down(gm_client):
    await _seed_battle(gm_client, regional_fade={
        "lair_slug": "adult-red-dragon",
        "days_total": 3, "days_remaining": 3, "faded": False,
    })
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/set_regional_fade",
        json={"action": "advance"},
    )
    assert resp.status_code == 200, resp.text
    fade = resp.json()["regional_fade"]
    assert fade["days_remaining"] == 2
    assert fade["faded"] is False
    # days_total is preserved across the tick.
    assert fade["days_total"] == 3


async def test_advance_to_zero_marks_faded(gm_client, gm_ws):
    await _seed_battle(gm_client, regional_fade={
        "lair_slug": "adult-red-dragon",
        "days_total": 5, "days_remaining": 1, "faded": False,
    })
    gm_ws.mark()
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/set_regional_fade",
        json={"action": "advance"},
    )
    assert resp.status_code == 200, resp.text
    fade = resp.json()["regional_fade"]
    assert fade["days_remaining"] == 0
    assert fade["faded"] is True

    msg = await gm_ws.wait_for("regional_fade_changed")
    assert msg["data"]["regional_fade"]["faded"] is True


async def test_advance_with_no_fade_409(gm_client):
    await _seed_battle(gm_client, regional_fade=None)
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/set_regional_fade",
        json={"action": "advance"},
    )
    assert resp.status_code == 409
    assert resp.json()["error"] == "no_active_fade"


async def test_clear_removes_tracker(gm_client, gm_ws):
    await _seed_battle(gm_client, regional_fade={
        "lair_slug": "adult-red-dragon",
        "days_total": 4, "days_remaining": 4, "faded": False,
    })
    gm_ws.mark()
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/set_regional_fade",
        json={"action": "clear"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["regional_fade"] is None

    msg = await gm_ws.wait_for("regional_fade_changed")
    assert msg["data"]["regional_fade"] is None


async def test_unknown_action_400(gm_client):
    await _seed_battle(gm_client)
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/set_regional_fade",
        json={"action": "explode"},
    )
    assert resp.status_code == 400


async def test_player_403(alice_client):
    resp = await alice_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/set_regional_fade",
        json={"action": "start"},
    )
    assert resp.status_code == 403
