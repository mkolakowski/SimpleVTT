"""v2.891.0 — GET /api/lair_action_catalog: the full SRD lair-action catalog
(id-deduped, with mechanics) that the tabletop resolves map-placed zone actions
against so they can be rendered + rolled without the source creature."""
from __future__ import annotations


async def test_catalog_returns_actions_with_mechanics(gm_client):
    resp = await gm_client.get("/api/lair_action_catalog")
    assert resp.status_code == 200, resp.text
    actions = resp.json()["actions"]
    assert isinstance(actions, list) and len(actions) > 0, actions
    by_id = {a["id"]: a for a in actions}
    # A known action carries its full mechanics (not just id/name/desc).
    assert "magma-erupts" in by_id, sorted(by_id)
    m = by_id["magma-erupts"]
    assert m["name"] == "Magma Erupts"
    assert m["damage"] == "6d6"
    assert m["damage_type"] == "fire"
    assert m["save_ability"] == "DEX"
    # ids are unique across the deduped catalog.
    assert len(by_id) == len(actions)


async def test_catalog_readable_by_a_player(alice_client):
    # Static SRD content — any signed-in user may read it.
    resp = await alice_client.get("/api/lair_action_catalog")
    assert resp.status_code == 200, resp.text
    assert len(resp.json()["actions"]) > 0
