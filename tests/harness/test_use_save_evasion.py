"""v2.51.5 — Evasion (Monk Lv 7+) in the save-spell damage pipeline.

When a Monk Lv 7+ (or Rogue Lv 7+) is hit by a Dex-save spell that
would normally do "half damage on save, full on fail," Evasion
intercepts:
  - save passed → 0 damage
  - save failed → half damage

Server-side helper ``_apply_evasion_to_dex_save_damage`` plugs into
every save-for-half path (cast_spell single + AoE, npc_cast_spell,
the AoE PC save reroll via roll_request response). Broadcasts a
``feature_used`` event with ``source: "evasion"`` when it fires.

Tests use the AoE multi-target Fireball flow (caster + bandit +
test PC) because the single-target Fireball-at-PC path doesn't
apply damage server-side — only the AoE flow stashes the
``is_aoe: True`` context that the roll-request response handler
needs to roll and apply damage.

Tests:
  - happy path (pass): Thalindra casts Fireball at [bandit, Kael];
    loop until Kael's Dex save passes; assert damage_applied == 0
    and a feature_used(source=evasion) broadcast fires.
  - happy path (fail): same setup; loop until Kael's save fails;
    assert damage_applied is roughly half of the rolled fireball.
  - control (non-Monk-7): Tavik (Cleric 5) takes the same Fireball;
    standard save-for-half applies (no Evasion broadcast, damage is
    half-on-save / full-on-fail).
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID


FIREBALL_INDEX = 7  # Thalindra's spell list — see test_cast_spell_aoe.py


async def _bandit_tmpl(gm_client):
    r = await gm_client.get(f"/api/campaign/{CAMPAIGN_ID}/templates")
    templates = r.json()
    return next((t for t in templates if "bandit" in t["name"].lower()), templates[0])


@pytest_asyncio.fixture
async def thalindra_rested(gm_client, roster):
    thal = roster["Thalindra Moonwhisper"]
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{thal['id']}/rest",
        json={"type": "long"},
    )
    return thal


async def _set_auto_apply(gm_client, on: bool) -> None:
    form = {
        "name": "Demo Campaign",
        "description": "demo",
        "game_system": "dnd5e",
        "gm_tab_color": "",
        "font_override": "",
        "default_encounter_id": "",
        "hp_threshold_1": "",
        "hp_threshold_2": "",
        "hp_threshold_3": "",
        "hp_threshold_4": "",
        "auto_play_playlist_id": "",
        "auto_play_mode": "order",
        "auto_play_initial_volume": "0.7",
    }
    if on:
        form["auto_apply_damage"] = "on"
    await gm_client.post(
        f"/campaign/{CAMPAIGN_ID}/settings", data=form,
        follow_redirects=False,
    )


async def _seed_battle(gm_client, combatants):
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": combatants, "turn_index": 0, "round": 1, "active": True},
    )


def _evasion_broadcasts(gm_ws, character_id: int) -> list:
    """Buffered feature_used broadcasts with source=evasion targeting
    the named character. Returns the list (possibly empty)."""
    return [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "evasion"
        and (m.get("data") or {}).get("character_id") == character_id
    ]


async def _drive_save_until_outcome(
    gm_client, gm_ws, caster, target, want_passed: bool, max_iters: int = 25,
):
    """Cast Fireball via the AoE path at [bandit, target], respond on
    the target's behalf, loop until the save outcome matches
    ``want_passed``. Returns the ``spell_cast_target_updated``
    broadcast for the matched run.

    Long-rests the caster between iterations so spell slots refill;
    re-seeds the battle each iteration so the target's HP doesn't
    drift into the death-save zone.
    """
    tmpl = await _bandit_tmpl(gm_client)
    target_tok = f"tok_ev_{target['id']}"
    for _ in range(max_iters):
        await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/character/{caster['id']}/rest",
            json={"type": "long"},
        )
        await _seed_battle(gm_client, [
            {"id": f"tok_ev_{caster['id']}", "char_id": caster["id"],
             "name": caster["name"], "initiative": 10,
             "hp_current": 24, "hp_max": 24, "buffs": [],
             "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0}},
            {"id": "tok_ev_bandit", "char_id": None,
             "token_template_id": tmpl["id"],
             "name": "Bandit", "initiative": 7,
             "hp_current": 50, "hp_max": 50, "buffs": [],
             "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0}},
            {"id": target_tok, "char_id": target["id"],
             "name": target["name"], "initiative": 8,
             "hp_current": 52, "hp_max": 52, "buffs": [],
             "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0}},
        ])
        gm_ws.mark()
        resp = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
            json={
                "character_id": caster["id"],
                "spell_index": FIREBALL_INDEX,
                "slot_level": 3,
                "class_slug": "wizard",
                "target_combatant_ids": ["tok_ev_bandit", target_tok],
                "override": True,
            },
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        targets = data.get("auto_save_targets") or []
        # The PC target entry should be pc_skipped with a pending_request_id.
        pc_entry = next(
            (t for t in targets if t.get("combatant_id") == target_tok), None,
        )
        assert pc_entry is not None, (
            f"no target entry for {target['name']} ({target_tok}); got: {targets}"
        )
        assert pc_entry.get("pc_skipped") is True
        pending_id = pc_entry["pending_request_id"]
        assert isinstance(pending_id, int) and pending_id > 0

        # GM-as-target submits the save. This fires the AoE PC save
        # path at tabletop_routes.py:~7645 which calls
        # _apply_evasion_to_dex_save_damage.
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/roll_request/{pending_id}/respond",
            json={"character_id": target["id"]},
        )
        assert r.status_code == 200, r.text
        upd = await gm_ws.wait_for("spell_cast_target_updated", timeout=3.0)
        upd_data = upd["data"]
        if bool(upd_data.get("passed")) == want_passed:
            return upd
    raise AssertionError(
        f"Could not land save_passed={want_passed} for {target['name']} "
        f"in {max_iters} attempts"
    )


async def test_evasion_save_success_zero_damage(
    gm_client, gm_ws, roster, thalindra_rested,
):
    """Kael (Monk Lv 7) — save passes → damage_applied == 0 AND a
    feature_used(source=evasion) broadcast fires for him.
    """
    await _set_auto_apply(gm_client, on=True)
    thal = thalindra_rested
    kael = roster["Kael Brightleaf"]

    upd = await _drive_save_until_outcome(
        gm_client, gm_ws, thal, kael, want_passed=True,
    )
    upd_data = upd["data"]
    assert upd_data["passed"] is True
    assert upd_data["damage_applied"] == 0, (
        f"Evasion should zero out damage on save success; got {upd_data['damage_applied']}"
    )
    ev_msgs = _evasion_broadcasts(gm_ws, kael["id"])
    assert ev_msgs, (
        f"Expected a feature_used(source=evasion) broadcast for Kael; "
        f"buffered: {[(m.get('type'), (m.get('data') or {}).get('source')) for m in gm_ws.buffered()]}"
    )


async def test_evasion_save_fail_half_damage(
    gm_client, gm_ws, roster, thalindra_rested,
):
    """Kael (Monk Lv 7) — save fails → damage_applied is roughly half
    of the rolled fireball damage. Feature_used(source=evasion) also
    fires on the fail branch (per RAW: Evasion always intercepts
    Dex-save damage, the modifier just changes by save outcome).
    """
    await _set_auto_apply(gm_client, on=True)
    thal = thalindra_rested
    kael = roster["Kael Brightleaf"]

    upd = await _drive_save_until_outcome(
        gm_client, gm_ws, thal, kael, want_passed=False,
    )
    upd_data = upd["data"]
    assert upd_data["passed"] is False
    # 8d6 fireball at L3 → range 8-48; half → 4-24. damage_applied
    # mirrors the post-Evasion `rolled // 2`. Floor lower bound at 4
    # to catch a regression where the helper short-circuits early.
    assert 4 <= upd_data["damage_applied"] <= 24, (
        f"Evasion failed-save should halve damage (8d6 → 4-24 range); "
        f"got damage_applied={upd_data['damage_applied']}"
    )
    ev_msgs = _evasion_broadcasts(gm_ws, kael["id"])
    assert ev_msgs, (
        f"Expected a feature_used(source=evasion) broadcast on the "
        f"fail branch too; buffered: "
        f"{[(m.get('type'), (m.get('data') or {}).get('source')) for m in gm_ws.buffered()]}"
    )


async def test_non_monk7_target_standard_save_for_half(
    gm_client, gm_ws, roster, thalindra_rested,
):
    """Control: Tavik (Cleric Lv 5, no Evasion) takes standard
    save-for-half damage from Fireball. No feature_used(source=
    evasion) broadcast should fire.

    On a save success, Tavik takes HALF damage (4-24 range for 8d6) —
    NOT zero (zero would mean Evasion fired erroneously).
    """
    await _set_auto_apply(gm_client, on=True)
    thal = thalindra_rested
    tavik = roster["Brother Tavik Stonebrow"]

    upd = await _drive_save_until_outcome(
        gm_client, gm_ws, thal, tavik, want_passed=True,
    )
    upd_data = upd["data"]
    assert upd_data["passed"] is True
    # Standard save-for-half: half on save (4-24 for 8d6). If this
    # comes back as 0 the helper fired on a non-Monk-7 PC — bug.
    assert upd_data["damage_applied"] > 0, (
        f"Standard save-for-half should leave Tavik with HALF damage "
        f"(not zero) on save success; got {upd_data['damage_applied']} — "
        f"Evasion may have fired on a non-Monk-7+ target."
    )
    ev_msgs = _evasion_broadcasts(gm_ws, tavik["id"])
    assert not ev_msgs, (
        f"Evasion broadcast should NOT fire for Tavik (Cleric Lv 5): {ev_msgs}"
    )
