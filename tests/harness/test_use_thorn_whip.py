"""Thorn Whip — Druid/Artificer cantrip (forced-movement retrofit).

v2.99.435 — Phase 6.3 of docs/plans/movement-and-summons.md. Third
`_force_move` retrofit and the first to exercise the `pull` path.

`POST /api/campaign/{cid}/use_thorn_whip` rolls a melee spell attack
(1d20 + prof + spellcasting mod) vs the target's AC server-side. On a
hit it applies piercing damage (1d6, scaling to 2d6 at Lv 5, 3d6 at 11,
4d6 at 17) via `_apply_damage_to_combatant` and **pulls the target's
token 10 ft toward the caster** via `_force_move(pull=True)`. Needs the
target on a gridded map with a token (off-grid → hit + damage, no pull).

Caster fixture: Mira Greenleaf (demo Druid Lv 5, WIS caster → +6 to hit).

Tests:
  - pull happy path: Mira (placed above the bandit) loops until she
    hits; on the hit assert `pull_applied` True + the bandit's token
    moved -140 px (2 cells / 10 ft toward Mira) + damage applied. A miss
    moves nothing. NPC token created + torn down.
  - 409 wrong_class: Krieger (Barbarian) → 409 wrong_class.
  - 400 missing target_combatant_id.
  - 404 target not in battle.
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


async def test_thorn_whip_pulls_target_on_hit(gm_client, roster):
    """Mira (above the bandit) lashes it; on the first hit the bandit's
    token is pulled -140 px (2 cells / 10 ft toward Mira) + takes piercing
    damage. Misses move nothing — so loop until a hit, then break."""
    mira = roster["Mira Greenleaf"]
    bandit_tmpl = await _bandit_template(gm_client)

    # Real NPC token for the bandit so _force_move can resolve + pull it.
    rt = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/tokens",
        json={"token_template_id": bandit_tmpl["id"], "x": 700.0, "y": 700.0},
    )
    assert rt.status_code == 200, rt.text
    bandit_tok_id = rt.json()["id"]

    # Mira directly above the bandit → pull (toward Mira) is straight up
    # (-y): the bandit moves from y=700 toward y=560.
    rp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{mira['id']}/place-token",
        json={"x": 700.0, "y": 560.0},
    )
    assert rp.status_code == 200, rp.text

    bandit_cb = "tok_test_tw_bandit"
    await _seed_battle(gm_client, [
        {"id": f"tok_test_{mira['id']}", "char_id": mira["id"],
         "name": mira["name"], "initiative": 10,
         "hp_current": 40, "hp_max": 40, "buffs": [],
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

    try:
        hit_seen = False
        for _ in range(30):
            before_y = await _token_y_by_id(gm_client, bandit_tok_id)
            r = await gm_client.post(
                f"/api/campaign/{CAMPAIGN_ID}/use_thorn_whip",
                json={
                    "character_id": mira["id"],
                    "target_combatant_id": bandit_cb,
                },
            )
            assert r.status_code == 200, r.text
            body = r.json()
            assert body["feature"] == "thorn-whip"
            assert body["target_ac"] > 0
            assert body["caster_level"] == 5
            if body["hit"]:
                # Mira Lv 5 → 2d6 piercing.
                assert body["damage_rolled"] > 0
                assert body["damage_applied"] > 0
                assert body["damage_type"] == "piercing"
                assert body["pull_applied"] is True
                assert body["pull_distance_ft"] == 10.0
                after_y = await _token_y_by_id(gm_client, bandit_tok_id)
                assert after_y == before_y - 140.0  # 10 ft toward Mira
                hit_seen = True
                break
            # On a miss: no damage, no pull, token unmoved.
            assert body["pull_applied"] is False
            assert body["damage_applied"] == 0
            assert await _token_y_by_id(gm_client, bandit_tok_id) == before_y
        assert hit_seen, "no hit in 30 attempts — flaky env?"
    finally:
        await gm_client.delete(
            f"/api/campaign/{CAMPAIGN_ID}/tokens/{bandit_tok_id}"
        )


async def test_thorn_whip_wrong_class(gm_client, roster):
    """Krieger (Barbarian) → 409 wrong_class."""
    krieger = roster["Krieger Stonefist"]
    bandit_tmpl = await _bandit_template(gm_client)
    bandit_cb = "tok_test_tw_wrong"
    await _seed_battle(gm_client, [
        {"id": f"tok_test_{krieger['id']}", "char_id": krieger["id"],
         "name": krieger["name"], "initiative": 10,
         "hp_current": 55, "hp_max": 55, "buffs": [],
         "economy": {"action": False, "bonus": False,
                     "reaction": False, "movement": 0}},
        {"id": bandit_cb, "char_id": None,
         "token_template_id": bandit_tmpl["id"],
         "name": bandit_tmpl["name"], "initiative": 7,
         "hp_current": 11, "hp_max": 11, "buffs": [],
         "economy": {"action": False, "bonus": False,
                     "reaction": False, "movement": 0}},
    ])
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_thorn_whip",
        json={"character_id": krieger["id"], "target_combatant_id": bandit_cb},
    )
    assert r.status_code == 409, r.text
    assert r.json()["error"] == "wrong_class"


async def test_thorn_whip_missing_target_400(gm_client, roster):
    """Missing target_combatant_id → 400."""
    mira = roster["Mira Greenleaf"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_thorn_whip",
        json={"character_id": mira["id"]},
    )
    assert r.status_code == 400, r.text


async def test_thorn_whip_target_not_in_battle_404(gm_client, roster):
    """Unknown target combatant (not in battle) → 404."""
    mira = roster["Mira Greenleaf"]
    await _seed_battle(gm_client, [
        {"id": f"tok_test_{mira['id']}", "char_id": mira["id"],
         "name": mira["name"], "initiative": 10,
         "hp_current": 40, "hp_max": 40, "buffs": [],
         "economy": {"action": False, "bonus": False,
                     "reaction": False, "movement": 0}},
    ])
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_thorn_whip",
        json={"character_id": mira["id"],
              "target_combatant_id": "nope_not_in_battle"},
    )
    assert r.status_code == 404, r.text
