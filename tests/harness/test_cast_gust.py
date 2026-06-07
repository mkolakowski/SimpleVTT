"""Gust — Druid/Sorcerer/Wizard cantrip, the last forced-mover.

v2.99.445 — Phase 6.3 of docs/plans/movement-and-summons.md. Gust
(Tasha's p.106): the target makes a STR save vs the caster's spell save
DC or is pushed 5 ft away. Rolls the save server-side and pushes via the
shared `_force_move` primitive on a fail.

Caster fixture: Thalindra Moonwhisper (demo Wizard, INT caster).

Tests:
  - push happy path: Thalindra (placed above the bandit) loops until it
    fails its STR save, then asserts `push_applied` + the bandit's token
    moved +70 px (5 ft / 1 cell away). A passed save moves nothing.
  - 409 cannot_cast: Krieger (Barbarian).
  - 400 missing target.
"""
from .conftest import CAMPAIGN_ID


async def _seed_battle(gm_client, combatants):
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": combatants, "turn_index": 0,
              "round": 1, "active": False},
    )


async def _bandit_template(gm_client):
    r = await gm_client.get(f"/api/campaign/{CAMPAIGN_ID}/templates")
    templates = r.json()
    return next(
        (t for t in templates if "bandit" in t["name"].lower()), templates[0]
    )


async def _token_y_by_id(gm_client, token_id):
    resp = await gm_client.get(f"/api/campaign/{CAMPAIGN_ID}/tokens")
    for t in resp.json()["tokens"]:
        if t["id"] == token_id:
            return float(t["y"])
    return None


async def test_gust_pushes_target_on_failed_save(gm_client, roster):
    """Thalindra (above the bandit) gusts it; on a failed STR save the
    bandit's token moves +70 px (5 ft / 1 cell away). A pass moves
    nothing."""
    thalindra = roster["Thalindra Moonwhisper"]
    bandit_tmpl = await _bandit_template(gm_client)

    rt = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/tokens",
        json={"token_template_id": bandit_tmpl["id"], "x": 700.0, "y": 700.0})
    assert rt.status_code == 200, rt.text
    bandit_tok_id = rt.json()["id"]

    rp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{thalindra['id']}/place-token",
        json={"x": 700.0, "y": 560.0})
    assert rp.status_code == 200, rp.text

    bandit_cb = "tok_test_gust_bandit"
    try:
        pushed = False
        for _ in range(30):
            await _seed_battle(gm_client, [
                {"id": f"tok_test_{thalindra['id']}", "char_id": thalindra["id"],
                 "name": thalindra["name"], "initiative": 10,
                 "hp_current": 30, "hp_max": 30, "buffs": [],
                 "economy": {"action": False, "bonus": False,
                             "reaction": False, "movement": 0}},
                {"id": bandit_cb, "char_id": None,
                 "token_template_id": bandit_tmpl["id"],
                 "source_token_id": bandit_tok_id,
                 "name": bandit_tmpl["name"], "initiative": 7,
                 "hp_current": 11, "hp_max": 11, "buffs": [],
                 "economy": {"action": False, "bonus": False,
                             "reaction": False, "movement": 0}},
            ])
            before_y = await _token_y_by_id(gm_client, bandit_tok_id)
            r = await gm_client.post(
                f"/api/campaign/{CAMPAIGN_ID}/cast_gust",
                json={"character_id": thalindra["id"],
                      "target_combatant_id": bandit_cb},
            )
            assert r.status_code == 200, r.text
            body = r.json()
            assert body["feature"] == "gust"
            assert body["save_resolved"] is True
            assert body["save_dc"] > 0
            if body["save_passed"] is False:
                assert body["push_applied"] is True
                after_y = await _token_y_by_id(gm_client, bandit_tok_id)
                assert after_y == before_y + 70.0  # 5 ft / 1 cell
                pushed = True
                break
            assert body["push_applied"] is False
            assert await _token_y_by_id(gm_client, bandit_tok_id) == before_y
        assert pushed, "no failed STR save in 30 attempts — flaky env?"
    finally:
        await gm_client.delete(
            f"/api/campaign/{CAMPAIGN_ID}/tokens/{bandit_tok_id}")


async def test_gust_cannot_cast(gm_client, roster):
    """Krieger (Barbarian) → 409 cannot_cast."""
    krieger = roster["Krieger Stonefist"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_gust",
        json={"character_id": krieger["id"], "target_combatant_id": "x"},
    )
    assert r.status_code == 409, r.text
    assert r.json()["error"] == "cannot_cast"


async def test_gust_missing_target_400(gm_client, roster):
    """Missing target_combatant_id → 400."""
    thalindra = roster["Thalindra Moonwhisper"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_gust",
        json={"character_id": thalindra["id"]},
    )
    assert r.status_code == 400, r.text
