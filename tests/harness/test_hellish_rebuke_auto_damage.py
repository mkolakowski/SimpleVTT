"""v2.446.0 — Hellish Rebuke auto-damage-roll + auto-apply.

Phase 2 #5 of ``docs/plans/cast-and-broadcast-tail.md``. Closes the
v2.71.0 filed "Auto-roll + auto-damage-to-attacker" gap on the
slot-based Hellish Rebuke reaction flow.

The v2.71.0 ship wired the spell-slot reaction-watcher branch but
left the damage roll + apply as "GM-narrated" — the broadcast
carried `damage_expr = (1+slot_level)d10` and the GM rolled +
applied manually. This commit rolls server-side and applies via
`_apply_damage_to_combatant` when the attacker's `combatant_id` is
in the reaction params (it always is for the standard damage_taken
trigger path).

RAW says the attacker makes a DEX save for half. This v1 applies
FULL damage; the save adjudication stays GM-narrated (the GM can
use `/undo_attack_damage` with the cast_id to halve the applied
damage if the attacker passes).

Tests:
  - Happy path: Krieger hits Magnus → Magnus casts Hellish Rebuke
    via the reaction → feature_used carries damage_total > 0,
    damage_applied > 0, and a damage_breakdown string.
  - The applied damage equals damage_total (full apply in v1).
"""
import asyncio

from .conftest import CAMPAIGN_ID


def _make_combatant(name, char_id, init=10, hp=40):
    return {
        "id": f"tok_hrd_{char_id}",
        "char_id": char_id,
        "name": name,
        "initiative": init,
        "hp_current": hp, "hp_max": hp,
        "buffs": [],
        "economy": {
            "action": False, "bonus": False,
            "reaction": False, "movement": 0,
        },
    }


async def _seed_battle(gm_client, combatants):
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={
            "combatants": combatants,
            "turn_index": 0,
            "round": 1,
            "active": True,
        },
    )


async def _set_auto_apply(gm_client, on: bool) -> None:
    """The damage_taken reaction prompt only fires when damage is
    actually applied. Re-toggle on entry so a long-running shared
    dev container doesn't have it off from a prior test."""
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
        f"/campaign/{CAMPAIGN_ID}/settings",
        data=form,
        follow_redirects=False,
    )


async def test_hellish_rebuke_rolls_and_applies_damage(
    gm_client, gm_ws, roster,
):
    """End-to-end: Krieger hits Magnus → reaction prompt fires →
    Magnus casts Hellish Rebuke → feature_used carries
    damage_total > 0 + damage_applied > 0 + damage_breakdown
    (vs. the legacy v2.71.0 broadcast that left them GM-rolled).
    """
    magnus = roster["Magnus Hexbinder"]
    krieger = roster["Krieger Stonefist"]
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{magnus['id']}/rest",
        json={"type": "long"},
    )
    await _set_auto_apply(gm_client, True)

    magnus_cid = f"tok_hrd_{magnus['id']}"
    krieger_cid = f"tok_hrd_{krieger['id']}"
    await _seed_battle(gm_client, [
        _make_combatant(krieger["name"], krieger["id"], init=12, hp=75),
        {
            "id": magnus_cid,
            "char_id": magnus["id"],
            "name": magnus["name"],
            "initiative": 10,
            "hp_current": 50, "hp_max": 50,
            "buffs": [],
            "economy": {
                "action": False, "bonus": False,
                "reaction": False, "movement": 0,
            },
        },
    ])
    await asyncio.sleep(0.15)
    gm_ws.mark()

    # Drive Krieger swings until a damage-applying hit lands.
    for _ in range(40):
        resp = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/attack",
            json={
                "character_id": krieger["id"],
                "attack_index": 0,
                "target_combatant_id": magnus_cid,
                "override": True,
                "override_range": True,
            },
        )
        if resp.status_code != 200:
            continue
        data = resp.json()
        if data.get("hit") and int(data.get("damage_applied") or 0) > 0:
            break
    else:
        raise AssertionError("no damage-applying hit landed in 40 swings")
    await asyncio.sleep(0.3)

    prompts = [
        m for m in gm_ws.buffered("reaction_prompt")
        if (m.get("data") or {}).get("watcher_char_id") == magnus["id"]
        and (m.get("data") or {}).get("trigger_event") == "damage_taken"
    ]
    assert prompts, "expected damage_taken reaction_prompt for Magnus"
    prompt_id = prompts[-1]["data"]["prompt_id"]

    gm_ws.mark()
    cast = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_reaction",
        json={
            "prompt_id": prompt_id,
            "reaction_key": "cast-hellish-rebuke",
            "watcher_char_id": magnus["id"],
        },
    )
    assert cast.status_code == 200, cast.text
    await asyncio.sleep(0.25)

    # feature_used(source=hellish-rebuke-cast) fires with the new
    # auto-damage fields.
    fu = [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "hellish-rebuke-cast"
        and (m.get("data") or {}).get("character_id") == magnus["id"]
    ]
    assert fu, "expected feature_used(source=hellish-rebuke-cast)"
    last = fu[-1]["data"]

    # v2.446.0 new fields:
    damage_total = int(last.get("damage_total") or 0)
    damage_applied = int(last.get("damage_applied") or 0)
    damage_breakdown = str(last.get("damage_breakdown") or "")

    # Magnus's slot is L3 → damage_dice = 1 + 3 = 4 → 4d10 = [4, 40].
    assert 4 <= damage_total <= 40, (
        f"damage_total should be 4d10 = [4, 40]; got {damage_total}"
    )
    assert damage_breakdown, (
        f"damage_breakdown should be non-empty; got {damage_breakdown!r}"
    )
    # v1: full damage is applied (no DEX save adjudicated server-side).
    assert damage_applied > 0, (
        f"damage_applied should be > 0 (the attacker takes damage); got "
        f"{damage_applied}"
    )
    # The applied damage should match damage_total in v1 (no save halving).
    assert damage_applied == damage_total, (
        f"v1 applies full damage; expected damage_applied=={damage_total}, "
        f"got {damage_applied}"
    )

    # Legacy fields still present.
    assert last.get("damage_expr") == "4d10"
    assert last.get("damage_type") == "fire"
