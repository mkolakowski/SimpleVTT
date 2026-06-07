"""Summon lifecycle — long-rest teardown.

v2.99.439 — Phase 7.1 of docs/plans/movement-and-summons.md. Closes the
plan's "companion lifecycle leak" risk: a long rest now drops every
summoned companion owned by the resting character (via
`_teardown_summons_for_owner`), removing the combatant + deleting its
token. A short rest leaves summons in place.

Owner fixture: Lyra Sunstrider.
"""
from .conftest import CAMPAIGN_ID


async def _seed_battle(gm_client, combatants):
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": combatants, "turn_index": 0,
              "round": 1, "active": False},
    )


def _lyra_cb(lyra):
    return {
        "id": f"tok_test_{lyra['id']}", "char_id": lyra["id"],
        "name": lyra["name"], "initiative": 10,
        "hp_current": 30, "hp_max": 30, "buffs": [],
        "economy": {"action": False, "bonus": False,
                    "reaction": False, "movement": 0},
    }


async def _tokens(gm_client):
    r = await gm_client.get(f"/api/campaign/{CAMPAIGN_ID}/tokens")
    return r.json()["tokens"]


async def _summon_wolf(gm_client, lyra):
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/summon_companion",
        json={"owner_character_id": lyra["id"], "companion_key": "wolf",
              "x": 700.0, "y": 700.0},
    )
    assert r.status_code == 200, r.text
    return r.json()["combatant"], r.json()["token_id"]


async def _rest(gm_client, char_id, rest_type):
    return await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/rest",
        json={"type": rest_type},
    )


async def test_long_rest_drops_summons(gm_client, roster):
    """A long rest tears down the owner's summon: the combatant id appears
    in `dismissed_summons`, the token is deleted, and a follow-up dismiss
    → 404 (already gone)."""
    lyra = roster["Lyra Sunstrider"]
    await _seed_battle(gm_client, [_lyra_cb(lyra)])
    cb, token_id = await _summon_wolf(gm_client, lyra)

    rest = await _rest(gm_client, lyra["id"], "long")
    assert rest.status_code == 200, rest.text
    assert cb["id"] in rest.json()["dismissed_summons"]

    toks = await _tokens(gm_client)
    assert not any(t["id"] == token_id for t in toks)

    # Already torn down → a manual dismiss now 404s.
    d2 = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/dismiss_companion",
        json={"combatant_id": cb["id"]},
    )
    assert d2.status_code == 404, d2.text


async def test_short_rest_keeps_summons(gm_client, roster):
    """A short rest leaves the owner's summon in place (no teardown)."""
    lyra = roster["Lyra Sunstrider"]
    # Long rest first to refill hit dice + clear any stray summons.
    await _rest(gm_client, lyra["id"], "long")
    await _seed_battle(gm_client, [_lyra_cb(lyra)])
    cb, token_id = await _summon_wolf(gm_client, lyra)
    try:
        rest = await _rest(gm_client, lyra["id"], "short")
        assert rest.status_code == 200, rest.text
        # Short rest doesn't carry the teardown field.
        assert "dismissed_summons" not in rest.json()
        toks = await _tokens(gm_client)
        assert any(t["id"] == token_id for t in toks)
    finally:
        await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/dismiss_companion",
            json={"combatant_id": cb["id"]},
        )
