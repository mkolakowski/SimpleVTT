"""v2.97.75 — Archmage NPC casts Banishment at Caelan via /npc_cast_spell.

Closes the loop on the NPC caster → PC target → condition install
path. /npc_cast_spell now accepts ``spell_slug`` (v2.97.75) which
triggers a ``_save_request_context`` stash on PC-target save spells;
the PC's /respond fires the existing condition install path on a
failed save. Caelan failing the CHA save installs Banished with all
the v2.97.71 catalog stamps + v2.97.67 concentration=False fix.

Test flow:
- Look up the Archmage template from /api/campaign/{cid}/templates.
- Seed battle with the Archmage NPC + Caelan PC.
- Archmage calls /npc_cast_spell with spell_slug="banishment",
  save_ability="CHA", save_dc=17 (SRD Archmage's spell DC).
- The PC's RollRequest is created. Respond as Caelan; loop until
  Caelan fails the CHA save.
- Assert Banished installs on Caelan with the v2.97.71 catalog
  shape (key="banished", source_spell="Banishment", concentration=False).
"""
from .conftest import CAMPAIGN_ID


async def _long_rest(gm_client, char_id: int) -> None:
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/rest",
        json={"type": "long"},
    )
    assert resp.status_code == 200, resp.text


async def test_archmage_banishment_at_caelan_installs_banished(
    gm_client, roster,
):
    caelan = roster["Sir Caelan Lightbringer"]
    await _long_rest(gm_client, caelan["id"])

    # Look up the Archmage template (registered by v2.97.74 demo seed).
    r = await gm_client.get(f"/api/campaign/{CAMPAIGN_ID}/templates")
    templates = r.json()
    archmage_tmpl = next(
        (t for t in templates
         if (t.get("name") or "").lower() == "archmage"),
        None,
    )
    assert archmage_tmpl is not None, (
        f"Archmage template not in campaign; got names="
        f"{[t.get('name') for t in templates]}"
    )

    archmage_tok = "tok_arch_banish_archmage"
    caelan_tok = f"tok_arch_banish_caelan_{caelan['id']}"

    landed = False
    for _ in range(30):
        await _long_rest(gm_client, caelan["id"])
        await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/end_buff",
            json={"character_id": caelan["id"], "key": "banished"},
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
                "spell_name": "Banishment",
                "spell_slug": "banishment",
                "spell_level": 4,
                "spell_range": "60 feet",
                "save_ability": "CHA",
                "save_dc": 17,
                "target_combatant_id": caelan_tok,
            },
        )
        assert cast.status_code == 200, cast.text
        data = cast.json()
        prompt_id = data.get("auto_save_prompt_id") or 0
        if not prompt_id:
            continue

        # Caelan responds to the save prompt.
        resp = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/roll_request/{prompt_id}/respond",
            json={"character_id": caelan["id"]},
        )
        body = resp.json()
        if body.get("auto_buff_installed") == "Banished":
            landed = True
            break

    assert landed, "no failed CHA save in 30 tries; Banished didn't install"

    # Verify Caelan's buff list carries Banished with the v2.97.71 stamps.
    caelan_buffs = (await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{caelan['id']}/buffs"
    )).json().get("buffs", [])
    banished = next(
        (b for b in caelan_buffs if (b or {}).get("key") == "banished"),
        None,
    )
    assert banished is not None, (
        f"Banished not on Caelan; got {caelan_buffs}"
    )
    assert (banished.get("source_spell") or "") == "Banishment"
    # v2.97.67 concentration=False on target buffs.
    assert banished.get("concentration") is False
