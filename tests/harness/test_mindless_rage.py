"""v2.57.0 — Mindless Rage (Path of the Berserker, Lv 6+).

Self-targeted condition-install immunity: while raging, the
barbarian can't be charmed or frightened. Mirrors the v2.55.0
Aura of Devotion gate but keyed off the saver's own active rage
buff instead of an ally aura.

Tests:
  - happy path: Krieger rages (`/use_rage`); Lyra casts Suggestion
    at Krieger; loop until Wis save FAILS → no Charmed buff
    installed + `feature_used(source=mindless-rage)` broadcast.
  - control without rage: Krieger does NOT rage; Lyra casts
    Suggestion at Krieger; loop until save fails → Charmed buff
    IS installed (normal flow), no Mindless Rage broadcast.
  - non-charm/non-fright bypass: Krieger rages; Tavik casts
    Hold Person; loop until save fails → Paralyzed IS installed
    (Mindless Rage is charm/fright-only).
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID


# Lyra's spell list — Suggestion at index 9.
SUGGESTION_INDEX = 9
# Tavik's spell list — Hold Person at index 8.
HOLD_PERSON_TAVIK_INDEX = 8


@pytest_asyncio.fixture
async def lyra_rested(gm_client, roster):
    lyra = roster["Lyra Sunstrider"]
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{lyra['id']}/rest",
        json={"type": "long"},
    )
    return lyra


@pytest_asyncio.fixture
async def tavik_rested(gm_client, roster):
    tavik = roster["Brother Tavik Stonebrow"]
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{tavik['id']}/rest",
        json={"type": "long"},
    )
    return tavik


@pytest_asyncio.fixture
async def krieger_rested(gm_client, roster):
    krieger = roster["Krieger Stonefist"]
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{krieger['id']}/rest",
        json={"type": "long"},
    )
    return krieger


def _make_combatant(name, char_id, init=10, hp=75):
    return {
        "id": f"tok_mr_{char_id}",
        "char_id": char_id,
        "name": name,
        "initiative": init,
        "hp_current": hp, "hp_max": hp,
        "buffs": [],
        "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0},
    }


async def _seed_battle(gm_client, combatants):
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": combatants, "turn_index": 0, "round": 1, "active": True},
    )


async def _get_buffs(gm_client, char_id: int) -> list:
    r = await gm_client.get(f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/buffs")
    return r.json().get("buffs", [])


async def _clear_buff(gm_client, char_id: int, key: str):
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/end_buff",
        json={"character_id": char_id, "key": key},
    )


def _mr_broadcasts(gm_ws, barbarian_char_id: int) -> list:
    return [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "mindless-rage"
        and (m.get("data") or {}).get("character_id") == barbarian_char_id
    ]


async def _cast_at_target(
    gm_client, caster, caster_class_slug, spell_index, slot_level, target,
):
    """Cast `spell_index` from `caster` at `target` (via combatant tok).
    Returns the cast_spell JSON.
    """
    target_tok = f"tok_mr_{target['id']}"
    cast_resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
        json={
            "character_id": caster["id"],
            "spell_index": spell_index,
            "slot_level": slot_level,
            "class_slug": caster_class_slug,
            "target_combatant_id": target_tok,
            "target_character_id": target["id"],
            "target_name": target["name"],
            "override": True,
        },
    )
    assert cast_resp.status_code == 200, cast_resp.text
    return cast_resp.json()


async def _drive_save_until(
    gm_client, gm_ws,
    *,
    caster, caster_class_slug, spell_index, slot_level, target,
    want_passed: bool, rage_first: bool,
    max_iters: int = 20,
):
    """Loop: long-rest caster, re-seed battle, optionally /use_rage on
    target, cast spell, respond on target's behalf, until the save
    outcome matches ``want_passed``. Returns the respond JSON.
    """
    base_combatants = [
        _make_combatant(caster["name"], caster["id"], init=12, hp=40),
        _make_combatant(target["name"], target["id"], init=8, hp=75),
    ]
    for _ in range(max_iters):
        await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/character/{caster['id']}/rest",
            json={"type": "long"},
        )
        # Ensure Krieger has rage uses + no leftover buffs.
        await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/character/{target['id']}/rest",
            json={"type": "long"},
        )
        await _clear_buff(gm_client, target["id"], "charmed")
        await _clear_buff(gm_client, target["id"], "paralyzed")
        await _clear_buff(gm_client, target["id"], "rage")
        await _seed_battle(gm_client, base_combatants)
        if rage_first:
            rage_resp = await gm_client.post(
                f"/api/campaign/{CAMPAIGN_ID}/use_rage",
                json={"character_id": target["id"], "override": True},
            )
            assert rage_resp.status_code == 200, rage_resp.text
        gm_ws.mark()
        cast_data = await _cast_at_target(
            gm_client, caster, caster_class_slug,
            spell_index, slot_level, target,
        )
        pending_id = cast_data.get("auto_save_prompt_id")
        assert isinstance(pending_id, int) and pending_id > 0, (
            f"expected a roll_request prompt id; got {cast_data}"
        )
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/roll_request/{pending_id}/respond",
            json={"character_id": target["id"]},
        )
        assert r.status_code == 200, r.text
        rdata = r.json()
        passed = rdata.get("total", 0) >= cast_data.get("auto_save_dc", 99)
        if passed == want_passed:
            return rdata
    raise AssertionError(
        f"Could not land save_passed={want_passed} for {target['name']} "
        f"in {max_iters} attempts"
    )


async def test_mindless_rage_blocks_charmed_install(
    gm_client, gm_ws, roster, lyra_rested, krieger_rested,
):
    """Krieger rages, Lyra casts Suggestion at Krieger, loop until
    Krieger's Wis save FAILS → no Charmed buff on Krieger AND a
    `feature_used(source=mindless-rage)` broadcast fires for him.
    """
    lyra = lyra_rested
    krieger = krieger_rested

    rdata = await _drive_save_until(
        gm_client, gm_ws,
        caster=lyra, caster_class_slug="bard",
        spell_index=SUGGESTION_INDEX, slot_level=2,
        target=krieger, want_passed=False,
        rage_first=True,
    )
    assert rdata.get("auto_buff_installed", "") == "", (
        f"Mindless Rage should block Charmed install; got "
        f"auto_buff_installed={rdata.get('auto_buff_installed')!r}"
    )
    buffs = await _get_buffs(gm_client, krieger["id"])
    assert not any((b or {}).get("key") == "charmed" for b in buffs), (
        f"Krieger should NOT have Charmed while raging; "
        f"got buffs: {[(b or {}).get('key') for b in buffs]}"
    )
    mr_msgs = _mr_broadcasts(gm_ws, krieger["id"])
    assert mr_msgs, (
        f"expected feature_used(source=mindless-rage) for Krieger; "
        f"buffered: {[(m.get('type'), (m.get('data') or {}).get('source')) for m in gm_ws.buffered()]}"
    )

    await _clear_buff(gm_client, krieger["id"], "rage")


async def test_charmed_installs_when_not_raging(
    gm_client, gm_ws, roster, lyra_rested, krieger_rested,
):
    """Control: Krieger does NOT rage. Lyra casts Suggestion at
    Krieger; loop until save fails → Charmed buff installs normally
    (no Mindless Rage broadcast).
    """
    lyra = lyra_rested
    krieger = krieger_rested

    rdata = await _drive_save_until(
        gm_client, gm_ws,
        caster=lyra, caster_class_slug="bard",
        spell_index=SUGGESTION_INDEX, slot_level=2,
        target=krieger, want_passed=False,
        rage_first=False,
    )
    assert rdata.get("auto_buff_installed", "").lower() in {
        "charmed", "charmed (suggestion)",
    }, (
        f"without rage, failed Suggestion save should install Charmed; "
        f"got auto_buff_installed={rdata.get('auto_buff_installed')!r}"
    )
    buffs = await _get_buffs(gm_client, krieger["id"])
    assert any((b or {}).get("key") == "charmed" for b in buffs), (
        f"Krieger should have Charmed (not raging); "
        f"got buffs: {[(b or {}).get('key') for b in buffs]}"
    )
    mr_msgs = _mr_broadcasts(gm_ws, krieger["id"])
    assert not mr_msgs, (
        f"no Mindless Rage broadcast should fire when not raging: {mr_msgs}"
    )

    await _clear_buff(gm_client, krieger["id"], "charmed")


async def test_mindless_rage_skips_non_charm_fright(
    gm_client, gm_ws, roster, tavik_rested, krieger_rested,
):
    """Krieger rages — but Tavik casts Hold Person (installs
    Paralyzed, not Charmed/Frightened). The Mindless Rage gate is
    charm/fright-only, so Krieger's failed save installs Paralyzed
    normally.
    """
    tavik = tavik_rested
    krieger = krieger_rested

    rdata = await _drive_save_until(
        gm_client, gm_ws,
        caster=tavik, caster_class_slug="cleric",
        spell_index=HOLD_PERSON_TAVIK_INDEX, slot_level=2,
        target=krieger, want_passed=False,
        rage_first=True,
    )
    assert rdata.get("auto_buff_installed", "").lower() == "paralyzed", (
        f"Mindless Rage blocks charm/fright only; Hold Person should "
        f"still install Paralyzed; got "
        f"auto_buff_installed={rdata.get('auto_buff_installed')!r}"
    )
    buffs = await _get_buffs(gm_client, krieger["id"])
    assert any((b or {}).get("key") == "paralyzed" for b in buffs), (
        f"Krieger should have Paralyzed (Mindless Rage doesn't gate "
        f"paralyzed); got buffs: {[(b or {}).get('key') for b in buffs]}"
    )
    mr_msgs = _mr_broadcasts(gm_ws, krieger["id"])
    assert not mr_msgs, (
        f"Mindless Rage broadcast should NOT fire on non-charm/fright: {mr_msgs}"
    )

    await _clear_buff(gm_client, krieger["id"], "paralyzed")
    await _clear_buff(gm_client, krieger["id"], "rage")
