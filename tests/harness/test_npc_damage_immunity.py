"""v2.99.125 — NPC damage immunity engine end-to-end test.

Closes the v2.99.124 filed item: adds `_immunity_zero_npc` and
wires it into the NPC branch of `_apply_damage_to_combatant`. The
helper mirrors the PC `_immunity_zero` shape and reads:
  - Template-level `sheet.damage_immunities` (SRD stat-block phrases)
  - Combatant-level `buffs[].effects.immunity_to` (dict-shape buff
    immunities)

Same "all" wildcard semantics as the PC path. Immunity is checked
BEFORE resistance (RAW: supersedes).

Tests:
  - bandit with a buff carrying `effects.immunity_to: ["all"]`
    takes 0 damage from any attack
  - bandit with a buff carrying `effects.immunity_to: ["bludgeoning"]`
    takes 0 damage from Tavik's Warhammer's bludgeoning component
    (Divine Strike radiant still passes)
  - bandit with no immunity buff (control) takes full damage
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID


def _mkc(cid, char_id=None, token_template_id=None, name="X",
         hp_cur=20, hp_max=20, buffs=None):
    return {
        "id": cid,
        "char_id": char_id,
        "token_template_id": token_template_id,
        "name": name,
        "initiative": 10,
        "hp_current": hp_cur, "hp_max": hp_max,
        "speed_walk": 30,
        "buffs": buffs or [],
        "economy": {"action": False, "bonus": False, "reaction": False,
                    "movement": 0, "dash_bonus_ft": 0},
    }


async def _seed_battle(gm_client, combatants):
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": combatants, "turn_index": 0,
              "round": 1, "active": True},
    )


async def _bandit_template(gm_client):
    r = await gm_client.get(f"/api/campaign/{CAMPAIGN_ID}/templates")
    templates = r.json()
    return next(
        (t for t in templates if "bandit" in t["name"].lower()), templates[0],
    )


async def test_all_immunity_buff_zeroes_npc_damage(gm_client, roster):
    """Bandit with `effects.immunity_to: ["all"]` buff takes 0
    damage from Tavik's Warhammer.
    """
    tavik = roster["Brother Tavik Stonebrow"]
    bandit_tmpl = await _bandit_template(gm_client)
    bandit_id = "tok_npc_imm_all_bandit"
    immunity_buff = {
        "key": "immune-test",
        "name": "Immune (test)",
        "icon": "🛡",
        "effects": {"immunity_to": ["all"]},
    }
    for _ in range(15):
        await _seed_battle(gm_client, [
            _mkc(f"tok_npc_imm_all_tv_{tavik['id']}", tavik["id"],
                 name=tavik["name"]),
            _mkc(bandit_id, token_template_id=bandit_tmpl["id"],
                 name=bandit_tmpl["name"],
                 buffs=[immunity_buff]),
        ])
        resp = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/attack",
            json={
                "character_id": tavik["id"],
                "attack_index": 0,  # Warhammer
                "target_combatant_id": bandit_id,
                "override": True,
            },
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        if data.get("hit"):
            assert data.get("damage_applied") == 0, (
                f"'all' immunity should zero NPC damage; "
                f"got {data.get('damage_applied')}"
            )
            assert data.get("target_resistance_applied") is False, data
            return
    raise AssertionError("no hit in 15 tries")


async def test_per_type_immunity_buff_zeroes_matching_npc_damage(
    gm_client, roster,
):
    """Bandit with `effects.immunity_to: ["bludgeoning"]` buff
    takes 0 damage from Tavik's Warhammer bludgeoning component.
    Divine Strike (+1d8 radiant) still passes, so total damage
    upper bound is max radiant only.
    """
    tavik = roster["Brother Tavik Stonebrow"]
    bandit_tmpl = await _bandit_template(gm_client)
    bandit_id = "tok_npc_imm_b_bandit"
    immunity_buff = {
        "key": "immune-test",
        "name": "Bludgeoning Immune (test)",
        "icon": "🛡",
        "effects": {"immunity_to": ["bludgeoning"]},
    }
    for _ in range(15):
        await _seed_battle(gm_client, [
            _mkc(f"tok_npc_imm_b_tv_{tavik['id']}", tavik["id"],
                 name=tavik["name"]),
            _mkc(bandit_id, token_template_id=bandit_tmpl["id"],
                 name=bandit_tmpl["name"],
                 buffs=[immunity_buff]),
        ])
        resp = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/attack",
            json={
                "character_id": tavik["id"],
                "attack_index": 0,
                "target_combatant_id": bandit_id,
                "override": True,
            },
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        if data.get("hit"):
            # Tavik's Divine Strike adds 1d8 radiant (max 8 non-crit
            # / 16 crit). The bludgeoning component is zeroed by
            # the per-type immunity; the radiant passes through.
            max_radiant = 16 if data.get("is_crit") else 8
            assert data.get("damage_applied", 0) <= max_radiant, (
                f"bludgeoning immunity should zero the Warhammer "
                f"component; got {data.get('damage_applied')} "
                f"(crit={data.get('is_crit')}, max radiant "
                f"= {max_radiant})"
            )
            return
    raise AssertionError("no hit in 15 tries")


async def test_no_immunity_baseline_full_npc_damage(gm_client, roster):
    """Control: bandit with no immunity buff. Tavik's Warhammer
    lands normally with damage_applied > 0.
    """
    tavik = roster["Brother Tavik Stonebrow"]
    bandit_tmpl = await _bandit_template(gm_client)
    bandit_id = "tok_npc_imm_ctl_bandit"
    for _ in range(15):
        await _seed_battle(gm_client, [
            _mkc(f"tok_npc_imm_ctl_tv_{tavik['id']}", tavik["id"],
                 name=tavik["name"]),
            _mkc(bandit_id, token_template_id=bandit_tmpl["id"],
                 name=bandit_tmpl["name"]),
        ])
        resp = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/attack",
            json={
                "character_id": tavik["id"],
                "attack_index": 0,
                "target_combatant_id": bandit_id,
                "override": True,
            },
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        if data.get("hit") and (data.get("damage_applied") or 0) > 0:
            return
    raise AssertionError("no nonzero-damage hit in 15 tries")
