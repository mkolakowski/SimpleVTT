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
- Caelan casts Heroism on Pip (v2.97.31 walker installs the buff
  with ``effects.condition_immunity_frightened: True``).
- Lyra casts Fear (Bard L3, appended to her demo spell list in
  v2.97.43) on Pip. Loop until Pip fails the Wis save.
- Assert ``/respond`` returns ``auto_buff_installed == ""`` and the
  Heroism broadcast fires; Pip's buffs should NOT include
  ``frightened``.
"""
from .conftest import CAMPAIGN_ID


async def _long_rest(gm_client, char_id: int) -> None:
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/rest",
        json={"type": "long"},
    )
    assert resp.status_code == 200, resp.text


async def test_heroism_blocks_frightened_install(gm_client, gm_ws, roster):
    """Caelan blesses Pip with Heroism; Lyra casts Fear at Pip; the
    failed Wis save no longer installs Frightened, and the Heroism
    immunity broadcast surfaces the block."""
    caelan = roster["Sir Caelan Lightbringer"]
    lyra = roster["Lyra Sunstrider"]
    pip = roster["Pip Quickfingers"]
    await _long_rest(gm_client, caelan["id"])
    await _long_rest(gm_client, lyra["id"])
    await _long_rest(gm_client, pip["id"])

    pip_tok = f"tok_hf_pip_{pip['id']}"

    blocked = False
    # Lyra's spell DC is 14 (Bard CHA-based); Pip's Wis save modifier
    # is low, so fail rate is ~65%. 30 tries cumulative miss-rate well
    # under 0.1%. (Bumped to 30 because each iteration re-seeds + casts
    # twice; flake budget is tight.)
    for _ in range(30):
        await _long_rest(gm_client, caelan["id"])
        await _long_rest(gm_client, lyra["id"])
        await _long_rest(gm_client, pip["id"])
        # Clear stale buffs.
        await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/end_buff",
            json={"character_id": pip["id"], "key": "heroism"},
        )
        await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/end_buff",
            json={"character_id": pip["id"], "key": "frightened"},
        )
        await gm_client.put(
            f"/api/campaign/{CAMPAIGN_ID}/battle",
            json={
                "combatants": [
                    {"id": f"tok_hf_caelan_{caelan['id']}", "char_id": caelan["id"],
                     "name": caelan["name"], "initiative": 14,
                     "hp_current": 60, "hp_max": 60, "buffs": [],
                     "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0}},
                    {"id": f"tok_hf_lyra_{lyra['id']}", "char_id": lyra["id"],
                     "name": lyra["name"], "initiative": 12,
                     "hp_current": 35, "hp_max": 35, "buffs": [],
                     "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0}},
                    {"id": pip_tok, "char_id": pip["id"],
                     "name": pip["name"], "initiative": 8,
                     "hp_current": 40, "hp_max": 40, "buffs": [],
                     "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0}},
                ],
                "turn_index": 0, "round": 1, "active": True,
            },
        )
        # Caelan casts Heroism on Pip (spell_index 7 per Caelan's
        # spell list — Bless=0, Cure Wounds=1, SoF=2, PFE=3,
        # Sanctuary=4, Aid=5, Lesser Restoration=6, ... actually
        # Caelan doesn't have Heroism. Use Lyra to cast Heroism (her
        # spell index 7) on Pip instead. That means Lyra acts twice
        # this iteration which is fine for the test.
        heroism_cast = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
            json={
                "character_id": lyra["id"],
                "spell_index": 7,  # Lyra's Heroism index
                "slot_level": 1,
                "class_slug": "bard",
                "target_character_id": pip["id"],
                "target_combatant_id": pip_tok,
                "target_name": pip["name"],
                "override": True,
                "override_range": True,
            },
        )
        assert heroism_cast.status_code == 200, heroism_cast.text
        # Verify Heroism is on Pip with the immunity marker.
        pip_buffs = (await gm_client.get(
            f"/api/campaign/{CAMPAIGN_ID}/character/{pip['id']}/buffs"
        )).json().get("buffs", [])
        hero = next(
            (b for b in pip_buffs if (b or {}).get("key") == "heroism"),
            None,
        )
        assert hero is not None, f"Heroism not installed; got {pip_buffs}"

        # Lyra casts Fear on Pip (Wis save).
        gm_ws.mark()
        fear_cast = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
            json={
                "character_id": lyra["id"],
                "spell_index": 19,  # Lyra's Fear index (appended v2.97.43)
                "slot_level": 3,
                "class_slug": "bard",
                "target_character_id": pip["id"],
                "target_combatant_id": pip_tok,
                "target_name": pip["name"],
                "override": True,
                "override_range": True,
            },
        )
        assert fear_cast.status_code == 200, fear_cast.text
        prompt_id = fear_cast.json().get("auto_save_prompt_id")
        if not prompt_id:
            continue
        # Pip responds to the save prompt.
        resp = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/roll_request/{prompt_id}/respond",
            json={"character_id": pip["id"]},
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

    # Verify the broadcast surfaced the immunity.
    msgs = gm_ws.buffered("feature_used")
    heroism_msgs = [m for m in msgs if (m.get("data") or {}).get("source") == "heroism"]
    assert heroism_msgs, (
        f"expected a feature_used(source=heroism) broadcast; "
        f"got types={[(m.get('data') or {}).get('source') for m in msgs]}"
    )

    # And Pip should NOT have a frightened buff.
    pip_buffs_final = (await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{pip['id']}/buffs"
    )).json().get("buffs", [])
    assert not any(
        (b or {}).get("key") == "frightened" for b in pip_buffs_final
    ), f"Frightened still installed despite Heroism immunity: {pip_buffs_final}"
