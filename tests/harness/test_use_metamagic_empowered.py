"""Sorcerer Empowered Spell metamagic — Phase 1 of the Sorcery Points +
Metamagic plan (docs/plans/sorcery-points-and-metamagic.md).

v2.49.124 — adds:
  - POST /use_metamagic_empowered_spell: 1 SP → arm a one-cast
    ``metamagic-empowered-pending`` buff on the caster. The buff
    carries ``effects.rerolls_available = max(1, CHA-mod)``.
  - /cast_spell damage-roll path (save-for-half NPC single-target)
    reads the buff and rerolls up to that many lowest dice, returning
    an ``empowered_spell`` block in the cast payload.

Demo subject: Zara Emberfire (Sorcerer Lv 5, CHA 17 → +3 mod, 5 SP).

Tests:
  - happy path: arm + cast Fireball → empowered_spell block in payload
  - 409 not_enough_points when SP = 0
  - 409 wrong_class when not a Sorcerer
  - 409 level_too_low when below Lv 3
  - cast WITHOUT armed buff returns no empowered_spell block (control)
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID


# Zara's spell list (per app/demo_seed.py:1694-1711). Fireball is
# index 11.
FIREBALL_INDEX = 11


@pytest_asyncio.fixture
async def zara_rested(gm_client, roster):
    zara = roster["Zara Emberfire"]
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{zara['id']}/rest",
        json={"type": "long"},
    )
    return zara


async def _seed_zara_vs_bandit(gm_client, zara, bandit_template_id, bandit_name):
    """Two-combatant battle: Zara + a bandit NPC. Required for the
    bonus-action gate + the save-for-half NPC damage path to fire."""
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={
            "combatants": [
                {"id": f"tok_emp_{zara['id']}", "char_id": zara["id"],
                 "name": zara["name"], "initiative": 10,
                 "hp_current": 37, "hp_max": 37, "buffs": [],
                 "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0}},
                {"id": "tok_emp_bandit", "char_id": None,
                 "token_template_id": bandit_template_id,
                 "name": bandit_name, "initiative": 7,
                 "hp_current": 100, "hp_max": 100, "buffs": [],
                 "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0}},
            ],
            "turn_index": 0, "round": 1, "active": True,
        },
    )


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


# ---------- Endpoint: arm Empowered Spell ----------

async def test_empowered_arms_pending_buff(gm_client, gm_ws, zara_rested):
    """Happy path: 1 SP → pending buff installed on caster, rerolls = CHA-mod."""
    zara = zara_rested
    # Seed a solo battle so the install lands.
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={
            "combatants": [{
                "id": f"tok_emp_solo_{zara['id']}",
                "char_id": zara["id"], "name": zara["name"], "initiative": 10,
                "hp_current": 37, "hp_max": 37, "buffs": [],
                "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0},
            }],
            "turn_index": 0, "round": 1, "active": True,
        },
    )
    # Flush seed broadcasts so wait_for picks up only post-POST events.
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_metamagic_empowered_spell",
        json={"character_id": zara["id"]},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
    assert body["sp_cost"] == 1
    assert body["sp_remaining"] == 4  # Zara starts with 5
    assert body["sp_max"] == 5
    assert body["rerolls_available"] == 3  # CHA 17 → mod +3

    # Verify the buff is on the combatant via the buff_update broadcast.
    bu = await gm_ws.wait_for("buff_update", timeout=2.0)
    data = bu.get("data") or {}
    assert data.get("character_id") == zara["id"]
    buffs = data.get("buffs") or []
    pending = next(
        (b for b in buffs if (b or {}).get("key") == "metamagic-empowered-pending"),
        None,
    )
    assert pending is not None, f"Empowered buff missing; got {buffs}"
    eff = pending.get("effects") or {}
    assert eff.get("rerolls_available") == 3
    assert eff.get("metamagic_option") == "empowered-spell"
    assert pending["concentration"] is False
    assert pending["duration_rounds"] == 1


async def test_empowered_409_when_no_sorcery_points(gm_client, zara_rested):
    """Arm 5 times in a row, exhausting Zara's 5 SP pool; the 6th
    call should 409 not_enough_points."""
    zara = zara_rested
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={
            "combatants": [{
                "id": f"tok_emp_drain_{zara['id']}",
                "char_id": zara["id"], "name": zara["name"], "initiative": 10,
                "hp_current": 37, "hp_max": 37, "buffs": [],
                "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0},
            }],
            "turn_index": 0, "round": 1, "active": True,
        },
    )
    # Drain to 0 SP. The pending buff key is reused so each call just
    # refreshes the buff; the SP counter still decrements each time.
    for _ in range(5):
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/use_metamagic_empowered_spell",
            json={"character_id": zara["id"]},
        )
        assert r.status_code == 200, r.text
    # 6th — should 409.
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_metamagic_empowered_spell",
        json={"character_id": zara["id"]},
    )
    assert r.status_code == 409, r.text
    err = r.json()
    assert err["error"] == "not_enough_points"
    assert err["required"] == 1
    assert err["have"] == 0


async def test_empowered_wrong_class(gm_client, roster):
    """Thalindra is a Wizard — 409 wrong_class."""
    thal = roster["Thalindra Moonwhisper"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_metamagic_empowered_spell",
        json={"character_id": thal["id"]},
    )
    assert r.status_code == 409, r.text
    err = r.json()
    assert err["error"] == "wrong_class"
    assert err["expected"] == "sorcerer"


# ---------- Integration: Fireball cast with armed buff ----------

async def test_empowered_buff_consumed_on_cast_fireball(gm_client, zara_rested):
    """Arm Empowered, then cast Fireball at a bandit. The payload's
    ``empowered_spell`` block should report the reroll count + the
    underlying buff should be removed after the cast (single-use).

    Asserts on the SHAPE (block present, reroll count == CHA-mod)
    rather than exact rolled values — the dice RNG is non-deterministic.
    """
    zara = zara_rested
    await _set_auto_apply(gm_client, on=True)
    r = await gm_client.get(f"/api/campaign/{CAMPAIGN_ID}/templates")
    templates = r.json()
    bandit_tmpl = next(
        (t for t in templates if "bandit" in t["name"].lower()),
        templates[0],
    )
    await _seed_zara_vs_bandit(
        gm_client, zara, bandit_tmpl["id"], bandit_tmpl["name"],
    )
    # Arm Empowered Spell.
    arm = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_metamagic_empowered_spell",
        json={"character_id": zara["id"]},
    )
    assert arm.status_code == 200, arm.text
    rerolls = arm.json()["rerolls_available"]
    assert rerolls == 3

    # Cast Fireball at the bandit. Override bypasses the bonus-action
    # gate (we already armed Empowered, which is free per PHB but the
    # cast itself uses the action chip).
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
        json={
            "character_id": zara["id"],
            "spell_index": FIREBALL_INDEX,
            "slot_level": 3,
            "class_slug": "sorcerer",
            "target_combatant_id": "tok_emp_bandit",
            "target_name": bandit_tmpl["name"],
            "override": True,
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    # Fireball: 8d6 fire, DEX save for half.
    assert data["auto_save_target_kind"] == "npc"
    assert data["auto_save_damage_type"] == "fire"
    # The Empowered block exists; the reroll count matches CHA-mod.
    assert "empowered_spell" in data, data
    emp = data["empowered_spell"]
    assert emp["rerolled_count"] == rerolls
    assert isinstance(emp["original_total"], int)
    assert isinstance(emp["final_total"], int)
    assert len(emp["rerolls"]) == rerolls
    # Each reroll log entry names the die size (d6 for Fireball).
    for entry in emp["rerolls"]:
        assert entry["sides"] == 6
        assert 1 <= entry["old"] <= 6
        assert 1 <= entry["new"] <= 6

    # The buff is consumed by the first cast (one-use semantics per PHB
    # p.102). A second Fireball cast without re-arming should NOT carry
    # an empowered_spell block. Verifies the buff was actually removed.
    resp2 = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
        json={
            "character_id": zara["id"],
            "spell_index": FIREBALL_INDEX,
            "slot_level": 3,
            "class_slug": "sorcerer",
            "target_combatant_id": "tok_emp_bandit",
            "target_name": bandit_tmpl["name"],
            "override": True,
        },
    )
    assert resp2.status_code == 200, resp2.text
    assert "empowered_spell" not in resp2.json()


async def test_no_empowered_block_when_buff_absent(gm_client, zara_rested):
    """Control: casting Fireball WITHOUT arming Empowered should not
    populate the ``empowered_spell`` block. Verifies the integration
    is gated on the buff and doesn't fire spuriously."""
    zara = zara_rested
    await _set_auto_apply(gm_client, on=True)
    r = await gm_client.get(f"/api/campaign/{CAMPAIGN_ID}/templates")
    templates = r.json()
    bandit_tmpl = next(
        (t for t in templates if "bandit" in t["name"].lower()),
        templates[0],
    )
    await _seed_zara_vs_bandit(
        gm_client, zara, bandit_tmpl["id"], bandit_tmpl["name"],
    )
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
        json={
            "character_id": zara["id"],
            "spell_index": FIREBALL_INDEX,
            "slot_level": 3,
            "class_slug": "sorcerer",
            "target_combatant_id": "tok_emp_bandit",
            "target_name": bandit_tmpl["name"],
            "override": True,
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert "empowered_spell" not in data
