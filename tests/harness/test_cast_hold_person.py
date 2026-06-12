"""v2.99.107 — /cast_hold_person endpoint tests.

Lv 2 concentration spell. Available to Cleric / Bard / Sorcerer /
Warlock / Wizard. v1 ships the speed→0 (Paralyzed) effect via
the new `_make_paralyzed_buff` factory; other Paralyzed mechanics
(auto-fail STR/DEX saves, attacks have advantage, melee auto-crits)
surface as raw_effects for GM narration.

RAW upcasting: 1 target at L2, +1 per upcast level above. v1
enforces the cap via 409 too_many_targets.

Tests:
  - happy path (Tavik casts on Krieger at L2 → 1 target, speed→0)
  - upcast L4 with 3 targets → all 3 affected
  - L2 with 2 targets → 409 too_many_targets
  - L1 slot → 400 (Hold Person is L2)
  - wrong class → 409 (Krieger Barbarian doesn't get Hold Person)
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID


def _mkc(cid, char_id=None, name="X", speed_walk=30):
    return {
        "id": cid,
        "char_id": char_id,
        "name": name,
        "initiative": 10,
        "hp_current": 50, "hp_max": 50,
        "speed_walk": speed_walk,
        "buffs": [],
        "economy": {"action": False, "bonus": False, "reaction": False,
                    "movement": 0, "dash_bonus_ft": 0},
    }


async def _seed_battle(gm_client, combatants):
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": combatants, "turn_index": 0,
              "round": 1, "active": True},
    )


@pytest_asyncio.fixture
async def tavik_and_krieger(gm_client, roster):
    tavik = roster["Brother Tavik Stonebrow"]
    krieger = roster["Krieger Stonefist"]
    tv_tok = f"tok_hp_tv_{tavik['id']}"
    kr_tok = f"tok_hp_kr_{krieger['id']}"
    await _seed_battle(gm_client, [
        _mkc(tv_tok, tavik["id"], name=tavik["name"], speed_walk=30),
        _mkc(kr_tok, krieger["id"], name=krieger["name"], speed_walk=40),
    ])
    yield tavik, krieger, kr_tok


async def test_cast_hold_person_installs_paralyzed_buff(
    gm_client, tavik_and_krieger,
):
    """Tavik (Cleric Lv 6) casts Hold Person at L2 on Krieger.
    Buff installs with speed_reduction_ft = 40 (Krieger's full
    base speed → effective speed 0).
    """
    tavik, krieger, kr_tok = tavik_and_krieger
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_hold_person",
        json={
            "character_id": tavik["id"],
            "class_slug": "cleric",
            "slot_level": 2,
            "target_combatant_ids": [kr_tok],
            "override": True,
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["ok"] is True
    assert data["duration_rounds"] == 10
    assert data["concentration"] is True
    assert data["max_targets"] == 1  # L2 → 1 target
    affected = data.get("affected") or []
    assert len(affected) == 1, affected
    entry = affected[0]
    assert entry["combatant_id"] == kr_tok
    assert entry["base_speed_walk"] == 40
    assert entry["speed_reduction_ft"] == 40, entry
    assert entry["installed"] is True


async def test_cast_hold_person_upcast_l4_allows_3_targets(
    gm_client, roster,
):
    """L4 upcast → 3 targets. Tavik affects Krieger + 2 fakes
    (the fakes won't resolve in hub but the cap check happens
    BEFORE the resolution loop, so they pass the gate; the
    affected list will only include those that resolve).
    """
    tavik = roster["Brother Tavik Stonebrow"]
    krieger = roster["Krieger Stonefist"]
    tv_tok = f"tok_hp_l4_tv_{tavik['id']}"
    kr_tok = f"tok_hp_l4_kr_{krieger['id']}"
    await _seed_battle(gm_client, [
        _mkc(tv_tok, tavik["id"], name=tavik["name"], speed_walk=30),
        _mkc(kr_tok, krieger["id"], name=krieger["name"], speed_walk=40),
    ])
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_hold_person",
        json={
            "character_id": tavik["id"],
            "class_slug": "cleric",
            "slot_level": 4,
            "target_combatant_ids": [kr_tok, "fake1", "fake2"],
            "override": True,
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["max_targets"] == 3  # L4 → 3 targets
    affected = data.get("affected") or []
    unaffected = data.get("unaffected") or []
    assert len(affected) == 1  # only Krieger resolved
    assert len(unaffected) == 2  # fakes not_found
    assert all(u["reason"] == "not_found" for u in unaffected)


async def test_cast_hold_person_l2_with_2_targets_rejected(gm_client, roster):
    """L2 caps at 1 target. 2 targets → 409 too_many_targets."""
    tavik = roster["Brother Tavik Stonebrow"]
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_hold_person",
        json={
            "character_id": tavik["id"],
            "class_slug": "cleric",
            "slot_level": 2,
            "target_combatant_ids": ["a", "b"],
            "override": True,
        },
    )
    assert resp.status_code == 409, resp.text
    data = resp.json()
    assert data["error"] == "too_many_targets"
    assert data["max"] == 1
    assert data["got"] == 2


async def test_cast_hold_person_l1_slot_rejected(gm_client, roster):
    """slot_level=1 → 400 (Hold Person is L2)."""
    tavik = roster["Brother Tavik Stonebrow"]
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_hold_person",
        json={
            "character_id": tavik["id"],
            "class_slug": "cleric",
            "slot_level": 1,
            "target_combatant_ids": ["a"],
            "override": True,
        },
    )
    assert resp.status_code == 400, resp.text


async def test_cast_hold_person_rejects_invalid_class(gm_client, roster):
    """Barbarian isn't in the Hold Person class list → 400.
    (Hold Person is on the Cleric/Bard/Sorcerer/Warlock/Wizard
    spell lists.)
    """
    tavik = roster["Brother Tavik Stonebrow"]
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_hold_person",
        json={
            "character_id": tavik["id"],
            "class_slug": "barbarian",
            "slot_level": 2,
            "target_combatant_ids": ["a"],
            "override": True,
        },
    )
    assert resp.status_code == 400, resp.text


async def test_cast_hold_person_undo_refunds_slot(
    gm_client, gm_ws, tavik_and_krieger,
):
    """v2.99.462 — bug fix: the chat-card ↶ Undo now refunds the spell
    slot a dedicated cast endpoint spent. Cast Hold Person (L2) → the
    response carries a `cast_id`; POST /undo_attack_damage with it →
    a `spell_slot_update` broadcasts the L2 cleric slot's `used` back
    down by 1.
    """
    tavik, krieger, kr_tok = tavik_and_krieger
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_hold_person",
        json={"character_id": tavik["id"], "class_slug": "cleric",
              "slot_level": 2, "target_combatant_ids": [kr_tok],
              "override": True},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    cast_id = data.get("cast_id")
    assert cast_id, "cast response must carry a cast_id for undo"
    used_after_cast = data["slot_used"]

    gm_ws.mark()
    u = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/undo_attack_damage",
        json={"attack_id": cast_id},
    )
    assert u.status_code == 200, u.text
    ssu = await gm_ws.wait_for("spell_slot_update", timeout=2.0)
    assert ssu["data"]["class_slug"] == "cleric"
    assert ssu["data"]["level"] == 2
    assert ssu["data"]["used"] == used_after_cast - 1  # slot refunded


# --- v2.183.16 Phase 4 deep-dive: the Paralyzed incapacitation stack ---
# The endpoint-contract tests above prove target-count gating + slot
# spend/refund. These two own the bespoke spell story the others skip:
# the installed Paralyzed condition's full contract, and the RAW
# end-of-turn WIS re-save (PHB p.290 / Hold Person) wired via
# /use_repeated_save off the buff's install-time stamps.


async def _combatant_buffs(gm_client, combatant_id):
    state = (await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
    )).json().get("battle") or {}
    for c in state.get("combatants") or []:
        if c.get("id") == combatant_id:
            return c.get("buffs") or []
    return []


async def _long_rest(gm_client, char_id) -> None:
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/rest",
        json={"type": "long"},
    )


async def _seed_dice(gm_client, seed) -> None:
    await gm_client.post("/api/test/dice/seed", json={"seed": seed})


async def test_cast_hold_person_buff_carries_paralyzed_contract(
    gm_client, tavik_and_krieger,
):
    """The installed buff is the canonical Paralyzed condition, not a
    bespoke per-spell shape. Reading Krieger's combatant buffs after a
    L2 cast must surface: key=="paralyzed", concentration, the
    hold-person source tag, the WIS end-of-turn re-save stamps, and the
    full RAW raw_effects narration (incapacitated / can't speak /
    auto-fail STR-DEX / melee auto-crit) plus the source-specific
    "WIS save at end of each turn" + "Only affects Humanoids" lines.
    """
    tavik, krieger, kr_tok = tavik_and_krieger
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_hold_person",
        json={"character_id": tavik["id"], "class_slug": "cleric",
              "slot_level": 2, "target_combatant_ids": [kr_tok],
              "override": True},
    )
    assert resp.status_code == 200, resp.text

    buffs = await _combatant_buffs(gm_client, kr_tok)
    para = next((b for b in buffs if b.get("key") == "paralyzed"), None)
    assert para is not None, buffs
    assert para["concentration"] is True
    assert para["source"] == "hold-person-spell"
    assert para["source_char_id"] == tavik["id"]
    # Install-time re-save stamps that wire /use_repeated_save.
    assert para["repeated_save_ability"] == "WIS"
    assert int(para["repeated_save_dc"]) > 0
    # speed → 0 is the only mechanically-enforced bit.
    assert para["effects"]["speed_reduction_ft"] == 40

    raw = para.get("raw_effects") or []
    joined = " | ".join(raw).lower()
    assert "incapacitated" in joined
    assert "can't speak" in joined
    assert "auto-fail str / dex saves" in joined
    assert "auto-crit" in joined
    assert any("wis save at end of each turn" in r.lower() for r in raw)
    assert any("only affects humanoids" in r.lower() for r in raw)


async def test_cast_hold_person_end_of_turn_wis_resave(
    gm_client, tavik_and_krieger,
):
    """RAW: "At the end of each of its turns, the target can make
    another WIS save; on a success the spell ends." /use_repeated_save
    resolves that save against the buff's stamped DC and drops the buff
    on a pass. Seed-loop (re-casting fresh + long-resting Tavik to
    refill L2 slots each iter) until BOTH a pass and a fail are
    observed; assert the save is always WIS vs a positive DC, and that
    buff_dropped tracks the pass/fail outcome.
    """
    tavik, krieger, kr_tok = tavik_and_krieger
    saw_pass = False
    saw_fail = False
    for seed in range(1, 60):
        await _long_rest(gm_client, tavik["id"])  # refill spent L2 slots
        cast = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/cast_hold_person",
            json={"character_id": tavik["id"], "class_slug": "cleric",
                  "slot_level": 2, "target_combatant_ids": [kr_tok],
                  "override": True},
        )
        assert cast.status_code == 200, cast.text
        await _seed_dice(gm_client, seed)
        rs = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/use_repeated_save",
            json={"character_id": krieger["id"], "buff_key": "paralyzed"},
        )
        assert rs.status_code == 200, rs.text
        data = rs.json()
        assert data["save_ability"] == "WIS"
        assert int(data["save_dc"]) > 0
        if data["passed"]:
            assert data["buff_dropped"] is True
            still = await _combatant_buffs(gm_client, kr_tok)
            assert not any(b.get("key") == "paralyzed" for b in still), \
                "passed save must drop the paralyzed buff"
            saw_pass = True
        else:
            assert data["buff_dropped"] is False
            saw_fail = True
        if saw_pass and saw_fail:
            break
    await _seed_dice(gm_client, None)  # reset determinism for siblings
    assert saw_pass, "no seed in range produced a passed WIS re-save"
    assert saw_fail, "no seed in range produced a failed WIS re-save"
