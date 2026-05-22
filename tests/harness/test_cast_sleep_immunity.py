"""RAW Sleep exclusion: undead + charm-immune creatures.

v2.49.64 — closes the v2.49.58 filed item. RAW Sleep: "Undead and
creatures immune to being charmed aren't affected by this spell."
The `_is_sleep_immune` helper inspects the target's stat block:
  - For NPCs: resolves the monster template via local_content (SRD
    JSON overlay), checks the `race` field for "undead" and the
    `condition_immunities` array for "charmed".
  - For PCs: checks the character sheet directly (same fields). PCs
    today don't have these flags, but the helper covers them
    defensively in case future races / feats add charm immunity.

Immune targets are surfaced in the `unaffected` array with
`reason: "undead"` or `reason: "charm_immune"` so the cast card can
show the exclusion to the caster.

Tests:
  - Undead: Skeleton template (Undead) → unaffected with reason="undead"
    even with a generous pool. Regular bandit alongside is affected.
  - Charm-immune (non-undead): Doppelganger template (Monstrosity +
    charmed in condition_immunities) → reason="charm_immune".
  - Bandit baseline: regular humanoid bandit → affected (regression
    guard against over-broad immunity filtering).
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID


async def _seed_battle(gm_client, combatants):
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": combatants, "turn_index": 0, "round": 1, "active": True},
    )


async def _template_by_name(gm_client, name: str) -> dict:
    r = await gm_client.get(f"/api/campaign/{CAMPAIGN_ID}/templates")
    templates = r.json()
    for t in templates:
        if (t.get("name") or "").lower() == name.lower():
            return t
    raise AssertionError(f"template {name!r} not in roster")


def _pc(char, tid_prefix: str, hp: int = 30):
    return {
        "id": f"{tid_prefix}_{char['id']}",
        "char_id": char["id"],
        "name": char["name"],
        "initiative": 10,
        "hp_current": hp,
        "hp_max": max(hp, 30),
        "buffs": [],
        "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0},
    }


def _npc(tmpl, tid: str, hp: int = 5):
    return {
        "id": tid,
        "char_id": None,
        "token_template_id": tmpl["id"],
        "name": tmpl["name"],
        "initiative": 5,
        "hp_current": hp,
        "hp_max": max(hp, 11),
        "buffs": [],
        "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0},
    }


@pytest_asyncio.fixture
async def thalindra_rested(gm_client, roster):
    thalindra = roster["Thalindra Moonwhisper"]
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{thalindra['id']}/rest",
        json={"type": "long"},
    )
    return thalindra


async def test_undead_excluded(gm_client, thalindra_rested):
    """Skeleton (Undead) targeted alongside a regular bandit. Cast at
    L3 (9d8 pool — generous so HP isn't the gate). Skeleton lands in
    `unaffected` with `reason="undead"`. Bandit is affected."""
    thalindra = thalindra_rested
    skeleton_tmpl = await _template_by_name(gm_client, "Skeleton")
    bandit_tmpl = await _template_by_name(gm_client, "Bandit")
    skel_id = "tok_imm_skel"
    bandit_id = "tok_imm_bandit"
    await _seed_battle(gm_client, [
        _pc(thalindra, "tok_imm_th"),
        _npc(skeleton_tmpl, skel_id, hp=5),
        _npc(bandit_tmpl, bandit_id, hp=5),
    ])
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_sleep",
        json={
            "character_id": thalindra["id"],
            "class_slug": "wizard",
            "slot_level": 3,  # 9d8 pool min=9, both HP=5 fit easily
            "target_combatant_ids": [skel_id, bandit_id],
            "override": True,
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    skel_entry = next(
        (u for u in body["unaffected"] if u["combatant_id"] == skel_id), None,
    )
    assert skel_entry is not None, (
        f"Skeleton should be in unaffected; got {body['unaffected']}"
    )
    assert skel_entry["reason"] == "undead", skel_entry
    # Bandit still affected.
    affected_ids = [a["combatant_id"] for a in body["affected"]]
    assert bandit_id in affected_ids, (
        f"bandit should be affected; got affected={affected_ids} "
        f"unaffected={body['unaffected']}"
    )


async def test_charm_immune_excluded(gm_client, thalindra_rested):
    """Doppelganger (Monstrosity, charmed in condition_immunities)
    targeted. Not undead → reason should be charm_immune."""
    thalindra = thalindra_rested
    doppel_tmpl = await _template_by_name(gm_client, "Doppelganger")
    bandit_tmpl = await _template_by_name(gm_client, "Bandit")
    doppel_id = "tok_imm_dop"
    bandit_id = "tok_imm_bandit2"
    await _seed_battle(gm_client, [
        _pc(thalindra, "tok_imm_th"),
        _npc(doppel_tmpl, doppel_id, hp=5),
        _npc(bandit_tmpl, bandit_id, hp=5),
    ])
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_sleep",
        json={
            "character_id": thalindra["id"],
            "class_slug": "wizard",
            "slot_level": 3,
            "target_combatant_ids": [doppel_id, bandit_id],
            "override": True,
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    doppel_entry = next(
        (u for u in body["unaffected"] if u["combatant_id"] == doppel_id), None,
    )
    assert doppel_entry is not None, (
        f"Doppelganger should be in unaffected; got {body['unaffected']}"
    )
    assert doppel_entry["reason"] == "charm_immune", doppel_entry
    affected_ids = [a["combatant_id"] for a in body["affected"]]
    assert bandit_id in affected_ids


async def test_regular_humanoid_still_affected(gm_client, thalindra_rested):
    """Regression guard: a plain bandit (humanoid, no charm immunity)
    must NOT be flagged immune. The immunity filter mustn't fire on
    every NPC."""
    thalindra = thalindra_rested
    bandit_tmpl = await _template_by_name(gm_client, "Bandit")
    bandit_id = "tok_imm_baseline"
    await _seed_battle(gm_client, [
        _pc(thalindra, "tok_imm_th"),
        _npc(bandit_tmpl, bandit_id, hp=5),
    ])
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_sleep",
        json={
            "character_id": thalindra["id"],
            "class_slug": "wizard",
            "slot_level": 1,
            "target_combatant_ids": [bandit_id],
            "override": True,
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    affected_ids = [a["combatant_id"] for a in body["affected"]]
    assert bandit_id in affected_ids, (
        f"plain bandit should be affected (not immune); got "
        f"affected={affected_ids} unaffected={body['unaffected']}"
    )
    # Bandit should NOT appear in unaffected with an immunity reason.
    bandit_unaffected = [
        u for u in body["unaffected"]
        if u["combatant_id"] == bandit_id
        and u.get("reason") in ("undead", "charm_immune")
    ]
    assert not bandit_unaffected, (
        f"bandit shouldn't be flagged immune; got {bandit_unaffected}"
    )
