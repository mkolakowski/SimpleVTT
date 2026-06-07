"""Find Familiar — Wizard L1 ritual, second summon retrofit.

v2.99.440 — Phase 7.2 of docs/plans/movement-and-summons.md. Builds on
the v2.99.437 summon primitive: `/cast_find_familiar` stands up the
tiny, non-combat `familiar` companion (a real combatant — its own token +
init slot) in a chosen animal form. Gates on knowing Find Familiar OR
being a Wizard / Artificer.

Caster fixture: Thalindra Moonwhisper (demo Wizard).

Tests:
  - happy path: Thalindra conjures an owl familiar → the summon combatant
    + token appear, name reflects the form, `summoned_by` is Thalindra.
  - 409 cannot_cast: Krieger (Barbarian, no Find Familiar).
"""
from .conftest import CAMPAIGN_ID


async def _seed_battle(gm_client, combatants):
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": combatants, "turn_index": 0,
              "round": 1, "active": False},
    )


def _pc_cb(c):
    return {
        "id": f"tok_test_{c['id']}", "char_id": c["id"], "name": c["name"],
        "initiative": 10, "hp_current": 30, "hp_max": 30, "buffs": [],
        "economy": {"action": False, "bonus": False,
                    "reaction": False, "movement": 0},
    }


async def _tokens(gm_client):
    r = await gm_client.get(f"/api/campaign/{CAMPAIGN_ID}/tokens")
    return r.json()["tokens"]


async def test_find_familiar_summons_companion(gm_client, gm_ws, roster):
    """Thalindra conjures an owl familiar → a `familiar` summon combatant
    + token appear; the name carries the form and `summoned_by` is her."""
    thalindra = roster["Thalindra Moonwhisper"]
    await _seed_battle(gm_client, [_pc_cb(thalindra)])

    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_find_familiar",
        json={"character_id": thalindra["id"], "form": "owl",
              "x": 700.0, "y": 700.0},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    cb = body["combatant"]
    try:
        assert body["feature"] == "find-familiar"
        assert body["form"] == "owl"
        assert cb["is_summon"] is True
        assert cb["companion_key"] == "familiar"
        assert cb["name"] == "Familiar (owl)"
        assert cb["hp_max"] == 1
        assert cb["ac"] == 11
        assert cb["summoned_by"] == thalindra["id"]
        assert body["token_id"] is not None

        ta = await gm_ws.wait_for("token_add", timeout=2.0)
        assert ta["data"]["id"] == body["token_id"]
        toks = await _tokens(gm_client)
        assert any(t["id"] == body["token_id"] and t["label"] == "Familiar (owl)"
                   for t in toks)
    finally:
        await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/dismiss_companion",
            json={"combatant_id": cb["id"]},
        )


async def test_find_familiar_cannot_cast(gm_client, roster):
    """Krieger (Barbarian, no Find Familiar, not a wizard) → 409
    cannot_cast."""
    krieger = roster["Krieger Stonefist"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_find_familiar",
        json={"character_id": krieger["id"]},
    )
    assert r.status_code == 409, r.text
    assert r.json()["error"] == "cannot_cast"
