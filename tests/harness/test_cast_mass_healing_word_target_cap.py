"""v2.381.0 — Mass Healing Word multi-target cap (RAW PHB p.258: "up to
six creatures").

The v2.381.0 `_SPELL_TARGET_CAPS` dict is a parallel cap-substrate for
spells whose multi-target dispatch goes through the heal loop (Mass
Healing Word, Mass Cure Wounds) rather than the buff-install branch
(where Aid + Bless live). The /cast_spell top-level gate reads
`_SPELL_TARGET_CAPS[spell_slug]` and returns 400 `too_many_targets`
when the caller passes more combatant ids than the cap. The cap can
grow with the slot level via `extra_targets_per_slot_above_base` +
`base_level` (same math as the v2.380.0 buff-cap extension), but Mass
Healing Word's RAW count is fixed at 6 regardless of slot — the
upcast scales the healing dice (handled by the v2.125.0 prose parser),
not the target count.

Tests:
  - L3 Mass Healing Word with 6 targets → 200 (RAW base cap).
  - L3 Mass Healing Word with 7 targets → 400 too_many_targets, limit=6.
  - L4 Mass Healing Word with 7 targets → 400 (upcast doesn't raise the
    count for Mass Healing Word — proves the cap stays fixed when
    `extra_targets_per_slot_above_base` is unset).
"""
from __future__ import annotations

import pytest_asyncio

from .conftest import CAMPAIGN_ID


TAVIK_MASS_HEALING_WORD_INDEX = 12  # Brother Tavik Stonebrow's spell list
                                    # (app/demo_seed.py:~1395):
                                    # 0 Sacred Flame, 1 Guidance, 2 Light,
                                    # 3 Bless, 4 Cure Wounds, 5 Healing Word,
                                    # 6 Lesser Restoration, 7 Spiritual Weapon,
                                    # 8 Hold Person, 9 Beacon of Hope,
                                    # 10 Revivify, 11 Spirit Guardians,
                                    # 12 Mass Healing Word.


async def _long_rest(gm_client, char_id):
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/rest",
        json={"type": "long"},
    )


def _mkc(cid, char_id=None, name="X"):
    return {
        "id": cid, "char_id": char_id, "name": name,
        "initiative": 10, "hp_current": 30, "hp_max": 40,
        "buffs": [],
        "economy": {"action": False, "bonus": False,
                    "reaction": False, "movement": 0},
    }


async def _seed_battle(gm_client, tavik, targets):
    """Seed a battle with Tavik + N PC targets. Returns combatant id
    list in placement order."""
    combatants = [_mkc(
        f"tok_mhw_tavik_{tavik['id']}", tavik["id"], name=tavik["name"],
    )]
    target_toks = []
    for i, t in enumerate(targets):
        tok = f"tok_mhw_{t['id']}_{i}"
        combatants.append(_mkc(tok, t["id"], name=t["name"]))
        target_toks.append(tok)
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": combatants, "turn_index": 0,
              "round": 1, "active": True},
    )
    return target_toks


@pytest_asyncio.fixture
async def tavik(gm_client, roster):
    tavik = roster["Brother Tavik Stonebrow"]
    await _long_rest(gm_client, tavik["id"])
    return tavik


@pytest_asyncio.fixture
async def six_targets(gm_client, roster):
    return [
        roster["Pip Quickfingers"],
        roster["Thalindra Moonwhisper"],
        roster["Sir Caelan Lightbringer"],
        roster["Mira Greenleaf"],
        roster["Kael Brightleaf"],
        roster["Krieger Stonefist"],
    ]


@pytest_asyncio.fixture
async def seven_targets(gm_client, six_targets, roster):
    return six_targets + [roster["Garrik Ironside"]]


async def test_mass_healing_word_l3_six_targets_succeeds(
    gm_client, tavik, six_targets,
):
    """L3 Mass Healing Word with 6 targets → 200 (RAW base cap)."""
    toks = await _seed_battle(gm_client, tavik, six_targets)
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
        json={
            "character_id": tavik["id"],
            "spell_index": TAVIK_MASS_HEALING_WORD_INDEX,
            "slot_level": 3,
            "class_slug": "cleric",
            "target_combatant_ids": toks,
            "target_name": "Mass Healing Word (6 targets)",
            "override": True,
            "override_range": True,
        },
    )
    assert resp.status_code == 200, resp.text


async def test_mass_healing_word_l3_seven_targets_returns_400(
    gm_client, tavik, seven_targets,
):
    """L3 Mass Healing Word with 7 targets → 400 too_many_targets, limit=6."""
    toks = await _seed_battle(gm_client, tavik, seven_targets)
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
        json={
            "character_id": tavik["id"],
            "spell_index": TAVIK_MASS_HEALING_WORD_INDEX,
            "slot_level": 3,
            "class_slug": "cleric",
            "target_combatant_ids": toks,
            "target_name": "Mass Healing Word (7 targets)",
            "override": True,
            "override_range": True,
        },
    )
    assert resp.status_code == 400, resp.text
    body = resp.json()
    assert body.get("error") == "too_many_targets"
    assert body.get("spell") == "mass-healing-word"
    assert body.get("limit") == 6
    assert body.get("received") == 7


async def test_mass_healing_word_l4_seven_targets_still_400(
    gm_client, tavik, seven_targets,
):
    """L4 Mass Healing Word with 7 targets → 400 (upcast doesn't raise
    the count for Mass Healing Word — RAW: healing dice scale, target
    count stays 6). Confirms `extra_targets_per_slot_above_base` is
    unset for this entry."""
    toks = await _seed_battle(gm_client, tavik, seven_targets)
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
        json={
            "character_id": tavik["id"],
            "spell_index": TAVIK_MASS_HEALING_WORD_INDEX,
            "slot_level": 4,
            "class_slug": "cleric",
            "target_combatant_ids": toks,
            "target_name": "Mass Healing Word (L4, 7 targets)",
            "override": True,
            "override_range": True,
        },
    )
    assert resp.status_code == 400, resp.text
    body = resp.json()
    assert body.get("limit") == 6
