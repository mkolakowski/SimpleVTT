"""v2.98.0 — NPC concentration tracking.

When an NPC caster casts a concentration spell (Hold Person, Fear,
Confusion, Banishment, …) v2.98.0 installs a
``concentration-<spell>`` anchor on the NPC's combatant. When the
NPC then takes damage, ``_maybe_npc_concentration_save`` rolls a
CON save (DC max(10, dmg // 2)); on fail the anchor drops AND every
target-side buff sourced from this NPC drops via the new
``_drop_paired_concentration_buffs_npc`` helper.

Test flow:
- Spawn Archmage + Pip + Caelan in battle.
- Archmage casts Hold Person on Caelan via /npc_cast_spell with
  ``spell_slug="hold-person"`` (v2.97.75 + v2.97.80 plumbing).
- Walk the save-fail loop until Caelan ends up Paralyzed.
- Assert the Archmage carries a ``concentration-hold-person`` buff
  with ``concentration: True`` (the v2.98.0 anchor install).
- Pip attacks the Archmage with /attack until at least one hit
  applies damage.
- Assert either (a) the anchor is still on the Archmage AND Caelan
  still has Paralyzed (save passed), OR (b) the anchor is gone AND
  Caelan's Paralyzed dropped (save failed → paired cleanup).

The pass-vs-fail outcome is dice-dependent; the test asserts the
contract on whichever branch fires.
"""
from .conftest import CAMPAIGN_ID


async def _long_rest(gm_client, char_id: int) -> None:
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/rest",
        json={"type": "long"},
    )
    assert resp.status_code == 200, resp.text


async def _install_paralyzed_on_caelan_from_archmage(
    gm_client, archmage_tmpl, archmage_tok, caelan, caelan_tok, pip, pip_tok,
):
    """Seed battle + walk the Archmage's Hold Person cast loop until
    Caelan fails the WIS save and Paralyzed installs. Returns nothing;
    the caller verifies the install + anchor."""
    landed = False
    for _ in range(40):
        await _long_rest(gm_client, caelan["id"])
        await _long_rest(gm_client, pip["id"])
        # Clear any stale Paralyzed / anchor state before each attempt.
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

    assert landed, (
        "no failed WIS save in 40 tries; Paralyzed didn't install"
    )


async def test_npc_concentration_anchor_installs_and_breaks_on_damage(
    gm_client, roster,
):
    caelan = roster["Sir Caelan Lightbringer"]
    pip = roster["Pip Quickfingers"]

    # Look up the Archmage template (registered by v2.97.74).
    r = await gm_client.get(f"/api/campaign/{CAMPAIGN_ID}/templates")
    templates = r.json()
    archmage_tmpl = next(
        (t for t in templates
         if (t.get("name") or "").lower() == "archmage"),
        None,
    )
    assert archmage_tmpl is not None

    archmage_tok = "tok_npcconc_archmage"
    caelan_tok = f"tok_npcconc_caelan_{caelan['id']}"
    pip_tok = f"tok_npcconc_pip_{pip['id']}"

    await _install_paralyzed_on_caelan_from_archmage(
        gm_client, archmage_tmpl, archmage_tok, caelan, caelan_tok, pip, pip_tok,
    )

    # Verify Archmage carries the v2.98.0 concentration anchor.
    battle = (await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/battle"
    )).json()
    archmage = next(
        (c for c in (battle.get("combatants") or [])
         if c.get("id") == archmage_tok),
        None,
    )
    assert archmage is not None
    anchor = next(
        (b for b in (archmage.get("buffs") or [])
         if (b or {}).get("key") == "concentration-hold-person"),
        None,
    )
    assert anchor is not None, (
        f"v2.98.0 anchor missing from Archmage; got buffs="
        f"{archmage.get('buffs')}"
    )
    assert anchor.get("concentration") is True
    assert anchor.get("source_combatant_id") == archmage_tok

    # Sanity: Caelan carries Paralyzed pre-attack.
    caelan_buffs_pre = (await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{caelan['id']}/buffs"
    )).json().get("buffs", [])
    assert any(
        (b or {}).get("key") == "paralyzed" for b in caelan_buffs_pre
    )

    # Pip attacks Archmage until a hit lands and damage applies.
    damage_landed = False
    for _ in range(30):
        atk = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/attack",
            json={
                "character_id": pip["id"],
                "attack_index": 0,  # Shortsword
                "target_combatant_id": archmage_tok,
                "override": True,
            },
        )
        if atk.status_code != 200:
            continue
        data = atk.json()
        if data.get("hit") and int(data.get("damage_applied") or 0) > 0:
            damage_landed = True
            break

    assert damage_landed, (
        "no Pip → Archmage hit landed in 30 tries; can't trigger NPC "
        "concentration save"
    )

    # Re-read Archmage + Caelan post-damage. Two valid contracts:
    # (a) concentration save PASSED → anchor still present + Caelan
    #     still Paralyzed.
    # (b) concentration save FAILED → anchor gone + Caelan no longer
    #     Paralyzed (paired cleanup fired).
    battle_post = (await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/battle"
    )).json()
    archmage_post = next(
        (c for c in (battle_post.get("combatants") or [])
         if c.get("id") == archmage_tok),
        None,
    )
    assert archmage_post is not None
    anchor_post = next(
        (b for b in (archmage_post.get("buffs") or [])
         if (b or {}).get("key") == "concentration-hold-person"),
        None,
    )
    caelan_buffs_post = (await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{caelan['id']}/buffs"
    )).json().get("buffs", [])
    caelan_has_paralyzed = any(
        (b or {}).get("key") == "paralyzed" for b in caelan_buffs_post
    )

    if anchor_post is not None:
        # Save passed: anchor stays, Caelan stays Paralyzed.
        assert caelan_has_paralyzed, (
            "v2.98.0 contract: anchor still on Archmage but Caelan's "
            "Paralyzed dropped — inconsistent state"
        )
    else:
        # Save failed: anchor gone, paired cleanup should drop Paralyzed.
        assert not caelan_has_paralyzed, (
            "v2.98.0 contract: anchor dropped from Archmage but "
            "Caelan's Paralyzed didn't drop — "
            "_drop_paired_concentration_buffs_npc didn't fire. "
            f"Caelan's buffs post-attack: {caelan_buffs_post}"
        )
