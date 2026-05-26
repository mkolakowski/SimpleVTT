"""v2.65.0 — F8 condition undo / reversal framework.

Phase A — refactored `_attack_damage_log` to `dict[str, list[dict]]`.
Each `_apply_damage_to_combatant` / `_apply_heal_to_combatant` call
APPENDS a snapshot entry; `/undo_attack_damage` walks the list in
REVERSE order and applies each undo. Pre-v2.65.0 multi-target writes
silently overwrote each other so undo only reverted the LAST target.

Phase B — condition-install snapshots. At the save-fail buff-install
site (`/roll_request/{id}/respond`), the target's pre-install buff
list is snapshotted into the undo log. /undo restores the buff list.

Tests:
  - Multi-target heal undo: Tavik casts Mass Healing Word at 2
    targets (Krieger + Pip); both heal; /undo reverts BOTH (not
    just the last).
  - Condition install undo: Lyra casts Suggestion at Krieger; save
    fails; Charmed installs; /undo restores Krieger's buff list
    (no Charmed entry).
  - Backward-compat: single-target damage undo still works after
    the log shape change. Tavik attacks NPC, undo reverts the
    damage. Validates that the legacy `hp_after` + `was_heal`
    response fields still populate.
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID


TAVIK_MASS_HEALING_WORD_INDEX = 12
LYRA_SUGGESTION_INDEX = 9


@pytest_asyncio.fixture
async def tavik_rested(gm_client, roster):
    tavik = roster["Brother Tavik Stonebrow"]
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{tavik['id']}/rest",
        json={"type": "long"},
    )
    return tavik


@pytest_asyncio.fixture
async def lyra_rested(gm_client, roster):
    lyra = roster["Lyra Sunstrider"]
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{lyra['id']}/rest",
        json={"type": "long"},
    )
    return lyra


@pytest_asyncio.fixture
async def krieger_wounded(gm_client, roster):
    krieger = roster["Krieger Stonefist"]
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{krieger['id']}/rest",
        json={"type": "long"},
    )
    await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{krieger['id']}/sheet-fields",
        json={"hp": {"current": 30}},
    )
    return krieger


@pytest_asyncio.fixture
async def pip_wounded(gm_client, roster):
    pip = roster["Pip Quickfingers"]
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{pip['id']}/rest",
        json={"type": "long"},
    )
    await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{pip['id']}/sheet-fields",
        json={"hp": {"current": 20}},
    )
    return pip


def _make_combatant(name, char_id, hp_current=30, hp_max=50):
    return {
        "id": f"tok_undo_{char_id}",
        "char_id": char_id,
        "name": name,
        "initiative": 10,
        "hp_current": hp_current, "hp_max": hp_max,
        "buffs": [],
        "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0},
    }


async def _seed_battle(gm_client, combatants):
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": combatants, "turn_index": 0, "round": 1, "active": True},
    )


# (no per-target HP-read helper needed — the undo response's
# `per_target` list is the canonical signal that multiple targets
# were undone; v2.65.0 ships this field exactly so callers don't
# need a per-character HP roundtrip.)


async def _get_buffs(gm_client, char_id: int) -> list:
    r = await gm_client.get(f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/buffs")
    return r.json().get("buffs", [])


async def test_multi_target_heal_undo_reverts_all(
    gm_client, tavik_rested, krieger_wounded, pip_wounded,
):
    """Tavik casts Mass Healing Word at Krieger + Pip (slot 3).
    Both heal. /undo_attack_damage reverts BOTH targets, not just
    the last one (pre-v2.65.0 bug).
    """
    tavik = tavik_rested
    krieger = krieger_wounded
    pip = pip_wounded

    krieger_hp_before = 30
    pip_hp_before = 20

    await _seed_battle(gm_client, [
        _make_combatant(tavik["name"], tavik["id"], hp_current=51, hp_max=51),
        _make_combatant(krieger["name"], krieger["id"],
                        hp_current=krieger_hp_before, hp_max=75),
        _make_combatant(pip["name"], pip["id"],
                        hp_current=pip_hp_before, hp_max=47),
    ])

    cast_resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
        json={
            "character_id": tavik["id"],
            "spell_index": TAVIK_MASS_HEALING_WORD_INDEX,
            "slot_level": 3,
            "class_slug": "cleric",
            "target_combatant_ids": [
                f"tok_undo_{krieger['id']}",
                f"tok_undo_{pip['id']}",
            ],
            "target_character_id": krieger["id"],
            "target_name": krieger["name"],
            "override": True,
        },
    )
    assert cast_resp.status_code == 200, cast_resp.text
    cast_data = cast_resp.json()
    cast_id = cast_data["id"]
    # Primary target's heal applied (carried in the response).
    assert cast_data.get("auto_heal_applied", 0) > 0, (
        f"primary heal didn't apply; got {cast_data}"
    )

    # Undo reverts BOTH.
    undo_resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/undo_attack_damage",
        json={"attack_id": cast_id},
    )
    assert undo_resp.status_code == 200, undo_resp.text
    undo = undo_resp.json()
    assert undo["ok"] is True
    # Per-target list should mention BOTH Krieger AND Pip — the
    # pre-v2.65.0 single-entry log would have only one of them.
    per = undo.get("per_target") or []
    target_ids = {e.get("target_char_id") for e in per}
    assert krieger["id"] in target_ids, (
        f"undo per_target should mention Krieger; got {per}"
    )
    assert pip["id"] in target_ids, (
        f"undo per_target should mention Pip; got {per}"
    )
    # Both per-target entries should have kind="heal".
    heal_kinds = [e.get("kind") for e in per if e.get("kind")]
    assert heal_kinds.count("heal") >= 2, (
        f"expected ≥ 2 heal-kind entries in per_target; got {per}"
    )


async def test_condition_install_undo_restores_buffs(
    gm_client, lyra_rested, krieger_wounded,
):
    """Lyra casts Suggestion at Krieger; loop until save fails;
    Charmed installs; /undo_attack_damage restores Krieger's buff
    list (no Charmed entry remains).
    """
    lyra = lyra_rested
    krieger = krieger_wounded

    # Make sure Krieger has no leftover buffs.
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/end_buff",
        json={"character_id": krieger["id"], "key": "charmed"},
    )

    # Drive saves until one fails — re-seeding battle each iteration
    # so the auto-broadcast machinery + save context state reset.
    target_tok = f"tok_undo_{krieger['id']}"
    last_pending_id = None
    for _ in range(20):
        await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/character/{lyra['id']}/rest",
            json={"type": "long"},
        )
        await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/end_buff",
            json={"character_id": krieger["id"], "key": "charmed"},
        )
        await _seed_battle(gm_client, [
            _make_combatant(lyra["name"], lyra["id"], hp_current=40, hp_max=40),
            _make_combatant(krieger["name"], krieger["id"],
                            hp_current=40, hp_max=75),
        ])
        cast_resp = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
            json={
                "character_id": lyra["id"],
                "spell_index": LYRA_SUGGESTION_INDEX,
                "slot_level": 2,
                "class_slug": "bard",
                "target_combatant_id": target_tok,
                "target_character_id": krieger["id"],
                "target_name": krieger["name"],
                "override": True,
            },
        )
        assert cast_resp.status_code == 200, cast_resp.text
        cast_data = cast_resp.json()
        pending_id = cast_data.get("auto_save_prompt_id")
        assert isinstance(pending_id, int)
        respond = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/roll_request/{pending_id}/respond",
            json={"character_id": krieger["id"]},
        )
        assert respond.status_code == 200, respond.text
        if respond.json().get("auto_buff_installed"):
            last_pending_id = pending_id
            break
    assert last_pending_id is not None, (
        "could not land a Suggestion save-fail on Krieger in 20 tries"
    )

    # Confirm Charmed buff IS on Krieger now.
    buffs_after_fail = await _get_buffs(gm_client, krieger["id"])
    assert any((b or {}).get("key") == "charmed" for b in buffs_after_fail), (
        f"expected Charmed on Krieger after save-fail; got {buffs_after_fail}"
    )

    # Undo using the roll_request id as the cast_id.
    undo_resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/undo_attack_damage",
        json={"attack_id": str(last_pending_id)},
    )
    assert undo_resp.status_code == 200, undo_resp.text
    undo = undo_resp.json()
    assert undo["ok"] is True

    # Charmed buff should be GONE.
    buffs_after_undo = await _get_buffs(gm_client, krieger["id"])
    assert not any((b or {}).get("key") == "charmed" for b in buffs_after_undo), (
        f"Charmed should be undone; got {buffs_after_undo}"
    )


async def test_single_target_damage_undo_backward_compat(
    gm_client, roster,
):
    """Pre-v2.65.0 the undo response carried `hp_after` + `was_heal`
    fields. v2.65.0's list-walker preserves them: `hp_after` is the
    final undone entry's hp_after; `was_heal` reflects the last
    is_heal entry. Single-target backward-compat: Tavik attacks
    an NPC, undo reverts.
    """
    tavik = roster["Brother Tavik Stonebrow"]
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{tavik['id']}/rest",
        json={"type": "long"},
    )

    # Set up auto_apply_damage briefly.
    form = {
        "name": "Demo Campaign", "description": "demo", "game_system": "dnd5e",
        "gm_tab_color": "", "font_override": "", "default_encounter_id": "",
        "hp_threshold_1": "", "hp_threshold_2": "", "hp_threshold_3": "",
        "hp_threshold_4": "", "auto_play_playlist_id": "",
        "auto_play_mode": "order", "auto_play_initial_volume": "0.7",
        "auto_apply_damage": "on",
    }
    await gm_client.post(
        f"/campaign/{CAMPAIGN_ID}/settings", data=form, follow_redirects=False,
    )

    try:
        target = {
            "id": "tok_undo_npc",
            "name": "Test NPC",
            "initiative": 5,
            "hp_current": 50, "hp_max": 50,
            "buffs": [],
            "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0},
        }
        for _ in range(8):
            await _seed_battle(gm_client, [
                _make_combatant(tavik["name"], tavik["id"], hp_current=51, hp_max=51),
                target,
            ])
            r = await gm_client.post(
                f"/api/campaign/{CAMPAIGN_ID}/attack",
                json={
                    "character_id": tavik["id"],
                    "attack_index": 0,  # Warhammer
                    "target_combatant_id": "tok_undo_npc",
                    "override": True,
                },
            )
            assert r.status_code == 200
            data = r.json()
            if not data.get("hit"):
                continue
            assert data.get("damage_applied", 0) > 0
            attack_id = data["id"]

            undo = await gm_client.post(
                f"/api/campaign/{CAMPAIGN_ID}/undo_attack_damage",
                json={"attack_id": attack_id},
            )
            assert undo.status_code == 200, undo.text
            ud = undo.json()
            assert ud["ok"] is True
            # Legacy fields preserved.
            assert "hp_after" in ud
            assert ud["was_heal"] is False
            assert ud["reverted"] > 0
            return
        raise AssertionError("Tavik did not land a hit on the NPC in 8 tries")
    finally:
        form_off = {k: v for k, v in form.items() if k != "auto_apply_damage"}
        await gm_client.post(
            f"/campaign/{CAMPAIGN_ID}/settings", data=form_off,
            follow_redirects=False,
        )
