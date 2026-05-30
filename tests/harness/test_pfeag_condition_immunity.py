"""v2.97.49 — PFE&G type-aware condition immunity hook.

Closes the second of three v2.97.46-filed Protection from Evil and
Good mechanical halves. The ``_pc_has_pfeag_against_type`` helper
walks the saver's buffs for the PFE&G key and checks the source
caster's creature type against the buff's
``effects.pfeag_protected_types`` list. ``/respond`` short-circuits
the Charmed / Frightened install when the marker is present and
emits a ``feature_used(source=protection-from-evil-and-good)``
broadcast naming the protected target and the source type.

Test flow:
- Caelan casts PFE&G on Pip (v2.97.31 walker installs the buff with
  ``effects.pfeag_protected_types`` covering fiend).
- Lyra's combatant gets ``creature_type: "fiend"`` via PUT /battle
  (the v2.97.48 helper resolves her as a fiend).
- Lyra casts Fear on Pip; loop until Pip fails the Wis save.
- Assert ``/respond`` returns ``auto_buff_installed == ""`` (gate
  fired) and the PFE&G broadcast surfaces the block.
- Pip's buffs should NOT include ``frightened``.
"""
from .conftest import CAMPAIGN_ID


async def _long_rest(gm_client, char_id: int) -> None:
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/rest",
        json={"type": "long"},
    )
    assert resp.status_code == 200, resp.text


async def test_pfeag_blocks_frightened_from_fiend_caster(
    gm_client, gm_ws, roster,
):
    """Caelan wards Pip with PFE&G; Lyra (flagged fiend via the
    combatant test override) casts Fear at Pip; the failed Wis save
    no longer installs Frightened because Lyra's creature type
    matches the buff's protected list."""
    caelan = roster["Sir Caelan Lightbringer"]
    lyra = roster["Lyra Sunstrider"]
    pip = roster["Pip Quickfingers"]
    await _long_rest(gm_client, caelan["id"])
    await _long_rest(gm_client, lyra["id"])
    await _long_rest(gm_client, pip["id"])

    pip_tok = f"tok_pfeag_imm_pip_{pip['id']}"
    lyra_tok = f"tok_pfeag_imm_lyra_{lyra['id']}"
    caelan_tok = f"tok_pfeag_imm_caelan_{caelan['id']}"

    blocked = False
    # Lyra's spell DC 14; Pip Wis save modifier is low — fail rate
    # ~65%. 30 iterations cumulative miss-rate well under 0.1%.
    for _ in range(30):
        await _long_rest(gm_client, caelan["id"])
        await _long_rest(gm_client, lyra["id"])
        await _long_rest(gm_client, pip["id"])
        # Aggressive cleanup to keep concentration anchors from
        # earlier tests from interfering.
        for _stale_key in (
            "heroism", "frightened", "bless", "aid", "shield-of-faith",
            "sacred-weapon", "bardic-inspiration-die", "baned",
            "faerie-fired", "paralyzed", "protection-from-evil-and-good",
        ):
            await gm_client.post(
                f"/api/campaign/{CAMPAIGN_ID}/end_buff",
                json={"character_id": pip["id"], "key": _stale_key},
            )
        # Lyra's combatant gets the creature_type="fiend" override
        # so the v2.97.48 helper resolves her as a fiend at gate time.
        await gm_client.put(
            f"/api/campaign/{CAMPAIGN_ID}/battle",
            json={
                "combatants": [
                    {"id": caelan_tok, "char_id": caelan["id"],
                     "name": caelan["name"], "initiative": 14,
                     "hp_current": 60, "hp_max": 60, "buffs": [],
                     "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0}},
                    {"id": lyra_tok, "char_id": lyra["id"],
                     "name": lyra["name"], "initiative": 12,
                     "hp_current": 35, "hp_max": 35, "buffs": [],
                     "creature_type": "fiend",
                     "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0}},
                    {"id": pip_tok, "char_id": pip["id"],
                     "name": pip["name"], "initiative": 8,
                     "hp_current": 40, "hp_max": 40, "buffs": [],
                     "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0}},
                ],
                "turn_index": 0, "round": 1, "active": True,
            },
        )
        # Caelan casts PFE&G on Pip.
        pfeag_cast = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
            json={
                "character_id": caelan["id"],
                "spell_index": 3,  # PFE&G
                "slot_level": 1,
                "class_slug": "paladin",
                "target_character_id": pip["id"],
                "target_combatant_id": pip_tok,
                "target_name": pip["name"],
                "override": True,
                "override_range": True,
            },
        )
        assert pfeag_cast.status_code == 200, pfeag_cast.text
        # Confirm PFE&G is on Pip with the protected types.
        pip_buffs_mid = (await gm_client.get(
            f"/api/campaign/{CAMPAIGN_ID}/character/{pip['id']}/buffs"
        )).json().get("buffs", [])
        pfeag_buff = next(
            (b for b in pip_buffs_mid if (b or {}).get("key") == "protection-from-evil-and-good"),
            None,
        )
        assert pfeag_buff is not None, (
            f"PFE&G not installed; got {pip_buffs_mid}"
        )

        # Lyra casts Fear on Pip (Wis save).
        gm_ws.mark()
        fear_cast = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
            json={
                "character_id": lyra["id"],
                "spell_index": 19,  # Lyra's Fear index (v2.97.43)
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
        # Re-read Pip's buffs as a sync point between Fear cast and
        # /respond. Mirrors the v2.97.43 Heroism test's workaround:
        # the intermediate request forces state to settle so the
        # PFE&G buff is reliably visible to the gate in /respond.
        pip_buffs_mid2 = (await gm_client.get(
            f"/api/campaign/{CAMPAIGN_ID}/character/{pip['id']}/buffs"
        )).json().get("buffs", [])
        assert any(
            (b or {}).get("key") == "protection-from-evil-and-good"
            for b in pip_buffs_mid2
        ), f"PFE&G dropped between cast and respond; got {pip_buffs_mid2}"
        # Pip responds to the save prompt.
        resp = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/roll_request/{prompt_id}/respond",
            json={"character_id": pip["id"]},
        )
        data = resp.json()
        if data.get("auto_buff_installed") == "Frightened":
            raise AssertionError(
                f"PFE&G failed to block Frightened install from fiend; "
                f"response={data}"
            )
        if data.get("auto_buff_installed") == "" and data.get("total", 100) < 14:
            blocked = True
            break

    assert blocked, (
        "no failed Wis save in 30 tries; couldn't confirm PFE&G "
        "type-aware immunity gate fired"
    )

    import asyncio as _asy
    await _asy.sleep(0.3)

    msgs = gm_ws.buffered("feature_used")
    pfeag_msgs = [
        m for m in msgs
        if (m.get("data") or {}).get("source") == "protection-from-evil-and-good"
    ]
    assert pfeag_msgs, (
        f"expected a feature_used(source=protection-from-evil-and-good) "
        f"broadcast; got types={[(m.get('data') or {}).get('source') for m in msgs]}"
    )

    # And Pip should NOT have a frightened buff.
    pip_buffs_final = (await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{pip['id']}/buffs"
    )).json().get("buffs", [])
    assert not any(
        (b or {}).get("key") == "frightened" for b in pip_buffs_final
    ), (
        f"Frightened still installed despite PFE&G immunity: "
        f"{pip_buffs_final}"
    )
