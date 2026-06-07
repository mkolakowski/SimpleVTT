"""Ranger's Companion — Beast Master Lv 3+, third summon retrofit.

v2.99.441 — Phase 7.2 of docs/plans/movement-and-summons.md. Builds on
the summon primitive: `/use_animal_companion` stands up the beast
companion (HP = max(beast HP, 4 × ranger level), AC = 13 + prof) and,
when a `target_combatant_id` is supplied, makes the beast's bite attack
server-side (2d4 + STR-mod piercing on a hit).

The demo Ranger (Rowan Quickbow) is a Hunter, so the happy-path tests
PATCH his subclass to Beast Master (then restore) — the same trick the
Battle Master / Open Hand suites use.

Tests:
  - summon-only: no target → the beast combatant appears with scaled HP
    (Lv 5 → 20) + AC 16; `attacked` False.
  - summon + bite: loop a fresh companion each cast until the bite hits a
    bandit → piercing damage applied.
  - 409 wrong_subclass: default Rowan (Hunter).
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
async def rowan_beast_master(gm_client, roster):
    """PATCH Rowan to Beast Master for the duration of the test, then
    restore his demo Hunter subclass."""
    rowan = roster["Rowan Quickbow"]
    await _patch_sheet(gm_client, rowan["id"], {"subclass": "Beast Master"})
    try:
        yield rowan
    finally:
        await _patch_sheet(gm_client, rowan["id"], {"subclass": "Hunter"})


async def test_animal_companion_summon_only(gm_client, rowan_beast_master):
    """No target → the beast combatant appears with HP scaled to the
    ranger's level (Lv 5 → 20) + AC 13 + prof (16); `attacked` False."""
    rowan = rowan_beast_master
    await _seed_battle(gm_client, [_pc_cb(rowan)])
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_animal_companion",
        json={"character_id": rowan["id"], "x": 700.0, "y": 700.0},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    cb = body["combatant"]
    try:
        assert body["feature"] == "animal-companion"
        assert body["attacked"] is False
        assert body["ranger_level"] == 5
        assert body["companion_hp"] == 20  # max(11, 4×5)
        assert body["companion_ac"] == 16  # 13 + prof 3
        assert cb["is_summon"] is True
        assert cb["companion_key"] == "beast-companion"
        assert cb["hp_max"] == 20
        assert cb["ac"] == 16
        assert cb["summoned_by"] == rowan["id"]
        assert body["token_id"] is not None
    finally:
        await _dismiss(gm_client, cb["id"])


async def test_animal_companion_bites_target(gm_client, rowan_beast_master):
    """Loop a fresh companion each cast until the bite hits a bandit →
    piercing damage applied. Each cast's companion is dismissed."""
    rowan = rowan_beast_master
    bandit_tmpl = await _bandit_template(gm_client)
    bandit_cb = "tok_test_ac_bandit"

    hit_seen = False
    for _ in range(30):
        await _seed_battle(gm_client, [
            _pc_cb(rowan),
            {"id": bandit_cb, "char_id": None,
             "token_template_id": bandit_tmpl["id"],
             "name": bandit_tmpl["name"], "initiative": 7,
             "hp_current": 30, "hp_max": 30, "buffs": [],
             "economy": {"action": False, "bonus": False,
                         "reaction": False, "movement": 0}},
        ])
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/use_animal_companion",
            json={"character_id": rowan["id"], "x": 700.0, "y": 700.0,
                  "target_combatant_id": bandit_cb},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["attacked"] is True
        assert body["target_ac"] > 0
        comp_id = body["combatant"]["id"]
        try:
            if body["hit"]:
                assert body["damage_type"] == "piercing"
                assert body["damage_rolled"] > 0
                assert body["damage_applied"] > 0
                hit_seen = True
                break
        finally:
            await _dismiss(gm_client, comp_id)
    assert hit_seen, "no bite hit in 30 casts — flaky env?"


async def test_animal_companion_wrong_subclass(gm_client, roster):
    """Default Rowan (Hunter) → 409 wrong_subclass_or_level."""
    rowan = roster["Rowan Quickbow"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_animal_companion",
        json={"character_id": rowan["id"]},
    )
    assert r.status_code == 409, r.text
    assert r.json()["error"] == "wrong_subclass_or_level"
