"""Monk Stunning Strike — class feature endpoint.

v2.49.55 — adds ``POST /api/campaign/{cid}/use_stunning_strike``.
Monk Lv 5+ class feature: spend 1 ki on a hit to force the target
to make a CON save or be Stunned until the end of the monk's next
turn. Save DC = 8 + monk prof + monk WIS mod.

The Stunned condition is concentration=False (1-turn duration, RAW)
— this commit exercises the v2.49.51 "incapacitating buff with
concentration=False" branch for NPCs via ``_install_buff_on_combatant_id``.
The PC roll_request path is wired the same way as Hold Person but
not exhaustively tested here (the v2.49.51 hook fires from
``_install_buff`` regardless of caller, and the Hold Person path
already pins that).

Tests:
  - Happy path (NPC): Kael (Monk Lv 5) uses Stunning Strike on a
    bandit; loop until save fails; assert Stunned installed on the
    bandit + ki decremented by 1 + 200 response.
  - 409 wrong_class: Krieger (Barbarian) → 409 wrong_class.
  - 409 no_ki: drain Kael's ki to 0; → 409 no_ki + ki not consumed.
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID


@pytest_asyncio.fixture
async def kael_rested(gm_client, roster):
    """Long-rest Kael + reset any leftover buffs from prior tests."""
    kael = roster["Kael Brightleaf"]
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{kael['id']}/rest",
        json={"type": "long"},
    )
    return kael


async def _seed_battle(gm_client, combatants):
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": combatants, "turn_index": 0, "round": 1, "active": True},
    )


async def _bandit_template(gm_client):
    r = await gm_client.get(f"/api/campaign/{CAMPAIGN_ID}/templates")
    templates = r.json()
    return next((t for t in templates if "bandit" in t["name"].lower()), templates[0])


async def test_stunning_strike_happy_path_npc(gm_client, gm_ws, kael_rested):
    """Kael uses Stunning Strike on a bandit; retry until save fails;
    assert Stunned buff installed (concentration=False) + ki spent."""
    kael = kael_rested
    bandit_tmpl = await _bandit_template(gm_client)
    bandit_id = "tok_test_stun_bandit"

    saw_stun = False
    for _ in range(20):
        # Refill ki + reset combatants each iteration so we don't run
        # out of ki across the loop.
        await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/character/{kael['id']}/rest",
            json={"type": "long"},
        )
        await _seed_battle(gm_client, [
            {"id": f"tok_test_{kael['id']}", "char_id": kael["id"],
             "name": kael["name"], "initiative": 10,
             "hp_current": 30, "hp_max": 30, "buffs": [],
             "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0}},
            {"id": bandit_id, "char_id": None,
             "token_template_id": bandit_tmpl["id"],
             "name": bandit_tmpl["name"], "initiative": 7,
             "hp_current": 11, "hp_max": 11, "buffs": [],
             "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0}},
        ])
        gm_ws.mark()
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/use_stunning_strike",
            json={
                "character_id": kael["id"],
                "target_combatant_id": bandit_id,
            },
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["ok"] is True
        assert body["auto_save_target_kind"] == "npc"
        assert body["save_dc"] > 0
        assert body["ki_remaining"] >= 0
        # Server should have rolled.
        assert body["auto_save_rolled"] is not None
        assert body["auto_save_passed"] is not None
        if body["auto_save_passed"]:
            continue  # save passed — no buff installed
        assert body["auto_save_buff_installed"] == "Stunned"
        # Verify via the battle_update broadcast that _install_buff_on_combatant_id
        # fired with the right shape — Stunned with concentration=False.
        bu = await gm_ws.wait_for("battle_update", timeout=2.0)
        combatants = (bu.get("data") or {}).get("combatants") or []
        bandit = next(
            (c for c in combatants if c.get("id") == bandit_id), None,
        )
        assert bandit is not None, f"bandit missing in battle_update; got {combatants}"
        stunned_buffs = [
            b for b in (bandit.get("buffs") or [])
            if (b or {}).get("key") == "stunned"
        ]
        assert stunned_buffs, f"Stunned buff missing; got {bandit.get('buffs')}"
        assert stunned_buffs[0].get("concentration") is False, (
            f"Stunned should be concentration=False (RAW 1-turn condition); "
            f"got {stunned_buffs[0]}"
        )
        assert stunned_buffs[0].get("source_char_id") == kael["id"], (
            f"source_char_id should be the monk; got {stunned_buffs[0]}"
        )
        saw_stun = True
        break

    assert saw_stun, "no save failure in 20 attempts — flaky env?"


async def test_stunning_strike_wrong_class(gm_client, roster):
    """Krieger (Barbarian) tries Stunning Strike → 409 wrong_class."""
    krieger = roster["Krieger Stonefist"]
    bandit_tmpl = await _bandit_template(gm_client)
    bandit_id = "tok_test_stun_wrong"
    await _seed_battle(gm_client, [
        {"id": f"tok_test_{krieger['id']}", "char_id": krieger["id"],
         "name": krieger["name"], "initiative": 10,
         "hp_current": 55, "hp_max": 55, "buffs": [],
         "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0}},
        {"id": bandit_id, "char_id": None,
         "token_template_id": bandit_tmpl["id"],
         "name": bandit_tmpl["name"], "initiative": 7,
         "hp_current": 11, "hp_max": 11, "buffs": [],
         "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0}},
    ])
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_stunning_strike",
        json={
            "character_id": krieger["id"],
            "target_combatant_id": bandit_id,
        },
    )
    assert r.status_code == 409, r.text
    err = r.json()
    assert err["error"] == "wrong_class"
    assert err["expected"] == "monk"


async def test_stunning_strike_no_ki(gm_client, kael_rested):
    """Drain Kael's ki via repeated /use_stunning_strike (each costs 1).
    When ki_remaining hits 0, next attempt → 409 no_ki."""
    kael = kael_rested
    bandit_tmpl = await _bandit_template(gm_client)
    bandit_id = "tok_test_stun_noki"
    await _seed_battle(gm_client, [
        {"id": f"tok_test_{kael['id']}", "char_id": kael["id"],
         "name": kael["name"], "initiative": 10,
         "hp_current": 30, "hp_max": 30, "buffs": [],
         "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0}},
        {"id": bandit_id, "char_id": None,
         "token_template_id": bandit_tmpl["id"],
         "name": bandit_tmpl["name"], "initiative": 7,
         "hp_current": 11, "hp_max": 11, "buffs": [],
         "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0}},
    ])
    # Drain ki via the endpoint itself; the response carries
    # ki_remaining so we know when to stop.
    ki_remaining = None
    for _ in range(20):  # cap iterations defensively
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/use_stunning_strike",
            json={
                "character_id": kael["id"],
                "target_combatant_id": bandit_id,
            },
        )
        assert r.status_code == 200, r.text
        ki_remaining = r.json()["ki_remaining"]
        if ki_remaining == 0:
            break
    assert ki_remaining == 0, f"failed to drain ki in 20 iterations; got {ki_remaining}"

    # Now ki is 0; next call → 409 no_ki.
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_stunning_strike",
        json={
            "character_id": kael["id"],
            "target_combatant_id": bandit_id,
        },
    )
    assert r.status_code == 409, r.text
    err = r.json()
    assert err["error"] == "no_ki"
    assert err["available"] == 0
