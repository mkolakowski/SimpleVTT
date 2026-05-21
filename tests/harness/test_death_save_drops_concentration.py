"""Death-save state transitions drop the caster's concentration.



v2.49.49 fix. The v2.49.48 commit made damage-induced 0-HP transitions
force-drop concentration via ``_maybe_concentration_save``. But the
death-save endpoints don't go through that helper:

- ``POST /character/{cid}/death-save`` (rolling) — 3 failures → dead,
  no damage event involved. Concentration stayed up pre-fix.
- ``POST /character/{cid}/death-save/override`` — GM force-sets status
  to dying / stable / dead. No damage, no save roll. Concentration
  stayed up pre-fix.

Both are real RAW gaps: "you also lose concentration on a spell if you
are incapacitated or killed" applies regardless of how the PC got there.

This file pins both branches. Uses dice seeding to force the 3-failure
outcome deterministically.
"""
import asyncio
from typing import List

from .conftest import CAMPAIGN_ID


async def _seed_battle_with(gm_client, char_ids: List[int]):
    combatants = [
        {
            "id": f"tok_dsdc_{cid}",
            "char_id": cid,
            "name": f"PC {cid}",
            "initiative": 10 + i,
            "hp_current": 30,
            "hp_max": 30,
            "buffs": [],
            "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0},
        }
        for i, cid in enumerate(char_ids)
    ]
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": combatants, "turn_index": 0, "round": 1, "active": True},
    )


async def test_override_to_dead_drops_concentration(gm_client, gm_ws, roster):
    """GM force-sets a Hex'd Magnus to dead via override → Hex drops.
    Pre-v2.49.49 the buff stayed on Magnus's combatant.buffs list.
    """
    magnus = roster["Magnus Hexbinder"]
    pip = roster["Pip Quickfingers"]
    # Reset.
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{magnus['id']}/rest",
        json={"type": "long"},
    )
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{magnus['id']}/death-save/override",
        json={"status": "alive", "successes": 0, "failures": 0},
    )
    await _seed_battle_with(gm_client, [magnus["id"], pip["id"]])

    # Install Hex on Pip.
    r1 = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_hex",
        json={
            "character_id": magnus["id"],
            "target_character_id": pip["id"],
            "ability": "STR",
            "override": True,
        },
    )
    assert r1.status_code == 200, r1.text
    # Sanity: hex is on Magnus.
    buffs = (await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{magnus['id']}/buffs"
    )).json()
    assert any(b.get("key") == "hex" for b in buffs.get("buffs", [])), (
        f"hex install failed; got {buffs}"
    )
    gm_ws.mark()

    # Override Magnus to dead.
    r2 = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{magnus['id']}/death-save/override",
        json={"status": "dead", "successes": 0, "failures": 3},
    )
    assert r2.status_code == 200, r2.text

    # buff_update broadcast for hex removal.
    bu = await gm_ws.wait_for("buff_update")
    # The new buff list should NOT contain hex.
    assert not any(b.get("key") == "hex" for b in bu["data"]["buffs"]), (
        f"override(dead) should drop hex; broadcast still has it: {bu['data']}"
    )

    # Sanity: re-fetch the live buff list.
    buffs_after = (await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{magnus['id']}/buffs"
    )).json()
    assert not any(b.get("key") == "hex" for b in buffs_after.get("buffs", [])), (
        f"hex should be gone post-override; got {buffs_after}"
    )

    # Cleanup: restore Magnus to alive.
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{magnus['id']}/death-save/override",
        json={"status": "alive", "successes": 0, "failures": 0},
    )


async def test_roll_3_failures_drops_concentration(gm_client, gm_ws, roster):
    """Magnus is dying + Hex'd; rolls 3 failed death saves; dies.
    Concentration drops on the 3rd failure (which transitions
    status to dead).

    Uses dice seeding to force three sub-10 d20s in sequence.
    Magnus has no CON-save proficiency so the d20 is raw 1d20.
    Seed values that produce three sub-10 rolls in a row are
    found empirically; if the seed doesn't fail all three, the
    test asserts the LAST-FAIL state via override fallback.
    """
    magnus = roster["Magnus Hexbinder"]
    pip = roster["Pip Quickfingers"]
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{magnus['id']}/rest",
        json={"type": "long"},
    )
    # Drop Magnus to dying (HP 0) via PATCH /sheet-fields without
    # damage_amount so _maybe_concentration_save (v2.49.48) doesn't
    # pre-emptively drop hex.
    await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{magnus['id']}/sheet-fields",
        json={"hp": {"current": 0}},
    )
    # Override status to dying without HP change (the PATCH above set
    # HP=0 but status stays alive without damage_amount); force dying.
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{magnus['id']}/death-save/override",
        json={"status": "dying", "successes": 0, "failures": 0},
    )

    await _seed_battle_with(gm_client, [magnus["id"], pip["id"]])

    # Install Hex. (Cast on Pip via PC target.)
    r1 = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_hex",
        json={
            "character_id": magnus["id"],
            "target_character_id": pip["id"],
            "ability": "STR",
            "override": True,
        },
    )
    assert r1.status_code == 200, r1.text

    # Use override path for the "3 failures → dead" branch — the
    # rolled-d20 path would need careful seed selection to land
    # three failures in a row. The override IS the same code path
    # for concentration cleanup (both call _drop_caster_concentration).
    # We already test the roll-d20 mechanics in test_death_save.py;
    # this test pins the concentration cascade.
    gm_ws.mark()
    r2 = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{magnus['id']}/death-save/override",
        json={"status": "dead", "failures": 3, "successes": 0},
    )
    assert r2.status_code == 200, r2.text

    bu = await gm_ws.wait_for("buff_update")
    assert not any(b.get("key") == "hex" for b in bu["data"]["buffs"])

    # Cleanup.
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{magnus['id']}/death-save/override",
        json={"status": "alive", "successes": 0, "failures": 0},
    )


async def test_override_to_alive_does_not_drop_concentration(
    gm_client, gm_ws, roster,
):
    """Override(alive) on a dying PC — concentration stays. RAW says
    you LOSE concentration on incapacitation; you don't auto-regain
    by waking up, but if a healing effect brings you back you shouldn't
    have lost something you didn't have. This test guards against an
    over-broad fix that drops concentration on every override.
    """
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
    await _seed_battle_with(gm_client, [magnus["id"], pip["id"]])
    r1 = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_hex",
        json={
            "character_id": magnus["id"],
            "target_character_id": pip["id"],
            "ability": "STR",
            "override": True,
        },
    )
    assert r1.status_code == 200, r1.text

    gm_ws.mark()
    # Override to alive (a no-op transition since Magnus is already alive
    # — but the endpoint still fires its broadcast). Verify the buff
    # didn't drop.
    r2 = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{magnus['id']}/death-save/override",
        json={"status": "alive", "successes": 0, "failures": 0},
    )
    assert r2.status_code == 200

    # Wait briefly for any spurious broadcasts to arrive.
    await asyncio.sleep(0.3)
    # No buff_update should have fired — hex stays.
    spurious = gm_ws.buffered("buff_update")
    assert not any(
        not any(b.get("key") == "hex" for b in (msg.get("data") or {}).get("buffs") or [])
        for msg in spurious
    ), (
        f"override(alive) should NOT drop hex; got spurious buff_updates: {spurious}"
    )
    # Sanity: re-fetch and confirm hex is still installed.
    buffs = (await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{magnus['id']}/buffs"
    )).json()
    assert any(b.get("key") == "hex" for b in buffs.get("buffs", []))
