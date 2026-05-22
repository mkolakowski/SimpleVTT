"""Sleep wake-on-damage hook.

v2.49.61 — closes the v2.49.58 filed item. RAW Sleep: "each creature
affected by this spell falls unconscious until the spell ends, the
sleeper takes damage, or someone uses an action to shake or slap
the sleeper awake." This commit wires the damage-wakes-sleeper branch.

The hook lives in `_wake_sleeping_on_damage`, called from both
branches of `_apply_damage_to_combatant`. Scoped tightly to buffs
with `source_spell == "Sleep"`, so other Unconscious sources (a
future Power Word Knockout etc.) aren't accidentally cleared by
stray damage. Zero-damage hits (resistance reduced to 0) don't wake.

Tests:
  - NPC wake: bandit pre-seeded with Sleep-Unconscious buff;
    Krieger attacks → buff dropped + 🌅 log fires + battle_update
    broadcast.
  - PC wake: Magnus pre-seeded with Sleep-Unconscious buff; Krieger
    attacks with auto_apply_damage on → Unconscious dropped from
    Magnus's buff list (hub + sheet mirror) + 🌅 log fires.
  - Non-Sleep unconscious preserved: bandit pre-seeded with
    Unconscious buff that has NO `source_spell` field → attack does
    NOT remove the buff.
"""
import asyncio
import time
import pytest_asyncio

from .conftest import CAMPAIGN_ID


def _sleep_unconscious_buff(source_char_id: int) -> dict:
    """Buff dict matching what cast_sleep installs (v2.49.58)."""
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
        "effects": ["pre-seeded for wake-on-damage test"],
    }


def _generic_unconscious_buff() -> dict:
    """Buff dict for a non-Sleep Unconscious (e.g., a future knockout
    feature). No `source_spell == "Sleep"` → wake hook must skip."""
    return {
        "key": "unconscious",
        "name": "Unconscious",
        "icon": "💤",
        "duration_rounds": 10,
        "duration_max": 10,
        "concentration": False,
        "effects": ["pre-seeded — not from Sleep"],
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


@pytest_asyncio.fixture
async def auto_apply_on(gm_client):
    """Toggle auto_apply_damage on for the campaign — needed so /attack
    actually mutates HP on the target. Mirror of the fixture in
    test_attack_auto_damage.py."""
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
        "auto_apply_damage": "on",
    }
    await gm_client.post(
        f"/campaign/{CAMPAIGN_ID}/settings", data=form, follow_redirects=False,
    )
    yield
    form_off = {**form}
    form_off.pop("auto_apply_damage", None)
    await gm_client.post(
        f"/campaign/{CAMPAIGN_ID}/settings", data=form_off, follow_redirects=False,
    )


async def test_wake_on_damage_npc(gm_client, gm_ws, roster, auto_apply_on):
    """Bandit pre-seeded with Sleep-Unconscious buff. Krieger attacks
    → buff dropped + 🌅 log fires."""
    krieger = roster["Krieger Stonefist"]
    thalindra = roster["Thalindra Moonwhisper"]
    bandit_tmpl = await _bandit_template(gm_client)
    bandit_id = "tok_wake_npc"
    await _seed_battle(gm_client, [
        {
            "id": f"tok_wake_k_{krieger['id']}",
            "char_id": krieger["id"],
            "name": krieger["name"],
            "initiative": 10,
            "hp_current": 55, "hp_max": 55,
            "buffs": [],
            "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0},
        },
        {
            "id": bandit_id,
            "char_id": None,
            "token_template_id": bandit_tmpl["id"],
            "name": bandit_tmpl["name"],
            "initiative": 5,
            "hp_current": 50, "hp_max": 50,  # plenty of HP — won't die from one hit
            "buffs": [_sleep_unconscious_buff(thalindra["id"])],
            "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0},
        },
    ])
    gm_ws.mark()

    # Loop until the attack hits (auto_apply_damage requires hit) AND
    # damage is applied. Krieger's first attack hits often vs a generic
    # bandit AC.
    saw_wake = False
    for _ in range(20):
        gm_ws.mark()
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/attack",
            json={
                "character_id": krieger["id"],
                "attack_index": 0,
                "target_combatant_id": bandit_id,
                "override": True,
            },
        )
        assert r.status_code == 200, r.text
        data = r.json()
        if not data.get("hit"):
            continue
        if (data.get("damage_applied") or 0) <= 0:
            continue
        # Two battle_update broadcasts arrive: (a) the damage broadcast
        # from _apply_damage_to_combatant, (b) the wake broadcast from
        # _wake_sleeping_on_damage. Poll for a broadcast where the
        # bandit no longer has the unconscious buff.
        deadline = time.monotonic() + 2.0
        bandit = None
        while time.monotonic() < deadline:
            updates = gm_ws.buffered("battle_update")
            if updates:
                # Use the LATEST broadcast (the wake one comes second).
                latest = updates[-1]
                combatants = (latest.get("data") or {}).get("combatants") or []
                bandit = next(
                    (c for c in combatants if c.get("id") == bandit_id), None,
                )
                if bandit is not None:
                    unconscious_buffs = [
                        b for b in (bandit.get("buffs") or [])
                        if (b or {}).get("key") == "unconscious"
                    ]
                    if not unconscious_buffs:
                        break
            await asyncio.sleep(0.05)
        assert bandit is not None, "no battle_update broadcast for bandit"
        unconscious_buffs = [
            b for b in (bandit.get("buffs") or [])
            if (b or {}).get("key") == "unconscious"
        ]
        assert not unconscious_buffs, (
            f"Sleep-Unconscious should be removed on damage; "
            f"latest battle_update buffs for bandit = {bandit.get('buffs')}"
        )
        # 🌅 wake log should fire.
        deadline = time.monotonic() + 2.0
        wake_logs: list = []
        while time.monotonic() < deadline:
            wake_logs = [
                m for m in gm_ws.buffered("roll")
                if "🌅" in ((m.get("data") or {}).get("note") or "")
            ]
            if wake_logs:
                break
            await asyncio.sleep(0.02)
        assert wake_logs, (
            f"expected 🌅 wake log; got "
            f"{[(m.get('data') or {}).get('note') for m in gm_ws.buffered('roll')]}"
        )
        saw_wake = True
        break

    assert saw_wake, "no hit + damage in 20 attempts — flaky env?"


async def test_wake_on_damage_pc(gm_client, gm_ws, roster, auto_apply_on):
    """Magnus pre-seeded with Sleep-Unconscious buff. Krieger attacks
    → Magnus's Unconscious buff dropped from BOTH hub state AND the
    sheet mirror + 🌅 log fires."""
    krieger = roster["Krieger Stonefist"]
    magnus = roster["Magnus Hexbinder"]
    thalindra = roster["Thalindra Moonwhisper"]

    # Reset Magnus state.
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
        {
            "id": f"tok_wake_k_{krieger['id']}",
            "char_id": krieger["id"],
            "name": krieger["name"],
            "initiative": 10,
            "hp_current": 55, "hp_max": 55,
            "buffs": [],
            "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0},
        },
        {
            "id": f"tok_wake_m_{magnus['id']}",
            "char_id": magnus["id"],
            "name": magnus["name"],
            "initiative": 9,
            "hp_current": 30, "hp_max": 30,
            "buffs": [_sleep_unconscious_buff(thalindra["id"])],
            "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0},
        },
    ])
    gm_ws.mark()

    saw_wake = False
    for _ in range(20):
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/attack",
            json={
                "character_id": krieger["id"],
                "attack_index": 0,
                "target_combatant_id": f"tok_wake_m_{magnus['id']}",
                "override": True,
            },
        )
        assert r.status_code == 200, r.text
        data = r.json()
        if not data.get("hit"):
            continue
        if (data.get("damage_applied") or 0) <= 0:
            continue
        # The wake hook should have fired via _remove_buff (PC path).
        # Poll the buffs endpoint until the Unconscious buff is gone.
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
        buffs_resp = b.json()
        hub_keys = [(bf or {}).get("key") for bf in buffs_resp.get("buffs", [])]
        sheet_keys = [(bf or {}).get("key") for bf in buffs_resp.get("sheet_buffs", [])]
        assert "unconscious" not in hub_keys, (
            f"Magnus's Unconscious should drop on damage (hub); got {hub_keys}"
        )
        assert "unconscious" not in sheet_keys, (
            f"Magnus's Unconscious should drop from sheet mirror too; "
            f"got {sheet_keys}"
        )
        deadline = time.monotonic() + 2.0
        wake_logs: list = []
        while time.monotonic() < deadline:
            wake_logs = [
                m for m in gm_ws.buffered("roll")
                if "🌅" in ((m.get("data") or {}).get("note") or "")
                and magnus["name"] in ((m.get("data") or {}).get("note") or "")
            ]
            if wake_logs:
                break
            await asyncio.sleep(0.02)
        assert wake_logs, (
            f"expected 🌅 wake log naming Magnus; got "
            f"{[(m.get('data') or {}).get('note') for m in gm_ws.buffered('roll')]}"
        )
        saw_wake = True
        break

    assert saw_wake, "no hit + damage in 20 attempts — flaky env?"


async def test_non_sleep_unconscious_preserved(gm_client, gm_ws, roster, auto_apply_on):
    """Bandit pre-seeded with a generic Unconscious buff that has NO
    `source_spell == "Sleep"`. Attack → damage applies BUT the buff
    must remain. Guards against the wake hook over-broadly clearing
    every Unconscious buff."""
    krieger = roster["Krieger Stonefist"]
    bandit_tmpl = await _bandit_template(gm_client)
    bandit_id = "tok_nowake_npc"
    await _seed_battle(gm_client, [
        {
            "id": f"tok_nowake_k_{krieger['id']}",
            "char_id": krieger["id"],
            "name": krieger["name"],
            "initiative": 10,
            "hp_current": 55, "hp_max": 55,
            "buffs": [],
            "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0},
        },
        {
            "id": bandit_id,
            "char_id": None,
            "token_template_id": bandit_tmpl["id"],
            "name": bandit_tmpl["name"],
            "initiative": 5,
            "hp_current": 50, "hp_max": 50,
            "buffs": [_generic_unconscious_buff()],
            "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0},
        },
    ])

    saw_hit = False
    for _ in range(20):
        gm_ws.mark()
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/attack",
            json={
                "character_id": krieger["id"],
                "attack_index": 0,
                "target_combatant_id": bandit_id,
                "override": True,
            },
        )
        assert r.status_code == 200, r.text
        data = r.json()
        if not data.get("hit"):
            continue
        if (data.get("damage_applied") or 0) <= 0:
            continue
        saw_hit = True
        break
    assert saw_hit, "no hit + damage in 20 attempts — flaky env?"

    # Pull the latest battle_update from the WS to inspect the bandit's
    # current buff list. The wake hook would have broadcast a SECOND
    # battle_update if it triggered; we expect ONLY the damage broadcast
    # because the buff isn't a Sleep-sourced unconscious.
    bandit = None
    deadline = time.monotonic() + 1.0
    while time.monotonic() < deadline:
        updates = gm_ws.buffered("battle_update")
        if updates:
            latest = updates[-1]
            combatants = (latest.get("data") or {}).get("combatants") or []
            bandit = next((c for c in combatants if c.get("id") == bandit_id), None)
            if bandit is not None:
                break
        await asyncio.sleep(0.05)
    assert bandit is not None, "no battle_update broadcast for bandit"
    unconscious_buffs = [
        b for b in (bandit.get("buffs") or [])
        if (b or {}).get("key") == "unconscious"
    ]
    assert unconscious_buffs, (
        f"non-Sleep Unconscious should be preserved on damage; "
        f"got {bandit.get('buffs')}"
    )
    # And the source_spell shouldn't have spontaneously become 'Sleep'.
    assert unconscious_buffs[0].get("source_spell") != "Sleep"
