"""v2.98.1 — symmetric coverage for /npc_cast_spell's save-or-suck
install path: Archmage NPC casts Hold Person at Caelan.

Mirror of v2.97.75's ``test_npc_archmage_banishment``. Closes the
"is the install path actually Banishment-agnostic?" gap by exercising
a different ``_SPELL_CONDITION_MAP`` entry through the same plumbing
(v2.97.75 ``spell_slug`` body param + v2.98.0 NPC anchor install).

Test flow mirrors the Banishment file: spawn Archmage + Caelan in
battle, /npc_cast_spell with spell_slug="hold-person", walk Caelan's
WIS save until a failure lands Paralyzed. Per-spell assertions:
- key == "paralyzed"
- source_spell == "Hold Person"
- concentration == False on the target buff (v2.97.67 fix)
- v2.97.60 repeated-save stamps present (ability=WIS, dc=17)
- v2.98.0 NPC anchor on Archmage with concentration=True and
  source_combatant_id matching the Archmage's token.
"""
from .conftest import CAMPAIGN_ID


async def _long_rest(gm_client, char_id: int) -> None:
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/rest",
        json={"type": "long"},
    )
    assert resp.status_code == 200, resp.text


async def test_archmage_hold_person_at_caelan_installs_paralyzed(
    gm_client, gm_ws, roster,
):
    caelan = roster["Sir Caelan Lightbringer"]
    await _long_rest(gm_client, caelan["id"])

    r = await gm_client.get(f"/api/campaign/{CAMPAIGN_ID}/templates")
    templates = r.json()
    archmage_tmpl = next(
        (t for t in templates
         if (t.get("name") or "").lower() == "archmage"),
        None,
    )
    assert archmage_tmpl is not None

    archmage_tok = "tok_arch_holdperson_archmage"
    caelan_tok = f"tok_arch_holdperson_caelan_{caelan['id']}"

    landed = False
    for _ in range(30):
        await _long_rest(gm_client, caelan["id"])
        await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/end_buff",
            json={"character_id": caelan["id"], "key": "paralyzed"},
        )

        await gm_client.put(
            f"/api/campaign/{CAMPAIGN_ID}/battle",
            json={
                "combatants": [
                    {"id": archmage_tok, "char_id": None,
                     "token_template_id": archmage_tmpl["id"],
                     "name": archmage_tmpl["name"], "initiative": 14,
                     "hp_current": 99, "hp_max": 99, "buffs": [],
                     "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0}},
                    {"id": caelan_tok, "char_id": caelan["id"],
                     "name": caelan["name"], "initiative": 8,
                     "hp_current": 60, "hp_max": 60, "buffs": [],
                     "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0}},
                ],
                "turn_index": 0, "round": 1, "active": True,
            },
        )

        cast = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/npc_cast_spell",
            json={
                "combatant_id": archmage_tok,
                "spell_name": "Hold Person",
                "spell_slug": "hold-person",
                "spell_level": 2,
                "spell_range": "60 feet",
                "save_ability": "WIS",
                "save_dc": 17,
                "target_combatant_id": caelan_tok,
            },
        )
        assert cast.status_code == 200, cast.text
        prompt_id = cast.json().get("auto_save_prompt_id") or 0
        if not prompt_id:
            continue

        resp = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/roll_request/{prompt_id}/respond",
            json={"character_id": caelan["id"]},
        )
        if resp.json().get("auto_buff_installed") == "Paralyzed":
            landed = True
            break

    assert landed, "no failed WIS save in 30 tries; Paralyzed didn't install"

    # Per-spell assertions on the target buff stamps.
    caelan_buffs = (await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{caelan['id']}/buffs"
    )).json().get("buffs", [])
    paralyzed = next(
        (b for b in caelan_buffs if (b or {}).get("key") == "paralyzed"),
        None,
    )
    assert paralyzed is not None, (
        f"Paralyzed not on Caelan; got {caelan_buffs}"
    )
    assert paralyzed.get("source_spell") == "Hold Person"
    # v2.97.67: target-side condition buff carries concentration=False;
    # the caster's anchor handles the concentration semantics.
    assert paralyzed.get("concentration") is False
    # v2.97.60: repeated-save stamps are present so /use_repeated_save
    # + end-of-turn auto-fire can resolve fresh saves.
    assert (paralyzed.get("repeated_save_ability") or "").upper() == "WIS"
    assert int(paralyzed.get("repeated_save_dc") or 0) == 17

    # v2.98.0: NPC anchor on the Archmage. Read the latest battle_update
    # off the WS buffer to find the Archmage's buff list.
    battle_updates = gm_ws.buffered("battle_update")
    assert battle_updates, "no battle_update broadcast captured"
    latest = battle_updates[-1]
    archmage_cb = next(
        (c for c in (latest.get("data") or {}).get("combatants") or []
         if c.get("id") == archmage_tok),
        None,
    )
    assert archmage_cb is not None
    anchor = next(
        (b for b in (archmage_cb.get("buffs") or [])
         if (b or {}).get("key") == "concentration-hold-person"),
        None,
    )
    assert anchor is not None, (
        f"v2.98.0 anchor missing from Archmage; got "
        f"{archmage_cb.get('buffs')}"
    )
    assert anchor.get("concentration") is True
    assert anchor.get("source_combatant_id") == archmage_tok
    assert anchor.get("source_spell") == "Hold Person"
