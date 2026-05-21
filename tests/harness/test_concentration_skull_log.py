"""GM-only roll-log entry distinguishes 💀 incapacitation from 💔 failed save.

v2.49.50 — UI distinction filed in v2.49.48. Pre-fix, every concentration
drop emitted the same "💔 NAME lost concentration on SPELL" log
regardless of cause. RAW lumps three causes together (failed CON save,
dropped to 0 HP, incapacitated by death-save / GM override) but the GM
log was muddling them. Fix splits the emoji + breakdown text:

  - 💔 = failed CON save (rolled, didn't hit DC)
  - 💀 = incapacitated (0 HP forced drop, 3 failed death saves, or GM
        override to a non-alive state)

The broadcast shape is otherwise unchanged — clients that filter on
``visibility=gm_only`` + ``type=roll`` continue to work. The note text
is what carries the cause distinction.

Tests:
  - 0-HP damage drop emits the 💀 variant with breakdown naming the
    cause (incapacitated, 0 HP).
  - GM override to status=dead emits the 💀 variant with breakdown
    naming the override reason.
  - 3-failures override (failures=3, status=dead) emits same.
  - High-damage non-0-HP failed save still emits the 💔 variant
    (regression guard — don't over-correct).
"""
import asyncio
from typing import List

from .conftest import CAMPAIGN_ID


async def _seed_battle_with(gm_client, chars: List[dict]):
    """Seed battle. ``chars`` is a list of dicts with ``id`` + ``name``
    keys (the harness roster entries). Names are propagated to the
    combatants so the GM log entries can name the caster correctly."""
    combatants = [
        {
            "id": f"tok_skull_{ch['id']}",
            "char_id": ch["id"],
            "name": ch["name"],
            "initiative": 10 + i,
            "hp_current": 30,
            "hp_max": 30,
            "buffs": [],
            "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0},
        }
        for i, ch in enumerate(chars)
    ]
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": combatants, "turn_index": 0, "round": 1, "active": True},
    )


async def _install_hex_on(gm_client, magnus_id: int, target_id: int):
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_hex",
        json={
            "character_id": magnus_id,
            "target_character_id": target_id,
            "ability": "STR",
            "override": True,
        },
    )
    assert r.status_code == 200, r.text


def _is_concentration_log(msg: dict) -> bool:
    if msg.get("type") != "roll":
        return False
    data = msg.get("data") or {}
    if data.get("visibility") != "gm_only":
        return False
    note = data.get("note") or ""
    return "lost concentration" in note.lower()


async def _wait_for_concentration_log(gm_ws, timeout: float = 3.0) -> dict:
    """Like wait_for('roll') but filters specifically for the
    concentration GM log entry (matched on note text). Useful because
    other ``roll``-type messages may be in flight."""
    import time
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        for m in gm_ws.buffered():
            if _is_concentration_log(m):
                return m
        await asyncio.sleep(0.02)
    raise AssertionError(
        f"No concentration GM log within {timeout}s. "
        f"Buffered: {[(m.get('type'), (m.get('data') or {}).get('note', '')[:40]) for m in gm_ws.buffered()]}"
    )


async def test_zero_hp_forced_drop_emits_skull_log(gm_client, gm_ws, roster):
    """Damage drops Magnus to 0 HP → 💀 log with 'incapacitated (0 HP)'
    in breakdown. Pre-v2.49.50 this emitted 💔 as if it was a failed
    save, which misled the GM (the save might have rolled a 20)."""
    magnus = roster["Magnus Hexbinder"]
    pip = roster["Pip Quickfingers"]
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{magnus['id']}/rest",
        json={"type": "long"},
    )
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{magnus['id']}/death-save/override",
        json={"status": "alive", "successes": 0, "failures": 0},
    )
    await _seed_battle_with(gm_client, [magnus, pip])
    await _install_hex_on(gm_client, magnus["id"], pip["id"])
    gm_ws.mark()

    resp = await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{magnus['id']}/sheet-fields",
        json={
            "hp": {"current": 0},
            "hp_change_reason": "damage",
            "damage_amount": 15,
        },
    )
    assert resp.status_code == 200, resp.text

    log = await _wait_for_concentration_log(gm_ws)
    note = log["data"]["note"]
    breakdown = log["data"]["breakdown"]
    assert note.startswith("💀"), (
        f"0-HP forced drop should emit 💀 not 💔; got note={note!r}"
    )
    assert "incapacitated" in breakdown.lower(), (
        f"breakdown should mention 'incapacitated'; got {breakdown!r}"
    )
    assert "0 hp" in breakdown.lower(), (
        f"breakdown should mention '0 HP' for forced-drop branch; got {breakdown!r}"
    )
    # The breakdown still shows what the d20 was for telemetry parity
    # ("save would have been …").
    assert "would have been" in breakdown.lower(), (
        f"breakdown should still surface the rolled save for telemetry; got {breakdown!r}"
    )
    assert "hex" in note.lower()


async def test_failed_con_save_still_emits_heart_log(gm_client, gm_ws, roster):
    """Damage that doesn't drop to 0 + CON save fails → 💔 log unchanged.
    Regression guard: don't over-broaden the v2.49.50 fix and turn
    all drops into 💀.

    Uses a retry loop because the d20 result is random; we need at
    least one failed save in the loop to assert on the 💔 log.
    """
    rowan = roster["Rowan Quickbow"]
    pip = roster["Pip Quickfingers"]
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{rowan['id']}/rest",
        json={"type": "long"},
    )
    await _seed_battle_with(gm_client, [rowan, pip])

    saw_heart_log = False
    for _ in range(15):
        # Top Rowan up + reinstall the mark each loop iteration.
        await gm_client.patch(
            f"/api/campaign/{CAMPAIGN_ID}/character/{rowan['id']}/sheet-fields",
            json={"hp": {"current": 44}},
        )
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

        # 30 damage → HP 14 (not 0). DC = max(10, 15) = 15.
        # Rowan's CON mod is low; failures are common.
        await gm_client.patch(
            f"/api/campaign/{CAMPAIGN_ID}/character/{rowan['id']}/sheet-fields",
            json={
                "hp": {"current": 14},
                "hp_change_reason": "damage",
                "damage_amount": 30,
            },
        )
        cs = await gm_ws.wait_for("concentration_save")
        # The non-0-HP branch sets forced_drop_on_zero_hp=False always.
        assert cs["data"]["forced_drop_on_zero_hp"] is False
        if cs["data"]["passed"]:
            continue
        log = await _wait_for_concentration_log(gm_ws)
        note = log["data"]["note"]
        breakdown = log["data"]["breakdown"]
        assert note.startswith("💔"), (
            f"failed CON save (not 0 HP) should keep the 💔 log; "
            f"got note={note!r} (regression: over-broad v2.49.50 fix?)"
        )
        assert "✗ failed" in breakdown.lower() or "failed" in breakdown.lower(), (
            f"failed-save breakdown should say so; got {breakdown!r}"
        )
        saw_heart_log = True
        break
    assert saw_heart_log, "no concentration failure in 15 attempts — flaky env?"


async def test_override_to_dead_emits_skull_log(gm_client, gm_ws, roster):
    """GM force-overrides Magnus → dead while Hex'd → 💀 log with
    ``GM override → dead`` in the breakdown."""
    magnus = roster["Magnus Hexbinder"]
    pip = roster["Pip Quickfingers"]
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{magnus['id']}/rest",
        json={"type": "long"},
    )
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{magnus['id']}/death-save/override",
        json={"status": "alive", "successes": 0, "failures": 0},
    )
    await _seed_battle_with(gm_client, [magnus, pip])
    await _install_hex_on(gm_client, magnus["id"], pip["id"])
    gm_ws.mark()

    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{magnus['id']}/death-save/override",
        json={"status": "dead", "successes": 0, "failures": 3},
    )
    assert r.status_code == 200, r.text

    log = await _wait_for_concentration_log(gm_ws)
    note = log["data"]["note"]
    breakdown = log["data"]["breakdown"]
    assert note.startswith("💀"), f"override→dead should emit 💀; got {note!r}"
    assert magnus["name"].split()[0] in note, f"caster name missing from note; got {note!r}"
    assert "hex" in note.lower()
    assert "gm override" in breakdown.lower(), (
        f"breakdown should name the cause; got {breakdown!r}"
    )
    assert "dead" in breakdown.lower(), (
        f"breakdown should include target status; got {breakdown!r}"
    )

    # Cleanup
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{magnus['id']}/death-save/override",
        json={"status": "alive", "successes": 0, "failures": 0},
    )


async def test_roll_3_failures_emits_skull_log(gm_client, gm_ws, roster):
    """``roll_death_save`` → ``_drop_caster_concentration`` uses
    reason='3 failed death saves' (distinct from the override path's
    reason). Verify the breakdown carries that string.

    Magnus has no CON-save proficiency so P(d20 fail) ≈ 45%. Retry
    loop: reset to dying/2-failures + reinstall hex each iteration;
    a failure on the next /death-save flips status→dead and triggers
    the helper. 15 attempts ≈ 99.99% success.
    """
    magnus = roster["Magnus Hexbinder"]
    pip = roster["Pip Quickfingers"]
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{magnus['id']}/rest",
        json={"type": "long"},
    )
    await _seed_battle_with(gm_client, [magnus, pip])

    saw_log = False
    for _ in range(15):
        # Reset Magnus: HP 0 + dying + 2 failures + Hex installed.
        await gm_client.patch(
            f"/api/campaign/{CAMPAIGN_ID}/character/{magnus['id']}/sheet-fields",
            json={"hp": {"current": 0}},
        )
        await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/character/{magnus['id']}/death-save/override",
            json={"status": "dying", "successes": 0, "failures": 2},
        )
        await _install_hex_on(gm_client, magnus["id"], pip["id"])
        gm_ws.mark()

        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/character/{magnus['id']}/death-save",
            json={},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        if body.get("status") != "dead":
            continue
        log = await _wait_for_concentration_log(gm_ws)
        note = log["data"]["note"]
        breakdown = log["data"]["breakdown"]
        assert note.startswith("💀"), f"roll→dead should emit 💀; got {note!r}"
        assert "hex" in note.lower()
        assert "death save" in breakdown.lower(), (
            f"roll-driven branch should name 'death saves' in breakdown; got {breakdown!r}"
        )
        saw_log = True
        break
    assert saw_log, "Magnus didn't die in 15 forced-failure attempts — flaky env?"

    # Cleanup
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{magnus['id']}/death-save/override",
        json={"status": "alive", "successes": 0, "failures": 0},
    )
