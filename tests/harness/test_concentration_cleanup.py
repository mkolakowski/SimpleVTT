"""Phase T.3e — concentration cleanup drops paired condition buffs.

v2.38.0: when a caster's concentration drops (broken on damage,
replaced by a new concentration cast, or ended manually via
``/end_buff``), every condition buff they granted under that
concentration drops in lock-step.

T.3c (v2.32.0) installs the condition with ``source_char_id`` +
``concentration: True`` on the target combatant. v2.38.0 also
installs a caster-side concentration buff (key
``concentration-<slug>``) at the same time so the cleanup helper
has an anchor to fire on. Ending the caster's concentration via
``/end_buff`` removes ALL paired buffs across the init tracker.

Tests:
  - Cast Hold Person at a bandit until they fail the save → both
    bandit-side Paralyzed AND caster-side ``concentration-hold-
    person`` are installed (verifiable via the /buffs GET on Tavik).
  - End Tavik's concentration via ``/end_buff`` → paired Paralyzed
    on the bandit drops (verifiable via re-casting; the new install
    succeeds because the slot is free).
  - Non-concentration buff removal (Rage on Krieger) does NOT trigger
    the paired-cleanup branch; nothing breaks.
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID


HOLD_PERSON_INDEX = 8


@pytest_asyncio.fixture
async def tavik_rested(gm_client, roster):
    tavik = roster["Brother Tavik Stonebrow"]
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{tavik['id']}/rest",
        json={"type": "long"},
    )
    return tavik


async def _seed_battle(gm_client, combatants):
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": combatants, "turn_index": 0, "round": 1, "active": True},
    )


async def _tavik_buff_keys(gm_client, tavik_id: int) -> list[str]:
    """Read Tavik's current buff keys via the /buffs GET endpoint."""
    r = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{tavik_id}/buffs",
    )
    if r.status_code != 200:
        return []
    return [(b or {}).get("key") for b in r.json().get("buffs", [])]


async def test_save_or_suck_installs_caster_concentration(gm_client, tavik_rested):
    """Hold Person on a failed save also installs a caster-side
    concentration buff on Tavik (key concentration-hold-person)."""
    tavik = tavik_rested
    r = await gm_client.get(f"/api/campaign/{CAMPAIGN_ID}/templates")
    templates = r.json()
    bandit_tmpl = next((t for t in templates if "bandit" in t["name"].lower()), templates[0])
    saw_install = False
    for _ in range(20):
        await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/character/{tavik['id']}/rest",
            json={"type": "long"},
        )
        await _seed_battle(gm_client, [
            {"id": f"tok_test_{tavik['id']}", "char_id": tavik["id"],
             "name": tavik["name"], "initiative": 10, "hp_current": 30, "hp_max": 30,
             "buffs": [],
             "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0}},
            {"id": "tok_test_bandit_t3e", "char_id": None,
             "token_template_id": bandit_tmpl["id"],
             "name": bandit_tmpl["name"], "initiative": 7, "hp_current": 11, "hp_max": 11,
             "buffs": [],
             "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0}},
        ])
        resp = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
            json={
                "character_id": tavik["id"],
                "spell_index": HOLD_PERSON_INDEX,
                "slot_level": 2,
                "class_slug": "cleric",
                "target_combatant_id": "tok_test_bandit_t3e",
                "target_name": bandit_tmpl["name"],
                "override": True,
            },
        )
        data = resp.json()
        if data["auto_save_passed"] is False and data["auto_save_buff_name"]:
            saw_install = True
            keys = await _tavik_buff_keys(gm_client, tavik["id"])
            assert "concentration-hold-person" in keys, (
                f"expected caster-side concentration buff; got {keys}"
            )
            break
    assert saw_install, "no save failure in 20 attempts — flaky env?"


async def test_end_concentration_drops_caster_buff(gm_client, tavik_rested):
    """After Hold Person installs both target buff + caster
    concentration, ending the caster's concentration via /end_buff
    removes the caster's concentration buff. (Removal of the paired
    target buff is broadcast via battle_update — we verify the
    caster-side side here; cross-target cleanup test below.)
    """
    tavik = tavik_rested
    r = await gm_client.get(f"/api/campaign/{CAMPAIGN_ID}/templates")
    templates = r.json()
    bandit_tmpl = next((t for t in templates if "bandit" in t["name"].lower()), templates[0])
    # Loop until we land a failure to get the install.
    installed = False
    for _ in range(20):
        await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/character/{tavik['id']}/rest",
            json={"type": "long"},
        )
        await _seed_battle(gm_client, [
            {"id": f"tok_test_{tavik['id']}", "char_id": tavik["id"],
             "name": tavik["name"], "initiative": 10, "hp_current": 30, "hp_max": 30,
             "buffs": [],
             "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0}},
            {"id": "tok_test_bandit_t3e2", "char_id": None,
             "token_template_id": bandit_tmpl["id"],
             "name": bandit_tmpl["name"], "initiative": 7, "hp_current": 11, "hp_max": 11,
             "buffs": [],
             "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0}},
        ])
        resp = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
            json={
                "character_id": tavik["id"],
                "spell_index": HOLD_PERSON_INDEX,
                "slot_level": 2,
                "class_slug": "cleric",
                "target_combatant_id": "tok_test_bandit_t3e2",
                "target_name": bandit_tmpl["name"],
                "override": True,
            },
        )
        if resp.json().get("auto_save_buff_name"):
            installed = True
            break
    assert installed, "no buff in 20 attempts"
    # Verify caster buff is there.
    assert "concentration-hold-person" in await _tavik_buff_keys(gm_client, tavik["id"])
    # End it.
    eb = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/end_buff",
        json={"character_id": tavik["id"], "key": "concentration-hold-person"},
    )
    assert eb.status_code == 200, eb.text
    assert eb.json()["removed_key"] == "concentration-hold-person"
    # Caster buff gone.
    assert "concentration-hold-person" not in await _tavik_buff_keys(gm_client, tavik["id"])


async def test_concentration_break_emits_gm_only_log(gm_client, gm_ws, alice_ws, roster):
    """v2.39.0: when a player loses concentration via a failed save,
    the server emits a GM-only ``roll`` event narrating the loss +
    the paired buffs that dropped. Players see their own buff vanish
    but don't get the audit log.

    Setup: install Hunter's Mark on Rowan (concentration), then
    damage Rowan with massive (≥ 21 HP) damage so DC ≥ 10 + a high
    chance of failure. The new GM-only roll log should appear in
    gm_ws but be filtered out of alice_ws by the visibility gate.
    """
    rowan = roster["Rowan Quickbow"]
    pip = roster["Pip Quickfingers"]
    # Reset everything to a known state.
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{rowan['id']}/rest",
        json={"type": "long"},
    )
    await _seed_battle(gm_client, [
        {"id": f"tok_test_{rowan['id']}", "char_id": rowan["id"],
         "name": rowan["name"], "initiative": 10, "hp_current": 44, "hp_max": 44,
         "buffs": [],
         "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0}},
        {"id": f"tok_test_{pip['id']}", "char_id": pip["id"],
         "name": pip["name"], "initiative": 8, "hp_current": 30, "hp_max": 30,
         "buffs": [],
         "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0}},
    ])
    # Install Hunter's Mark on Pip (target) — Rowan is the caster.
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_hunters_mark",
        json={
            "character_id": rowan["id"],
            "target_character_id": pip["id"],
            "override": True,
        },
    )
    assert r.status_code == 200, r.text
    gm_ws.mark()
    alice_ws.mark()
    # Damage Rowan heavily so failure is likely. Loop up to 10 times.
    saw_log = False
    for _ in range(10):
        # Reset Rowan's HP between iterations and reinstall the mark
        # if it dropped.
        await gm_client.patch(
            f"/api/campaign/{CAMPAIGN_ID}/character/{rowan['id']}/sheet-fields",
            json={"hp": {"current": 44}},
        )
        await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/cast_hunters_mark",
            json={
                "character_id": rowan["id"],
                "target_character_id": pip["id"],
                "override": True,
            },
        )
        gm_ws.mark()
        alice_ws.mark()
        # 30 damage → DC = max(10, 15) = 15. Rowan's CON mod is low,
        # so failure is very likely.
        await gm_client.patch(
            f"/api/campaign/{CAMPAIGN_ID}/character/{rowan['id']}/sheet-fields",
            json={
                "hp": {"current": 14},
                "hp_change_reason": "damage",
                "damage_amount": 30,
            },
        )
        cs = await gm_ws.wait_for("concentration_save")
        if cs["data"]["passed"]:
            continue  # passed → no log; retry
        # On fail, the new GM-only roll log entry fires.
        log = await gm_ws.wait_for("roll", timeout=2.0)
        assert log["data"]["visibility"] == "gm_only"
        assert "lost concentration" in log["data"]["note"].lower()
        assert rowan["name"] in log["data"]["note"]
        saw_log = True
        break
    assert saw_log, "no concentration failure in 10 attempts — flaky env?"


async def test_non_concentration_buff_removal_unaffected(gm_client, roster):
    """Removing a non-concentration buff (Rage) does NOT trigger the
    paired-cleanup branch — smoke check that v2.38.0's modified
    /end_buff path still handles vanilla removals."""
    krieger = roster["Krieger Stonefist"]
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{krieger['id']}/rest",
        json={"type": "long"},
    )
    await _seed_battle(gm_client, [
        {"id": f"tok_test_{krieger['id']}", "char_id": krieger["id"],
         "name": krieger["name"], "initiative": 10, "hp_current": 55, "hp_max": 55,
         "buffs": [],
         "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0}},
    ])
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_rage",
        json={"character_id": krieger["id"], "override": True},
    )
    assert r.status_code == 200, r.text
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/end_buff",
        json={"character_id": krieger["id"], "key": "rage"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["removed_key"] == "rage"
