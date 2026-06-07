"""Summon companion primitive — Phase 7.1 of the automation plan.

v2.99.437 — docs/plans/movement-and-summons.md P7.1. `_summon_companion`
stands up a summoned companion as a REAL combatant: an NPC token + an
init slot + HP/AC that ride on the combatant dict (no TokenTemplate row),
so it reuses the existing damage/HP pipeline. `POST /summon_companion`
wraps it; `POST /dismiss_companion` tears it down (removes the combatant +
deletes the token).

The "it's a real combatant" contract is proven by casting Thunderwave at
the summon and asserting it takes damage — every target takes ≥ half on a
save, so the HP drop is deterministic. Caster/owner fixture: Lyra
Sunstrider (demo Bard, knows Thunderwave).

Tests:
  - summon creates a combatant + token (shape + broadcasts).
  - summon is a real combatant: Thunderwave applies damage to it.
  - dismiss removes the combatant + deletes the token; re-dismiss → 404.
  - unknown companion_key → 400; dismiss unknown → 404.
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


async def test_summon_creates_combatant_and_token(gm_client, gm_ws, roster):
    """Lyra summons a Wolf → 200 with the combatant shape (is_summon,
    11 HP, AC 13, summoned_by Lyra), a token_add + battle_update
    broadcast, and the token present on the map."""
    lyra = roster["Lyra Sunstrider"]
    await _seed_battle(gm_client, [_lyra_cb(lyra)])

    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/summon_companion",
        json={"owner_character_id": lyra["id"], "companion_key": "wolf",
              "x": 700.0, "y": 700.0, "initiative": 12},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    cb = body["combatant"]
    token_id = body["token_id"]
    try:
        assert body["companion_key"] == "wolf"
        assert cb["is_summon"] is True
        assert cb["name"] == "Wolf"
        assert cb["hp_max"] == 11
        assert cb["hp_current"] == 11
        assert cb["ac"] == 13
        assert cb["summoned_by"] == lyra["id"]
        assert cb["source_token_id"] == token_id
        assert cb["initiative"] == 12

        ta = await gm_ws.wait_for("token_add", timeout=2.0)
        assert ta["data"]["id"] == token_id
        bu = await gm_ws.wait_for("battle_update", timeout=2.0)
        ids = [c["id"] for c in (bu["data"].get("combatants") or [])]
        assert cb["id"] in ids

        toks = await _tokens(gm_client)
        assert any(t["id"] == token_id and t["label"] == "Wolf" for t in toks)
    finally:
        await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/dismiss_companion",
            json={"combatant_id": cb["id"]},
        )


async def test_summon_is_real_combatant_takes_damage(gm_client, roster):
    """The summon reuses the damage pipeline: Lyra casts Thunderwave at
    her own Wolf and it takes damage (≥ half on any save → deterministic
    HP drop)."""
    lyra = roster["Lyra Sunstrider"]
    await _seed_battle(gm_client, [_lyra_cb(lyra)])
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/summon_companion",
        json={"owner_character_id": lyra["id"], "companion_key": "wolf",
              "x": 700.0, "y": 700.0},
    )
    assert r.status_code == 200, r.text
    cb = r.json()["combatant"]
    try:
        tw = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/use_thunderwave",
            json={"character_id": lyra["id"],
                  "target_combatant_ids": [cb["id"]]},
        )
        assert tw.status_code == 200, tw.text
        results = tw.json()["results"]
        wolf_res = next(r for r in results if r["combatant_id"] == cb["id"])
        # Every Thunderwave target takes at least half damage.
        assert wolf_res["damage_applied"] > 0
        assert wolf_res["save_passed"] is not None
    finally:
        await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/dismiss_companion",
            json={"combatant_id": cb["id"]},
        )


async def test_dismiss_removes_combatant_and_token(gm_client, gm_ws, roster):
    """Dismiss removes the summon's combatant + deletes its token; a
    second dismiss → 404 (no longer a summon in the battle)."""
    lyra = roster["Lyra Sunstrider"]
    await _seed_battle(gm_client, [_lyra_cb(lyra)])
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/summon_companion",
        json={"owner_character_id": lyra["id"], "companion_key": "wolf",
              "x": 700.0, "y": 700.0},
    )
    assert r.status_code == 200, r.text
    cb = r.json()["combatant"]
    token_id = r.json()["token_id"]

    gm_ws.mark()
    d = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/dismiss_companion",
        json={"combatant_id": cb["id"]},
    )
    assert d.status_code == 200, d.text
    assert d.json()["removed"] is True
    assert d.json()["token_id"] == token_id

    td = await gm_ws.wait_for("token_delete", timeout=2.0)
    assert td["data"]["id"] == token_id

    toks = await _tokens(gm_client)
    assert not any(t["id"] == token_id for t in toks)

    # Second dismiss → 404 (already gone).
    d2 = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/dismiss_companion",
        json={"combatant_id": cb["id"]},
    )
    assert d2.status_code == 404, d2.text


async def test_summon_unknown_companion_400(gm_client, roster):
    """Unknown companion_key → 400 unknown_companion."""
    lyra = roster["Lyra Sunstrider"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/summon_companion",
        json={"owner_character_id": lyra["id"], "companion_key": "dragon"},
    )
    assert r.status_code == 400, r.text
    assert r.json()["error"] == "unknown_companion"


async def test_dismiss_unknown_404(gm_client):
    """Dismiss an unknown combatant id → 404."""
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/dismiss_companion",
        json={"combatant_id": "nope_not_a_summon"},
    )
    assert r.status_code == 404, r.text
