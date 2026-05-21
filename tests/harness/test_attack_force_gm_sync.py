"""/api/campaign/{cid}/attack — battle_update broadcast carries
``force_gm_sync: True`` so GM clients pick up NPC HP changes.

v2.49.40 fix. Before this fix, the broadcast at
``_apply_damage_to_combatant`` (line 1146) lacked the flag — the
GM client's ``battle_update`` handler in tabletop.html:5543 only
accepts the message when ``!IS_GM || msg.force_gm_sync``, so the
GM ignored the broadcast and their local ``battle.combatants[…]
.hp_current`` stayed at the pre-attack value. A subsequent
``pushBattle()`` (any drag-token or init-edit action) overwrote
the server's correctly-updated HP with the GM's stale value.

The encounter-sim test suite's GM-driver caveat (documented in
every Phase 1/2 PoC docstring + the test_garrik_strike top-of-file
comment) was a workaround for this bug. With the fix in place,
the workaround is no longer necessary.

Mirrors the v2.48.8 /place_aoe pattern (tabletop_routes.py:7986)
which already broadcasts force_gm_sync correctly.
"""
from .conftest import CAMPAIGN_ID


def _mkc(cid, char_id=None, hp_cur=30, hp_max=30, name="X", template_id=None):
    out = {
        "id": cid,
        "char_id": char_id,
        "name": name,
        "initiative": 10,
        "hp_current": hp_cur,
        "hp_max": hp_max,
        "buffs": [],
        "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0},
    }
    if template_id is not None:
        out["token_template_id"] = template_id
    return out


async def _seed_battle(gm_client, combatants):
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": combatants, "turn_index": 0, "round": 1, "active": True},
    )


async def _set_auto_apply(gm_client, on: bool) -> None:
    form = {
        "name": "Demo Campaign", "description": "demo", "game_system": "dnd5e",
        "gm_tab_color": "", "font_override": "", "default_encounter_id": "",
        "hp_threshold_1": "", "hp_threshold_2": "", "hp_threshold_3": "",
        "hp_threshold_4": "",
        "auto_play_playlist_id": "", "auto_play_mode": "order",
        "auto_play_initial_volume": "0.7",
    }
    if on:
        form["auto_apply_damage"] = "on"
    await gm_client.post(
        f"/campaign/{CAMPAIGN_ID}/settings", data=form, follow_redirects=False,
    )


async def test_npc_damage_broadcast_carries_force_gm_sync(gm_client, gm_ws, roster):
    """Attack an NPC combatant; assert the ``battle_update`` broadcast
    has ``force_gm_sync: True`` set."""
    krieger = roster["Krieger Stonefist"]
    bandit_cid = "tok_fgs_bandit"

    # Long-rest Krieger so any prior test's depleted state doesn't
    # interfere.
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{krieger['id']}/rest",
        json={"type": "long"},
    )
    await _set_auto_apply(gm_client, on=True)

    # Fetch the bandit template id so the NPC combatant has a real
    # token_template_id (auto_save_target_kind / damage path needs it).
    r = await gm_client.get(f"/api/campaign/{CAMPAIGN_ID}/templates")
    templates = r.json()
    bandit_tmpl = next((t for t in templates if "bandit" in t["name"].lower()), templates[0])

    await _seed_battle(gm_client, [
        _mkc(f"tok_fgs_krieger_{krieger['id']}", char_id=krieger["id"],
             name=krieger["name"], hp_cur=58, hp_max=58),
        _mkc(bandit_cid, template_id=bandit_tmpl["id"], name="Bandit Alpha",
             hp_cur=50, hp_max=50),
    ])
    gm_ws.mark()

    try:
        resp = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/attack",
            json={
                "character_id": krieger["id"],
                "attack_index": 0,
                "target_combatant_id": bandit_cid,
                "override": True,
            },
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()

        # If the attack hit and applied damage, a battle_update broadcast
        # fires from _apply_damage_to_combatant's NPC branch. Skip the
        # assertion on miss (no broadcast in that case).
        if body.get("damage_applied", 0) > 0:
            msg = await gm_ws.wait_for("battle_update")
            assert msg.get("force_gm_sync") is True, (
                f"v2.49.40 regression: battle_update for NPC damage should "
                f"carry force_gm_sync=True so the GM client applies it. "
                f"Got: {msg}"
            )
            # Sanity: the broadcasted state actually contains the updated
            # combatant with the post-damage HP.
            bandit_after = next(
                (c for c in msg["data"]["combatants"] if c["id"] == bandit_cid), None
            )
            assert bandit_after is not None
            assert bandit_after["hp_current"] == body["target_hp_after"]
    finally:
        # v2.49.43 — restore auto_apply_damage to OFF (demo default) so
        # subsequent tests in the same session that ASSUME off don't
        # flake. The harness's existing tests sometimes assert
        # "damage_applied == 0 when toggle off"; without this teardown
        # they could see the on-state from this test leaking through.
        # Surfaced in the v2.49.40 commit run as a sporadic
        # test_attack_sneak_attack_uplift failure.
        await _set_auto_apply(gm_client, on=False)
