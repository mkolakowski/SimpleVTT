"""Homebrew monster attack fields → rollable buttons (TODO reconciliation).

This was filed as unbuilt but is already shipped (since v2.3.8): the homebrew
monster Actions editor (`data-row-mode="action"` in campaign_settings.html +
features_editor.js) exposes structured attack fields; `_coalesce_monster_actions`
persists them; and the shared monster stat-block read-view
(`_monster_template_to_sheet` → `sheet["attacks"]` → `_tab_actions.html` →
`renderActionButtons`) renders them as clickable 🎯/🎲 buttons firing
`/npc_attack` — identical to shipped SRD monsters.

This test locks in the persistence contract end-to-end: a homebrew monster
created with an attack action round-trips through `/custom-monsters` with its
`attack_roll` / `attack_bonus` / `damage` / `damage_type` intact (read back via
`/api/content/monsters/{slug}`).
"""
import json

from .conftest import CAMPAIGN_ID


async def test_homebrew_monster_persists_attack_action_fields(gm_client):
    # Single-token name → deterministic slug.
    name = "Zzharnessattackogre"
    slug = "zzharnessattackogre"
    actions = [{
        "name": "Greataxe", "desc": "Melee Weapon Attack",
        "attack_roll": True, "attack_bonus": "+6",
        "damage": "1d12+4", "damage_type": "slashing",
    }]
    # Pre-clean in case a prior run left it behind.
    await gm_client.post(
        f"/campaign/{CAMPAIGN_ID}/custom-monsters/{slug}/delete")

    r = await gm_client.post(
        f"/campaign/{CAMPAIGN_ID}/custom-monsters",
        data={
            "name": name, "hit_points": "45", "challenge_rating": "2",
            "actions_json": json.dumps(actions),
        },
    )
    assert r.status_code in (200, 303), r.text
    try:
        c = await gm_client.get(
            f"/api/content/monsters/{slug}?campaign_id={CAMPAIGN_ID}")
        assert c.status_code == 200, c.text
        rec = c.json()["record"]
        atk = next((a for a in (rec.get("actions") or [])
                    if a.get("name") == "Greataxe"), None)
        assert atk is not None, rec.get("actions")
        assert atk["attack_roll"] is True
        assert atk["attack_bonus"] == "+6"
        assert atk["damage"] == "1d12+4"
        assert atk["damage_type"] == "slashing"
    finally:
        await gm_client.post(
            f"/campaign/{CAMPAIGN_ID}/custom-monsters/{slug}/delete")


async def test_homebrew_monster_save_action_persists_save_fields(gm_client):
    """A save-based action keeps its save_ability + save_dc (for the
    📋 Prompt SAVE button)."""
    name = "Zzharnesssavedrake"
    slug = "zzharnesssavedrake"
    actions = [{
        "name": "Fire Breath", "desc": "DEX save",
        "save_ability": "dex", "save_dc": 14,
        "damage": "4d6", "damage_type": "fire",
    }]
    await gm_client.post(
        f"/campaign/{CAMPAIGN_ID}/custom-monsters/{slug}/delete")
    r = await gm_client.post(
        f"/campaign/{CAMPAIGN_ID}/custom-monsters",
        data={"name": name, "hit_points": "30", "challenge_rating": "1",
              "actions_json": json.dumps(actions)})
    assert r.status_code in (200, 303), r.text
    try:
        rec = (await gm_client.get(
            f"/api/content/monsters/{slug}?campaign_id={CAMPAIGN_ID}")
        ).json()["record"]
        atk = next((a for a in (rec.get("actions") or [])
                    if a.get("name") == "Fire Breath"), None)
        assert atk is not None
        assert atk["save_ability"] == "dex"
        assert atk["save_dc"] == 14
        assert atk["damage"] == "4d6"
    finally:
        await gm_client.post(
            f"/campaign/{CAMPAIGN_ID}/custom-monsters/{slug}/delete")
