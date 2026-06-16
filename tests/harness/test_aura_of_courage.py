"""v2.368.0 — Paladin Aura of Courage (base Paladin Lv 10+).

RAW (PHB p.85): "Starting at 10th level, you and friendly creatures
within 10 feet of you can't be frightened while you are conscious.
At 18th level, the range of this aura increases to 30 feet."

Mirror of the v2.55.0 Aura of Devotion gate but:
- Oath-agnostic (base Paladin Lv 10, not Devotion-only).
- Blocks Frightened (not Charmed).
- Installed at `_install_buff` rather than the /respond handler, so
  every Frightened install path (failed save via /respond, Demon
  Slayer on_hit_save, future fear effects) is gated uniformly.

Demo fixture: Sir Caelan Lightbringer is Lv 7 by default — the gate
won't fire mechanically until he's PATCH-bumped to Lv 10. The base
level row (`aura-of-courage`) on his class_features list is seeded
unconditionally so the picker surfaces the feature as a discoverable
Lv-10+ unlock.

Tests:
  - Caelan Lv 10 + Krieger in init → Lyra casts Fear at Krieger
    → loop until Krieger's Wis save FAILS → no Frightened buff on
    Krieger + `feature_used(source=aura-of-courage)` broadcast.
  - Caelan Lv 7 baseline (no aura) → loop until save fails →
    Frightened buff IS installed (gate didn't fire — Lv-10 threshold).
  - Caelan Lv 10 but unconscious (HP 0) → Frightened install
    succeeds (paladin can't grant aura while unconscious).
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID


LYRA_FEAR_INDEX = 19  # appended v2.97.43


def _make_combatant(name, char_id, init=10, hp=80):
    return {
        "id": f"tok_aoc_{char_id}",
        "char_id": char_id,
        "name": name,
        "initiative": init,
        "hp_current": hp, "hp_max": hp,
        "buffs": [],
        "economy": {"action": False, "bonus": False,
                    "reaction": False, "movement": 0},
    }


async def _seed_battle(gm_client, combatants):
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": combatants, "turn_index": 0,
              "round": 1, "active": True},
    )


async def _patch_level(gm_client, char_id, level):
    """PATCH a PC's level so the AoC Lv-10 gate fires (or doesn't).
    Snapshot returned for finally-restore."""
    sheet_r = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-json",
    )
    sheet = (sheet_r.json() or {}).get("sheet") or {}
    snap = sheet.get("level")
    await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-fields",
        json={"level": level},
    )
    return snap


async def _patch_hp(gm_client, char_id, hp):
    sheet_r = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-json",
    )
    sheet = (sheet_r.json() or {}).get("sheet") or {}
    snap = dict(sheet.get("hp") or {})
    await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-fields",
        json={"hp": hp},
    )
    return snap


async def _get_buffs(gm_client, char_id):
    r = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/buffs",
    )
    return r.json().get("buffs", [])


async def _clear_buff(gm_client, char_id, key):
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/end_buff",
        json={"character_id": char_id, "key": key},
    )


def _aoc_broadcasts(gm_ws, paladin_char_id):
    return [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "aura-of-courage"
        and (m.get("data") or {}).get("character_id") == paladin_char_id
    ]


@pytest_asyncio.fixture
async def lyra_rested(gm_client, roster):
    lyra = roster["Lyra Sunstrider"]
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{lyra['id']}/rest",
        json={"type": "long"},
    )
    return lyra


async def _cast_and_respond_for_save_outcome(
    gm_client, gm_ws, caster, target, *, want_passed,
    extra_combatants=None, max_iters=30,
):
    """Generic save-fail driver. Casts Lyra's Fear at target, loops
    until /respond returns a save outcome matching `want_passed`.
    Long-rests caster between iterations + clears the Frightened buff
    so the install path fires cleanly each time."""
    target_tok = f"tok_aoc_{target['id']}"
    base_combatants = [
        _make_combatant(caster["name"], caster["id"], init=12),
        _make_combatant(target["name"], target["id"], init=8, hp=80),
    ] + list(extra_combatants or [])
    for _ in range(max_iters):
        await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/character/{caster['id']}/rest",
            json={"type": "long"},
        )
        await _clear_buff(gm_client, target["id"], "frightened")
        await _seed_battle(gm_client, base_combatants)
        gm_ws.mark()
        cast_resp = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
            json={
                "character_id": caster["id"],
                "spell_index": LYRA_FEAR_INDEX,
                "slot_level": 3,
                "class_slug": "bard",
                "target_combatant_id": target_tok,
                "target_character_id": target["id"],
                "target_name": target["name"],
                "override": True,
                "override_range": True,
            },
        )
        assert cast_resp.status_code == 200, cast_resp.text
        cast_data = cast_resp.json()
        pending_id = cast_data.get("auto_save_prompt_id")
        if not (isinstance(pending_id, int) and pending_id > 0):
            continue
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


async def test_aoc_blocks_frightened_install_at_lv10(
    gm_client, gm_ws, roster, lyra_rested,
):
    """Caelan PATCH'd to Lv 10 + in init → Lyra casts Fear at Krieger
    → on a failed Wis save, no Frightened buff installs AND a
    `feature_used(source=aura-of-courage)` broadcast fires."""
    lyra = lyra_rested
    caelan = roster["Sir Caelan Lightbringer"]
    krieger = roster["Krieger Stonefist"]
    level_snap = await _patch_level(gm_client, caelan["id"], 10)
    try:
        rdata = await _cast_and_respond_for_save_outcome(
            gm_client, gm_ws,
            caster=lyra, target=krieger, want_passed=False,
            extra_combatants=[
                _make_combatant(caelan["name"], caelan["id"], init=10),
            ],
        )
        # AoC blocked the install — no Frightened buff on Krieger.
        buffs = await _get_buffs(gm_client, krieger["id"])
        assert not any((b or {}).get("key") == "frightened" for b in buffs), (
            f"Krieger should NOT have Frightened buff after AoC blocked "
            f"install; got buffs: {[(b or {}).get('key') for b in buffs]}"
        )
        # Broadcast surfaces the immunity, naming Caelan.
        aoc_msgs = _aoc_broadcasts(gm_ws, caelan["id"])
        assert aoc_msgs, (
            f"expected feature_used(source=aura-of-courage) for Caelan; "
            f"sources buffered: "
            f"{[(m.get('data') or {}).get('source') for m in gm_ws.buffered('feature_used')]}"
        )
    finally:
        await _clear_buff(gm_client, krieger["id"], "frightened")
        if level_snap is not None:
            await gm_client.patch(
                f"/api/campaign/{CAMPAIGN_ID}/character/{caelan['id']}/sheet-fields",
                json={"level": level_snap},
            )


async def test_aoc_does_not_fire_at_lv9_or_below(
    gm_client, gm_ws, roster, lyra_rested,
):
    """Caelan at his seed Lv 7 — the AoC gate doesn't fire. Lyra
    casts Fear at Krieger → on a failed Wis save, Frightened IS
    installed and no AoC broadcast fires."""
    lyra = lyra_rested
    caelan = roster["Sir Caelan Lightbringer"]
    krieger = roster["Krieger Stonefist"]
    # Caelan's seed level is 7 — below the Lv 10 AoC threshold.
    try:
        await _cast_and_respond_for_save_outcome(
            gm_client, gm_ws,
            caster=lyra, target=krieger, want_passed=False,
            extra_combatants=[
                _make_combatant(caelan["name"], caelan["id"], init=10),
            ],
        )
        buffs = await _get_buffs(gm_client, krieger["id"])
        assert any((b or {}).get("key") == "frightened" for b in buffs), (
            f"Krieger should have Frightened buff (Caelan Lv 7 < 10, "
            f"AoC inactive); got buffs: "
            f"{[(b or {}).get('key') for b in buffs]}"
        )
        aoc_msgs = _aoc_broadcasts(gm_ws, caelan["id"])
        assert not aoc_msgs, (
            f"AoC broadcast should NOT fire below Lv 10; got: {aoc_msgs}"
        )
    finally:
        await _clear_buff(gm_client, krieger["id"], "frightened")


async def test_aoc_disabled_when_paladin_unconscious(
    gm_client, gm_ws, roster, lyra_rested,
):
    """Caelan Lv 10 but at 0 HP (dying / unconscious) → AoC suspends.
    Lyra casts Fear → on a failed Wis save, Frightened IS installed."""
    lyra = lyra_rested
    caelan = roster["Sir Caelan Lightbringer"]
    krieger = roster["Krieger Stonefist"]
    level_snap = await _patch_level(gm_client, caelan["id"], 10)
    hp_snap = await _patch_hp(gm_client, caelan["id"], {"current": 0})
    try:
        await _cast_and_respond_for_save_outcome(
            gm_client, gm_ws,
            caster=lyra, target=krieger, want_passed=False,
            extra_combatants=[
                _make_combatant(caelan["name"], caelan["id"],
                                init=10, hp=0),
            ],
        )
        buffs = await _get_buffs(gm_client, krieger["id"])
        assert any((b or {}).get("key") == "frightened" for b in buffs), (
            f"Krieger should have Frightened buff (Caelan unconscious, "
            f"AoC suspends); got buffs: "
            f"{[(b or {}).get('key') for b in buffs]}"
        )
        aoc_msgs = _aoc_broadcasts(gm_ws, caelan["id"])
        assert not aoc_msgs, (
            f"AoC broadcast should NOT fire when paladin unconscious; "
            f"got: {aoc_msgs}"
        )
    finally:
        await _clear_buff(gm_client, krieger["id"], "frightened")
        await gm_client.patch(
            f"/api/campaign/{CAMPAIGN_ID}/character/{caelan['id']}/sheet-fields",
            json={"hp": hp_snap},
        )
        if level_snap is not None:
            await gm_client.patch(
                f"/api/campaign/{CAMPAIGN_ID}/character/{caelan['id']}/sheet-fields",
                json={"level": level_snap},
            )
