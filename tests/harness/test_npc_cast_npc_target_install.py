"""v2.98.5 — /npc_cast_spell installs conditions on NPC targets.

Pre-v2.98.5, ``/npc_cast_spell`` installed conditions on PC targets
via the v2.97.75 ``_save_request_context`` stash + /respond hook,
but completely skipped NPC targets — an NPC casting Hold Person at
another NPC rolled the save server-side and reported pass/fail in
the chat card but never installed Paralyzed even on a failure.
v2.98.5 ports the v2.38.0 PC-caster → NPC-target inline-install
block (in /cast_spell at line ~12895) over to /npc_cast_spell:
when the spell has a ``_SPELL_CONDITION_MAP`` entry + the NPC target
failed the save, install the condition buff on the target via
``_install_buff_on_combatant_id`` + install the v2.97.80
concentration anchor on the NPC caster.

Test flow:
- Spawn Archmage NPC + a bandit NPC in battle. The bandit's WIS
  save mod is low (Wis 11 → +0) so a DC 17 WIS save fails reliably.
- Archmage casts Hold Person at the bandit via /npc_cast_spell.
- Walk loop until the response carries ``auto_save_passed: False``
  and ``auto_save_buff_name: "Paralyzed"``.
- Pluck the bandit's buff state from the latest battle_update.
- Assert Paralyzed installed with the v2.97.71 catalog shape +
  v2.97.80 NPC source stamps. Assert the Archmage has the
  ``concentration-hold-person`` anchor.
"""
from .conftest import CAMPAIGN_ID


def _find_combatant(battle_msg, combatant_id):
    for c in (battle_msg.get("data") or {}).get("combatants") or []:
        if c.get("id") == combatant_id:
            return c
    return None


async def test_npc_cast_npc_target_installs_paralyzed(
    gm_client, gm_ws, roster,
):
    # Look up the Archmage + a bandit template.
    r = await gm_client.get(f"/api/campaign/{CAMPAIGN_ID}/templates")
    templates = r.json()
    archmage_tmpl = next(
        (t for t in templates
         if (t.get("name") or "").lower() == "archmage"),
        None,
    )
    bandit_tmpl = next(
        (t for t in templates
         if "bandit" in (t.get("name") or "").lower()
         and "captain" not in (t.get("name") or "").lower()),
        None,
    )
    assert archmage_tmpl is not None
    assert bandit_tmpl is not None

    archmage_tok = "tok_npccast_archmage"
    bandit_tok = "tok_npccast_bandit"

    landed = False
    for _ in range(40):
        await gm_client.put(
            f"/api/campaign/{CAMPAIGN_ID}/battle",
            json={
                "combatants": [
                    {"id": archmage_tok, "char_id": None,
                     "token_template_id": archmage_tmpl["id"],
                     "name": archmage_tmpl["name"], "initiative": 14,
                     "hp_current": 99, "hp_max": 99, "buffs": [],
                     "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0}},
                    {"id": bandit_tok, "char_id": None,
                     "token_template_id": bandit_tmpl["id"],
                     "name": bandit_tmpl["name"], "initiative": 8,
                     "hp_current": 30, "hp_max": 30, "buffs": [],
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
                "target_combatant_id": bandit_tok,
            },
        )
        assert cast.status_code == 200, cast.text
        data = cast.json()
        if (
            data.get("auto_save_passed") is False
            and data.get("auto_save_buff_name") == "Paralyzed"
        ):
            landed = True
            break

    assert landed, (
        "no failed bandit WIS save in 40 tries; "
        "Paralyzed didn't install on NPC target"
    )

    # Pluck the latest battle_update for the bandit + Archmage buff state.
    battle_updates = gm_ws.buffered("battle_update")
    assert battle_updates, "no battle_update broadcast captured"
    latest = battle_updates[-1]

    bandit_cb = _find_combatant(latest, bandit_tok)
    assert bandit_cb is not None
    paralyzed = next(
        (b for b in (bandit_cb.get("buffs") or [])
         if (b or {}).get("key") == "paralyzed"),
        None,
    )
    assert paralyzed is not None, (
        f"v2.98.5 contract: Paralyzed not on bandit; got "
        f"{bandit_cb.get('buffs')}"
    )
    assert paralyzed.get("source_spell") == "Hold Person"
    # v2.97.67: target-side buff carries concentration: False.
    assert paralyzed.get("concentration") is False
    # v2.97.80: source_combatant_id points at the NPC caster.
    assert paralyzed.get("source_combatant_id") == archmage_tok
    # v2.97.60: repeated-save stamps populated.
    assert (paralyzed.get("repeated_save_ability") or "").upper() == "WIS"
    assert int(paralyzed.get("repeated_save_dc") or 0) == 17

    # Archmage carries the v2.97.80 anchor.
    archmage_cb = _find_combatant(latest, archmage_tok)
    assert archmage_cb is not None
    anchor = next(
        (b for b in (archmage_cb.get("buffs") or [])
         if (b or {}).get("key") == "concentration-hold-person"),
        None,
    )
    assert anchor is not None, (
        f"v2.98.5 contract: anchor missing from Archmage; got "
        f"{archmage_cb.get('buffs')}"
    )
    assert anchor.get("concentration") is True
    assert anchor.get("source_combatant_id") == archmage_tok
