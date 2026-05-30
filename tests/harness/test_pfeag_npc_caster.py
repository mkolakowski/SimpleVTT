"""v2.98.2 — PFE&G save-advantage now fires against NPC-sourced
condition installs.

Pre-v2.98.2, when an NPC caster (via /npc_cast_spell with a
``spell_slug`` body param + the v2.97.75 install path) caused a PC
to fail their save and install a Charmed / Frightened condition,
the buff was stamped with ``source_caster_creature_type: ""``. The
v2.97.50 ``_saver_pfeag_save_advantage`` check requires a non-empty
caster type to match against the PFE&G ``pfeag_protected_types``
list, so repeated saves against NPC-installed conditions ran at
straight d20 even when PFE&G covered the NPC caster's type.

v2.98.2 closes the gap: ``/respond``'s install path now looks up
the NPC caster's combatant by id (threaded via ``caster_combatant_id``
since v2.97.80) and reads its creature type via the existing
``_attacker_creature_type`` helper.

Test flow:
- Spawn an NPC bandit-captain with ``creature_type: "fiend"`` runtime
  override + Pip + Caelan in battle.
- The NPC casts Fear at Pip via /npc_cast_spell. Walk the save-fail
  loop until Frightened lands.
- Verify Pip's Frightened carries ``source_caster_creature_type: "fiend"``
  (the v2.98.2 stamp).
- Caelan casts PFE&G on Pip (fiend in protected list).
- Pip calls /use_repeated_save; assert ``pfeag_advantage_applied: True``.
"""
from .conftest import CAMPAIGN_ID


async def _long_rest(gm_client, char_id: int) -> None:
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/rest",
        json={"type": "long"},
    )
    assert resp.status_code == 200, resp.text


async def test_pfeag_advantage_against_npc_caster(gm_client, roster):
    """NPC caster (creature_type override 'fiend') installs Frightened
    on Pip; Caelan wards Pip with PFE&G; Pip's repeated save carries
    pfeag_advantage_applied: True."""
    pip = roster["Pip Quickfingers"]
    caelan = roster["Sir Caelan Lightbringer"]

    # Use the bandit-captain template (any humanoid template works —
    # the creature_type runtime override forces it to "fiend" anyway).
    r = await gm_client.get(f"/api/campaign/{CAMPAIGN_ID}/templates")
    templates = r.json()
    fiend_tmpl = next(
        (t for t in templates
         if (t.get("name") or "").lower() in ("bandit captain", "bandit", "archmage")),
        templates[0],
    )

    fiend_tok = "tok_pfeag_npc_fiend"
    pip_tok = f"tok_pfeag_npc_pip_{pip['id']}"
    caelan_tok = f"tok_pfeag_npc_caelan_{caelan['id']}"

    landed = False
    for _ in range(40):
        await _long_rest(gm_client, pip["id"])
        await _long_rest(gm_client, caelan["id"])
        for _stale in (
            "frightened", "paralyzed", "charmed",
            "protection-from-evil-and-good",
        ):
            await gm_client.post(
                f"/api/campaign/{CAMPAIGN_ID}/end_buff",
                json={"character_id": pip["id"], "key": _stale},
            )

        await gm_client.put(
            f"/api/campaign/{CAMPAIGN_ID}/battle",
            json={
                "combatants": [
                    {"id": fiend_tok, "char_id": None,
                     "token_template_id": fiend_tmpl["id"],
                     "name": fiend_tmpl["name"], "initiative": 14,
                     "hp_current": 99, "hp_max": 99, "buffs": [],
                     "creature_type": "fiend",
                     "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0}},
                    {"id": caelan_tok, "char_id": caelan["id"],
                     "name": caelan["name"], "initiative": 10,
                     "hp_current": 60, "hp_max": 60, "buffs": [],
                     "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0}},
                    {"id": pip_tok, "char_id": pip["id"],
                     "name": pip["name"], "initiative": 8,
                     "hp_current": 40, "hp_max": 40, "buffs": [],
                     "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0}},
                ],
                "turn_index": 0, "round": 1, "active": True,
            },
        )

        cast = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/npc_cast_spell",
            json={
                "combatant_id": fiend_tok,
                "spell_name": "Fear",
                "spell_slug": "fear",
                "spell_level": 3,
                "spell_range": "30 feet",
                "save_ability": "WIS",
                "save_dc": 17,
                "target_combatant_id": pip_tok,
            },
        )
        assert cast.status_code == 200, cast.text
        prompt_id = cast.json().get("auto_save_prompt_id") or 0
        if not prompt_id:
            continue
        resp = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/roll_request/{prompt_id}/respond",
            json={"character_id": pip["id"]},
        )
        if resp.json().get("auto_buff_installed") == "Frightened":
            landed = True
            break

    assert landed, (
        "no failed WIS save in 40 tries; Frightened didn't install"
    )

    # v2.98.2 contract: Pip's Frightened carries the NPC caster's
    # creature type as "fiend".
    pip_buffs = (await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{pip['id']}/buffs"
    )).json().get("buffs", [])
    frightened = next(
        (b for b in pip_buffs if (b or {}).get("key") == "frightened"),
        None,
    )
    assert frightened is not None
    assert (frightened.get("source_caster_creature_type") or "").lower() == "fiend", (
        f"v2.98.2: NPC caster type not captured. "
        f"source_caster_creature_type="
        f"{frightened.get('source_caster_creature_type')!r}"
    )

    # Caelan casts PFE&G on Pip (fiend in the protected list).
    pfeag_cast = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
        json={
            "character_id": caelan["id"],
            "spell_index": 3,
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

    # Pip's repeated save now picks up PFE&G advantage.
    rs = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_repeated_save",
        json={"character_id": pip["id"], "buff_key": "frightened"},
    )
    assert rs.status_code == 200, rs.text
    data = rs.json()
    assert data["pfeag_advantage_applied"] is True, (
        "v2.98.2 contract: PFE&G advantage should fire when NPC "
        "caster's creature type matches a protected type. "
        f"Response: {data}"
    )
