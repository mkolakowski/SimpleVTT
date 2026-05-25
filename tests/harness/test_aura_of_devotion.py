"""v2.55.0 — Paladin Aura of Devotion (Oath of Devotion, Lv 7+).

First **condition-install immunity gate**. When a failed save would
install the Charmed condition on a PC ally, and any Paladin Lv 7+
with subclass Oath of Devotion is in the active battle's init,
the install is BLOCKED and a `feature_used(source=aura-of-devotion)`
broadcast surfaces the immunity. Distinct from Aura of Protection
(adds a bonus to the save roll) — Aura of Devotion acts AFTER the
save resolves and bypasses the consequence entirely.

Tests:
  - happy path: Caelan + Krieger in init; Lyra casts Suggestion at
    Krieger; loop until Krieger's Wis save FAILS → no Charmed buff
    on Krieger + `feature_used(source=aura-of-devotion)` broadcast.
  - control without paladin: Caelan NOT in init; loop until save
    fails → Charmed buff IS installed (normal flow).
  - non-charm condition: Caelan in init; Tavik casts Hold Person at
    Krieger; loop until save fails → Paralyzed buff IS installed
    (Aura of Devotion is charm-only, doesn't block Paralyzed).
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID


# Lyra's spell list — Suggestion at index 9.
SUGGESTION_INDEX = 9
# Tavik's spell list — Hold Person at index 8 (test_cast_spell_save).
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


def _make_combatant(name, char_id, init=10, hp=40):
    return {
        "id": f"tok_aod_{char_id}",
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
    """Clear a specific buff key off a character (between iterations
    so the next save's install branch fires cleanly)."""
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/end_buff",
        json={"character_id": char_id, "key": key},
    )


def _aod_broadcasts(gm_ws, paladin_char_id: int) -> list:
    return [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "aura-of-devotion"
        and (m.get("data") or {}).get("character_id") == paladin_char_id
    ]


async def _cast_and_respond_for_save_outcome(
    gm_client, gm_ws, caster, caster_class_slug, spell_index, slot_level,
    target, want_passed: bool, *, max_iters: int = 20,
    aoe: bool = False, extra_combatants=None,
):
    """Generic save-fail/pass driver. Casts the spell at target,
    responds on target's behalf, loops until the save outcome matches
    ``want_passed``. Re-seeds + long-rests between iterations.
    Returns the /roll_request/{id}/respond JSON for the matched run.
    """
    target_tok = f"tok_aod_{target['id']}"
    caster_tok = f"tok_aod_{caster['id']}"
    base_combatants = [
        _make_combatant(caster["name"], caster["id"], init=12),
        _make_combatant(target["name"], target["id"], init=8, hp=55),
    ] + list(extra_combatants or [])
    for _ in range(max_iters):
        await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/character/{caster['id']}/rest",
            json={"type": "long"},
        )
        # Clear any leftover Charmed / Paralyzed from prior iteration
        # so the install path fires cleanly.
        await _clear_buff(gm_client, target["id"], "charmed")
        await _clear_buff(gm_client, target["id"], "paralyzed")
        await _seed_battle(gm_client, base_combatants)
        gm_ws.mark()
        cast_kw = {
            "character_id": caster["id"],
            "spell_index": spell_index,
            "slot_level": slot_level,
            "class_slug": caster_class_slug,
            "target_combatant_id": target_tok,
            "target_character_id": target["id"],
            "target_name": target["name"],
            "override": True,
        }
        cast_resp = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/cast_spell", json=cast_kw,
        )
        assert cast_resp.status_code == 200, cast_resp.text
        cast_data = cast_resp.json()
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


async def test_aura_of_devotion_blocks_charmed_install(
    gm_client, gm_ws, roster, lyra_rested,
):
    """Caelan (Paladin Lv 7 Oath of Devotion) is in init. Lyra casts
    Suggestion at Krieger; loop until Krieger fails his Wis save →
    the Charmed buff is NOT installed AND a
    `feature_used(source=aura-of-devotion)` broadcast fires for
    Caelan.
    """
    lyra = lyra_rested
    krieger = roster["Krieger Stonefist"]
    caelan = roster["Sir Caelan Lightbringer"]

    rdata = await _cast_and_respond_for_save_outcome(
        gm_client, gm_ws,
        caster=lyra, caster_class_slug="bard",
        spell_index=SUGGESTION_INDEX, slot_level=2,
        target=krieger, want_passed=False,
        extra_combatants=[_make_combatant(caelan["name"], caelan["id"], init=10)],
    )
    # AoD blocked the install — no Charmed buff on Krieger.
    assert rdata.get("auto_buff_installed", "") == "", (
        f"AoD should block Charmed install; got auto_buff_installed="
        f"{rdata.get('auto_buff_installed')!r}"
    )
    buffs = await _get_buffs(gm_client, krieger["id"])
    assert not any((b or {}).get("key") == "charmed" for b in buffs), (
        f"Krieger should NOT have Charmed buff after AoD blocked install; "
        f"got buffs: {[(b or {}).get('key') for b in buffs]}"
    )
    # Broadcast surfaces the immunity, naming Caelan.
    aod_msgs = _aod_broadcasts(gm_ws, caelan["id"])
    assert aod_msgs, (
        f"expected feature_used(source=aura-of-devotion) for Caelan; "
        f"buffered: {[(m.get('type'), (m.get('data') or {}).get('source')) for m in gm_ws.buffered()]}"
    )


async def test_charmed_installs_when_paladin_absent(
    gm_client, gm_ws, roster, lyra_rested,
):
    """Control: Caelan NOT in init. Lyra casts Suggestion at Krieger
    → save-fail iteration → Charmed buff IS installed (standard
    flow); no Aura of Devotion broadcast.
    """
    lyra = lyra_rested
    krieger = roster["Krieger Stonefist"]

    rdata = await _cast_and_respond_for_save_outcome(
        gm_client, gm_ws,
        caster=lyra, caster_class_slug="bard",
        spell_index=SUGGESTION_INDEX, slot_level=2,
        target=krieger, want_passed=False,
        # No extra combatants — Caelan absent.
    )
    assert rdata.get("auto_buff_installed", "").lower() in {"charmed", "charmed (suggestion)"}, (
        f"without AoD in init, failed Suggestion save should install "
        f"Charmed; got auto_buff_installed={rdata.get('auto_buff_installed')!r}"
    )
    buffs = await _get_buffs(gm_client, krieger["id"])
    assert any((b or {}).get("key") == "charmed" for b in buffs), (
        f"Krieger should have Charmed buff (no AoD blocking); "
        f"got buffs: {[(b or {}).get('key') for b in buffs]}"
    )
    aod_msgs = [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "aura-of-devotion"
    ]
    assert not aod_msgs, (
        f"no AoD broadcast should fire when paladin is absent: {aod_msgs}"
    )

    # Cleanup so subsequent tests don't see Krieger Charmed.
    await _clear_buff(gm_client, krieger["id"], "charmed")


async def test_aod_skips_non_charm_conditions(
    gm_client, gm_ws, roster, tavik_rested,
):
    """Caelan in init — but Tavik casts Hold Person (installs
    Paralyzed, NOT Charmed). The AoD gate is charm-only, so
    Krieger's failed save installs Paralyzed normally.
    """
    tavik = tavik_rested
    krieger = roster["Krieger Stonefist"]
    caelan = roster["Sir Caelan Lightbringer"]

    rdata = await _cast_and_respond_for_save_outcome(
        gm_client, gm_ws,
        caster=tavik, caster_class_slug="cleric",
        spell_index=HOLD_PERSON_TAVIK_INDEX, slot_level=2,
        target=krieger, want_passed=False,
        extra_combatants=[_make_combatant(caelan["name"], caelan["id"], init=10)],
    )
    assert rdata.get("auto_buff_installed", "").lower() == "paralyzed", (
        f"AoD blocks Charmed only; Hold Person should still install "
        f"Paralyzed; got auto_buff_installed={rdata.get('auto_buff_installed')!r}"
    )
    buffs = await _get_buffs(gm_client, krieger["id"])
    assert any((b or {}).get("key") == "paralyzed" for b in buffs), (
        f"Krieger should have Paralyzed buff (AoD doesn't gate paralyzed); "
        f"got buffs: {[(b or {}).get('key') for b in buffs]}"
    )
    aod_msgs = _aod_broadcasts(gm_ws, caelan["id"])
    assert not aod_msgs, (
        f"AoD broadcast should NOT fire on non-charm condition: {aod_msgs}"
    )

    # Cleanup so subsequent tests don't see Krieger Paralyzed.
    await _clear_buff(gm_client, krieger["id"], "paralyzed")
