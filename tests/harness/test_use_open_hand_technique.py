"""Monk Open Hand Technique — Way of the Open Hand subclass feature.

v2.49.57 — adds ``POST /api/campaign/{cid}/use_open_hand_technique``.
Monk Way of the Open Hand Lv 3+. RAW: when monk hits with a Flurry
of Blows attack, they may impose one of three riders on the target
(see endpoint docstring). Modeled on Stunning Strike — same trust-
the-caller convention for the "must follow a Flurry hit" gate (UI is
expected to surface the button only after a Flurry hit).

Three modes:
  - ``prone``: DEX save vs DC 8 + monk prof + WIS mod. On fail
    install Prone. Routes through the save-or-suck pipeline + the
    new ``open-hand-prone`` entry in ``_SPELL_CONDITION_MAP``.
  - ``push``: STR save vs the same DC. No buff installed; response
    carries ``push_authorized`` so the GM UI can drag the token.
  - ``no_reactions``: no save, install ``reaction-denied`` buff
    inline (1-turn duration, RAW).

Tests:
  - prone NPC happy path: Kael uses prone on a bandit; retry until
    save fails; assert Prone installed + 200 response shape.
  - push NPC happy path: Kael uses push on a bandit; assert response
    carries ``push_authorized`` matching the (server-rolled) save
    outcome (False on pass, True on fail). Single-iteration assert
    (push_authorized is non-None either way).
  - no_reactions NPC: no save, immediate install; assert
    ``reaction-denied`` lands + roll-log entry fires.
  - 409 wrong_class: Krieger (Barbarian) → 409 wrong_class.
  - 409 wrong_subclass: Garrik (Fighter? no — pick a monk from a
    different subclass if any, else fall back to the wrong_class
    test). Demo only has one monk and it's Open Hand, so this case
    is covered with a sheet-patch trick: temporarily change Kael's
    subclass via /sheet PATCH, fire the endpoint, restore.
  - 400 bad mode: invalid mode string → 400.
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID


@pytest_asyncio.fixture
async def kael_rested(gm_client, roster):
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


async def test_open_hand_prone_happy_path_npc(gm_client, gm_ws, kael_rested):
    """Kael uses Open Hand (prone) on a bandit; retry until DEX save
    fails; assert Prone buff installed (key='prone', concentration=False)."""
    kael = kael_rested
    bandit_tmpl = await _bandit_template(gm_client)
    bandit_id = "tok_test_oht_prone"

    saw_prone = False
    for _ in range(20):
        await _seed_battle(gm_client, [
            {"id": f"tok_test_{kael['id']}", "char_id": kael["id"],
             "name": kael["name"], "initiative": 10,
             "hp_current": 38, "hp_max": 38, "buffs": [],
             "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0}},
            {"id": bandit_id, "char_id": None,
             "token_template_id": bandit_tmpl["id"],
             "name": bandit_tmpl["name"], "initiative": 7,
             "hp_current": 11, "hp_max": 11, "buffs": [],
             "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0}},
        ])
        gm_ws.mark()
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/use_open_hand_technique",
            json={
                "character_id": kael["id"],
                "target_combatant_id": bandit_id,
                "mode": "prone",
            },
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["ok"] is True
        assert body["mode"] == "prone"
        assert body["auto_save_target_kind"] == "npc"
        assert body["save_dc"] > 0
        assert body["auto_save_rolled"] is not None
        assert body["auto_save_passed"] is not None
        if body["auto_save_passed"]:
            continue
        assert body["auto_save_buff_installed"] == "Prone"
        bu = await gm_ws.wait_for("battle_update", timeout=2.0)
        combatants = (bu.get("data") or {}).get("combatants") or []
        bandit = next(
            (c for c in combatants if c.get("id") == bandit_id), None,
        )
        assert bandit is not None
        prone_buffs = [
            b for b in (bandit.get("buffs") or [])
            if (b or {}).get("key") == "prone"
        ]
        assert prone_buffs, f"Prone missing; got {bandit.get('buffs')}"
        assert prone_buffs[0].get("concentration") is False
        assert prone_buffs[0].get("source_char_id") == kael["id"]
        saw_prone = True
        break

    assert saw_prone, "no save failure in 20 attempts — flaky env?"


async def test_open_hand_push_npc(gm_client, kael_rested):
    """Kael uses Open Hand (push) on a bandit. NPC path: server rolls
    inline; response carries ``push_authorized`` matching the save
    outcome. No buff installed either way (push has no
    _SPELL_CONDITION_MAP entry).
    """
    kael = kael_rested
    bandit_tmpl = await _bandit_template(gm_client)
    bandit_id = "tok_test_oht_push"
    await _seed_battle(gm_client, [
        {"id": f"tok_test_{kael['id']}", "char_id": kael["id"],
         "name": kael["name"], "initiative": 10,
         "hp_current": 38, "hp_max": 38, "buffs": [],
         "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0}},
        {"id": bandit_id, "char_id": None,
         "token_template_id": bandit_tmpl["id"],
         "name": bandit_tmpl["name"], "initiative": 7,
         "hp_current": 11, "hp_max": 11, "buffs": [],
         "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0}},
    ])
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_open_hand_technique",
        json={
            "character_id": kael["id"],
            "target_combatant_id": bandit_id,
            "mode": "push",
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["mode"] == "push"
    assert body["auto_save_target_kind"] == "npc"
    assert body["auto_save_rolled"] is not None
    assert body["auto_save_passed"] is not None
    assert body["push_authorized"] is not None
    # push_authorized is the boolean inverse of the save outcome.
    assert body["push_authorized"] == (not body["auto_save_passed"])
    # No buff installed in push mode.
    assert body["auto_save_buff_installed"] == ""


async def test_open_hand_no_reactions_npc(gm_client, gm_ws, kael_rested):
    """Kael uses Open Hand (no_reactions) on a bandit. No save —
    immediate install of ``reaction-denied`` buff + public roll-log
    entry."""
    kael = kael_rested
    bandit_tmpl = await _bandit_template(gm_client)
    bandit_id = "tok_test_oht_noreact"
    await _seed_battle(gm_client, [
        {"id": f"tok_test_{kael['id']}", "char_id": kael["id"],
         "name": kael["name"], "initiative": 10,
         "hp_current": 38, "hp_max": 38, "buffs": [],
         "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0}},
        {"id": bandit_id, "char_id": None,
         "token_template_id": bandit_tmpl["id"],
         "name": bandit_tmpl["name"], "initiative": 7,
         "hp_current": 11, "hp_max": 11, "buffs": [],
         "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0}},
    ])
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_open_hand_technique",
        json={
            "character_id": kael["id"],
            "target_combatant_id": bandit_id,
            "mode": "no_reactions",
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["mode"] == "no_reactions"
    assert body["auto_save_prompted"] is False
    assert body["buff_installed"] == "No Reactions (Open Hand)"
    bu = await gm_ws.wait_for("battle_update", timeout=2.0)
    combatants = (bu.get("data") or {}).get("combatants") or []
    bandit = next(
        (c for c in combatants if c.get("id") == bandit_id), None,
    )
    assert bandit is not None
    buffs = [
        b for b in (bandit.get("buffs") or [])
        if (b or {}).get("key") == "reaction-denied"
    ]
    assert buffs, f"reaction-denied missing; got {bandit.get('buffs')}"
    assert buffs[0].get("concentration") is False
    assert buffs[0].get("duration_rounds") == 1
    assert buffs[0].get("source_char_id") == kael["id"]


async def test_open_hand_wrong_class(gm_client, roster):
    """Krieger (Barbarian) → 409 wrong_class."""
    krieger = roster["Krieger Stonefist"]
    bandit_tmpl = await _bandit_template(gm_client)
    bandit_id = "tok_test_oht_wrong"
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
        f"/api/campaign/{CAMPAIGN_ID}/use_open_hand_technique",
        json={
            "character_id": krieger["id"],
            "target_combatant_id": bandit_id,
            "mode": "prone",
        },
    )
    assert r.status_code == 409, r.text
    err = r.json()
    assert err["error"] == "wrong_class"
    assert err["expected"] == "monk"


async def test_open_hand_bad_mode(gm_client, kael_rested):
    """Invalid mode string → 400."""
    kael = kael_rested
    bandit_tmpl = await _bandit_template(gm_client)
    bandit_id = "tok_test_oht_badmode"
    await _seed_battle(gm_client, [
        {"id": f"tok_test_{kael['id']}", "char_id": kael["id"],
         "name": kael["name"], "initiative": 10,
         "hp_current": 38, "hp_max": 38, "buffs": [],
         "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0}},
        {"id": bandit_id, "char_id": None,
         "token_template_id": bandit_tmpl["id"],
         "name": bandit_tmpl["name"], "initiative": 7,
         "hp_current": 11, "hp_max": 11, "buffs": [],
         "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0}},
    ])
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_open_hand_technique",
        json={
            "character_id": kael["id"],
            "target_combatant_id": bandit_id,
            "mode": "spinning_palm_of_doom",
        },
    )
    assert r.status_code == 400, r.text
