"""Shake-awake action endpoint (the third RAW Sleep wake branch).

v2.49.62 — closes the v2.49.61 filed "wake-via-shake" item. RAW Sleep:
"each creature affected by this spell falls unconscious until the
spell ends, the sleeper takes damage, or someone uses an action to
shake or slap the sleeper awake." This endpoint covers branch three;
the damage branch shipped in v2.49.61.

Endpoint: ``POST /api/campaign/{cid}/shake_awake``. Any class can
shake — RAW "someone" — but it costs an action and the target must
have a Sleep-sourced Unconscious buff (key=`unconscious`,
source_spell=`Sleep`). Other Unconscious sources (dying at 0 HP,
future knockout features) aren't in scope; shaking a dying PC won't
wake them.

Tests:
  - NPC wake: bandit pre-seeded with Sleep-Unconscious; Pip shakes →
    buff removed + 🤚 log fires + action chip burned.
  - PC wake: Magnus pre-seeded with Sleep-Unconscious; Pip shakes →
    Unconscious dropped from hub AND sheet mirror + 🤚 log names
    both shaker + target.
  - 409 not_asleep: target with no Sleep-Unconscious → 409 error.
  - 409 not_asleep on generic Unconscious: target has Unconscious
    but no source_spell=Sleep → still 409 (regression guard;
    shaking a dying creature isn't a wake).
"""
import asyncio
import time
import pytest_asyncio

from .conftest import CAMPAIGN_ID


def _sleep_unconscious_buff(source_char_id: int) -> dict:
    return {
        "key": "unconscious",
        "name": "Unconscious (Sleep)",
        "icon": "💤",
        "source_char_id": source_char_id,
        "source_char_name": "Thalindra Moonwhisper",
        "source_spell": "Sleep",
        "duration_rounds": 10,
        "duration_max": 10,
        "concentration": False,
        "effects": ["pre-seeded for shake-awake test"],
    }


def _generic_unconscious_buff() -> dict:
    return {
        "key": "unconscious",
        "name": "Unconscious",
        "icon": "💤",
        "duration_rounds": 10,
        "duration_max": 10,
        "concentration": False,
        "effects": ["pre-seeded — not Sleep"],
    }


async def _seed_battle(gm_client, combatants):
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": combatants, "turn_index": 0, "round": 1, "active": True},
    )


async def _bandit_template(gm_client):
    r = await gm_client.get(f"/api/campaign/{CAMPAIGN_ID}/templates")
    templates = r.json()
    return next((t for t in templates if "bandit" in t["name"].lower()), templates[0])


def _pc(char, tid_prefix: str, hp: int = 30, init: int = 10, buffs=None):
    return {
        "id": f"{tid_prefix}_{char['id']}",
        "char_id": char["id"],
        "name": char["name"],
        "initiative": init,
        "hp_current": hp,
        "hp_max": max(hp, 30),
        "buffs": buffs or [],
        "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0},
    }


async def test_shake_awake_npc(gm_client, gm_ws, roster):
    """Bandit pre-seeded with Sleep-Unconscious. Pip shakes the bandit
    awake → buff dropped + 🤚 log + action chip burned."""
    pip = roster["Pip Quickfingers"]
    thalindra = roster["Thalindra Moonwhisper"]
    bandit_tmpl = await _bandit_template(gm_client)
    bandit_id = "tok_shake_npc"
    await _seed_battle(gm_client, [
        _pc(pip, "tok_shake_pip"),
        {
            "id": bandit_id,
            "char_id": None,
            "token_template_id": bandit_tmpl["id"],
            "name": bandit_tmpl["name"],
            "initiative": 5,
            "hp_current": 11, "hp_max": 11,
            "buffs": [_sleep_unconscious_buff(thalindra["id"])],
            "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0},
        },
    ])
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/shake_awake",
        json={
            "character_id": pip["id"],
            "target_combatant_id": bandit_id,
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
    assert body["action_used"] is True
    assert body["buffs_removed"] == 1

    # Latest battle_update broadcast should show the bandit without
    # the Unconscious buff.
    bandit = None
    deadline = time.monotonic() + 2.0
    while time.monotonic() < deadline:
        updates = gm_ws.buffered("battle_update")
        if updates:
            latest = updates[-1]
            combatants = (latest.get("data") or {}).get("combatants") or []
            bandit = next((c for c in combatants if c.get("id") == bandit_id), None)
            if bandit is not None:
                unconscious_buffs = [
                    b for b in (bandit.get("buffs") or [])
                    if (b or {}).get("key") == "unconscious"
                ]
                if not unconscious_buffs:
                    break
        await asyncio.sleep(0.05)
    assert bandit is not None
    unconscious_buffs = [
        b for b in (bandit.get("buffs") or [])
        if (b or {}).get("key") == "unconscious"
    ]
    assert not unconscious_buffs, (
        f"Sleep-Unconscious should be removed; got {bandit.get('buffs')}"
    )

    # 🤚 wake log entry.
    wake_logs = [
        m for m in gm_ws.buffered("roll")
        if "🤚" in ((m.get("data") or {}).get("note") or "")
    ]
    assert wake_logs, (
        f"expected 🤚 wake log; got "
        f"{[(m.get('data') or {}).get('note') for m in gm_ws.buffered('roll')]}"
    )
    note = (wake_logs[0].get("data") or {}).get("note") or ""
    assert pip["name"] in note, f"log should name Pip; got {note!r}"
    assert bandit_tmpl["name"] in note, f"log should name bandit; got {note!r}"


async def test_shake_awake_pc(gm_client, gm_ws, roster):
    """Magnus pre-seeded with Sleep-Unconscious. Pip shakes → Magnus's
    Unconscious dropped from BOTH hub and sheet mirror."""
    pip = roster["Pip Quickfingers"]
    magnus = roster["Magnus Hexbinder"]
    thalindra = roster["Thalindra Moonwhisper"]

    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{magnus['id']}/rest",
        json={"type": "long"},
    )
    for k in ("unconscious", "hex"):
        await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/end_buff",
            json={"character_id": magnus["id"], "key": k},
        )

    await _seed_battle(gm_client, [
        _pc(pip, "tok_shake_pip"),
        _pc(magnus, "tok_shake_m", hp=30,
            buffs=[_sleep_unconscious_buff(thalindra["id"])]),
    ])
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/shake_awake",
        json={
            "character_id": pip["id"],
            "target_combatant_id": f"tok_shake_m_{magnus['id']}",
        },
    )
    assert r.status_code == 200, r.text
    assert r.json()["buffs_removed"] == 1

    # Hub + sheet mirror.
    deadline = time.monotonic() + 2.0
    while time.monotonic() < deadline:
        b = await gm_client.get(
            f"/api/campaign/{CAMPAIGN_ID}/character/{magnus['id']}/buffs"
        )
        keys = [(bf or {}).get("key") for bf in b.json().get("buffs", [])]
        if "unconscious" not in keys:
            break
        await asyncio.sleep(0.05)
    b = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{magnus['id']}/buffs"
    )
    resp = b.json()
    hub_keys = [(bf or {}).get("key") for bf in resp.get("buffs", [])]
    sheet_keys = [(bf or {}).get("key") for bf in resp.get("sheet_buffs", [])]
    assert "unconscious" not in hub_keys, (
        f"Magnus's Unconscious should drop (hub); got {hub_keys}"
    )
    assert "unconscious" not in sheet_keys, (
        f"Magnus's Unconscious should drop from sheet mirror; got {sheet_keys}"
    )

    wake_logs = [
        m for m in gm_ws.buffered("roll")
        if "🤚" in ((m.get("data") or {}).get("note") or "")
        and pip["name"] in ((m.get("data") or {}).get("note") or "")
        and magnus["name"] in ((m.get("data") or {}).get("note") or "")
    ]
    assert wake_logs, (
        f"expected 🤚 log naming both shaker + target; got "
        f"{[(m.get('data') or {}).get('note') for m in gm_ws.buffered('roll')]}"
    )


async def test_shake_awake_not_asleep_no_buff(gm_client, roster):
    """Target has no Unconscious buff at all → 409 not_asleep."""
    pip = roster["Pip Quickfingers"]
    bandit_tmpl = await _bandit_template(gm_client)
    bandit_id = "tok_shake_awake"
    await _seed_battle(gm_client, [
        _pc(pip, "tok_shake_pip"),
        {
            "id": bandit_id,
            "char_id": None,
            "token_template_id": bandit_tmpl["id"],
            "name": bandit_tmpl["name"],
            "initiative": 5,
            "hp_current": 11, "hp_max": 11,
            "buffs": [],
            "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0},
        },
    ])
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/shake_awake",
        json={
            "character_id": pip["id"],
            "target_combatant_id": bandit_id,
        },
    )
    assert r.status_code == 409, r.text
    err = r.json()
    assert err["error"] == "not_asleep"


async def test_shake_awake_not_asleep_non_sleep_unconscious(gm_client, roster):
    """Target has a generic Unconscious buff (no source_spell=Sleep) →
    409 not_asleep. RAW shake-awake is Sleep-specific; shaking a
    dying / knocked-out creature isn't a wake."""
    pip = roster["Pip Quickfingers"]
    bandit_tmpl = await _bandit_template(gm_client)
    bandit_id = "tok_shake_dying"
    await _seed_battle(gm_client, [
        _pc(pip, "tok_shake_pip"),
        {
            "id": bandit_id,
            "char_id": None,
            "token_template_id": bandit_tmpl["id"],
            "name": bandit_tmpl["name"],
            "initiative": 5,
            "hp_current": 11, "hp_max": 11,
            "buffs": [_generic_unconscious_buff()],
            "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0},
        },
    ])
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/shake_awake",
        json={
            "character_id": pip["id"],
            "target_combatant_id": bandit_id,
        },
    )
    assert r.status_code == 409, r.text
    err = r.json()
    assert err["error"] == "not_asleep"
