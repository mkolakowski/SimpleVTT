"""Phase T.2 — /attack hit determination + auto-apply damage + undo.

v2.24.0: when ``Campaign.auto_apply_damage`` is True AND a target is
set AND the attack hits the target's AC, server applies HP damage to
the target via ``_apply_hp_change`` (PCs) or by mutating the hub
combatant (NPCs). Crit doubles damage dice. Resistance from Phase B
halves correctly. Undo endpoint reverts the last damage application.

Tests:
  - hit determined from target_ac (no auto-apply when toggle off)
  - miss => no damage applied
  - auto-apply on hit when toggle on
  - crit doubles damage dice
  - resistance halves damage on raging target
  - undo reverts the HP change
  - undo on a miss is a no-op
  - undo with unknown attack_id => 404
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID


@pytest_asyncio.fixture
async def krieger_full(gm_client, roster):
    krieger = roster["Krieger Stonefist"]
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{krieger['id']}/rest",
        json={"type": "long"},
    )
    return krieger


@pytest_asyncio.fixture
async def auto_apply_on(gm_client):
    """Ensure auto_apply_damage is on for the duration of the test.

    v2.80.2 — restored to the demo's seeded default (ON, per
    `app/demo_seed.py:auto_apply_damage=True`) on teardown instead
    of removing the form key (which the server interprets as OFF).
    The previous teardown was matching the v2.79.0-fixed UD-test
    bug — flipping auto_apply_damage off after every test polluted
    state for subsequent tests in the same suite run. Same fix
    playbook.

    This uses the public settings endpoint rather than mutating the
    DB directly because the harness doesn't have a DB session —
    only HTTP + WS.
    """
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
        "auto_apply_damage": "on",
    }
    await gm_client.post(f"/campaign/{CAMPAIGN_ID}/settings", data=form,
                        follow_redirects=False)
    yield
    # Restore demo default (ON). Keep the form key so the server
    # interprets it as ON.
    await gm_client.post(f"/campaign/{CAMPAIGN_ID}/settings", data=form,
                        follow_redirects=False)


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
    """Explicit toggle helper so tests don't depend on the previous
    suite leaving the setting in a known state."""
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
    await gm_client.post(f"/campaign/{CAMPAIGN_ID}/settings", data=form,
                        follow_redirects=False)


async def test_attack_hit_determination_without_auto_apply(gm_client, krieger_full, roster):
    """auto_apply_damage off: hit/target_ac in response but no HP
    changes."""
    krieger = krieger_full
    pip = roster["Pip Quickfingers"]
    pip_cid = f"tok_{pip['id']}"
    # Defensive: ensure the toggle is OFF for this test even if the
    # previous test in another file left it on.
    await _set_auto_apply(gm_client, False)
    await _seed_battle(gm_client, [
        _mkc(f"tok_{krieger['id']}", krieger['id'], name="Krieger"),
        _mkc(pip_cid, pip['id'], hp_cur=30, hp_max=30, name=pip['name']),
    ])
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/attack",
        json={
            "character_id": krieger["id"],
            "attack_index": 0,
            "target_combatant_id": pip_cid,
            "override": True,
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["target_ac"] is not None  # Pip's AC was looked up
    assert data["hit"] in (True, False)
    # Auto-apply is OFF (default) — damage_applied is 0 regardless of hit.
    assert data["damage_applied"] == 0
    assert data["auto_applied"] is False


async def test_attack_auto_apply_on_hit(gm_client, krieger_full, roster, auto_apply_on):
    """auto_apply_damage on: hits trigger HP change to the PC via
    _apply_hp_change.

    v2.51.6: assertion switched from `target_hp_after < 30` (absolute,
    hardcoded) to `target_hp_after < pip_hp_before` (relative). The
    absolute form was wrong for two reasons:
      1. Pip's max HP is sheet-defined (33 pre-v2.51.6, 47 post-bump);
         the hardcoded 30 was never her actual max.
      2. Uncanny Dodge (v2.49.243) halves Krieger's Greataxe min damage
         (5 → 2), so a fresh-rested Pip lands at hp_max - 2 which is
         still > 30. The flake only surfaced when Pip was at full HP
         going into this test — visible after v2.51.6 since her max
         climbs further from the hardcoded threshold.
    Relative comparison stays robust regardless of Pip's starting HP
    or whether Uncanny Dodge fires.
    """
    krieger = krieger_full
    pip = roster["Pip Quickfingers"]
    pip_cid = f"tok_{pip['id']}"
    # Read Pip's actual sheet HP via the roster so the assertion is
    # against the real pre-attack value, not a battle-state placeholder.
    pip_hp_before = int(pip.get("hp_current") or 0)
    await _seed_battle(gm_client, [
        _mkc(f"tok_{krieger['id']}", krieger['id'], name="Krieger"),
        _mkc(pip_cid, pip['id'],
             hp_cur=pip_hp_before, hp_max=pip_hp_before, name=pip['name']),
    ])
    # Krieger's Greataxe is +7 to hit. Pip's AC is 14. We need a d20
    # roll of 7+ to hit. Run up to 8 attempts and assert at least one
    # hit applied damage > 0.
    hit_seen = False
    for _ in range(8):
        resp = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/attack",
            json={
                "character_id": krieger["id"],
                "attack_index": 0,
                "target_combatant_id": pip_cid,
                "override": True,
            },
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        if data["hit"] and data["damage_applied"] > 0:
            hit_seen = True
            assert data["target_hp_after"] < pip_hp_before, (
                f"hp_after={data['target_hp_after']} should be less than "
                f"hp_before={pip_hp_before}; damage_applied={data['damage_applied']}"
            )
            assert data["auto_applied"] is True
            break
    assert hit_seen, "expected at least one hit + auto-apply in 8 swings"


async def test_attack_crit_doubles_damage(gm_client, krieger_full, roster, auto_apply_on):
    """Crits double damage dice. Greataxe (1d12+4) on a crit rolls
    2d12+4. We can't force a crit deterministically via /attack, so we
    fall back to inspecting damage_total ranges — but the more reliable
    assertion is: when is_crit is True in the response, damage is at
    least 2 × min_dice + flat = 2 + 4 = 6, and damage_breakdown
    contains "2d12".
    """
    krieger = krieger_full
    pip = roster["Pip Quickfingers"]
    pip_cid = f"tok_{pip['id']}"
    await _seed_battle(gm_client, [
        _mkc(f"tok_{krieger['id']}", krieger['id'], name="Krieger"),
        _mkc(pip_cid, pip['id'], hp_cur=30, hp_max=30, name=pip['name']),
    ])
    # Run up to 100 attacks to catch a nat-20. Statistically 1 in 20.
    crit_seen = False
    for _ in range(100):
        resp = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/attack",
            json={
                "character_id": krieger["id"],
                "attack_index": 0,
                "target_combatant_id": pip_cid,
                "override": True,
            },
        )
        data = resp.json()
        if data.get("is_crit"):
            crit_seen = True
            # Damage breakdown should reference 2d12 (Greataxe doubled).
            assert "2d12" in (data["damage_breakdown"] or ""), data["damage_breakdown"]
            # Minimum doubled damage = 2 + 4 = 6.
            assert data["damage_total"] >= 6
            break
    assert crit_seen, "no crit in 100 attempts — RNG broke?"


async def test_undo_attack_damage(gm_client, krieger_full, roster, auto_apply_on):
    """Auto-apply damage, then undo. Pip's HP recovers."""
    krieger = krieger_full
    pip = roster["Pip Quickfingers"]
    pip_cid = f"tok_{pip['id']}"
    await _seed_battle(gm_client, [
        _mkc(f"tok_{krieger['id']}", krieger['id'], name="Krieger"),
        _mkc(pip_cid, pip['id'], hp_cur=30, hp_max=30, name=pip['name']),
    ])
    # Run swings until one hits and applies damage.
    applied_attack_id = None
    applied_amount = 0
    hp_before_undo = None
    for _ in range(8):
        resp = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/attack",
            json={
                "character_id": krieger["id"],
                "attack_index": 0,
                "target_combatant_id": pip_cid,
                "override": True,
            },
        )
        data = resp.json()
        if data.get("damage_applied", 0) > 0:
            applied_attack_id = data["id"]
            applied_amount = data["damage_applied"]
            hp_before_undo = data["target_hp_after"]
            break
    assert applied_attack_id, "no hit applied — RNG broke?"

    # Undo.
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/undo_attack_damage",
        json={"attack_id": applied_attack_id},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["reverted"] == applied_amount
    assert data["hp_after"] == hp_before_undo + applied_amount


async def test_undo_unknown_attack_id(gm_client):
    """Undo with a never-seen attack_id returns 404."""
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/undo_attack_damage",
        json={"attack_id": "nonexistent_id_xyz"},
    )
    assert r.status_code == 404


async def test_undo_missing_attack_id_field(gm_client):
    """Missing attack_id body field returns 400."""
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/undo_attack_damage",
        json={},
    )
    assert r.status_code == 400
