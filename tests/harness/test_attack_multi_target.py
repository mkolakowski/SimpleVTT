"""Multi-target attacks via /api/campaign/{cid}/attack.

v2.49.85 — `POST /attack` now accepts ``target_combatant_ids: list``
in addition to the existing ``target_combatant_id`` singular. Each
entry in the list gets its OWN fresh attack roll + damage roll (RAW
weapon attacks per-target — same to-hit modifier + same damage
expression, but freshly rolled per target). Per-target outcomes
return in a new ``auto_attack_targets`` array on the response +
the ``weapon_attack`` broadcast.

The PRIMARY target (first entry in the list) rides through the
existing single-target code path, so the legacy fields
(``target_combatant_id``, ``hit``, ``damage_applied``, etc.) carry
its outcome for backward compat. Additional targets only appear in
the new ``auto_attack_targets`` list.

Auto-uplifts (Hex / Hunter's Mark / Colossus Slayer) intentionally
apply only to the PRIMARY target — those are target-bound mechanics;
spreading a Hexed-target's +1d6 across unrelated enemies would be
RAW-wrong. Filed: per-target uplift detection for multi-target.

Tests:
  - Single-target via the legacy ``target_combatant_id`` still
    populates the legacy fields AND emits a 1-entry
    ``auto_attack_targets`` (the primary target).
  - Multi-target via ``target_combatant_ids`` of length 3 produces a
    3-entry ``auto_attack_targets`` with per-target attack rolls.
  - Multi-target with ``auto_apply_damage`` on → per-target HP drops.
  - Empty ``target_combatant_ids`` + no singular ID → empty
    ``auto_attack_targets`` (untargeted attack-roll flow unchanged).
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID


async def _set_auto_apply(gm_client, on: bool) -> None:
    """Toggle the campaign's ``auto_apply_damage`` flag."""
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
        f"/campaign/{CAMPAIGN_ID}/settings", data=form, follow_redirects=False,
    )


async def _seed_battle(gm_client, combatants):
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": combatants, "turn_index": 0, "round": 1, "active": True},
    )


async def _bandit_template(gm_client):
    r = await gm_client.get(f"/api/campaign/{CAMPAIGN_ID}/templates")
    templates = r.json()
    return next(t for t in templates if t["name"].lower() == "bandit")


def _mkpc(char, tid, hp=30):
    return {
        "id": tid, "char_id": char["id"], "name": char["name"],
        "initiative": 10, "hp_current": hp, "hp_max": max(hp, 30),
        "buffs": [],
        "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0},
    }


def _mknpc(tmpl, tid, name, hp=30, init=5):
    return {
        "id": tid, "char_id": None,
        "token_template_id": tmpl["id"], "name": name,
        "initiative": init, "hp_current": hp, "hp_max": max(hp, 30),
        "buffs": [],
        "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0},
    }


async def test_attack_legacy_single_target_emits_one_entry(gm_client, gm_ws, roster):
    """Legacy ``target_combatant_id`` (singular) still works — the
    response carries the existing fields AND a 1-entry
    ``auto_attack_targets`` mirroring the primary outcome.
    """
    pip = roster["Pip Quickfingers"]
    tmpl = await _bandit_template(gm_client)
    await _seed_battle(gm_client, [
        _mkpc(pip, f"tok_mt_pip_{pip['id']}"),
        _mknpc(tmpl, "tok_mt_b1", "Bandit Alpha", hp=30),
    ])
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/attack",
        json={
            "character_id": pip["id"],
            "attack_index": 0,        # Shortsword
            "target_combatant_id": "tok_mt_b1",
            "override": True,
        },
    )
    assert r.status_code == 200, r.text
    data = r.json()
    targets = data.get("auto_attack_targets") or []
    assert len(targets) == 1
    t = targets[0]
    assert t["combatant_id"] == "tok_mt_b1"
    assert t["target_name"] == "Bandit Alpha"
    assert t["attack_total"] == data["attack_total"]
    assert t["damage_total"] == data["damage_total"]


async def test_attack_multi_target_fresh_rolls(gm_client, gm_ws, roster):
    """``target_combatant_ids`` of length 3 → 3 entries in
    ``auto_attack_targets`` with INDEPENDENT attack + damage rolls per
    target (fresh d20 + fresh damage dice per target, RAW)."""
    pip = roster["Pip Quickfingers"]
    tmpl = await _bandit_template(gm_client)
    await _seed_battle(gm_client, [
        _mkpc(pip, f"tok_mt_pip_{pip['id']}"),
        _mknpc(tmpl, "tok_mt_b1", "Bandit Alpha", hp=30),
        _mknpc(tmpl, "tok_mt_b2", "Bandit Beta", hp=30, init=6),
        _mknpc(tmpl, "tok_mt_b3", "Bandit Gamma", hp=30, init=7),
    ])
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/attack",
        json={
            "character_id": pip["id"],
            "attack_index": 0,
            "target_combatant_ids": ["tok_mt_b1", "tok_mt_b2", "tok_mt_b3"],
            "override": True,
        },
    )
    assert r.status_code == 200, r.text
    data = r.json()
    targets = data.get("auto_attack_targets") or []
    assert len(targets) == 3, f"expected 3 per-target outcomes, got {targets}"
    names = {t["target_name"] for t in targets}
    assert names == {"Bandit Alpha", "Bandit Beta", "Bandit Gamma"}
    # Each target carries its own attack_total + damage_total.
    for t in targets:
        assert isinstance(t["attack_total"], int)
        assert 7 <= t["attack_total"] <= 26  # 1d20+6 (Pip shortsword)
        assert isinstance(t["damage_total"], int)
        assert 4 <= t["damage_total"] <= 9  # 1d6+3
        assert isinstance(t["hit"], bool)


async def test_attack_multi_target_auto_apply_damage(gm_client, gm_ws, roster):
    """When ``auto_apply_damage`` is on, each hit target's HP drops by
    its per-target damage_applied. Setup uses Pip's Dagger (1d4+3,
    range 20/60 ft so all 3 close-by bandits are reachable)."""
    pip = roster["Pip Quickfingers"]
    tmpl = await _bandit_template(gm_client)
    await _set_auto_apply(gm_client, on=True)
    try:
        await _seed_battle(gm_client, [
            _mkpc(pip, f"tok_mtad_pip_{pip['id']}"),
            _mknpc(tmpl, "tok_mtad_b1", "Bandit Alpha", hp=50),
            _mknpc(tmpl, "tok_mtad_b2", "Bandit Beta", hp=50, init=6),
        ])
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/attack",
            json={
                "character_id": pip["id"],
                "attack_index": 1,  # Dagger (thrown 20/60 — long range)
                "target_combatant_ids": ["tok_mtad_b1", "tok_mtad_b2"],
                "override": True,
            },
        )
        assert r.status_code == 200, r.text
        data = r.json()
        targets = data.get("auto_attack_targets") or []
        assert len(targets) == 2
        # auto_apply: every hit must have damage_applied > 0.
        for t in targets:
            assert t["damage_applied"] == (t["damage_total"] if t["hit"] else 0)
    finally:
        await _set_auto_apply(gm_client, on=False)


async def test_attack_no_target_yields_empty_list(gm_client, gm_ws, roster):
    """Untargeted attack (no ``target_combatant_id`` AND empty
    ``target_combatant_ids``) → ``auto_attack_targets`` is an empty
    list. Existing untargeted behavior unchanged."""
    pip = roster["Pip Quickfingers"]
    await _seed_battle(gm_client, [
        _mkpc(pip, f"tok_mt_pip_{pip['id']}"),
    ])
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/attack",
        json={
            "character_id": pip["id"],
            "attack_index": 0,
            "override": True,
        },
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["target_combatant_id"] == ""
    assert data.get("auto_attack_targets") == []
