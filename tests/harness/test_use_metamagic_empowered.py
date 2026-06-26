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


# Zara's spell list (per app/demo_seed.py:1694-1711).
FIRE_BOLT_INDEX = 0       # 2d10 single-beam attack-roll cantrip
SCORCHING_RAY_INDEX = 10  # 3 beams of 2d6 attack-roll spell (L2 slot)
FIREBALL_INDEX = 11       # 8d6 DEX-save-for-half AoE (L3 slot)


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


# ---------- Multi-beam (v2.49.125 helper, v2.49.126 content) ----------

async def test_empowered_pool_reroll_scorching_ray(gm_client, zara_rested):
    """v2.49.126 — Scorching Ray's content JSON now carries
    ``damage_scaling: [{level:1, damage:2d6, extra_beams:2}]`` so a cast
    fires 3 beams of 2d6 (RAW PHB p.273). With Zara's CHA-mod +3 reroll
    budget and 3 beams' worth of dice (6 d6 in the pool when all hit),
    the budget should fully fire (3 rerolls) when ≥ 2 beams hit.

    Loops up to 20 casts until at least 2 beams hit AND the reroll
    budget fully fires (3 rerolls). Each beam at Zara's +6 spell-atk
    vs the AC 12 bandit hits ~75% — P(<2 hits across 3 beams) ≈ 16%
    per cast, so 20 retries is well over enough headroom for the
    strong-form invariant to fire.
    """
    zara = zara_rested
    await _set_auto_apply(gm_client, on=True)
    r = await gm_client.get(f"/api/campaign/{CAMPAIGN_ID}/templates")
    templates = r.json()
    bandit_tmpl = next(
        (t for t in templates if "bandit" in t["name"].lower()),
        templates[0],
    )
    emp = None
    data = None
    for _ in range(20):
        await _seed_zara_vs_bandit(
            gm_client, zara, bandit_tmpl["id"], bandit_tmpl["name"],
        )
        await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/character/{zara['id']}/rest",
            json={"type": "long"},
        )
        arm = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/use_metamagic_empowered_spell",
            json={"character_id": zara["id"]},
        )
        assert arm.status_code == 200, arm.text
        resp = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
            json={
                "character_id": zara["id"],
                "spell_index": SCORCHING_RAY_INDEX,
                "slot_level": 2,
                "class_slug": "sorcerer",
                "target_combatant_id": "tok_emp_bandit",
                "target_name": bandit_tmpl["name"],
                "override": True,
            },
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        # Sanity: every cast should fire 3 beams (per the JSON tier).
        assert len(data.get("auto_attack_beams", [])) == 3, (
            f"Expected 3 beams; got {len(data.get('auto_attack_beams', []))}"
        )
        emp = data.get("empowered_spell")
        if emp is None:
            # No beam hit (all 3 missed) — retry.
            continue
        # Sanity on the log shape.
        for entry in emp["rerolls"]:
            assert entry["sides"] == 6
            assert 1 <= entry["old"] <= 6
            assert 1 <= entry["new"] <= 6
        if emp["rerolled_count"] == 3:
            break
    assert emp is not None, "20 Scorching Ray casts and no beam hit?"
    assert emp["rerolled_count"] == 3, (
        f"Expected 3 rerolls when ≥ 2 beams hit, got {emp['rerolled_count']}. "
        f"Pool reroll may be clipping to a single beam."
    )
    # When the pool spans beams the lowest dice can come from any beam.
    # Verify by counting beams that carry the '→' annotation in their
    # damage_breakdown — should be ≥ 1, and when 3 rerolls land across
    # multiple beams it's commonly ≥ 2.
    arrow_count = sum(
        1 for beam in data.get("auto_attack_beams", [])
        if "→" in (beam.get("damage_breakdown") or "")
    )
    assert arrow_count >= 1, (
        f"Expected ≥ 1 beam's breakdown to carry the old→new reroll "
        f"arrow; got beams={data.get('auto_attack_beams')}"
    )


async def test_scorching_ray_l3_slot_fires_four_beams(gm_client, zara_rested):
    """v2.49.127 — Scorching Ray RAW PHB p.273 upcast: +1 ray per slot
    level above 2. Engine field ``extra_beams_per_slot_above_base: 1``
    on the action makes a L3-slot cast fire 4 beams (3 base + 1 upcast).

    Doesn't arm Empowered — this test is just for the beam-count math.
    Casts at a bandit at L3 and asserts exactly 4 beams in the response.
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
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
        json={
            "character_id": zara["id"],
            "spell_index": SCORCHING_RAY_INDEX,
            "slot_level": 3,
            "class_slug": "sorcerer",
            "target_combatant_id": "tok_emp_bandit",
            "target_name": bandit_tmpl["name"],
            "override": True,
        },
    )
    assert resp.status_code == 200, resp.text
    beams = resp.json().get("auto_attack_beams", [])
    assert len(beams) == 4, (
        f"Expected 4 beams at L3 slot (3 base + 1 upcast); got {len(beams)}: {beams}"
    )


async def test_scorching_ray_l2_slot_fires_three_beams(gm_client, zara_rested):
    """v2.49.127 control — Scorching Ray at its base L2 slot fires 3
    beams (no upcast bonus). Regression guard for the slot-delta math
    in cast_spell (off-by-one would produce 2 or 4 beams instead of 3).
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
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
        json={
            "character_id": zara["id"],
            "spell_index": SCORCHING_RAY_INDEX,
            "slot_level": 2,
            "class_slug": "sorcerer",
            "target_combatant_id": "tok_emp_bandit",
            "target_name": bandit_tmpl["name"],
            "override": True,
        },
    )
    assert resp.status_code == 200, resp.text
    beams = resp.json().get("auto_attack_beams", [])
    assert len(beams) == 3, (
        f"Expected 3 beams at base L2 slot (no upcast bonus); got {len(beams)}: {beams}"
    )


async def test_empowered_single_beam_fire_bolt(gm_client, zara_rested):
    """Fire Bolt is a single-beam attack-roll cantrip (2d10 at L5).
    Verifies the attack-roll Empowered path works for the single-beam
    case too (same code path as Scorching Ray, just total_beams=1)."""
    zara = zara_rested
    await _set_auto_apply(gm_client, on=True)
    r = await gm_client.get(f"/api/campaign/{CAMPAIGN_ID}/templates")
    templates = r.json()
    bandit_tmpl = next(
        (t for t in templates if "bandit" in t["name"].lower()),
        templates[0],
    )
    emp = None
    for _ in range(20):
        await _seed_zara_vs_bandit(
            gm_client, zara, bandit_tmpl["id"], bandit_tmpl["name"],
        )
        await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/character/{zara['id']}/rest",
            json={"type": "long"},
        )
        arm = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/use_metamagic_empowered_spell",
            json={"character_id": zara["id"]},
        )
        assert arm.status_code == 200, arm.text
        resp = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
            json={
                "character_id": zara["id"],
                "spell_index": FIRE_BOLT_INDEX,
                "slot_level": 0,
                "class_slug": "sorcerer",
                "target_combatant_id": "tok_emp_bandit",
                "target_name": bandit_tmpl["name"],
                "override": True,
            },
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        emp = data.get("empowered_spell")
        if emp is not None:
            break
    assert emp is not None, "Fire Bolt never hit in 20 tries?"
    # CHA-mod +3 budget. Fire Bolt at Lv 5 is 2d10 normally → pool 2
    # → rerolled = min(3, 2) = 2. On a crit `_double_dice_for_crit`
    # doubles the dice to 4d10 → pool 4 → rerolled = min(3, 4) = 3.
    # Either is correct cap behavior; the 20-attempt loop can land on
    # either path (a nat-20 in 20 tries is ~64% likely). v2.49.233:
    # CI surfaced the crit-path failure that local runs had been
    # consistently lucky enough to skip.
    assert emp["rerolled_count"] in (2, 3), (
        f"Expected rerolled_count in {{2 (2d10 non-crit), 3 (4d10 crit)}}; "
        f"got {emp['rerolled_count']}"
    )
    # Sanity: the count matches the log length (no off-by-one in the
    # cap → log path).
    assert len(emp["rerolls"]) == emp["rerolled_count"]
    for entry in emp["rerolls"]:
        assert entry["sides"] == 10
        assert 1 <= entry["old"] <= 10
        assert 1 <= entry["new"] <= 10


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


# ---------- AoE multi-target (/place_aoe) integration (v2.661.0) ----------

async def test_empowered_reroll_aoe_multi_target_place_aoe(
    gm_client, zara_rested,
):
    """v2.661.0 — Sorcery Phase 1.5: Empowered Spell reroll now integrates
    with the AoE multi-target `/place_aoe` path (previously only the
    single-target save-for-half + multi-beam attack paths were wired).

    Arm Empowered, cast Fireball with NO target (→ pending AoE placement),
    then `/place_aoe` at two NPC bandits. RAW Empowered rerolls "the damage
    roll" once per cast, so the reroll fires on the FIRST target's damage
    roll (first-target-wins) and the `/place_aoe` response + the
    `spell_cast_aoe_resolved` broadcast carry the `empowered_spell` log.
    Asserts on the SHAPE (block present, reroll count == CHA-mod, d6 dice)
    since the RNG is non-deterministic.
    """
    zara = zara_rested
    await _set_auto_apply(gm_client, on=True)
    templates = (await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/templates")).json()
    bandit = next(
        (t for t in templates if "bandit" in t["name"].lower()), templates[0],
    )
    b1, b2 = "tok_emp_aoe_b1", "tok_emp_aoe_b2"
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": [
            {"id": f"tok_emp_aoe_z_{zara['id']}", "char_id": zara["id"],
             "name": zara["name"], "initiative": 10,
             "hp_current": 37, "hp_max": 37, "buffs": [],
             "economy": {"action": False, "bonus": False,
                         "reaction": False, "movement": 0}},
            {"id": b1, "char_id": None, "token_template_id": bandit["id"],
             "name": "Bandit Alpha", "initiative": 7,
             "hp_current": 100, "hp_max": 100, "buffs": [],
             "economy": {"action": False, "bonus": False,
                         "reaction": False, "movement": 0}},
            {"id": b2, "char_id": None, "token_template_id": bandit["id"],
             "name": "Bandit Beta", "initiative": 6,
             "hp_current": 100, "hp_max": 100, "buffs": [],
             "economy": {"action": False, "bonus": False,
                         "reaction": False, "movement": 0}},
        ], "turn_index": 0, "round": 1, "active": True},
    )

    # Arm Empowered (CHA 17 → +3 reroll budget).
    arm = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_metamagic_empowered_spell",
        json={"character_id": zara["id"]},
    )
    assert arm.status_code == 200, arm.text
    rerolls = arm.json()["rerolls_available"]
    assert rerolls == 3

    # Cast Fireball with NO target → pending AoE placement (the armed
    # Empowered buff survives — no damage rolls here).
    cast = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
        json={"character_id": zara["id"], "spell_index": FIREBALL_INDEX,
              "slot_level": 3, "class_slug": "sorcerer", "override": True},
    )
    assert cast.status_code == 200, cast.text
    cd = cast.json()
    assert cd.get("pending_aoe_placement") is True, cd
    assert "empowered_spell" not in cd  # not consumed by the no-damage cast
    cast_id = cd["id"]

    # Place the AoE on both bandits → the reroll fires on the first target.
    place = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/place_aoe",
        json={"cast_id": cast_id, "target_combatant_ids": [b1, b2],
              "center": {"x": 100, "y": 100}, "override_range": True},
    )
    assert place.status_code == 200, place.text
    pd = place.json()
    assert len(pd.get("auto_save_targets") or []) == 2, pd
    assert "empowered_spell" in pd, pd
    emp = pd["empowered_spell"]
    assert emp["rerolled_count"] == rerolls
    assert len(emp["rerolls"]) == rerolls
    for entry in emp["rerolls"]:
        assert entry["sides"] == 6
        assert 1 <= entry["old"] <= 6
        assert 1 <= entry["new"] <= 6

    # Buff consumed once: a second placement of a fresh Fireball (no
    # re-arm) carries no empowered_spell block.
    cast2 = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
        json={"character_id": zara["id"], "spell_index": FIREBALL_INDEX,
              "slot_level": 3, "class_slug": "sorcerer", "override": True},
    )
    assert cast2.status_code == 200, cast2.text
    place2 = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/place_aoe",
        json={"cast_id": cast2.json()["id"],
              "target_combatant_ids": [b1, b2],
              "center": {"x": 100, "y": 100}, "override_range": True},
    )
    assert place2.status_code == 200, place2.text
    assert "empowered_spell" not in place2.json()
