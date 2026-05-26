"""v2.61.0 — F1 token positional adjacency framework wired into auras.

Tests the new ``_distance_ft_between_chars`` range gate that v2.61.0
added to Aura of Devotion (10/30 ft) + Aura of Protection (10/30 ft)
+ Countercharm (30 ft). Pre-v2.61.0 each aura applied to any ally in
init regardless of token position; post-v2.61.0 the gate checks the
in-game distance and skips the aura when the ally is out of range.

The fall-back-to-no-position semantics are tested by existing
``test_aura_of_devotion.py`` / ``test_aura_of_protection.py`` /
``test_use_countercharm.py`` — those tests don't place tokens, so
the helper returns None and the aura applies to "any in init"
(pre-v2.61.0 behavior). This file covers the NEW path: tokens are
placed, and the gate either fires the aura (in range) or skips it
(out of range).

Tests in this file (Aura of Devotion):
  - Caelan at (350, 350), Krieger at (420, 350) — 5 ft apart →
    AoD BLOCKS Charmed install (in range).
  - Caelan at (350, 350), Krieger at (700, 350) — 25 ft apart →
    AoD does NOT block (out of range).

Demo grid: 70 px / cell, 5 ft / cell. Chebyshev distance on square
grids per RAW 5-5-5 diagonals.
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID


SUGGESTION_INDEX = 9  # Lyra's spell list (College of Lore Bard)


@pytest_asyncio.fixture
async def lyra_rested(gm_client, roster):
    lyra = roster["Lyra Sunstrider"]
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{lyra['id']}/rest",
        json={"type": "long"},
    )
    return lyra


def _make_combatant(name, char_id, init=10, hp=55):
    return {
        "id": f"tok_range_{char_id}",
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


async def _place_token(gm_client, char_id, x, y):
    """Place a character's token on the active map at the given
    pixel coordinates. Replaces any existing token for that
    character.
    """
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/place-token",
        json={"x": float(x), "y": float(y)},
    )
    assert r.status_code == 200, r.text


async def _delete_token(gm_client, char_id):
    """Remove a character's token from the active map. Used in test
    cleanup so subsequent tests (especially the v2.55.0 AoD tests
    that don't place tokens) get the no-position fallback path
    rather than a stale placement from this file.
    """
    await gm_client.delete(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/token",
    )


def _aod_broadcasts(gm_ws, paladin_char_id: int) -> list:
    return [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "aura-of-devotion"
        and (m.get("data") or {}).get("character_id") == paladin_char_id
    ]


async def _clear_buff(gm_client, char_id: int, key: str):
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/end_buff",
        json={"character_id": char_id, "key": key},
    )


async def _drive_suggestion_until_save_fails(
    gm_client, gm_ws, lyra, krieger, caelan,
    *,
    max_iters: int = 20,
):
    """Cast Suggestion at Krieger from Lyra; loop until the Wis save
    fails. Returns the /roll_request/{id}/respond JSON for the matched
    iteration. Re-seeds the battle each iteration (so AoD condition
    state and rolling-rest state reset cleanly).
    """
    base_combatants = [
        _make_combatant(lyra["name"], lyra["id"], init=12, hp=40),
        _make_combatant(krieger["name"], krieger["id"], init=8, hp=75),
        _make_combatant(caelan["name"], caelan["id"], init=10),
    ]
    target_tok = f"tok_range_{krieger['id']}"
    for _ in range(max_iters):
        await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/character/{lyra['id']}/rest",
            json={"type": "long"},
        )
        await _clear_buff(gm_client, krieger["id"], "charmed")
        await _seed_battle(gm_client, base_combatants)
        gm_ws.mark()
        cast_resp = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
            json={
                "character_id": lyra["id"],
                "spell_index": SUGGESTION_INDEX,
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
        assert isinstance(pending_id, int) and pending_id > 0, (
            f"expected auto_save_prompt_id; got {cast_data}"
        )
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/roll_request/{pending_id}/respond",
            json={"character_id": krieger["id"]},
        )
        assert r.status_code == 200, r.text
        rdata = r.json()
        if rdata.get("total", 0) < cast_data.get("auto_save_dc", 99):
            return rdata
    raise AssertionError(
        f"could not land a Suggestion save-fail on Krieger in {max_iters} tries"
    )


async def test_aura_of_devotion_blocks_when_paladin_within_10_ft(
    gm_client, gm_ws, roster, lyra_rested,
):
    """Caelan placed 5 ft from Krieger (1 cell = 70 px = 5 ft) →
    AoD range gate passes → Charmed install blocked AND broadcast
    fires.
    """
    lyra = lyra_rested
    krieger = roster["Krieger Stonefist"]
    caelan = roster["Sir Caelan Lightbringer"]

    # Place Caelan and Krieger on the active map 1 cell apart (5 ft).
    await _place_token(gm_client, caelan["id"], 350.0, 350.0)
    await _place_token(gm_client, krieger["id"], 420.0, 350.0)

    try:
        rdata = await _drive_suggestion_until_save_fails(
            gm_client, gm_ws, lyra, krieger, caelan,
        )
        assert rdata.get("auto_buff_installed", "") == "", (
            f"AoD should block Charmed when Caelan is in 10 ft range; "
            f"got auto_buff_installed={rdata.get('auto_buff_installed')!r}"
        )
        aod_msgs = _aod_broadcasts(gm_ws, caelan["id"])
        assert aod_msgs, (
            f"expected aura-of-devotion broadcast at 5 ft range; "
            f"buffered: {[(m.get('type'), (m.get('data') or {}).get('source')) for m in gm_ws.buffered()]}"
        )
    finally:
        # Cleanup so subsequent aura tests get the no-token fallback.
        await _delete_token(gm_client, caelan["id"])
        await _delete_token(gm_client, krieger["id"])


async def test_aura_of_devotion_skips_when_paladin_outside_10_ft(
    gm_client, gm_ws, roster, lyra_rested,
):
    """Caelan placed 25 ft from Krieger (5 cells = 350 px = 25 ft) →
    AoD range gate skips → Charmed install proceeds normally AND no
    AoD broadcast.
    """
    lyra = lyra_rested
    krieger = roster["Krieger Stonefist"]
    caelan = roster["Sir Caelan Lightbringer"]

    # 5 cells = 25 ft, outside Lv 7 Devotion's 10 ft aura.
    await _place_token(gm_client, caelan["id"], 350.0, 350.0)
    await _place_token(gm_client, krieger["id"], 700.0, 350.0)

    try:
        rdata = await _drive_suggestion_until_save_fails(
            gm_client, gm_ws, lyra, krieger, caelan,
        )
        assert rdata.get("auto_buff_installed", "").lower() in {
            "charmed", "charmed (suggestion)",
        }, (
            f"AoD should NOT fire at 25 ft (outside 10 ft); Charmed should "
            f"install normally; got auto_buff_installed={rdata.get('auto_buff_installed')!r}"
        )
        aod_msgs = _aod_broadcasts(gm_ws, caelan["id"])
        assert not aod_msgs, (
            f"no AoD broadcast at 25 ft range; got: "
            f"{[(m.get('data') or {}).get('feature_name') for m in aod_msgs]}"
        )
    finally:
        # Cleanup: remove tokens + clear the installed Charmed buff
        # so the next test sees a fresh state.
        await _clear_buff(gm_client, krieger["id"], "charmed")
        await _delete_token(gm_client, caelan["id"])
        await _delete_token(gm_client, krieger["id"])
