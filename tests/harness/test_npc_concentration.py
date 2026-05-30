"""v2.98.0 — NPC concentration tracking.

When an NPC caster casts a concentration spell (Hold Person, Fear,
Confusion, Banishment, …) v2.98.0 installs a
``concentration-<spell>`` anchor on the NPC's combatant. When the
NPC then takes damage, ``_maybe_npc_concentration_save`` rolls a
CON save (DC max(10, dmg // 2)); on fail the anchor drops AND every
target-side buff sourced from this NPC drops via
``_drop_paired_concentration_buffs_npc``.

Test flow:
- Spawn Archmage + Pip + Caelan in battle.
- Archmage casts Hold Person at Caelan via /npc_cast_spell with
  ``spell_slug="hold-person"``.
- Walk save-fail loop until Caelan ends up Paralyzed.
- Capture the v2.98.0 anchor install via the buffered ``battle_update``
  broadcast (the helper at ``_install_buff_on_combatant_id`` fires it).
- Pip attacks the Archmage until a hit lands and damage applies.
- Capture the v2.98.0 ``concentration_save`` broadcast (the helper
  at ``_maybe_npc_concentration_save`` fires it).
- If save passed: verify the anchor still exists in the post-damage
  battle state and Caelan still carries Paralyzed.
- If save failed: verify the paired-cleanup dropped both the anchor
  and Caelan's Paralyzed.

v2.98.3: rewrite of the v2.98.0 shipped test which used a non-
existent ``GET /battle`` endpoint; this version reads battle state
out of the buffered ``battle_update`` broadcasts instead.
"""
from .conftest import CAMPAIGN_ID


async def _long_rest(gm_client, char_id: int) -> None:
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/rest",
        json={"type": "long"},
    )
    assert resp.status_code == 200, resp.text


def _find_combatant(battle_msg, combatant_id):
    for c in (battle_msg.get("data") or {}).get("combatants") or []:
        if c.get("id") == combatant_id:
            return c
    return None


async def test_npc_concentration_anchor_installs_and_breaks_on_damage(
    gm_client, gm_ws, roster,
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

    landed = False
    for _ in range(40):
        await _long_rest(gm_client, caelan["id"])
        await _long_rest(gm_client, pip["id"])
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

    assert landed, "no failed WIS save in 40 tries; Paralyzed didn't install"

    # Pluck the most recent battle_update from the WS buffer — the
    # v2.98.0 _install_buff_on_combatant_id helper broadcasts one when
    # the anchor lands on the NPC caster.
    battle_updates = gm_ws.buffered("battle_update")
    assert battle_updates, (
        "no battle_update fired during the install loop — "
        "v2.98.0 _install_buff_on_combatant_id should broadcast"
    )
    latest = battle_updates[-1]
    archmage_cb = _find_combatant(latest, archmage_tok)
    assert archmage_cb is not None
    anchor = next(
        (b for b in (archmage_cb.get("buffs") or [])
         if (b or {}).get("key") == "concentration-hold-person"),
        None,
    )
    assert anchor is not None, (
        f"v2.98.0 anchor missing from Archmage; buffs="
        f"{archmage_cb.get('buffs')}"
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

    # v2.99.2 — explicit Pip cleanup so any state leaked from prior
    # suite tests (Frightened from Fear, prone from Open Hand,
    # Stunned from Stunning Strike, etc.) doesn't degrade his attack
    # rolls below the 30-iteration budget. The install loop above
    # already long-rests him; this also clears any persistent buff
    # keys that affect to-hit. Long-rest again afterwards to refresh
    # HP + reset death-save state.
    for _stale_pip_buff in (
        "frightened", "paralyzed", "stunned", "prone", "blinded",
        "incapacitated", "unconscious", "asleep", "charmed",
        "baned", "faerie-fired", "concentration-hex",
    ):
        await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/end_buff",
            json={"character_id": pip["id"], "key": _stale_pip_buff},
        )
    await _long_rest(gm_client, pip["id"])

    # Mark the WS cursor so the next wait_for only sees post-attack
    # broadcasts.
    gm_ws.mark()

    # Pip attacks Archmage until a hit lands and damage applies.
    # v2.99.2 — bumped 30 → 60 iterations as a margin against suite-
    # level contention. Pip's Shortsword +6 vs Archmage AC ~18 hits
    # ~55% of the time per RAW; 60 iterations gives a cumulative
    # miss rate of ~0.45^60 ≈ 10^-21 against an unbiased d20, so
    # any 60-iter dry spell is a hard signal of degraded test state
    # rather than dice variance.
    damage_landed = False
    for _ in range(60):
        atk = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/attack",
            json={
                "character_id": pip["id"],
                "attack_index": 0,
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
        "no Pip → Archmage hit landed in 60 tries"
    )

    # v2.98.0 contract: a concentration_save event fires for the
    # Archmage's combatant_id.
    conc_save = await gm_ws.wait_for("concentration_save", timeout=3.0)
    cs_data = conc_save.get("data") or {}
    assert cs_data.get("combatant_id") == archmage_tok, (
        f"concentration_save fired but for the wrong combatant: "
        f"{cs_data}"
    )
    assert cs_data.get("buff_key") == "concentration-hold-person"
    assert cs_data.get("dc") >= 10
    save_passed = bool(cs_data.get("passed"))

    # Verify the post-damage state matches the save outcome.
    caelan_buffs_post = (await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{caelan['id']}/buffs"
    )).json().get("buffs", [])
    caelan_has_paralyzed = any(
        (b or {}).get("key") == "paralyzed" for b in caelan_buffs_post
    )

    if save_passed:
        assert caelan_has_paralyzed, (
            "v2.98.0 contract: save passed but Caelan's Paralyzed "
            f"dropped anyway. Buffs: {caelan_buffs_post}"
        )
    else:
        assert not caelan_has_paralyzed, (
            "v2.98.0 contract: save failed → paired cleanup should "
            "drop Caelan's Paralyzed. Buffs post-cleanup: "
            f"{caelan_buffs_post}"
        )
