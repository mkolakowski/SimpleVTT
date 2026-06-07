"""v2.101.0 — persist the battle hub to the DB + GET /battle endpoint.

Context: before v2.101.0 the hub's battle map (`realtime.CampaignHub.
_battle`) was RAM-only and never persisted, so an app restart or the
hourly demo reseed silently emptied it and every server-side battle
read (OA detection, the over-speed gate, reaction routing) no-oped
until the GM next mutated the battle. v2.101.0 turns the hub into a
write-through cache over a new `battles` table: `set_battle` persists,
`get_battle` lazily rehydrates on a cache miss.

The new GET endpoint reads the persisted `battles` row directly from
the DB, so this PUT→GET round-trip proves the PUT write actually
reached the DB (not just the in-memory cache). A genuine
survives-a-restart assertion would need a container bounce the HTTP
harness can't drive — the DB round-trip is the closest in-process
proof.

Tests:
  - happy path: PUT a battle → GET returns the same combatants from
    the DB (HTTP 200 + ``{"battle": {...}}`` shape) → and a fresh WS
    connect replays it as a ``battle_update``.
  - error path: a non-GM PUT is rejected (403) so the GM-only write
    gate still holds.
"""
from .conftest import CAMPAIGN_ID
from .helpers import open_ws, WSCollector


def _battle_payload(roster):
    pip = roster["Pip Quickfingers"]
    return {
        "combatants": [
            {"id": f"tok_battle_pip_{pip['id']}", "char_id": pip["id"],
             "name": pip["name"], "initiative": 17,
             "hp_current": 24, "hp_max": 24,
             "buffs": [],
             "economy": {"action": False, "bonus": False,
                         "reaction": False, "movement": 0}},
        ],
        "turn_index": 0, "round": 1, "active": True,
    }


async def test_battle_put_persists_and_get_round_trips(gm_client, roster):
    """PUT a battle, then GET it back from the persisted `battles`
    row. The GET reads the DB directly, so a matching round-trip
    proves the write-through persisted the state.
    """
    payload = _battle_payload(roster)
    put = await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle", json=payload,
    )
    assert put.status_code == 200, put.text
    assert put.json() == {"ok": True}

    got = await gm_client.get(f"/api/campaign/{CAMPAIGN_ID}/battle")
    assert got.status_code == 200, got.text
    body = got.json()
    assert "battle" in body, f"GET /battle must return a battle key: {body}"
    state = body["battle"]
    assert state is not None, "battle should be persisted after the PUT"
    assert state.get("active") is True
    assert state.get("round") == 1
    names = {c.get("name") for c in (state.get("combatants") or [])}
    assert "Pip Quickfingers" in names, (
        f"persisted battle should carry the seeded combatant; got {names}"
    )

    # Connect-time WS hydration replays the persisted/cached state to a
    # newly connected client as a battle_update. The priming messages
    # land during WSCollector's __aenter__ drain (before mark()), so we
    # read collector.messages directly rather than the post-mark buffer.
    ws = await open_ws(gm_client, CAMPAIGN_ID)
    try:
        async with WSCollector(ws) as collector:
            updates = [m for m in collector.messages
                       if m.get("type") == "battle_update"]
            assert updates, "fresh WS connect should replay a battle_update"
            combatants = updates[-1]["data"].get("combatants") or []
            assert any(
                c.get("name") == "Pip Quickfingers" for c in combatants
            ), f"connect battle_update should carry the combatant: {combatants}"
    finally:
        await ws.close()


async def test_battle_put_requires_gm(alice_client, roster):
    """A non-GM player cannot write the battle state — the PUT stays
    GM-only (403). Guards the write gate that the new GET (viewer-
    readable) deliberately does not share.
    """
    resp = await alice_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle", json=_battle_payload(roster),
    )
    assert resp.status_code == 403, (
        f"non-GM PUT /battle must be rejected; got {resp.status_code}"
    )
