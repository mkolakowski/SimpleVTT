"""Thunderwave — Bard/Druid/Sorcerer/Wizard L1 (multi-target push retrofit).

v2.99.436 — Phase 6.3 of docs/plans/movement-and-summons.md. The first
*multi-target* `_force_move` retrofit.

`POST /api/campaign/{cid}/use_thunderwave` rolls a CON save for each
supplied target vs the caster's spell save DC. The 2d8 thunder damage is
rolled once (RAW: one roll for the whole cube); a failed save takes full
+ is **pushed 10 ft away from the caster** via `_force_move`, a passed
save takes half + isn't pushed.

Caster fixture: Lyra Sunstrider (demo Bard, knows Thunderwave, CHA 17 /
prof +3 → spell save DC 14).

Tests:
  - multi-target push: two bandits flank Lyra (one above, one below);
    loop until at least one fails its CON save, then assert the failed
    one(s) were pushed 10 ft (±140 px) directly away from Lyra and any
    that passed weren't moved.
  - unknown target → per-result `error: not_in_battle` (200, not a 404).
  - 409 spell_not_known: Krieger (Barbarian) → 409.
  - 400 missing target list.
"""
from .conftest import CAMPAIGN_ID


async def _bandit_template(gm_client):
    r = await gm_client.get(f"/api/campaign/{CAMPAIGN_ID}/templates")
    templates = r.json()
    return next(
        (t for t in templates if "bandit" in t["name"].lower()), templates[0]
    )


async def _seed_battle(gm_client, combatants):
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": combatants, "turn_index": 0,
              "round": 1, "active": False},
    )


async def _token_y_by_id(gm_client, token_id):
    resp = await gm_client.get(f"/api/campaign/{CAMPAIGN_ID}/tokens")
    for t in resp.json()["tokens"]:
        if t["id"] == token_id:
            return float(t["y"])
    return None


def _bandit_cb(cb_id, tok_id, tmpl):
    return {
        "id": cb_id, "char_id": None,
        "token_template_id": tmpl["id"], "source_token_id": tok_id,
        "name": tmpl["name"], "initiative": 7,
        "hp_current": 11, "hp_max": 11, "buffs": [],
        "economy": {"action": False, "bonus": False,
                    "reaction": False, "movement": 0},
    }


async def test_thunderwave_pushes_failed_targets(gm_client, roster):
    """Two bandits flank Lyra (one 10 ft above, one 10 ft below). Each
    rolls its own CON save; a failed save is pushed 10 ft away (±140 px),
    a passed save isn't. Loop until at least one fails, asserting the
    per-target push correctness every iteration."""
    lyra = roster["Lyra Sunstrider"]
    tmpl = await _bandit_template(gm_client)

    # Two real NPC tokens, directly above + below Lyra so pushes are on
    # the y-axis: A above (push further up, −y); B below (push down, +y).
    ra = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/tokens",
        json={"token_template_id": tmpl["id"], "x": 700.0, "y": 560.0})
    assert ra.status_code == 200, ra.text
    tok_a = ra.json()["id"]
    rb = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/tokens",
        json={"token_template_id": tmpl["id"], "x": 700.0, "y": 840.0})
    assert rb.status_code == 200, rb.text
    tok_b = rb.json()["id"]

    rl = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{lyra['id']}/place-token",
        json={"x": 700.0, "y": 700.0})
    assert rl.status_code == 200, rl.text

    cb_a, cb_b = "tok_test_tw_a", "tok_test_tw_b"
    try:
        push_seen = False
        for _ in range(40):
            # Re-seed each iteration to reset the bandits' HP (the damage
            # accumulates otherwise); token positions drift on fails, so
            # read the before-position fresh each time.
            await _seed_battle(gm_client, [
                {"id": f"tok_test_{lyra['id']}", "char_id": lyra["id"],
                 "name": lyra["name"], "initiative": 10,
                 "hp_current": 30, "hp_max": 30, "buffs": [],
                 "economy": {"action": False, "bonus": False,
                             "reaction": False, "movement": 0}},
                _bandit_cb(cb_a, tok_a, tmpl),
                _bandit_cb(cb_b, tok_b, tmpl),
            ])
            before_a = await _token_y_by_id(gm_client, tok_a)
            before_b = await _token_y_by_id(gm_client, tok_b)
            r = await gm_client.post(
                f"/api/campaign/{CAMPAIGN_ID}/use_thunderwave",
                json={"character_id": lyra["id"],
                      "target_combatant_ids": [cb_a, cb_b]},
            )
            assert r.status_code == 200, r.text
            body = r.json()
            assert body["feature"] == "thunderwave"
            assert body["save_dc"] == 14  # 8 + prof 3 + CHA mod 3
            assert 2 <= body["damage_rolled"] <= 16
            res = {x["combatant_id"]: x for x in body["results"]}
            after_a = await _token_y_by_id(gm_client, tok_a)
            after_b = await _token_y_by_id(gm_client, tok_b)

            # Bandit A (above Lyra): a fail pushes it further up (−140).
            if res[cb_a]["save_passed"] is False:
                assert res[cb_a]["pushed"] is True
                assert after_a == before_a - 140.0
            else:
                assert res[cb_a]["pushed"] is False
                assert after_a == before_a
            # Bandit B (below Lyra): a fail pushes it down (+140).
            if res[cb_b]["save_passed"] is False:
                assert res[cb_b]["pushed"] is True
                assert after_b == before_b + 140.0
            else:
                assert res[cb_b]["pushed"] is False
                assert after_b == before_b

            if res[cb_a]["save_passed"] is False or res[cb_b]["save_passed"] is False:
                assert body["any_pushed"] is True
                push_seen = True
                break
        assert push_seen, "no failed CON save across 40 casts — flaky env?"
    finally:
        await gm_client.delete(f"/api/campaign/{CAMPAIGN_ID}/tokens/{tok_a}")
        await gm_client.delete(f"/api/campaign/{CAMPAIGN_ID}/tokens/{tok_b}")


async def test_thunderwave_unknown_target_per_result_error(gm_client, roster):
    """An unknown combatant id yields a per-result `not_in_battle` error
    (200 overall, not a top-level 404)."""
    lyra = roster["Lyra Sunstrider"]
    await _seed_battle(gm_client, [
        {"id": f"tok_test_{lyra['id']}", "char_id": lyra["id"],
         "name": lyra["name"], "initiative": 10,
         "hp_current": 30, "hp_max": 30, "buffs": [],
         "economy": {"action": False, "bonus": False,
                     "reaction": False, "movement": 0}},
    ])
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_thunderwave",
        json={"character_id": lyra["id"],
              "target_combatant_ids": ["nope_not_in_battle"]},
    )
    assert r.status_code == 200, r.text
    results = r.json()["results"]
    assert results[0]["error"] == "not_in_battle"
    assert results[0]["pushed"] is False


async def test_thunderwave_spell_not_known(gm_client, roster):
    """Krieger (Barbarian, no Thunderwave) → 409 spell_not_known."""
    krieger = roster["Krieger Stonefist"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_thunderwave",
        json={"character_id": krieger["id"],
              "target_combatant_ids": ["x"]},
    )
    assert r.status_code == 409, r.text
    assert r.json()["error"] == "spell_not_known"


async def test_thunderwave_missing_targets_400(gm_client, roster):
    """Empty/missing target list → 400."""
    lyra = roster["Lyra Sunstrider"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_thunderwave",
        json={"character_id": lyra["id"], "target_combatant_ids": []},
    )
    assert r.status_code == 400, r.text
