"""v2.97.43 — Heroism Frightened immunity hook.

Closes one of the two v2.97.37-filed Heroism mechanical halves. The
``_pc_has_heroism_frightened_immunity`` helper walks the saver's
buffs for ``effects.condition_immunity_frightened`` (Heroism today;
future buffs with the same marker opt in by carrying the flag).
``/respond`` short-circuits the Frightened install when the marker
is present and emits a ``feature_used(source=heroism)`` broadcast
naming the protected target — same pre-install gate shape as the
v2.55.0 Aura of Devotion and v2.57.0 Mindless Rage gates.

Test flow:
- Lyra casts Heroism on Garrik (v2.97.31 walker installs the buff
  with ``effects.condition_immunity_frightened: True``).
- Lyra casts Fear (Bard L3, appended to her demo spell list in
  v2.97.43) on Garrik. Loop until Garrik fails the Wis save.
- Assert ``/respond`` returns ``auto_buff_installed == ""`` and the
  Heroism broadcast fires; Garrik's buffs should NOT include
  ``frightened``.

v2.99.16 — target swapped from Pip (Halfling) to Garrik (Variant
Human Fighter). The v2.99.14 Halfling Brave save advantage made
Pip's Wis save pass too often, starving the failed-save loop and
preventing the Heroism gate from firing. Garrik has no race trait
on Wis saves and a clean ~65% fail rate at DC 14.
"""
from .conftest import CAMPAIGN_ID


async def _long_rest(gm_client, char_id: int) -> None:
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/rest",
        json={"type": "long"},
    )
    assert resp.status_code == 200, resp.text


async def test_heroism_blocks_frightened_install(gm_client, gm_ws, roster):
    """Lyra casts Heroism on Garrik then Fear at Garrik; the failed
    Wis save no longer installs Frightened, and the Heroism immunity
    broadcast surfaces the block.

    v2.99.16 — target was Pip Quickfingers (Halfling Rogue) before this
    fix. The v2.99.14 Halfling Brave save advantage made Pip's Wis save
    pass too often, starving the failed-save loop and preventing the
    Heroism gate from firing. Garrik (Fighter, Variant Human, Wis +1
    non-proficient) has no race save-trait and a ~65% fail rate against
    DC 14 — clean Heroism test target. Also dropped Caelan from the
    battle so Aura of Protection doesn't add +CHA to the save.
    """
    lyra = roster["Lyra Sunstrider"]
    garrik = roster["Garrik Ironside"]
    await _long_rest(gm_client, lyra["id"])
    await _long_rest(gm_client, garrik["id"])

    garrik_tok = f"tok_hf_garrik_{garrik['id']}"

    blocked = False
    # Lyra's spell DC is 14 (Bard CHA-based); Garrik's Wis save modifier
    # is +1 (Variant Human, Wis 12, non-proficient as a Fighter), so
    # fail rate is ~65%. 30 tries cumulative miss-rate well under 0.1%.
    for _ in range(30):
        await _long_rest(gm_client, lyra["id"])
        await _long_rest(gm_client, garrik["id"])
        # Clear stale buffs aggressively — any prior test may have
        # left Garrik with concentration anchors (Bless, Aid, Heroism,
        # Sacred Weapon, …) that interfere with the Heroism→Fear
        # concentration-swap logic in /respond. End everything we
        # know about.
        for _stale_key in (
            "heroism", "frightened", "bless", "aid", "shield-of-faith",
            "sacred-weapon", "bardic-inspiration-die", "baned",
            "faerie-fired", "paralyzed", "indomitable-armed",
        ):
            await gm_client.post(
                f"/api/campaign/{CAMPAIGN_ID}/end_buff",
                json={"character_id": garrik["id"], "key": _stale_key},
            )
        await gm_client.put(
            f"/api/campaign/{CAMPAIGN_ID}/battle",
            json={
                "combatants": [
                    {"id": f"tok_hf_lyra_{lyra['id']}", "char_id": lyra["id"],
                     "name": lyra["name"], "initiative": 12,
                     "hp_current": 35, "hp_max": 35, "buffs": [],
                     "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0}},
                    {"id": garrik_tok, "char_id": garrik["id"],
                     "name": garrik["name"], "initiative": 8,
                     "hp_current": 60, "hp_max": 60, "buffs": [],
                     "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0}},
                ],
                "turn_index": 0, "round": 1, "active": True,
            },
        )
        # Lyra casts Heroism on Garrik (her spell index 7), then casts
        # Fear on him below. Lyra acts twice per iteration which is
        # fine for the test.
        heroism_cast = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
            json={
                "character_id": lyra["id"],
                "spell_index": 7,  # Lyra's Heroism index
                "slot_level": 1,
                "class_slug": "bard",
                "target_character_id": garrik["id"],
                "target_combatant_id": garrik_tok,
                "target_name": garrik["name"],
                "override": True,
                "override_range": True,
            },
        )
        assert heroism_cast.status_code == 200, heroism_cast.text
        # Verify Heroism is on Garrik with the immunity marker.
        garrik_buffs = (await gm_client.get(
            f"/api/campaign/{CAMPAIGN_ID}/character/{garrik['id']}/buffs"
        )).json().get("buffs", [])
        hero = next(
            (b for b in garrik_buffs if (b or {}).get("key") == "heroism"),
            None,
        )
        assert hero is not None, f"Heroism not installed; got {garrik_buffs}"

        # Lyra casts Fear on Garrik (Wis save).
        gm_ws.mark()
        fear_cast = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
            json={
                "character_id": lyra["id"],
                "spell_index": 19,  # Lyra's Fear index (appended v2.97.43)
                "slot_level": 3,
                "class_slug": "bard",
                "target_character_id": garrik["id"],
                "target_combatant_id": garrik_tok,
                "target_name": garrik["name"],
                "override": True,
                "override_range": True,
            },
        )
        assert fear_cast.status_code == 200, fear_cast.text
        prompt_id = fear_cast.json().get("auto_save_prompt_id")
        if not prompt_id:
            continue
        # Debug — check Garrik's buffs right before /respond. Heroism
        # should still be there with the immunity marker.
        garrik_buffs_mid = (await gm_client.get(
            f"/api/campaign/{CAMPAIGN_ID}/character/{garrik['id']}/buffs"
        )).json().get("buffs", [])
        hero_mid = next(
            (b for b in garrik_buffs_mid if (b or {}).get("key") == "heroism"),
            None,
        )
        assert hero_mid is not None, (
            f"Heroism dropped between cast and respond; "
            f"got {garrik_buffs_mid}"
        )
        assert (hero_mid.get("effects") or {}).get(
            "condition_immunity_frightened"
        ) is True, (
            f"Heroism missing immunity marker; got {hero_mid}"
        )
        # Garrik responds to the save prompt.
        resp = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/roll_request/{prompt_id}/respond",
            json={"character_id": garrik["id"]},
        )
        data = resp.json()
        # The save can pass or fail. We only care about the fail case
        # where Frightened would normally install. With Heroism active,
        # the immunity gate should fire and auto_buff_installed should
        # be empty (the block fired), NOT "Frightened".
        if data.get("auto_buff_installed") == "Frightened":
            # Should not happen with v2.97.43 — Heroism's immunity
            # should have short-circuited the install.
            raise AssertionError(
                f"Heroism failed to block Frightened install; "
                f"response={data}"
            )
        # Determine if we hit a failed save by reading the total
        # against the spell DC (14). Failed save + empty
        # auto_buff_installed means the gate fired.
        if data.get("auto_buff_installed") == "" and data.get("total", 100) < 14:
            blocked = True
            break

    assert blocked, (
        "no failed Wis save in 30 tries; couldn't confirm Heroism "
        "immunity gate fired"
    )

    # Give async broadcasts a beat to land in the buffer.
    import asyncio as _asy
    await _asy.sleep(0.3)

    # Verify the broadcast surfaced the immunity.
    msgs = gm_ws.buffered("feature_used")
    heroism_msgs = [m for m in msgs if (m.get("data") or {}).get("source") == "heroism"]
    assert heroism_msgs, (
        f"expected a feature_used(source=heroism) broadcast; "
        f"got types={[(m.get('data') or {}).get('source') for m in msgs]}"
    )

    # And Garrik should NOT have a frightened buff.
    garrik_buffs_final = (await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{garrik['id']}/buffs"
    )).json().get("buffs", [])
    assert not any(
        (b or {}).get("key") == "frightened" for b in garrik_buffs_final
    ), f"Frightened still installed despite Heroism immunity: {garrik_buffs_final}"
