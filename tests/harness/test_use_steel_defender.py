"""Steel Defender — Battle Smith Artificer Lv 3+, fourth summon retrofit.

v2.99.442 — Phase 7.2 of docs/plans/movement-and-summons.md. Builds on
the summon primitive: `/use_steel_defender` stands up the construct
companion (HP = 2 + INT mod + 5 × level, AC 15) and, when a
`target_combatant_id` is supplied, makes its Force-Empowered Rend attack
server-side (1d8 + prof force on a hit).

The demo has no Artificer, so the happy-path tests PATCH Thalindra
Moonwhisper's subclass to "Battle Smith" (then restore) — the gate keys
off the unambiguous subclass + level. Her Lv 5 / INT 16 stand in for a
Battle Smith's level + INT (defender HP 2 + 3 + 25 = 30).

Tests:
  - summon-only: no target → the construct appears with HP 30 / AC 15;
    `attacked` False.
  - summon + rend: loop a fresh defender each cast until the rend hits a
    bandit → force damage applied.
  - 409 wrong_subclass: default Thalindra (Evocation).
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID


async def _patch_sheet(gm_client, char_id, fields):
    r = await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-fields",
        json=dict(fields),
    )
    assert r.status_code == 200, r.text


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


def _pc_cb(c):
    return {
        "id": f"tok_test_{c['id']}", "char_id": c["id"], "name": c["name"],
        "initiative": 10, "hp_current": 40, "hp_max": 40, "buffs": [],
        "economy": {"action": False, "bonus": False,
                    "reaction": False, "movement": 0},
    }


async def _dismiss(gm_client, combatant_id):
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/dismiss_companion",
        json={"combatant_id": combatant_id},
    )


@pytest_asyncio.fixture
async def thalindra_battle_smith(gm_client, roster):
    """PATCH Thalindra to Battle Smith for the test, then restore her
    demo Evocation subclass. Pins level + abilities (INT 16) to the demo
    values so the Steel Defender HP (2 + INT mod + 5×level) is
    deterministic regardless of any DB drift from earlier sheet PATCHes
    in the suite."""
    thalindra = roster["Thalindra Moonwhisper"]
    await _patch_sheet(gm_client, thalindra["id"], {
        "subclass": "Battle Smith",
        "level": 5,
        "abilities": {"STR": 8, "DEX": 14, "CON": 13,
                      "INT": 16, "WIS": 12, "CHA": 10},
    })
    try:
        yield thalindra
    finally:
        await _patch_sheet(
            gm_client, thalindra["id"], {"subclass": "School of Evocation"})


async def test_steel_defender_summon_only(gm_client, thalindra_battle_smith):
    """No target → the construct appears with HP 2 + INT mod + 5×level
    (Lv 5 / INT 16 → 30) + AC 15; `attacked` False."""
    art = thalindra_battle_smith
    await _seed_battle(gm_client, [_pc_cb(art)])
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_steel_defender",
        json={"character_id": art["id"], "x": 700.0, "y": 700.0},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    cb = body["combatant"]
    try:
        assert body["feature"] == "steel-defender"
        assert body["attacked"] is False
        assert body["defender_hp"] == 30  # 2 + INT 3 + 5×5
        assert body["defender_ac"] == 15
        assert cb["is_summon"] is True
        assert cb["companion_key"] == "steel-defender"
        assert cb["hp_max"] == 30
        assert cb["ac"] == 15
        assert cb["summoned_by"] == art["id"]
        assert body["token_id"] is not None
    finally:
        await _dismiss(gm_client, cb["id"])


async def test_steel_defender_rends_target(gm_client, thalindra_battle_smith):
    """Loop a fresh defender each cast until the Rend hits a bandit →
    force damage applied. Each defender is dismissed."""
    art = thalindra_battle_smith
    bandit_tmpl = await _bandit_template(gm_client)
    bandit_cb = "tok_test_sd_bandit"

    hit_seen = False
    for _ in range(30):
        await _seed_battle(gm_client, [
            _pc_cb(art),
            {"id": bandit_cb, "char_id": None,
             "token_template_id": bandit_tmpl["id"],
             "name": bandit_tmpl["name"], "initiative": 7,
             "hp_current": 30, "hp_max": 30, "buffs": [],
             "economy": {"action": False, "bonus": False,
                         "reaction": False, "movement": 0}},
        ])
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/use_steel_defender",
            json={"character_id": art["id"], "x": 700.0, "y": 700.0,
                  "target_combatant_id": bandit_cb},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["attacked"] is True
        assert body["target_ac"] > 0
        def_id = body["combatant"]["id"]
        try:
            if body["hit"]:
                assert body["damage_type"] == "force"
                assert body["damage_rolled"] > 0
                assert body["damage_applied"] > 0
                hit_seen = True
                break
        finally:
            await _dismiss(gm_client, def_id)
    assert hit_seen, "no rend hit in 30 casts — flaky env?"


async def test_steel_defender_wrong_subclass(gm_client, roster):
    """Default Thalindra (Evocation) → 409 wrong_subclass_or_level."""
    thalindra = roster["Thalindra Moonwhisper"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_steel_defender",
        json={"character_id": thalindra["id"]},
    )
    assert r.status_code == 409, r.text
    assert r.json()["error"] == "wrong_subclass_or_level"
