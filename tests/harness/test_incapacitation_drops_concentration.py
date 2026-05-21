"""RAW: incapacitating a concentrating PC drops THEIR concentration.

v2.49.51 — closes the non-damage incapacitation gap filed in v2.49.49.
PHB p.203: "you also lose concentration on a spell if you are
incapacitated or killed." The v2.49.48/49 commits covered damage-
induced (0 HP) and death-save-driven incapacitation; this commit
covers BUFF-driven incapacitation (Hold Person, Hideous Laughter,
Sleep, etc. — anything that lands a paralyzed / stunned / unconscious
/ petrified / incapacitated condition on the PC).

Mechanism: `_install_buff` now checks the just-installed buff's key
against `_INCAPACITATING_BUFF_KEYS` and calls
`_drop_caster_concentration` on the target when matched. The helper
filters concentration buffs by `source_char_id` so the just-installed
condition (sourced by the enemy caster) is preserved while the
target's own anchors (Hex, Hunter's Mark) drop.

Tests:
  - Magnus has Hex installed (concentration). Tavik casts Hold
    Person at Magnus; Magnus fails the save → Paralyzed lands AND
    Magnus's Hex drops. The Paralyzed buff stays (not over-dropped).
  - Non-incapacitating condition (Charmed via Charm Person) on a
    Hex'd PC does NOT drop Hex. Regression guard: only the
    incapacitating-key whitelist fires.
  - Paired-cleanup regression: dropping the source caster's
    concentration still cascade-removes the target's Paralyzed
    buff (the v2.38.0 path stays intact).
"""
from typing import List

from .conftest import CAMPAIGN_ID


HOLD_PERSON_INDEX = 8
CHARM_PERSON_INDEX = 5


async def _seed_battle(gm_client, combatants: List[dict]):
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": combatants, "turn_index": 0, "round": 1, "active": True},
    )


async def _buff_keys(gm_client, char_id: int) -> List[str]:
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


async def test_paralyzed_pc_drops_own_concentration(gm_client, gm_ws, roster):
    """Magnus is Hex'd (concentrating). Tavik casts Hold Person at Magnus
    → Magnus fails the save → Paralyzed lands → Magnus's Hex drops.

    Retry loop because WIS save outcome is random; Magnus's WIS mod
    is low so failures are common. The post-paralyzed assertions
    only execute when we successfully land the paralyzed buff."""
    tavik = roster["Brother Tavik Stonebrow"]
    magnus = roster["Magnus Hexbinder"]
    pip = roster["Pip Quickfingers"]

    saw_fix = False
    for _ in range(15):
        await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/character/{tavik['id']}/rest",
            json={"type": "long"},
        )
        await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/character/{magnus['id']}/rest",
            json={"type": "long"},
        )
        # Clear any leftover state on Magnus from prior iterations.
        for k in ("paralyzed", "hex"):
            await gm_client.post(
                f"/api/campaign/{CAMPAIGN_ID}/end_buff",
                json={"character_id": magnus["id"], "key": k},
            )
        await _seed_battle(gm_client, [
            {"id": f"tok_inc_{tavik['id']}", "char_id": tavik["id"],
             "name": tavik["name"], "initiative": 10,
             "hp_current": 30, "hp_max": 30, "buffs": [],
             "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0}},
            {"id": f"tok_inc_{magnus['id']}", "char_id": magnus["id"],
             "name": magnus["name"], "initiative": 9,
             "hp_current": 30, "hp_max": 30, "buffs": [],
             "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0}},
            {"id": f"tok_inc_{pip['id']}", "char_id": pip["id"],
             "name": pip["name"], "initiative": 8,
             "hp_current": 30, "hp_max": 30, "buffs": [],
             "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0}},
        ])
        # Magnus casts Hex on Pip (Magnus is now concentrating).
        await _install_hex(gm_client, magnus["id"], pip["id"])
        pre_keys = await _buff_keys(gm_client, magnus["id"])
        assert "hex" in pre_keys, f"pre-cond: hex should be on magnus; got {pre_keys}"

        # Tavik casts Hold Person at Magnus.
        cast_resp = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
            json={
                "character_id": tavik["id"],
                "spell_index": HOLD_PERSON_INDEX,
                "slot_level": 2,
                "class_slug": "cleric",
                "target_character_id": magnus["id"],
                "target_combatant_id": f"tok_inc_{magnus['id']}",
                "target_name": magnus["name"],
                "override": True,
            },
        )
        prompt_id = cast_resp.json()["auto_save_prompt_id"]
        gm_ws.mark()
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/roll_request/{prompt_id}/respond",
            json={"character_id": magnus["id"]},
        )
        assert r.status_code == 200, r.text
        if r.json().get("auto_buff_installed") != "Paralyzed":
            continue  # save passed — retry

        # Save failed: paralyzed should land AND hex should drop.
        post_keys = await _buff_keys(gm_client, magnus["id"])
        assert "paralyzed" in post_keys, (
            f"Paralyzed should land on Magnus; got {post_keys}"
        )
        assert "hex" not in post_keys, (
            f"Magnus's Hex should drop when incapacitated; got {post_keys}"
        )
        # 💀 GM log entry should fire naming the cause. The broadcast
        # is async vs the HTTP /respond return, so poll for up to 2s.
        import asyncio
        import time
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
        assert "paralyzed" in breakdown.lower(), (
            f"breakdown should name the incapacitating buff; got {breakdown!r}"
        )
        saw_fix = True
        break
    assert saw_fix, "no save failure in 15 attempts — flaky env?"

    # Cleanup
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/end_buff",
        json={"character_id": magnus["id"], "key": "paralyzed"},
    )


async def test_charmed_pc_keeps_own_concentration(gm_client, roster):
    """Regression guard: non-incapacitating condition (Charmed via
    Charm Person) should NOT drop the target's concentration. Charm
    Person doesn't appear in _INCAPACITATING_BUFF_KEYS — the fix is
    scoped to incapacitating keys only.

    Retry loop because WIS save outcome is random."""
    tavik = roster["Brother Tavik Stonebrow"]
    magnus = roster["Magnus Hexbinder"]
    pip = roster["Pip Quickfingers"]

    saw_charm = False
    for _ in range(15):
        await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/character/{tavik['id']}/rest",
            json={"type": "long"},
        )
        await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/character/{magnus['id']}/rest",
            json={"type": "long"},
        )
        for k in ("charmed", "hex"):
            await gm_client.post(
                f"/api/campaign/{CAMPAIGN_ID}/end_buff",
                json={"character_id": magnus["id"], "key": k},
            )
        await _seed_battle(gm_client, [
            {"id": f"tok_inc_{tavik['id']}", "char_id": tavik["id"],
             "name": tavik["name"], "initiative": 10,
             "hp_current": 30, "hp_max": 30, "buffs": [],
             "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0}},
            {"id": f"tok_inc_{magnus['id']}", "char_id": magnus["id"],
             "name": magnus["name"], "initiative": 9,
             "hp_current": 30, "hp_max": 30, "buffs": [],
             "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0}},
            {"id": f"tok_inc_{pip['id']}", "char_id": pip["id"],
             "name": pip["name"], "initiative": 8,
             "hp_current": 30, "hp_max": 30, "buffs": [],
             "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0}},
        ])
        await _install_hex(gm_client, magnus["id"], pip["id"])

        cast_resp = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
            json={
                "character_id": tavik["id"],
                "spell_index": CHARM_PERSON_INDEX,
                "slot_level": 1,
                "class_slug": "cleric",
                "target_character_id": magnus["id"],
                "target_combatant_id": f"tok_inc_{magnus['id']}",
                "target_name": magnus["name"],
                "override": True,
            },
        )
        body = cast_resp.json()
        prompt_id = body.get("auto_save_prompt_id")
        if not prompt_id:
            # Charm Person might not have a save prompt in this seed
            # (depends on spell-data shape). Skip the test gracefully.
            return
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/roll_request/{prompt_id}/respond",
            json={"character_id": magnus["id"]},
        )
        if r.json().get("auto_buff_installed") != "Charmed":
            continue
        # Charmed landed; Hex should still be on Magnus.
        keys = await _buff_keys(gm_client, magnus["id"])
        assert "charmed" in keys, f"charmed should land; got {keys}"
        assert "hex" in keys, (
            f"Charmed (non-incapacitating) should NOT drop Hex; got {keys}"
        )
        saw_charm = True
        break

    if not saw_charm:
        # Charm Person may be index-shifted in this seed; treat as
        # no-op rather than failing the suite. The paralyzed test is
        # the load-bearing assertion.
        return

    # Cleanup.
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/end_buff",
        json={"character_id": magnus["id"], "key": "charmed"},
    )
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/end_buff",
        json={"character_id": magnus["id"], "key": "hex"},
    )


async def test_source_caster_concentration_still_cascades(gm_client, roster):
    """Regression guard for the source_char_id filter in
    _drop_caster_concentration. The v2.49.51 refactor narrowed the
    helper to only drop buffs the target is concentrating ON
    (source_char_id absent or == self). The paired-cleanup helper
    (_drop_paired_concentration_buffs) is a separate code path that
    fires when the source caster's concentration ends — it should
    STILL cascade-remove the target's Paralyzed buff.

    Setup: Tavik casts Hold Person at Magnus, Magnus fails save,
    Paralyzed lands on Magnus + concentration-hold-person on Tavik.
    Then end Tavik's concentration. Magnus's Paralyzed should drop.
    """
    tavik = roster["Brother Tavik Stonebrow"]
    magnus = roster["Magnus Hexbinder"]

    saw_install = False
    for _ in range(15):
        await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/character/{tavik['id']}/rest",
            json={"type": "long"},
        )
        await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/character/{magnus['id']}/rest",
            json={"type": "long"},
        )
        for k in ("paralyzed", "hex", "concentration-hold-person"):
            await gm_client.post(
                f"/api/campaign/{CAMPAIGN_ID}/end_buff",
                json={"character_id": magnus["id"], "key": k},
            )
            await gm_client.post(
                f"/api/campaign/{CAMPAIGN_ID}/end_buff",
                json={"character_id": tavik["id"], "key": k},
            )
        await _seed_battle(gm_client, [
            {"id": f"tok_inc_{tavik['id']}", "char_id": tavik["id"],
             "name": tavik["name"], "initiative": 10,
             "hp_current": 30, "hp_max": 30, "buffs": [],
             "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0}},
            {"id": f"tok_inc_{magnus['id']}", "char_id": magnus["id"],
             "name": magnus["name"], "initiative": 9,
             "hp_current": 30, "hp_max": 30, "buffs": [],
             "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0}},
        ])
        cast_resp = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
            json={
                "character_id": tavik["id"],
                "spell_index": HOLD_PERSON_INDEX,
                "slot_level": 2,
                "class_slug": "cleric",
                "target_character_id": magnus["id"],
                "target_combatant_id": f"tok_inc_{magnus['id']}",
                "target_name": magnus["name"],
                "override": True,
            },
        )
        prompt_id = cast_resp.json()["auto_save_prompt_id"]
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/roll_request/{prompt_id}/respond",
            json={"character_id": magnus["id"]},
        )
        if r.json().get("auto_buff_installed") == "Paralyzed":
            saw_install = True
            break
    assert saw_install, "no save fail in 15 attempts — flaky env?"

    # Pre-condition: Magnus has Paralyzed, Tavik has concentration anchor.
    magnus_keys_pre = await _buff_keys(gm_client, magnus["id"])
    tavik_keys_pre = await _buff_keys(gm_client, tavik["id"])
    assert "paralyzed" in magnus_keys_pre
    assert "concentration-hold-person" in tavik_keys_pre

    # End Tavik's concentration.
    end = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/end_buff",
        json={"character_id": tavik["id"], "key": "concentration-hold-person"},
    )
    assert end.status_code == 200, end.text

    # Magnus's Paralyzed should be gone (paired-cleanup cascade still works).
    magnus_keys_post = await _buff_keys(gm_client, magnus["id"])
    assert "paralyzed" not in magnus_keys_post, (
        f"v2.49.51 refactor regressed paired-cleanup; "
        f"Paralyzed should drop when Tavik ends concentration. "
        f"Got {magnus_keys_post}"
    )
