"""Monk Stunning Strike — class feature endpoint.

v2.49.55 — adds ``POST /api/campaign/{cid}/use_stunning_strike``.
Monk Lv 5+ class feature: spend 1 ki on a hit to force the target
to make a CON save or be Stunned until the end of the monk's next
turn. Save DC = 8 + monk prof + monk WIS mod.

The Stunned condition is concentration=False (1-turn duration, RAW)
— this commit exercises the v2.49.51 "incapacitating buff with
concentration=False" branch for NPCs via ``_install_buff_on_combatant_id``.
The PC roll_request path (added later, see PC integration test below)
exercises the same hook via ``_install_buff`` — concentration=False
incapacitating buff installed on a PC who is currently concentrating
on a spell of their own drops their anchor + emits the 💀 GM log.

Tests:
  - Happy path (NPC): Kael (Monk Lv 5) uses Stunning Strike on a
    bandit; loop until save fails; assert Stunned installed on the
    bandit + ki decremented by 1 + 200 response.
  - 409 wrong_class: Krieger (Barbarian) → 409 wrong_class.
  - 409 no_ki: drain Kael's ki to 0; → 409 no_ki + ki not consumed.
  - PC integration (v2.49.56): Magnus has Hex up. Kael uses Stunning
    Strike on Magnus → roll_request created. GM responds on Magnus's
    behalf; loop until save fails. Assert (a) Stunned installed on
    Magnus, (b) Magnus's Hex dropped (v2.49.51 hook on a
    concentration=False incapacitating buff via the PC /respond path),
    (c) 💀 GM log fired.
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID


@pytest_asyncio.fixture
async def kael_rested(gm_client, roster):
    """Long-rest Kael + reset any leftover buffs from prior tests."""
    kael = roster["Kael Brightleaf"]
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{kael['id']}/rest",
        json={"type": "long"},
    )
    return kael


async def _seed_battle(gm_client, combatants):
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": combatants, "turn_index": 0, "round": 1, "active": True},
    )


async def _bandit_template(gm_client):
    r = await gm_client.get(f"/api/campaign/{CAMPAIGN_ID}/templates")
    templates = r.json()
    return next((t for t in templates if "bandit" in t["name"].lower()), templates[0])


async def test_stunning_strike_happy_path_npc(gm_client, gm_ws, kael_rested):
    """Kael uses Stunning Strike on a bandit; retry until save fails;
    assert Stunned buff installed (concentration=False) + ki spent."""
    kael = kael_rested
    bandit_tmpl = await _bandit_template(gm_client)
    bandit_id = "tok_test_stun_bandit"

    saw_stun = False
    for _ in range(20):
        # Refill ki + reset combatants each iteration so we don't run
        # out of ki across the loop.
        await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/character/{kael['id']}/rest",
            json={"type": "long"},
        )
        await _seed_battle(gm_client, [
            {"id": f"tok_test_{kael['id']}", "char_id": kael["id"],
             "name": kael["name"], "initiative": 10,
             "hp_current": 30, "hp_max": 30, "buffs": [],
             "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0}},
            {"id": bandit_id, "char_id": None,
             "token_template_id": bandit_tmpl["id"],
             "name": bandit_tmpl["name"], "initiative": 7,
             "hp_current": 11, "hp_max": 11, "buffs": [],
             "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0}},
        ])
        gm_ws.mark()
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/use_stunning_strike",
            json={
                "character_id": kael["id"],
                "target_combatant_id": bandit_id,
            },
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["ok"] is True
        assert body["auto_save_target_kind"] == "npc"
        assert body["save_dc"] > 0
        assert body["ki_remaining"] >= 0
        # Server should have rolled.
        assert body["auto_save_rolled"] is not None
        assert body["auto_save_passed"] is not None
        if body["auto_save_passed"]:
            continue  # save passed — no buff installed
        assert body["auto_save_buff_installed"] == "Stunned"
        # Verify via the battle_update broadcast that _install_buff_on_combatant_id
        # fired with the right shape — Stunned with concentration=False.
        bu = await gm_ws.wait_for("battle_update", timeout=2.0)
        combatants = (bu.get("data") or {}).get("combatants") or []
        bandit = next(
            (c for c in combatants if c.get("id") == bandit_id), None,
        )
        assert bandit is not None, f"bandit missing in battle_update; got {combatants}"
        stunned_buffs = [
            b for b in (bandit.get("buffs") or [])
            if (b or {}).get("key") == "stunned"
        ]
        assert stunned_buffs, f"Stunned buff missing; got {bandit.get('buffs')}"
        assert stunned_buffs[0].get("concentration") is False, (
            f"Stunned should be concentration=False (RAW 1-turn condition); "
            f"got {stunned_buffs[0]}"
        )
        assert stunned_buffs[0].get("source_char_id") == kael["id"], (
            f"source_char_id should be the monk; got {stunned_buffs[0]}"
        )
        saw_stun = True
        break

    assert saw_stun, "no save failure in 20 attempts — flaky env?"


async def test_stunning_strike_wrong_class(gm_client, roster):
    """Krieger (Barbarian) tries Stunning Strike → 409 wrong_class."""
    krieger = roster["Krieger Stonefist"]
    bandit_tmpl = await _bandit_template(gm_client)
    bandit_id = "tok_test_stun_wrong"
    await _seed_battle(gm_client, [
        {"id": f"tok_test_{krieger['id']}", "char_id": krieger["id"],
         "name": krieger["name"], "initiative": 10,
         "hp_current": 55, "hp_max": 55, "buffs": [],
         "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0}},
        {"id": bandit_id, "char_id": None,
         "token_template_id": bandit_tmpl["id"],
         "name": bandit_tmpl["name"], "initiative": 7,
         "hp_current": 11, "hp_max": 11, "buffs": [],
         "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0}},
    ])
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_stunning_strike",
        json={
            "character_id": krieger["id"],
            "target_combatant_id": bandit_id,
        },
    )
    assert r.status_code == 409, r.text
    err = r.json()
    assert err["error"] == "wrong_class"
    assert err["expected"] == "monk"


async def test_stunning_strike_no_ki(gm_client, kael_rested):
    """Drain Kael's ki via repeated /use_stunning_strike (each costs 1).
    When ki_remaining hits 0, next attempt → 409 no_ki."""
    kael = kael_rested
    bandit_tmpl = await _bandit_template(gm_client)
    bandit_id = "tok_test_stun_noki"
    await _seed_battle(gm_client, [
        {"id": f"tok_test_{kael['id']}", "char_id": kael["id"],
         "name": kael["name"], "initiative": 10,
         "hp_current": 30, "hp_max": 30, "buffs": [],
         "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0}},
        {"id": bandit_id, "char_id": None,
         "token_template_id": bandit_tmpl["id"],
         "name": bandit_tmpl["name"], "initiative": 7,
         "hp_current": 11, "hp_max": 11, "buffs": [],
         "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0}},
    ])
    # Drain ki via the endpoint itself; the response carries
    # ki_remaining so we know when to stop.
    ki_remaining = None
    for _ in range(20):  # cap iterations defensively
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/use_stunning_strike",
            json={
                "character_id": kael["id"],
                "target_combatant_id": bandit_id,
            },
        )
        assert r.status_code == 200, r.text
        ki_remaining = r.json()["ki_remaining"]
        if ki_remaining == 0:
            break
    assert ki_remaining == 0, f"failed to drain ki in 20 iterations; got {ki_remaining}"

    # Now ki is 0; next call → 409 no_ki.
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_stunning_strike",
        json={
            "character_id": kael["id"],
            "target_combatant_id": bandit_id,
        },
    )
    assert r.status_code == 409, r.text
    err = r.json()
    assert err["error"] == "no_ki"
    assert err["available"] == 0


async def _buff_keys(gm_client, char_id: int) -> list[str]:
    r = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/buffs"
    )
    if r.status_code != 200:
        return []
    return [(b or {}).get("key") for b in r.json().get("buffs", [])]


async def _install_hex(gm_client, magnus_id: int, target_id: int):
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


async def test_stunning_strike_pc_drops_own_concentration(
    gm_client, gm_ws, kael_rested, roster,
):
    """v2.49.56 — closes the v2.49.55 filed item.

    Magnus is Hex'd (concentrating). Kael (Monk Lv 5) uses Stunning
    Strike on Magnus → roll_request prompts Magnus's CON save → on
    fail, /respond installs Stunned via ``_install_buff`` which fires
    the v2.49.51 incapacitation hook. Because Stunned is
    ``concentration: False``, the hook's "anchor still in new_list"
    branch runs — explicitly removes Magnus's Hex via ``_remove_buff``
    and emits a 💀 GM log naming the cause.

    This pins both (a) the PC roll_request → /respond → install path
    for a non-spell class-feature entry in ``_SPELL_CONDITION_MAP``
    and (b) the v2.49.51 concentration=False incapacitation branch
    end-to-end through the PC pipeline.

    Retry loop because Magnus's CON save outcome is random.
    """
    import asyncio
    import time

    kael = kael_rested
    magnus = roster["Magnus Hexbinder"]
    pip = roster["Pip Quickfingers"]

    saw_fix = False
    for _ in range(15):
        # Refill Kael's ki + reset Magnus's leftover state every loop.
        await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/character/{kael['id']}/rest",
            json={"type": "long"},
        )
        await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/character/{magnus['id']}/rest",
            json={"type": "long"},
        )
        for k in ("stunned", "hex"):
            await gm_client.post(
                f"/api/campaign/{CAMPAIGN_ID}/end_buff",
                json={"character_id": magnus["id"], "key": k},
            )
        await _seed_battle(gm_client, [
            {"id": f"tok_stun_{kael['id']}", "char_id": kael["id"],
             "name": kael["name"], "initiative": 10,
             "hp_current": 38, "hp_max": 38, "buffs": [],
             "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0}},
            {"id": f"tok_stun_{magnus['id']}", "char_id": magnus["id"],
             "name": magnus["name"], "initiative": 9,
             "hp_current": 30, "hp_max": 30, "buffs": [],
             "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0}},
            {"id": f"tok_stun_{pip['id']}", "char_id": pip["id"],
             "name": pip["name"], "initiative": 8,
             "hp_current": 30, "hp_max": 30, "buffs": [],
             "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0}},
        ])

        # Magnus casts Hex on Pip → Magnus is now concentrating.
        await _install_hex(gm_client, magnus["id"], pip["id"])
        pre_keys = await _buff_keys(gm_client, magnus["id"])
        assert "hex" in pre_keys, f"pre-cond: hex should be on magnus; got {pre_keys}"

        # Kael uses Stunning Strike on Magnus → roll_request flow.
        gm_ws.mark()
        cast_resp = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/use_stunning_strike",
            json={
                "character_id": kael["id"],
                "target_combatant_id": f"tok_stun_{magnus['id']}",
            },
        )
        assert cast_resp.status_code == 200, cast_resp.text
        body = cast_resp.json()
        assert body["auto_save_target_kind"] == "pc"
        assert body["auto_save_prompted"] is True
        prompt_id = body["auto_save_prompt_id"]
        assert isinstance(prompt_id, int) and prompt_id > 0

        # GM-as-Magnus responds.
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/roll_request/{prompt_id}/respond",
            json={"character_id": magnus["id"]},
        )
        assert r.status_code == 200, r.text
        if r.json().get("auto_buff_installed") != "Stunned":
            continue  # CON save passed; retry

        # Save failed: Stunned should land AND Hex should drop.
        post_keys = await _buff_keys(gm_client, magnus["id"])
        assert "stunned" in post_keys, (
            f"Stunned should land on Magnus; got {post_keys}"
        )
        assert "hex" not in post_keys, (
            f"Magnus's Hex should drop when stunned (v2.49.51 hook on a "
            f"concentration=False incapacitating buff); got {post_keys}"
        )

        # 💀 GM log entry should fire naming Hex as the dropped anchor.
        # Broadcast is async vs the HTTP return, so poll up to 2 s.
        deadline = time.monotonic() + 2.0
        skull_logs: list = []
        while time.monotonic() < deadline:
            skull_logs = [
                m for m in gm_ws.buffered("roll")
                if (m.get("data") or {}).get("visibility") == "gm_only"
                and "💀" in ((m.get("data") or {}).get("note") or "")
                and "hex" in ((m.get("data") or {}).get("note") or "").lower()
            ]
            if skull_logs:
                break
            await asyncio.sleep(0.02)
        assert skull_logs, (
            f"expected 💀 GM log for Magnus's Hex drop; got "
            f"{[(m.get('data') or {}).get('note') for m in gm_ws.buffered('roll')]}"
        )
        breakdown = (skull_logs[0].get("data") or {}).get("breakdown") or ""
        assert "incapacitated" in breakdown.lower(), (
            f"breakdown should name incapacitation cause; got {breakdown!r}"
        )
        assert "stunned" in breakdown.lower(), (
            f"breakdown should name the incapacitating buff; got {breakdown!r}"
        )
        saw_fix = True
        break

    assert saw_fix, "no save failure in 15 attempts — flaky env?"

    # Cleanup so subsequent tests start fresh.
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/end_buff",
        json={"character_id": magnus["id"], "key": "stunned"},
    )
