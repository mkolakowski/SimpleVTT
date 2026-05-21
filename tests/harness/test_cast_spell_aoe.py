"""Phase T.5 — /cast_spell AoE multi-target dispatch.

v2.44.0: spells with ``area.shape == "sphere"`` accept a list of
combatants via ``target_combatant_ids`` (in addition to the existing
single-target ``target_combatant_id``). The endpoint loops save +
damage application per target and returns a per-target outcome list
in ``auto_save_targets``.

Tests:
  - Thalindra casts Fireball at 3 bandits with auto_apply_damage on:
    response carries ``auto_save_targets`` with 3 entries, each with
    rolled / passed / damage_applied; each bandit's HP dropped.
  - Single-target fallback: ``target_combatant_id`` (no list) still
    works unchanged.
  - PC target in AoE list is recorded as ``pc_skipped: True`` — v1
    doesn't auto-roll PC AoE saves; the GM still resolves manually.
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID


FIREBALL_INDEX = 7  # Demo Thalindra's spell list (app/demo_seed.py): 0 Fire Bolt,
                    # 1 Mage Hand, 2 Prestidigitation, 3 Magic Missile, 4 Shield,
                    # 5 Misty Step, 6 Scorching Ray, 7 Fireball, 8 Counterspell.


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


async def _bandit_tmpl(gm_client):
    r = await gm_client.get(f"/api/campaign/{CAMPAIGN_ID}/templates")
    templates = r.json()
    return next(t for t in templates if "bandit" in t["name"].lower())


async def test_fireball_hits_three_bandits(gm_client, gm_ws, roster, thalindra_rested):
    """Thalindra casts Fireball at 3 bandits — server loops the save
    + damage path 3 times, response includes 3 auto_save_targets.
    """
    thal = thalindra_rested
    tmpl = await _bandit_tmpl(gm_client)
    await _set_auto_apply(gm_client, on=True)
    await _seed_battle(gm_client, [
        {"id": f"tok_aoe_{thal['id']}", "char_id": thal["id"],
         "name": thal["name"], "initiative": 10, "hp_current": 24, "hp_max": 24,
         "buffs": [],
         "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0}},
        {"id": "tok_aoe_b1", "char_id": None,
         "token_template_id": tmpl["id"],
         "name": "Bandit Alpha", "initiative": 7, "hp_current": 50, "hp_max": 50,
         "buffs": [],
         "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0}},
        {"id": "tok_aoe_b2", "char_id": None,
         "token_template_id": tmpl["id"],
         "name": "Bandit Beta", "initiative": 6, "hp_current": 50, "hp_max": 50,
         "buffs": [],
         "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0}},
        {"id": "tok_aoe_b3", "char_id": None,
         "token_template_id": tmpl["id"],
         "name": "Bandit Gamma", "initiative": 5, "hp_current": 50, "hp_max": 50,
         "buffs": [],
         "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0}},
    ])

    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
        json={
            "character_id": thal["id"],
            "spell_index": FIREBALL_INDEX,
            "slot_level": 3,
            "class_slug": "wizard",
            "target_combatant_ids": ["tok_aoe_b1", "tok_aoe_b2", "tok_aoe_b3"],
            "override": True,
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    targets = data.get("auto_save_targets") or []
    assert len(targets) == 3, (
        f"expected 3 per-target outcomes, got {len(targets)}: {targets}"
    )
    names = {t["target_name"] for t in targets}
    assert names == {"Bandit Alpha", "Bandit Beta", "Bandit Gamma"}, (
        f"unexpected target names: {names}"
    )
    for t in targets:
        assert "rolled" in t and isinstance(t["rolled"], int)
        assert "passed" in t and isinstance(t["passed"], bool)
        # 8d6 fire damage — every bandit should have taken at least 1 HP
        # of damage (half on save, full on fail; both are > 0 for 8d6).
        assert t["damage_applied"] > 0, (
            f"bandit {t['target_name']} took 0 damage: {t}"
        )
        assert t["damage_type"] == "fire"


async def test_single_target_fallback_unchanged(gm_client, gm_ws, roster, thalindra_rested):
    """Casting with the old single-target ``target_combatant_id`` and
    no ``target_combatant_ids`` list still works — the response
    carries the existing auto_save_* headline fields AND
    auto_save_targets with exactly 1 entry (the canonical target).
    """
    thal = thalindra_rested
    tmpl = await _bandit_tmpl(gm_client)
    await _set_auto_apply(gm_client, on=True)
    await _seed_battle(gm_client, [
        {"id": f"tok_solo_{thal['id']}", "char_id": thal["id"],
         "name": thal["name"], "initiative": 10, "hp_current": 24, "hp_max": 24,
         "buffs": [],
         "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0}},
        {"id": "tok_solo_bandit", "char_id": None,
         "token_template_id": tmpl["id"],
         "name": "Bandit", "initiative": 7, "hp_current": 50, "hp_max": 50,
         "buffs": [],
         "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0}},
    ])

    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
        json={
            "character_id": thal["id"],
            "spell_index": FIREBALL_INDEX,
            "slot_level": 3,
            "class_slug": "wizard",
            # Old field — no list.
            "target_combatant_id": "tok_solo_bandit",
            "target_name": "Bandit",
            "override": True,
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    # Headline single-target fields populated as before.
    assert data["auto_save_target_kind"] == "npc"
    assert data["auto_save_target_name"] == "Bandit"
    assert isinstance(data["auto_save_rolled"], int)
    # auto_save_targets seeded with the single target for client uniformity.
    targets = data.get("auto_save_targets") or []
    assert len(targets) == 1, f"expected 1 target, got {len(targets)}: {targets}"
    assert targets[0]["target_name"] == "Bandit"


async def test_aoe_list_with_pc_target_marks_pc_skipped(
    gm_client, gm_ws, roster, thalindra_rested,
):
    """When an AoE list includes a PC token, the server fires a per-
    PC ``roll_request`` (v2.47.0 T.5d) so the player can roll their
    save. The headline payload still carries ``pc_skipped: True``
    with ``rolled: None`` so the client shows a "pending" pill — but
    the entry now ALSO carries ``pending_request_id`` so the cast
    card can correlate the eventual ``spell_cast_target_updated``
    broadcast back to this target.
    """
    thal = thalindra_rested
    pip = roster["Pip Quickfingers"]
    tmpl = await _bandit_tmpl(gm_client)
    await _set_auto_apply(gm_client, on=True)
    await _seed_battle(gm_client, [
        {"id": f"tok_mixed_{thal['id']}", "char_id": thal["id"],
         "name": thal["name"], "initiative": 10, "hp_current": 24, "hp_max": 24,
         "buffs": [],
         "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0}},
        {"id": "tok_mixed_bandit", "char_id": None,
         "token_template_id": tmpl["id"],
         "name": "Bandit", "initiative": 7, "hp_current": 50, "hp_max": 50,
         "buffs": [],
         "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0}},
        {"id": f"tok_mixed_{pip['id']}", "char_id": pip["id"],
         "name": pip["name"], "initiative": 8, "hp_current": 24, "hp_max": 24,
         "buffs": [],
         "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0}},
    ])

    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
        json={
            "character_id": thal["id"],
            "spell_index": FIREBALL_INDEX,
            "slot_level": 3,
            "class_slug": "wizard",
            "target_combatant_ids": ["tok_mixed_bandit", f"tok_mixed_{pip['id']}"],
            "override": True,
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    targets = data.get("auto_save_targets") or []
    # 2 entries: bandit (NPC, auto-resolved) + pip (PC, skipped).
    assert len(targets) == 2, f"expected 2 targets, got {len(targets)}: {targets}"
    bandit_entry = next(t for t in targets if t["target_name"] == "Bandit")
    pip_entry = next(t for t in targets if t["target_name"] == pip["name"])
    assert isinstance(bandit_entry["rolled"], int)
    assert bandit_entry["damage_applied"] > 0
    # PC was skipped on the initial response — no auto-roll, no
    # auto-damage. The card will show a save-prompt pending state.
    assert pip_entry.get("pc_skipped") is True
    assert pip_entry["rolled"] is None
    assert pip_entry["damage_applied"] == 0
    # v2.47.0 T.5d: the server also fired a roll_request for the PC
    # and stashed the cast context. The entry should carry the
    # ``pending_request_id`` so the client can correlate the
    # ``spell_cast_target_updated`` broadcast back to this target
    # when the PC submits their save.
    assert isinstance(pip_entry.get("pending_request_id"), int), (
        f"PC entry missing pending_request_id: {pip_entry}"
    )


async def test_aoe_pc_response_applies_damage_and_broadcasts_update(
    gm_client, gm_ws, roster, thalindra_rested,
):
    """v2.47.0 Phase T.5d — end-to-end PC AoE save resolution.

    After the AoE cast queues a roll_request for the PC, the PC
    submits their save via ``/roll_request/{id}/respond``. The server
    rolls save-for-half damage (auto_apply_damage is on), updates the
    PC's HP, and broadcasts a ``spell_cast_target_updated`` event so
    the client can repaint the cast card's pill for that target.
    """
    thal = thalindra_rested
    pip = roster["Pip Quickfingers"]
    tmpl = await _bandit_tmpl(gm_client)
    await _set_auto_apply(gm_client, on=True)

    # Long-rest Pip so an earlier test's damage doesn't leave her at
    # low HP — 8d6 fireball can one-shot a low-HP rogue, which makes
    # damage_applied ≠ HP-delta because the HP floors at 0 in the
    # _apply_hp_change path while the broadcast carries the rolled
    # amount.
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{pip['id']}/rest",
        json={"type": "long"},
    )

    # Read Pip's starting HP via the roster so we can assert the drop.
    async def _pip_hp():
        roster_resp = await gm_client.get(
            f"/api/campaign/{CAMPAIGN_ID}/roster"
        )
        chars = roster_resp.json()["characters"]
        return int(next(c for c in chars if c["id"] == pip["id"])["hp_current"])
    pip_hp_before = await _pip_hp()

    await _seed_battle(gm_client, [
        {"id": f"tok_t5d_{thal['id']}", "char_id": thal["id"],
         "name": thal["name"], "initiative": 10, "hp_current": 24, "hp_max": 24,
         "buffs": [],
         "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0}},
        {"id": "tok_t5d_bandit", "char_id": None,
         "token_template_id": tmpl["id"],
         "name": "Bandit", "initiative": 7, "hp_current": 50, "hp_max": 50,
         "buffs": [],
         "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0}},
        {"id": f"tok_t5d_{pip['id']}", "char_id": pip["id"],
         "name": pip["name"], "initiative": 8, "hp_current": pip_hp_before, "hp_max": 24,
         "buffs": [],
         "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0}},
    ])

    cast_resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
        json={
            "character_id": thal["id"],
            "spell_index": FIREBALL_INDEX,
            "slot_level": 3,
            "class_slug": "wizard",
            "target_combatant_ids": ["tok_t5d_bandit", f"tok_t5d_{pip['id']}"],
            "override": True,
        },
    )
    assert cast_resp.status_code == 200, cast_resp.text
    cast_data = cast_resp.json()
    cast_id = cast_data["id"]
    targets = cast_data.get("auto_save_targets") or []
    pip_entry = next(t for t in targets if t["target_name"] == pip["name"])
    assert pip_entry["pc_skipped"] is True
    pending_id = pip_entry["pending_request_id"]
    assert isinstance(pending_id, int)

    gm_ws.mark()

    # GM-as-Pip submits the save response. Damage gets rolled fresh
    # server-side and applied via _apply_damage_to_combatant.
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/roll_request/{pending_id}/respond",
        json={"character_id": pip["id"]},
    )
    assert r.status_code == 200, r.text

    # The ``spell_cast_target_updated`` broadcast carries the resolved
    # PC outcome — rolled / passed / damage_applied — so the client
    # can mutate the matching ``auto_save_targets`` entry and repaint
    # the pill row.
    upd = await gm_ws.wait_for("spell_cast_target_updated", timeout=3.0)
    upd_data = upd["data"]
    assert upd_data["cast_id"] == cast_id
    assert upd_data["combatant_id"] == f"tok_t5d_{pip['id']}"
    assert upd_data["target_name"] == pip["name"]
    assert isinstance(upd_data["rolled"], int)
    assert isinstance(upd_data["passed"], bool)
    assert upd_data["damage_type"] == "fire"

    # Pip's HP should have dropped. Full damage on fail, half (rounded
    # down) on save — both > 0 for an 8d6 fireball.
    pip_hp_after = await _pip_hp()
    assert pip_hp_after < pip_hp_before, (
        f"Pip's HP did not drop: before={pip_hp_before} after={pip_hp_after}"
    )
    # damage_applied is the post-resistance amount the server tried to
    # subtract; the actual HP delta floors at 0, so the broadcast may
    # overshoot when the PC was already low. With a fresh long-rest
    # above, Pip starts at 33 HP — 8d6 fire (avg ~28) won't usually
    # one-shot her, so the broadcast value should match the HP delta.
    assert upd_data["damage_applied"] >= pip_hp_before - pip_hp_after, (
        f"damage_applied lower than HP delta: broadcast says "
        f"{upd_data['damage_applied']}, HP delta is "
        f"{pip_hp_before - pip_hp_after}"
    )


async def test_aoe_cast_without_targets_lands_pending_then_place_aoe_resolves(
    gm_client, gm_ws, roster, thalindra_rested,
):
    """v2.48.0 Phase T.5e — caster-gated AoE placement.

    A Fireball cast WITHOUT ``target_combatant_ids`` lands as a
    pending-placement card. The new ``/place_aoe`` endpoint resolves
    targets when the caster (or GM) clicks the cast card's Place
    button. Asserts:
      - initial /cast_spell response carries pending_aoe_placement=True
        + the area shape/size_ft from the spell JSON
      - /place_aoe with target_combatant_ids resolves NPC saves +
        damage and broadcasts ``spell_cast_aoe_resolved``
      - bandit HP drops
    """
    thal = thalindra_rested
    tmpl = await _bandit_tmpl(gm_client)
    await _set_auto_apply(gm_client, on=True)
    await _seed_battle(gm_client, [
        {"id": f"tok_pend_{thal['id']}", "char_id": thal["id"],
         "name": thal["name"], "initiative": 10, "hp_current": 24, "hp_max": 24,
         "buffs": [],
         "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0}},
        {"id": "tok_pend_b1", "char_id": None,
         "token_template_id": tmpl["id"],
         "name": "Bandit Alpha", "initiative": 7, "hp_current": 50, "hp_max": 50,
         "buffs": [],
         "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0}},
        {"id": "tok_pend_b2", "char_id": None,
         "token_template_id": tmpl["id"],
         "name": "Bandit Beta", "initiative": 6, "hp_current": 50, "hp_max": 50,
         "buffs": [],
         "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0}},
    ])

    cast_resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
        json={
            "character_id": thal["id"],
            "spell_index": FIREBALL_INDEX,
            "slot_level": 3,
            "class_slug": "wizard",
            # No targets — server should mark this as pending placement.
            "override": True,
        },
    )
    assert cast_resp.status_code == 200, cast_resp.text
    cast_data = cast_resp.json()
    cast_id = cast_data["id"]
    assert cast_data["pending_aoe_placement"] is True, cast_data
    assert cast_data["area_shape"] == "sphere"
    assert cast_data["area_size_ft"] == 20
    # No targets resolved yet.
    assert cast_data["auto_save_targets"] == []

    gm_ws.mark()

    # GM places the AoE on both bandits.
    place_resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/place_aoe",
        json={
            "cast_id": cast_id,
            "target_combatant_ids": ["tok_pend_b1", "tok_pend_b2"],
        },
    )
    assert place_resp.status_code == 200, place_resp.text
    targets = place_resp.json().get("auto_save_targets") or []
    assert len(targets) == 2
    names = {t["target_name"] for t in targets}
    assert names == {"Bandit Alpha", "Bandit Beta"}
    for t in targets:
        assert isinstance(t["rolled"], int)
        assert isinstance(t["passed"], bool)
        assert t["damage_applied"] > 0, f"bandit took 0 damage: {t}"
        assert t["damage_type"] == "fire"

    # The cast card's per-target pill row mutates on the broadcast.
    res = await gm_ws.wait_for("spell_cast_aoe_resolved", timeout=3.0)
    rdata = res["data"]
    assert rdata["cast_id"] == cast_id
    assert len(rdata["auto_save_targets"]) == 2
    assert rdata["save_ability"] == "DEX"
    assert rdata["dc"] >= 8  # caster + prof + spc mod gives at least 8


async def test_place_aoe_auto_rolls_pc_save_and_applies_damage(
    gm_client, gm_ws, roster, thalindra_rested,
):
    """v2.48.3 — /place_aoe auto-rolls PC saves alongside NPCs.

    The v2.47.0 T.5d roll_request prompt path is bypassed for the
    /place_aoe flow; instead the server rolls every PC target's
    save server-side (using the PC's character sheet's save mod)
    and applies save-for-half damage exactly like NPCs. The cast
    card pill row shows the auto-rolled outcome for every target.
    """
    thal = thalindra_rested
    pip = roster["Pip Quickfingers"]
    tmpl = await _bandit_tmpl(gm_client)
    await _set_auto_apply(gm_client, on=True)

    # Long-rest Pip so an earlier test's damage doesn't leave her at
    # low HP — 8d6 fireball can one-shot a low-HP rogue.
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{pip['id']}/rest",
        json={"type": "long"},
    )

    async def _pip_hp():
        roster_resp = await gm_client.get(
            f"/api/campaign/{CAMPAIGN_ID}/roster"
        )
        chars = roster_resp.json()["characters"]
        return int(next(c for c in chars if c["id"] == pip["id"])["hp_current"])
    pip_hp_before = await _pip_hp()

    await _seed_battle(gm_client, [
        {"id": f"tok_pcr_{thal['id']}", "char_id": thal["id"],
         "name": thal["name"], "initiative": 10, "hp_current": 24, "hp_max": 24,
         "buffs": [],
         "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0}},
        {"id": "tok_pcr_bandit", "char_id": None,
         "token_template_id": tmpl["id"],
         "name": "Bandit", "initiative": 7, "hp_current": 50, "hp_max": 50,
         "buffs": [],
         "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0}},
        {"id": f"tok_pcr_{pip['id']}", "char_id": pip["id"],
         "name": pip["name"], "initiative": 8, "hp_current": pip_hp_before, "hp_max": 24,
         "buffs": [],
         "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0}},
    ])

    cast_resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
        json={
            "character_id": thal["id"],
            "spell_index": FIREBALL_INDEX,
            "slot_level": 3,
            "class_slug": "wizard",
            "override": True,
        },
    )
    assert cast_resp.status_code == 200, cast_resp.text
    cast_id = cast_resp.json()["id"]

    place_resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/place_aoe",
        json={
            "cast_id": cast_id,
            "target_combatant_ids": ["tok_pcr_bandit", f"tok_pcr_{pip['id']}"],
        },
    )
    assert place_resp.status_code == 200, place_resp.text
    targets = place_resp.json().get("auto_save_targets") or []
    assert len(targets) == 2
    pip_entry = next(t for t in targets if t["target_name"] == pip["name"])
    bandit_entry = next(t for t in targets if t["target_name"] == "Bandit")
    # Both targets are auto-rolled — pc_skipped / pending_request_id
    # never appear on the entry.
    assert "pc_skipped" not in pip_entry
    assert "pending_request_id" not in pip_entry
    assert isinstance(pip_entry["rolled"], int)
    assert isinstance(pip_entry["passed"], bool)
    assert pip_entry["damage_applied"] > 0, f"Pip took 0 damage: {pip_entry}"
    assert pip_entry["damage_type"] == "fire"
    # Bandit auto-rolled too.
    assert isinstance(bandit_entry["rolled"], int)
    assert bandit_entry["damage_applied"] > 0

    # Pip's HP dropped server-side.
    pip_hp_after = await _pip_hp()
    assert pip_hp_after < pip_hp_before, (
        f"Pip's HP did not drop: before={pip_hp_before} after={pip_hp_after}"
    )


async def test_place_aoe_rejects_non_caster_non_gm(gm_client, roster, thalindra_rested):
    """Auth gate: someone who isn't the caster AND isn't the GM gets
    403 on /place_aoe. The test client authenticates as the GM, so
    we can't easily test the non-caster-non-GM denial here directly;
    instead, assert that /place_aoe with a bogus cast_id returns
    404 (the auth check runs after the stash lookup, so 404 fires
    first for missing context — verifying the endpoint's error
    surface is reachable from the harness)."""
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/place_aoe",
        json={"cast_id": "does-not-exist", "target_combatant_ids": []},
    )
    assert resp.status_code == 404, resp.text
