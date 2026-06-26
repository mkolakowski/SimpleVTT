"""v2.658.0 — Phase 3c-1 of docs/plans/pending-resolution-state-machine.md:
weapon on-hit-*save* condition installs against an NPC target are now logged
under the originating attack's id, so the install is undoable via
``/undo_attack_damage`` (and — Phase 3c-2 — revertible on a hit->miss flip).

Recipe mirrors ``test_menacing_attack.py``: PATCH Garrik to a Battle Master,
arm Menacing Attack (an on-hit ``weapon_hit_save`` rider), hit an NPC bandit
until the WIS save fails (Frightened installs synchronously via
``_fire_weapon_hit_saves`` -> ``_resolve_feature_save``), then undo the attack
and assert the Frightened condition is reverted off the bandit.

Before this commit the NPC on-hit-save install was un-logged, so
``/undo_attack_damage`` healed the damage but left Frightened stuck on the
target. This test is the regression net for that gap.
"""
import asyncio
import pytest_asyncio

from .conftest import CAMPAIGN_ID


async def _patch_sheet(gm_client, char_id, fields, class_slug=None):
    body = dict(fields)
    if class_slug:
        body["class_slug"] = class_slug
    r = await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-fields",
        json=body,
    )
    assert r.status_code == 200, r.text


def _superiority_dice_block(current: int, maximum: int) -> dict:
    return {
        "key": "superiority-dice",
        "name": "Superiority Dice",
        "current": current, "max": maximum, "reset": "short",
        "source": "fighter Lv 3 / Combat Superiority",
        "class_slug": "fighter",
        "desc": "Battle Master maneuvers. Refreshes on short or long rest.",
        "manual": False,
    }


@pytest_asyncio.fixture
async def garrik_battle_master(gm_client, roster):
    """PATCH Garrik to Battle Master + seed a deep superiority-dice pool."""
    garrik = roster["Garrik Ironside"]
    await _patch_sheet(
        gm_client, garrik["id"],
        {
            "subclass": "Battle Master",
            "superiority_die_size": "d8",
            "resources": [_superiority_dice_block(40, 40)],
        },
        class_slug="fighter",
    )
    try:
        yield garrik
    finally:
        await _patch_sheet(
            gm_client, garrik["id"],
            {"subclass": "Champion", "resources": []},
            class_slug="fighter",
        )


def _bandit_template(templates):
    return next(
        (t for t in templates if "bandit" in (t.get("name") or "").lower()),
        templates[0],
    )


async def _reset_battle(gm_client, garrik, garrik_tok, dummy_tok, bandit):
    """Fresh battle state each iteration — clears the once-per-turn econ
    flag on Garrik AND any Frightened left on the bandit, so each retry
    is a clean slate."""
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": [
            {"id": garrik_tok, "char_id": garrik["id"], "name": garrik["name"],
             "initiative": 12, "hp_current": 60, "hp_max": 60, "buffs": [],
             "economy": {"action": False, "bonus": False,
                         "reaction": False, "movement": 0}},
            {"id": dummy_tok, "char_id": None,
             "token_template_id": bandit["id"], "name": bandit["name"],
             "initiative": 8, "hp_current": 30, "hp_max": 30, "buffs": [],
             "economy": {"action": False, "bonus": False,
                         "reaction": False, "movement": 0}},
        ], "turn_index": 0, "round": 1, "active": True},
    )


async def test_undo_reverts_npc_on_hit_save_condition(
    gm_client, gm_ws, garrik_battle_master,
):
    """Happy path: a failed NPC on-hit save installs Frightened, and
    ``/undo_attack_damage`` reverts it (logged under the attack id)."""
    garrik = garrik_battle_master
    templates = (await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/templates")).json()
    bandit = _bandit_template(templates)
    garrik_tok = f"tok_whsu_garrik_{garrik['id']}"
    dummy_tok = "tok_whsu_bandit"

    # Loop until a single swing both HITS and FAILS the WIS save (DC 16 vs
    # a Bandit's +0 WIS fails ~75% of hits). Re-arm + reset each iteration
    # because the rider is once-per-turn and the bandit save is random.
    attack_id = None
    for _ in range(40):
        await _reset_battle(gm_client, garrik, garrik_tok, dummy_tok, bandit)
        arm = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/use_menacing_attack",
            json={"character_id": garrik["id"]},
        )
        assert arm.status_code == 200, arm.text
        assert arm.json()["buff_installed"] is True

        fired = None
        for _ in range(25):
            a = await gm_client.post(
                f"/api/campaign/{CAMPAIGN_ID}/attack",
                json={"character_id": garrik["id"], "attack_index": 0,
                      "target_combatant_id": dummy_tok, "override": True},
            )
            assert a.status_code == 200, a.text
            if a.json()["hit"]:
                fired = a.json()
                break
        if not fired:
            continue
        fs = [s for s in (fired.get("feature_saves") or [])
              if s.get("source") == "menacing-attack" and s.get("resolved")]
        if not fs:
            continue
        if not fs[0].get("condition_installed"):
            continue  # save passed — retry for a failed one
        attack_id = fired["id"]
        break

    assert attack_id, "no hit+failed WIS save in 40 tries; can't test the undo"

    # Frightened is now on the bandit. Confirm via the authoritative battle
    # state (hub write-through-persists the install to the Battle row).
    await asyncio.sleep(0.2)
    state = (await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/battle")).json().get("battle") or {}
    dummy_cb = next(
        (c for c in (state.get("combatants") or [])
         if c.get("id") == dummy_tok), None)
    assert dummy_cb is not None
    assert any((b or {}).get("key") == "frightened"
               for b in (dummy_cb.get("buffs") or [])), \
        f"Frightened not installed pre-undo: {dummy_cb.get('buffs')}"

    # Undo the attack → the on-hit Frightened install is reverted.
    gm_ws.mark()
    u = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/undo_attack_damage",
        json={"attack_id": attack_id},
    )
    assert u.status_code == 200, u.text
    per_target = u.json().get("per_target") or []
    assert any(
        e.get("kind") == "buff_install" and e.get("buff_key") == "frightened"
        for e in per_target
    ), f"undo didn't report reverting Frightened: {per_target}"

    # The bandit is no longer Frightened.
    await asyncio.sleep(0.2)
    state2 = (await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/battle")).json().get("battle") or {}
    dummy_cb2 = next(
        (c for c in (state2.get("combatants") or [])
         if c.get("id") == dummy_tok), None)
    assert dummy_cb2 is not None
    assert not any((b or {}).get("key") == "frightened"
                   for b in (dummy_cb2.get("buffs") or [])), \
        f"Frightened still present after undo: {dummy_cb2.get('buffs')}"


async def test_undo_unknown_attack_id_404(gm_client):
    """Error path: undoing an attack id that was never logged → 404."""
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/undo_attack_damage",
        json={"attack_id": "deadbeefcafe"},
    )
    assert r.status_code == 404, r.text
