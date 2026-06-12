"""v2.175.0 — lair-action initiative-20 server broadcast (RAW MM p.11).

Lair actions fire on initiative count 20 (losing ties). v2.174.0 surfaced
the prompt client-side (render-derived banner + toast). This commit
promotes it to a server-authoritative WS broadcast: when a PUT /battle
lands the turn order in the init-20 zone — the active combatant's
initiative <= 20, or every combatant is above 20 — and the lair is active
and hasn't already acted/broadcast this round, the server fires a
`lair_init_20_reached` broadcast carrying `{lair_slug, owner_name, round}`.
Deduped per round via the `lair_init20_broadcast_round` marker parked on
the battle state (carried forward across PUTs that omit it).

These tests drive PUT /battle directly with manual NPC combatants (no
char_id) carrying `lair_actions`, the same shape the GM client persists.
"""
import asyncio

from .conftest import CAMPAIGN_ID

_LAIR_SLUG = "adult-red-dragon"
_DRAGON_ID = "npc_init20_dragon"
_HERO_ID = "npc_init20_hero"

_LAIR_ACTIONS = [
    {"id": "magma-erupts", "name": "Magma Erupts", "save_ability": "dex",
     "save_dc": 15, "damage": "6d6", "damage_type": "fire", "half_on_save": True},
    {"id": "tremor", "name": "Tremor", "save_ability": "dex",
     "save_dc": 15, "effect": "prone"},
]


def _combatants(hero_init=25, dragon_init=20):
    return [
        {"id": _HERO_ID, "char_id": None, "token_template_id": None,
         "name": "Hero", "initiative": hero_init,
         "hp_current": 30, "hp_max": 30, "buffs": [],
         "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0}},
        {"id": _DRAGON_ID, "char_id": None, "token_template_id": None,
         "name": "Ancient Red Dragon", "initiative": dragon_init,
         "hp_current": 546, "hp_max": 546, "buffs": [],
         "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0},
         "lair_slug": _LAIR_SLUG, "lair_actions": _LAIR_ACTIONS},
    ]


async def _put_battle(gm_client, *, turn_index, round=1, in_lair=True,
                      combatants=None, lair_acted_round=None,
                      lair_init20_broadcast_round=None):
    body = {
        "combatants": combatants if combatants is not None else _combatants(),
        "turn_index": turn_index,
        "round": round,
        "active": True,
        "in_lair": in_lair,
        "lair_slug": _LAIR_SLUG if in_lair else "",
        "last_lair_action_id": "",
        "lair_acted_round": lair_acted_round,
        # Sent explicitly so the carry-forward dedup marker doesn't leak
        # across tests (the guard only preserves a key the client omits).
        "lair_init20_broadcast_round": lair_init20_broadcast_round,
    }
    resp = await gm_client.put(f"/api/campaign/{CAMPAIGN_ID}/battle", json=body)
    assert resp.status_code == 200, resp.text
    return resp


async def test_init_20_broadcast_when_active_at_or_below_20(gm_client, gm_ws):
    """Active combatant at init 20 (<= 20) + in_lair → server broadcasts
    `lair_init_20_reached` carrying the lair owner's name + round."""
    gm_ws.mark()
    # turn_index=1 → the Dragon (init 20) is active → count 20 reached.
    await _put_battle(gm_client, turn_index=1, round=1)
    msg = await gm_ws.wait_for("lair_init_20_reached")
    assert msg["data"]["lair_slug"] == _LAIR_SLUG
    assert msg["data"]["owner_name"] == "Ancient Red Dragon"
    assert msg["data"]["round"] == 1


async def test_no_broadcast_when_active_above_20(gm_client, gm_ws):
    """Active combatant at init 25 (> 20) with a sub-20 combatant present
    → count 20 NOT yet reached → no broadcast."""
    gm_ws.mark()
    # turn_index=0 → the Hero (init 25) is active; the Dragon is at 20, so
    # not all-above-20 → reached is False.
    await _put_battle(gm_client, turn_index=0, round=1)
    # Give the broadcast a beat to (not) arrive.
    await asyncio.sleep(0.3)
    assert gm_ws.buffered("lair_init_20_reached") == []


async def test_all_combatants_above_20_broadcasts(gm_client, gm_ws):
    """When every combatant is above 20, init count 20 falls after the
    last turn → the prompt fires regardless of turn_index."""
    gm_ws.mark()
    await _put_battle(gm_client, turn_index=0, round=1,
                      combatants=_combatants(hero_init=30, dragon_init=25))
    msg = await gm_ws.wait_for("lair_init_20_reached")
    assert msg["data"]["owner_name"] == "Ancient Red Dragon"


async def test_no_broadcast_out_of_lair(gm_client, gm_ws):
    """in_lair False → no init-20 prompt even at init 20."""
    gm_ws.mark()
    await _put_battle(gm_client, turn_index=1, round=1, in_lair=False)
    await asyncio.sleep(0.3)
    assert gm_ws.buffered("lair_init_20_reached") == []


async def test_deduped_within_same_round(gm_client, gm_ws):
    """A second PUT in the same round (still in the init-20 zone) does NOT
    re-broadcast — the `lair_init20_broadcast_round` marker is carried
    forward across the client PUT that omits it."""
    gm_ws.mark()
    await _put_battle(gm_client, turn_index=1, round=1)
    first = await gm_ws.wait_for("lair_init_20_reached")
    assert first["data"]["round"] == 1

    # Second PUT, same round — omit the dedup marker so the carry-forward
    # guard restores it (this is the real client path).
    gm_ws.mark()
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={
            "combatants": _combatants(),
            "turn_index": 1, "round": 1, "active": True,
            "in_lair": True, "lair_slug": _LAIR_SLUG,
        },
    )
    await asyncio.sleep(0.3)
    assert gm_ws.buffered("lair_init_20_reached") == []


async def test_next_round_rebroadcasts(gm_client, gm_ws):
    """A new round re-arms the prompt — the dedup is per-round, so round 2
    broadcasts again even though round 1 already did."""
    gm_ws.mark()
    await _put_battle(gm_client, turn_index=1, round=1)
    await gm_ws.wait_for("lair_init_20_reached")

    gm_ws.mark()
    # Round 2, dedup marker carried forward as 1 → 1 != 2 → re-broadcasts.
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={
            "combatants": _combatants(),
            "turn_index": 1, "round": 2, "active": True,
            "in_lair": True, "lair_slug": _LAIR_SLUG,
        },
    )
    msg = await gm_ws.wait_for("lair_init_20_reached")
    assert msg["data"]["round"] == 2


async def test_no_broadcast_when_already_acted_this_round(gm_client, gm_ws):
    """If the lair already acted this round (`lair_acted_round` == round),
    the init-20 prompt is suppressed — it's already moot."""
    gm_ws.mark()
    await _put_battle(gm_client, turn_index=1, round=1, lair_acted_round=1)
    await asyncio.sleep(0.3)
    assert gm_ws.buffered("lair_init_20_reached") == []
